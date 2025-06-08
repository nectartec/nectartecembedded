import streamlit as st
import pdfplumber
import pandas as pd
import re
import pytesseract
from pdf2image import convert_from_bytes
from io import BytesIO
import json
import numpy as np
from datetime import datetime
from supabase import create_client, Client
from groq import Groq
import openai
from openai import OpenAI, RateLimitError, APIConnectionError

# Configurar Tesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

# Configurações de API armazenadas em secrets
GROQ_API_KEY = st.secrets.get("GROQ_API_KEY", "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")

# Conectar ao Supabase
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Instanciar cliente OpenAI com API moderna
client_openai = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# Instanciar cliente Groq
client_groq = Groq(api_key=GROQ_API_KEY)

# Funções auxiliares para embeddings e similaridade
def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def get_embedding(text):
    response = client_openai.embeddings.create(input=[text], model="text-embedding-ada-002")
    return response.data[0].embedding

def extract_text_from_pdf(file):
    text = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    if not text.strip():
        file.seek(0)
        images = convert_from_bytes(file.read())
        for img in images:
            text += pytesseract.image_to_string(img)
    return text

def clean_text_for_ia(text):
    lines = text.split("\n")
    ignore_keywords = ["bank", "sorting", "notify", "charges", "advance"]
    return "\n".join([line for line in lines if not any(kw in line.lower() for kw in ignore_keywords)])

def detectar_modelo_pdf(texto):
    """
    Detecta o modelo/fornecedor do PDF baseado em palavras-chave no texto.
    Esta função é crucial para identificar o tipo de documento e aplicar
    o contexto específico de cada fornecedor via RAG.
    """
    texto_lower = texto.lower()
    
    # Dicionário de fornecedores e suas palavras-chave de identificação
    fornecedores = {
        "PANORAMA": ["panorama produce"],
        "FRUTTITAL": ["fruttital"],
        "DIRBECK": ["dirbeck"],
        "BRATZLER": ["bratzler"],
        "DAYKA": ["dayka hackett"],
        "GOTTMANN": ["gottmann"],
        "EXCELLENT": ["excellent", "fruits"],
        "GLOBAL": ["global fruit point"],
        "INTERNATIONAL": ["international", "fruit"],
        "SUNSHINE": ["sunshine", "export"],
        "FRESHWAY": ["freshway", "logistics"]
    }
    
    # Verificar cada fornecedor
    for fornecedor, keywords in fornecedores.items():
        if any(keyword in texto_lower for keyword in keywords):
            return fornecedor
            
    # Se não encontrar, retorna genérico
    return "GENERIC"

def processar_texto_com_ia(texto, contexto_extra="", modelo_ia="openai", modelo_pdf="GENERIC"):
    """
    Processa o texto utilizando OpenAI ou Groq conforme selecionado.
    Utiliza o contexto recuperado do RAG para melhorar a extração de dados,
    especialmente quando o modelo do PDF já é conhecido.
    
    Args:
        texto: O texto do PDF para processar
        contexto_extra: Contexto adicional do RAG (documentos similares)
        modelo_ia: O modelo de IA a ser usado (openai ou groq)
        modelo_pdf: O modelo/fornecedor do PDF detectado
    """
    # Instrução base para extração de dados
    INSTRUCAO_BASE = """
    <INSTRUCAO>
    Você deve interpretar o conteúdo dos PDFs de venda de diferentes fornecedores (Accountsale) e retornar os dados estruturados em um formato padronizado para armazenamento em SQL.

    Para cada PDF, extraia:
    - Nome da empresa
    - Número do contêiner
    - Comissão % (se existir)
    - Comissão Valor (se existir)
    - Trucking container (se aplicável)
    - Valor total
    - Net Amount (valor líquido a receber)

    E também a lista de produtos vendidos, contendo:
    - tipo (ex: Mango, Grapes Arra, etc.)
    - tamanho (ex: 8, 10kg, calibre, etc.)
    - quantidade
    - preço unitário
    - preço total
    - moeda utilizada (USD, EUR, etc.)

    O resultado deve ser em JSON com a estrutura:
    {
      "dados_principais": {
        "Nome da empresa": "",
        "Número do contêiner": "",
        "Comissão %": "",
        "Comissão Valor": "",
        "Trucking container": "",
        "Valor total": "",
        "Net Amount": ""
      },
      "produtos": []
    }

    Ignore seções irrelevantes como: Departure, taxas, transporte, comissão, frete, inspeções, banco, pagamentos antecipados, EOP, assinatura, IBAN, dados de banco ou rodapé fiscal.
    </INSTRUCAO>
    """
    
    # Adicionar contexto específico do fornecedor
    instrucao_fornecedor = ""
    if modelo_pdf != "GENERIC":
        instrucao_fornecedor = f"""
        <CONTEXTO_FORNECEDOR>
        Este documento é do fornecedor {modelo_pdf}. 
        
        Dicas específicas para este fornecedor:
        """
        
        # Adicionar dicas específicas por fornecedor
        if modelo_pdf == "PANORAMA":
            instrucao_fornecedor += """
            - Os números de container geralmente estão no início do documento
            - Os valores de comissão costumam estar em uma linha com 'commission'
            - Os produtos geralmente estão em uma tabela com colunas para quantidade, descrição e preço
            """
        elif modelo_pdf == "DIRBECK":
            instrucao_fornecedor += """
            - Procure o número do container próximo a "Container No."
            - Os valores estão geralmente em EUR
            - A comissão é frequentemente indicada em percentual
            """
        elif modelo_pdf == "BRATZLER":
            instrucao_fornecedor += """
            - O número do container é encontrado perto de "Container No" ou "Container Number"
            - Os produtos são listados com detalhes específicos de calibre
            - Verifique valores totais no final do documento, geralmente em USD
            """
        elif modelo_pdf == "DAYKA":
            instrucao_fornecedor += """
            - Procure a seção "Account Sales" para os principais detalhes
            - Os produtos são listados com descrição detalhada, incluindo variedade e calibre
            - Verifique valores totais e comissões geralmentes ao final do documento
            """
        elif modelo_pdf == "GOTTMANN":
            instrucao_fornecedor += """
            - O formato inclui "Accountsale" no topo do documento
            - Produtos geralmente listados com código, descrição e valor
            - Comissões geralmente indicadas em percentual e valor
            """
        
        instrucao_fornecedor += """
        </CONTEXTO_FORNECEDOR>
        """
    
    system_message = "Meu nome é AccountsaleBot. Extraio dados padronizados de diferentes formatos de Accountsale PDFs para armazenamento em SQL. Use a memória fornecida se relevante e as dicas específicas do fornecedor. Não responda nada que não esteja dentro de <INSTRUCAO></INSTRUCAO>"
    content = contexto_extra + instrucao_fornecedor + INSTRUCAO_BASE + texto
    
    try:
        if modelo_ia == "openai":
            response = client_openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": content}
                ],
                temperature=0.5,
                top_p=1
            )
            content_response = response.choices[0].message.content
            
        elif modelo_ia == "groq":
            response = client_groq.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": content}
                ],
                temperature=0.7
            )
            content_response = response.choices[0].message.content
            
        try:
            return json.loads(content_response)
        except:
            st.warning(f"A resposta da IA não é um JSON válido. Tentando extrair JSON da resposta...")
            # Tentar extrair apenas o JSON da resposta (caso tenha texto adicional)
            match = re.search(r'{[\s\S]*}', content_response)
            if match:
                try:
                    return json.loads(match.group())
                except:
                    pass
            return {"dados_principais": {}, "produtos": []}
    except Exception as e:
        st.error(f"Erro ao processar com IA ({modelo_ia}): {e}")
        return {"dados_principais": {}, "produtos": []}

# Configuração da página Streamlit
st.set_page_config(page_title="PDF Processor com Groq e OpenAI", layout="wide")
st.title("🤖 PDF Processor - Leitor de PDFs com IA")

# Seleção do modelo de IA a ser usado
modelo_ia = st.sidebar.radio(
    "Selecione o modelo de IA:",
    ["openai", "groq"],
    captions=["Usar OpenAI (GPT-4o-mini)", "Usar Groq (Llama-4-Scout)"]
)

uploaded_files = st.file_uploader("📎 Envie os arquivos PDF", type="pdf", accept_multiple_files=True)
memoria = supabase.table("memoria_pdf").select("id, texto, resultado_ia, embedding, arquivo, modelo_pdf, modelo_ia, data_processamento").execute()
        
if uploaded_files:
    for uploaded_file in uploaded_files:
        st.subheader(f"📄 Arquivo: {uploaded_file.name}")

        texto_pdf = extract_text_from_pdf(uploaded_file)
        texto_pdf_limpo = clean_text_for_ia(texto_pdf)
        modelo = detectar_modelo_pdf(texto_pdf)

        st.markdown(f"**🔍 Modelo PDF detectado:** `{modelo}`")
        st.markdown(f"**🔍 Modelo IA selecionado:** `{modelo_ia}`")
        
        with st.expander("Ver texto extraído do PDF"):
            st.text(texto_pdf_limpo)

        reprocessar = st.checkbox(f"🔁 Reprocessar IA para {uploaded_file.name}?", key=uploaded_file.name)

        # Criar embedding para busca de similaridade
        embedding = get_embedding(texto_pdf_limpo)
        
        # Buscar memórias similares no Supabase
        #memoria = supabase.table("memoria_pdf").select("id, texto, resultado_ia, embedding, arquivo, modelo_pdf, modelo_ia, data_processamento").execute()
        similares = []
        similares_mesmo_fornecedor = []
        
        if memoria.data:
            for item in memoria.data:
                if item["embedding"]:
                    emb_mem = item["embedding"]
                    if isinstance(emb_mem, str):
                        emb_mem = json.loads(emb_mem)
                    sim = cosine_similarity(emb_mem, embedding)
                    
                    # Separar documentos do mesmo fornecedor
                    if item.get("modelo_pdf") == modelo:
                        similares_mesmo_fornecedor.append((sim, item))
                    else:
                        similares.append((sim, item))
            
            # Priorizar documentos do mesmo fornecedor se houver
            if similares_mesmo_fornecedor:
                similares_mesmo_fornecedor.sort(reverse=True, key=lambda x: x[0])
                top_contexto = similares_mesmo_fornecedor[0][1]["resultado_ia"] if similares_mesmo_fornecedor[0][0] > 0.7 else None
                top_similarity = similares_mesmo_fornecedor[0][0]
                top_source = "mesmo_fornecedor"
            elif similares:
                similares.sort(reverse=True, key=lambda x: x[0])
                top_contexto = similares[0][1]["resultado_ia"] if similares[0][0] > 0.8 else None
                top_similarity = similares[0][0]
                top_source = "outro_fornecedor"
            else:
                top_contexto = None
                top_similarity = 0
                top_source = None
        else:
            top_contexto = None
            top_similarity = 0
            top_source = None

        contexto_extra = ""
        if top_contexto:
            st.markdown(f"**🧠 Memória mais semelhante usada como contexto:**")
            if top_source == "mesmo_fornecedor":
                st.markdown(f"*Similaridade: {top_similarity:.2f} (do mesmo fornecedor)*")
            else:
                st.markdown(f"*Similaridade: {top_similarity:.2f}*")
            st.code(json.dumps(top_contexto, indent=2))
            contexto_extra = f"<MEMORIA_ANTERIOR>\n{json.dumps(top_contexto)}\n</MEMORIA_ANTERIOR>\n"

        # Processar com IA ou usar memória
        resultado = processar_texto_com_ia(texto_pdf_limpo, contexto_extra, modelo_ia, modelo) if reprocessar else None

        if not resultado or resultado == {"dados_principais": {}, "produtos": []}:
            st.info("⚠️ Usando resultado mais próximo salvo na memória.")
            resultado = top_contexto or {"dados_principais": {}, "produtos": []}
        
        # Se reprocessou, salvar no Supabase
        if reprocessar:
            supabase.table("memoria_pdf").insert({
                "arquivo": uploaded_file.name,
                "modelo_pdf": modelo,
                "texto": texto_pdf_limpo,
                "embedding": embedding,
                "resultado_ia": resultado,
                "modelo_ia": modelo_ia
            }).execute()

        # Verificar se os dados estão no formato correto para SQL
        dados_padronizados = True
        campos_necessarios = ["Nome da empresa", "Número do contêiner", "Valor total"]
        for campo in campos_necessarios:
            if campo not in resultado["dados_principais"] or not resultado["dados_principais"][campo]:
                dados_padronizados = False
                break
        
        if not dados_padronizados:
            st.warning("⚠️ Alguns campos necessários para o SQL estão ausentes ou vazios!")
            
        # Exibir resultados como dataframes
        df_main = pd.DataFrame([resultado["dados_principais"]])
        df_products = pd.DataFrame(resultado.get("produtos", []))

        st.markdown("**📊 Dados principais extraídos:**")
        st.dataframe(df_main, use_container_width=True)

        st.markdown("**🔹 Lista de produtos extraída:**")
        if not df_products.empty:
            st.dataframe(df_products, use_container_width=True)
        else:
            st.info("Nenhum produto encontrado pela IA.")

        # Botão para gerar SQL INSERT
        if st.button("🔄 Gerar SQL para inserção"):
            try:
                # Sanitizar dados para SQL
                empresa = resultado["dados_principais"].get("Nome da empresa", "").replace("'", "''")
                container = resultado["dados_principais"].get("Número do contêiner", "").replace("'", "''")
                comissao_pct = resultado["dados_principais"].get("Comissão %", "0")
                comissao_valor = resultado["dados_principais"].get("Comissão Valor", "0")
                trucking = resultado["dados_principais"].get("Trucking container", "").replace("'", "''")
                valor_total = resultado["dados_principais"].get("Valor total", "0")
                net_amount = resultado["dados_principais"].get("Net Amount", "0")
                
                # Limpar valores
                comissao_pct = re.sub(r'[^0-9.]', '', str(comissao_pct)) or "0"
                comissao_valor = re.sub(r'[^0-9.]', '', str(comissao_valor)) or "0"
                valor_total = re.sub(r'[^0-9.]', '', str(valor_total)) or "0"
                net_amount = re.sub(r'[^0-9.]', '', str(net_amount)) or "0"
                
                # SQL para inserção
                sql = f"""-- Inserir ou obter fornecedor
INSERT INTO fornecedores (nome, identificacao) 
VALUES ('{empresa}', '{modelo}')
ON CONFLICT (identificacao) DO NOTHING;

-- Obter ID do fornecedor
WITH fornecedor_id AS (
    SELECT id FROM fornecedores WHERE identificacao = '{modelo}' LIMIT 1
)

-- Inserir container
INSERT INTO containers (
    numero, 
    fornecedor_id, 
    comissao_percentual, 
    comissao_valor, 
    trucking_container, 
    valor_total, 
    net_amount
)
VALUES (
    '{container}',
    (SELECT id FROM fornecedor_id),
    {comissao_pct},
    {comissao_valor},
    '{trucking}',
    {valor_total},
    {net_amount}
)
RETURNING id;
"""
                
                # SQL para produtos
                if not df_products.empty:
                    sql += "\n-- Inserir produtos (execute após obter o ID do container)\n"
                    for _, produto in df_products.iterrows():
                        tipo = str(produto.get('tipo', '')).replace("'", "''")
                        tamanho = str(produto.get('tamanho', '')).replace("'", "''")
                        quantidade = re.sub(r'[^0-9]', '', str(produto.get('quantidade', '0'))) or "0"
                        preco_unit = re.sub(r'[^0-9.]', '', str(produto.get('preço unitário', '0'))) or "0"
                        preco_total = re.sub(r'[^0-9.]', '', str(produto.get('preço total', '0'))) or "0"
                        
                        sql += f"""INSERT INTO produtos (container_id, tipo, tamanho, quantidade, preco_unitario, preco_total)
VALUES (
    (SELECT id FROM containers WHERE numero = '{container}' ORDER BY data_processamento DESC LIMIT 1),
    '{tipo}',
    '{tamanho}',
    {quantidade},
    {preco_unit},
    {preco_total}
);
"""
                
                st.code(sql, language="sql")
                
                # Botão para download do SQL
                st.download_button(
                    label="📥 Baixar SQL",
                    data=sql,
                    file_name=f"insert_{uploaded_file.name}.sql",
                    mime="text/plain"
                )
                
            except Exception as e:
                st.error(f"Erro ao gerar SQL: {e}")

        # Opções de download
        st.download_button(
            label="📅 Baixar dados principais (CSV)",
            data=df_main.to_csv(index=False).encode('utf-8'),
            file_name=f"dados_principais_{uploaded_file.name}.csv",
            mime='text/csv'
        )

        if not df_products.empty:
            output_excel = BytesIO()
            with pd.ExcelWriter(output_excel, engine='xlsxwriter') as writer:
                df_products.to_excel(writer, index=False, sheet_name='Produtos')
            output_excel.seek(0)

            st.download_button(
                label="📅 Baixar produtos (Excel)",
                data=output_excel,
                file_name=f"produtos_{uploaded_file.name}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        st.markdown("---")

    # Histórico de PDFs processados
    
    st.markdown("## 📚 Histórico completo de PDFs processados")
    if memoria.data:
        historico_df = pd.DataFrame([{
            "Arquivo": item["arquivo"],
            "Modelo PDF": item["modelo_pdf"],
            "Modelo IA": item.get("modelo_ia", "openai"),  # Compatibilidade com registros antigos
            "Data": item["data_processamento"]
        } for item in memoria.data])
        st.dataframe(historico_df.sort_values("Data", ascending=False), use_container_width=True)
    else:
        st.info("Nenhum histórico encontrado no Supabase.")

# Adicionar estatísticas na barra lateral
with st.sidebar:
    st.markdown("## 📊 Estatísticas")
    if memoria.data:
        st.metric("Total de PDFs processados", len(memoria.data))
        
        # Estatísticas por modelo de PDF/fornecedor
        modelos_pdf = {}
        for item in memoria.data:
            modelo_pdf = item.get("modelo_pdf", item.get("modelo", "GENERIC"))  # Compatibilidade com registros antigos
            modelos_pdf[modelo_pdf] = modelos_pdf.get(modelo_pdf, 0) + 1
        
        st.markdown("### Fornecedores detectados")
        for modelo_pdf, count in modelos_pdf.items():
            st.text(f"{modelo_pdf}: {count}")
        
        # Estatísticas por modelo de IA
        modelos_ia = {}
        for item in memoria.data:
            modelo_ia = item.get("modelo_ia", "openai")  # Compatibilidade com registros antigos
            modelos_ia[modelo_ia] = modelos_ia.get(modelo_ia, 0) + 1
        
        st.markdown("### Modelos de IA")
        for modelo_ia, count in modelos_ia.items():
            st.text(f"{modelo_ia}: {count}")
    
    # Adicionar opção para limpar cache (útil para testar novos modelos)
    st.markdown("## ⚙️ Configurações")
    if st.button("🧹 Limpar Cache RAG"):
        try:
            # Não exclui dados, apenas força reprocessamento
            st.session_state["force_reprocess"] = True
            st.success("Cache limpo! Próximos PDFs serão processados do zero.")
        except Exception as e:
            st.error(f"Erro ao limpar cache: {e}")
    
    # Adicionar opção para exportar schema SQL
    if st.button("📦 Gerar Schema SQL"):
        sql_schema = """
CREATE TABLE fornecedores (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(255) NOT NULL,
    identificacao VARCHAR(50) UNIQUE
);

CREATE TABLE containers (
    id SERIAL PRIMARY KEY,
    numero VARCHAR(50) NOT NULL,
    fornecedor_id INTEGER REFERENCES fornecedores(id),
    data_processamento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    comissao_percentual DECIMAL(5,2),
    comissao_valor DECIMAL(10,2),
    trucking_container VARCHAR(100),
    valor_total DECIMAL(12,2) NOT NULL,
    net_amount DECIMAL(12,2),
    moeda VARCHAR(3) DEFAULT 'USD'
);

CREATE TABLE produtos (
    id SERIAL PRIMARY KEY,
    container_id INTEGER REFERENCES containers(id),
    tipo VARCHAR(100) NOT NULL,
    tamanho VARCHAR(50),
    quantidade INTEGER NOT NULL,
    preco_unitario DECIMAL(10,2) NOT NULL,
    preco_total DECIMAL(12,2) NOT NULL,
    observacoes TEXT
);

CREATE TABLE memoria_pdfs (
    id SERIAL PRIMARY KEY,
    arquivo VARCHAR(255) NOT NULL,
    modelo_pdf VARCHAR(50) NOT NULL,
    texto TEXT,
    embedding VECTOR(1536),  -- Para PostgreSQL com pgvector
    resultado_ia JSONB NOT NULL,
    modelo_ia VARCHAR(50) NOT NULL,
    data_processamento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
        """
        st.code(sql_schema, language="sql")
        
        # Botão para download do SQL
        st.download_button(
            label="📥 Baixar Schema SQL",
            data=sql_schema,
            file_name="pdf_processor_schema.sql",
            mime="text/plain"
        )