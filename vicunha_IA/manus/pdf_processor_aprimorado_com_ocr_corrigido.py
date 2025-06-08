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
import platform
import logging
from supabase import create_client, Client
import openai
from openai import OpenAI

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configurar Tesseract baseado no sistema operacional
if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

# Funções auxiliares para embeddings e similaridade
def cosine_similarity(a, b):
    """Calcula a similaridade de cosseno entre dois vetores"""
    a = np.array(a)
    b = np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def get_embedding(text, client_openai=None):
    """Gera embedding para o texto usando OpenAI"""
    try:
        if client_openai:
            response = client_openai.embeddings.create(input=[text], model="text-embedding-ada-002")
            return response.data[0].embedding
        else:
            # Retornar um embedding vazio se não houver cliente
            logger.warning("Cliente OpenAI não disponível para gerar embedding")
            return [0] * 1536
    except Exception as e:
        logger.error(f"Erro ao gerar embedding: {e}")
        # Retornar um embedding vazio em caso de erro
        return [0] * 1536

def extract_text_from_pdf(file):
    """
    Extração de texto aprimorada com suporte a diferentes ambientes e melhor tratamento de erros.
    Tenta primeiro extrair texto diretamente, depois usa OCR se necessário.
    """
    text = ""
    try:
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        
        # Se não extraiu texto, tenta OCR
        if not text.strip():
            file.seek(0)
            # Detectar sistema operacional para configurar Tesseract
            if platform.system() == "Windows":
                pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
            
            # Converter PDF para imagens e extrair texto
            try:
                images = convert_from_bytes(file.read())
                for img in images:
                    text += pytesseract.image_to_string(img)
            except Exception as e:
                logger.error(f"Erro no OCR: {str(e)}")
                return f"Erro no OCR: {str(e)}\n{text}"
        
        return text
    except Exception as e:
        logger.error(f"Erro na extração: {str(e)}")
        return f"Erro na extração: {str(e)}"

def clean_text_for_ia(text):
    """
    Limpa o texto para processamento com IA, removendo linhas irrelevantes
    e normalizando espaços.
    """
    if not text:
        return ""
        
    lines = text.split("\n")
    ignore_keywords = [
        "bank", "sorting", "notify", "charges", "advance", 
        "iban", "swift", "bic", "vat reg", "tax id", "footer",
        "signature", "signed", "page", "print", "date:"
    ]
    
    # Filtrar linhas irrelevantes
    filtered_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if not any(kw.lower() in line.lower() for kw in ignore_keywords):
            filtered_lines.append(line)
    
    # Normalizar espaços extras
    cleaned_text = "\n".join(filtered_lines)
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text)
    cleaned_text = re.sub(r'\n\s*\n', '\n\n', cleaned_text)
    
    return cleaned_text


def extract_ocr_text_first_page(file):
    try:
        file.seek(0)
        images = convert_from_bytes(file.read(), first_page=1, last_page=1)
        ocr_text = pytesseract.image_to_string(images[0])
        return ocr_text
    except Exception as e:
        logger.error(f"Erro ao extrair OCR da primeira página: {e}")
        return ""

def detectar_fornecedor_ocr(ocr_text):
    linhas = [l.strip() for l in ocr_text.split('\n') if l.strip()]
    for linha in linhas:
        if "GRUPO" in linha.upper() and len(linha.split()) >= 2:
            return linha.strip()
    return "Fornecedor não identificado"


def detectar_modelo_pdf(texto):
    """
    Sistema aprimorado para detectar o modelo/fornecedor do PDF com mais opções
    e detecção baseada em padrões estruturais além de palavras-chave.
    """
    if not texto:
        return "GENERIC"
        
    texto_lower = texto.lower()
    
    # Dicionário expandido de fornecedores e suas palavras-chave
    fornecedores = {
        "PANORAMA": ["panorama produce"],
        "DIRBECK": ["dirbeck", "anton durbeck"],
        "BRATZLER": ["bratzler"],
        "DAYKA": ["dayka hackett"],
        "GOTTMANN": ["gottmann"],
        "EXCELLENT": ["excellent", "fruits"],
        "GLOBAL": ["global fruit point"],
        "INTERNATIONAL": ["international", "fruit"],
        "SUNSHINE": ["sunshine", "export"],
        "FRESHWAY": ["freshway", "logistics"],
        "AMAZON": ["amazon produce network"],
        "NATURES_PRIDE": ["nature's pride", "naturespride"]
    }
    
    # Verificar cada fornecedor
    for fornecedor, keywords in fornecedores.items():
        if any(keyword in texto_lower for keyword in keywords):
            return fornecedor
    
    # Detecção baseada em padrões estruturais
    if "account sale" in texto_lower or "accountsale" in texto_lower:
        if "container no" in texto_lower and "total eur" in texto_lower:
            return "EUROPEAN_ACCOUNT_SALE"
        elif "sea container no" in texto_lower:
            return "DUTCH_ACCOUNT_SALE"
    
    if "grower status report" in texto_lower:
        return "GROWER_REPORT"
            
    # Se não encontrar, retorna genérico
    return "GENERIC"

def obter_instrucao_especifica(modelo_pdf, texto):
    """
    Gera instruções específicas para cada tipo de layout identificado,
    melhorando a precisão da extração.
    """
    instrucao_especifica = ""
    
    if modelo_pdf == "AMAZON" or modelo_pdf == "GROWER_REPORT":
        instrucao_especifica = """
        Este é um relatório da Amazon Produce Network.
        - O nome da empresa está próximo a "Supplier:" (Findbrasa Agroindustrial S.A.)
        - O número do contêiner está próximo a "Container #:" (MNBU3129968)
        - A comissão está na seção "Expenses" como "Commission at X%" (10.00%)
        - O valor total está próximo a "Grower Set XXXX Totals on Receipts:" ($27,560.36)
        - O Net Amount está próximo a "Net Due Grower" ($13,387.89)
        - Os produtos estão na tabela com colunas Product, Variety, Size, etc.
        - Cada produto tem tipo (Mango Kent), tamanho (4 KG size XX), quantidade, preço unitário e total
        - A moeda utilizada é USD
        """
    elif modelo_pdf == "DIRBECK" or modelo_pdf == "EUROPEAN_ACCOUNT_SALE":
        instrucao_especifica = """
        Este é um Account Sale da Anton Durbeck ou similar europeu.
        - O nome da empresa está no topo do documento (Findbrasa Agroindustrial SA)
        - O número do contêiner não está explícito, mas pode estar como "Vessel No." ou similar
        - A comissão está na seção "Costs" como "Kommission" (8,00 %)
        - O valor total está próximo a "Total Sales Result" (48.991,46)
        - O Net Amount está próximo a "Total Net Result EUR" (18.341,23)
        - Os produtos estão na tabela com colunas Product, Brand, Origin, etc.
        - Cada produto tem tipo (Grapes Arra 15), marca (SUNVALLEY), quantidade, preço unitário e total
        - A moeda utilizada é EUR
        """
    elif modelo_pdf == "NATURES_PRIDE" or modelo_pdf == "DUTCH_ACCOUNT_SALE":
        instrucao_especifica = """
        Este é um Accountsale da Nature's Pride ou similar holandês.
        - O nome da empresa está no meio do documento (Findbrasa Agroinductrial SA)
        - O número do contêiner está próximo a "Sea Container No." (SEGU9009374)
        - A comissão está na seção "Specification Costs" como "Commission" (10,00 %)
        - O valor total está próximo a "Total" ou "Total Gross" (33.320,00)
        - Há um "Trucking container" na seção de custos (394,04)
        - Os produtos estão na tabela com colunas Product, Remark, No., Price, Amount
        - Cada produto tem tipo (Mango kent/palmer), tamanho (5 SC, 9 SC, etc.), quantidade, preço e total
        - A moeda utilizada é EUR
        """
    elif modelo_pdf == "PANORAMA":
        instrucao_especifica = """
        Este é um documento da Panorama Produce.
        - O nome da empresa está no cabeçalho do documento
        - O número do contêiner geralmente está no início do documento
        - Os valores de comissão costumam estar em uma linha com 'commission'
        - Os produtos geralmente estão em uma tabela com colunas para quantidade, descrição e preço
        - A moeda utilizada geralmente é USD
        """
    
    return instrucao_especifica

def validar_dados_extraidos(resultado):
    """
    Valida os dados extraídos e tenta corrigir problemas comuns.
    """
    if not resultado or not isinstance(resultado, dict):
        return {"dados_principais": {}, "produtos": []}
    
    # Garantir que a estrutura básica existe
    if "dados_principais" not in resultado:
        resultado["dados_principais"] = {}
    if "produtos" not in resultado:
        resultado["produtos"] = []
    
    # Validar campos obrigatórios
    campos_obrigatorios = ["Nome da empresa", "Número do contêiner", "Valor total"]
    for campo in campos_obrigatorios:
        if campo not in resultado["dados_principais"] or not resultado["dados_principais"][campo]:
            resultado["dados_principais"][campo] = "Não identificado"
    
    # Validar e padronizar valores numéricos
    campos_numericos = ["Comissão %", "Comissão Valor", "Valor total", "Net Amount"]
    for campo in campos_numericos:
        if campo in resultado["dados_principais"]:
            valor = resultado["dados_principais"][campo]
            if isinstance(valor, str):
                # Remover caracteres não numéricos, exceto ponto e vírgula
                valor_limpo = re.sub(r'[^\d.,]', '', str(valor))
                # Substituir vírgula por ponto para cálculos
                valor_limpo = valor_limpo.replace(',', '.')
                try:
                    resultado["dados_principais"][campo] = float(valor_limpo)
                except:
                    resultado["dados_principais"][campo] = 0
    
    # Validar produtos
    produtos_validos = []
    for produto in resultado["produtos"]:
        if isinstance(produto, dict) and "tipo" in produto and "quantidade" in produto:
            # Garantir que todos os campos necessários existem
            campos_produto = ["tipo", "tamanho", "quantidade", "preço unitário", "preço total", "moeda"]
            for campo in campos_produto:
                if campo not in produto:
                    produto[campo] = ""
            produtos_validos.append(produto)
    
    resultado["produtos"] = produtos_validos
    return resultado

def buscar_contexto_inteligente(texto_pdf, embedding, memoria_data):
    """
    Busca contexto mais relevante considerando tanto similaridade quanto
    padrões estruturais do documento.
    """
    # Detectar modelo do PDF
    modelo = detectar_modelo_pdf(texto_pdf)
    
    # Separar memórias por modelo e outras
    similares_mesmo_modelo = []
    similares_outros = []
    
    for item in memoria_data:
        if item["embedding"]:
            emb_mem = item["embedding"]
            if isinstance(emb_mem, str):
                emb_mem = json.loads(emb_mem)
            sim = cosine_similarity(emb_mem, embedding)
            
            if item.get("modelo_pdf") == modelo:
                similares_mesmo_modelo.append((sim, item))
            else:
                similares_outros.append((sim, item))
    
    # Estratégia de seleção de contexto
    contexto = None
    fonte_contexto = None
    similaridade = 0
    
    # Prioridade 1: Mesmo modelo com alta similaridade
    if similares_mesmo_modelo:
        similares_mesmo_modelo.sort(reverse=True, key=lambda x: x[0])
        if similares_mesmo_modelo[0][0] > 0.7:
            contexto = similares_mesmo_modelo[0][1]["resultado_ia"]
            similaridade = similares_mesmo_modelo[0][0]
            fonte_contexto = "mesmo_modelo_alta_similaridade"
    
    # Prioridade 2: Mesmo modelo com similaridade média
    if not contexto and similares_mesmo_modelo:
        for sim, item in similares_mesmo_modelo:
            if 0.5 <= sim < 0.7:
                contexto = item["resultado_ia"]
                similaridade = sim
                fonte_contexto = "mesmo_modelo_media_similaridade"
                break
    
    # Prioridade 3: Outro modelo com alta similaridade
    if not contexto and similares_outros:
        similares_outros.sort(reverse=True, key=lambda x: x[0])
        if similares_outros[0][0] > 0.8:
            contexto = similares_outros[0][1]["resultado_ia"]
            similaridade = similares_outros[0][0]
            fonte_contexto = "outro_modelo_alta_similaridade"
    
    # Prioridade 4: Combinar múltiplos contextos
    if not contexto and len(similares_mesmo_modelo) + len(similares_outros) >= 3:
        # Combinar os 3 mais similares
        todos_similares = similares_mesmo_modelo + similares_outros
        todos_similares.sort(reverse=True, key=lambda x: x[0])
        contextos_combinados = [item[1]["resultado_ia"] for item in todos_similares[:3]]
        contexto = {
            "dados_principais": {},
            "produtos": []
        }
        # Mesclar dados principais de todos os contextos
        for ctx in contextos_combinados:
            for campo, valor in ctx.get("dados_principais", {}).items():
                if campo not in contexto["dados_principais"] or not contexto["dados_principais"][campo]:
                    contexto["dados_principais"][campo] = valor
        
        similaridade = todos_similares[0][0]
        fonte_contexto = "contextos_combinados"
    
    return contexto, similaridade, fonte_contexto

def processar_texto_com_ia(texto, contexto_extra="", modelo_ia="openai", modelo_pdf="GENERIC", client_openai=None, client_groq=None):
    """
    Processamento aprimorado com IA, usando instruções específicas por modelo
    e validação de resultados.
    """
    # Verificar se temos clientes de IA disponíveis
    if modelo_ia == "openai" and not client_openai:
        logger.error("Cliente OpenAI não disponível")
        return {"dados_principais": {}, "produtos": [], "erro": "Cliente OpenAI não disponível"}
    
    if modelo_ia == "groq" and not client_groq:
        logger.error("Cliente Groq não disponível")
        return {"dados_principais": {}, "produtos": [], "erro": "Cliente Groq não disponível"}
    
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
    
    # Obter instruções específicas para o modelo de PDF
    instrucao_especifica = obter_instrucao_especifica(modelo_pdf, texto)
    
    if instrucao_especifica:
        instrucao_especifica = f"""
        <CONTEXTO_ESPECIFICO>
        {instrucao_especifica}
        </CONTEXTO_ESPECIFICO>
        """
    
    system_message = """Meu nome é AccountsaleBot. Extraio dados padronizados de diferentes formatos de Account sale PDFs para armazenamento em SQL. Use a memória fornecida se relevante e as instruções específicas do tipo de documento. Não responda nada que não esteja dentro de <INSTRUCAO>Nome da empresa
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
    - moeda utilizada (USD, EUR, etc.)</INSTRUCAO>"""
    content = contexto_extra + instrucao_especifica + INSTRUCAO_BASE + texto
    
    try:
        if modelo_ia == "openai":
            response = client_openai.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": content}
                ],
                temperature=0.7,
                max_tokens=2048,
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
        else:
            return {"dados_principais": {}, "produtos": [], "erro": f"Modelo de IA não suportado: {modelo_ia}"}
        
        # Tentar extrair JSON da resposta
        try:
            resultado = json.loads(content_response)
        except:
            # Tentar extrair apenas o JSON da resposta (caso tenha texto adicional)
            match = re.search(r'{[\s\S]*}', content_response)
            if match:
                try:
                    resultado = json.loads(match.group())
                except:
                    resultado = {"dados_principais": {}, "produtos": []}
            else:
                resultado = {"dados_principais": {}, "produtos": []}
        
        # Validar e corrigir os dados extraídos
        resultado_validado = validar_dados_extraidos(resultado)
        return resultado_validado
        
    except Exception as e:
        logger.error(f"Erro ao processar com IA ({modelo_ia}): {e}")
        return {"dados_principais": {}, "produtos": [], "erro": str(e)}

def gerar_sql_para_insercao(resultado):
    """
    Gera comandos SQL para inserção dos dados extraídos no banco de dados.
    """
    if not resultado or not isinstance(resultado, dict):
        return "-- Erro: Dados inválidos para geração de SQL"
    
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
VALUES ('{empresa}', '{detectar_modelo_pdf(empresa)}')
ON CONFLICT (identificacao) DO NOTHING;

-- Obter ID do fornecedor
WITH fornecedor_id AS (
    SELECT id FROM fornecedores WHERE nome = '{empresa}' LIMIT 1
)

-- Inserir venda
INSERT INTO vendas (
    fornecedor_id, 
    container, 
    comissao_percentual, 
    comissao_valor, 
    trucking_container, 
    valor_total, 
    valor_liquido, 
    data_registro
)
SELECT 
    id, 
    '{container}', 
    {comissao_pct}, 
    {comissao_valor}, 
    '{trucking}', 
    {valor_total}, 
    {net_amount}, 
    CURRENT_TIMESTAMP
FROM fornecedor_id
RETURNING id as venda_id;

-- Inserir produtos
"""
        
        # Adicionar inserções de produtos
        for i, produto in enumerate(resultado.get("produtos", [])):
            if not isinstance(produto, dict):
                continue
                
            tipo = produto.get("tipo", "").replace("'", "''")
            tamanho = produto.get("tamanho", "").replace("'", "''")
            quantidade = re.sub(r'[^0-9.]', '', str(produto.get("quantidade", "0"))) or "0"
            preco_unitario = re.sub(r'[^0-9.]', '', str(produto.get("preço unitário", "0"))) or "0"
            preco_total = re.sub(r'[^0-9.]', '', str(produto.get("preço total", "0"))) or "0"
            moeda = produto.get("moeda", "USD").replace("'", "''")
            
            sql += f"""
-- Produto {i+1}: {tipo}
INSERT INTO produtos_venda (
    venda_id, 
    tipo, 
    tamanho, 
    quantidade, 
    preco_unitario, 
    preco_total, 
    moeda
)
SELECT 
    venda_id, 
    '{tipo}', 
    '{tamanho}', 
    {quantidade}, 
    {preco_unitario}, 
    {preco_total}, 
    '{moeda}'
FROM (SELECT lastval() as venda_id);
"""
        
        return sql
    except Exception as e:
        logger.error(f"Erro ao gerar SQL: {e}")
        return f"-- Erro ao gerar SQL: {e}"

# Função principal do Streamlit
def main():
    # Configuração da página Streamlit
    st.set_page_config(page_title="PDF Processor Aprimorado", layout="wide")
    st.title("🤖 PDF Processor - Leitor de PDFs com IA")
    st.markdown("### Extração inteligente de dados de PDFs com layouts variados")
    
    # Configurações de API armazenadas em secrets
    try:
        GROQ_API_KEY = st.secrets.get("GROQ_API_KEY", "")
        SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
        SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")
        OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "")
        
        # Conectar ao Supabase se as credenciais estiverem disponíveis
        supabase = None
        if SUPABASE_URL and SUPABASE_KEY:
            try:
                from supabase import create_client
                supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
                st.sidebar.success("✅ Conectado ao Supabase")
            except Exception as e:
                logger.error(f"Erro ao conectar ao Supabase: {e}")
                st.sidebar.error(f"❌ Erro ao conectar ao Supabase")
        else:
            st.sidebar.warning("⚠️ Credenciais do Supabase não configuradas")
        
        # Instanciar cliente OpenAI se a chave estiver disponível
        client_openai = None
        if OPENAI_API_KEY:
            try:
                client_openai = OpenAI(api_key=OPENAI_API_KEY)
                st.sidebar.success("✅ API OpenAI configurada")
            except Exception as e:
                logger.error(f"Erro ao configurar OpenAI: {e}")
                st.sidebar.error(f"❌ Erro ao configurar OpenAI")
        else:
            st.sidebar.warning("⚠️ Chave da API OpenAI não configurada")
        
        # Instanciar cliente Groq se a chave estiver disponível
        client_groq = None
        if GROQ_API_KEY:
            try:
                from groq import Groq
                client_groq = Groq(api_key=GROQ_API_KEY)
                st.sidebar.success("✅ API Groq configurada")
            except Exception as e:
                logger.error(f"Erro ao configurar Groq: {e}")
                st.sidebar.error(f"❌ Erro ao configurar Groq")
        else:
            st.sidebar.warning("⚠️ Chave da API Groq não configurada")
        
    except Exception as e:
        logger.error(f"Erro ao configurar APIs: {e}")
        st.sidebar.error(f"Erro ao configurar APIs: {e}")
        client_openai = None
        client_groq = None
        supabase = None
    
    # Seleção do modelo de IA a ser usado
    modelo_ia = st.sidebar.radio(
        "Selecione o modelo de IA:",
        ["openai", "groq"],
        captions=["Usar OpenAI (gpt-4.1)", "Usar Groq (Llama-4-Scout)"]
    )
    
    # Verificar se o modelo selecionado está disponível
    if modelo_ia == "openai" and not client_openai:
        st.sidebar.error("❌ OpenAI selecionado, mas API não está configurada")
    elif modelo_ia == "groq" and not client_groq:
        st.sidebar.error("❌ Groq selecionado, mas API não está configurada")
    
    # Opções avançadas
    with st.sidebar.expander("Opções avançadas"):
        usar_memoria = st.checkbox("Usar memória de PDFs anteriores", value=True)
        mostrar_detalhes = st.checkbox("Mostrar detalhes técnicos", value=False)
        forcar_reprocessamento = st.checkbox("Forçar reprocessamento", value=False)
    
    uploaded_files = st.file_uploader("📎 Envie os arquivos PDF", type="pdf", accept_multiple_files=True)
    
    if uploaded_files:
        # Carregar memória do Supabase
        memoria_data = []
        if usar_memoria and supabase:
            try:
                memoria = supabase.table("memoria_pdf").select("id, texto, resultado_ia, embedding, arquivo, modelo_pdf, modelo_ia, data_processamento").execute()
                memoria_data = memoria.data if memoria and hasattr(memoria, 'data') else []
                if memoria_data:
                    st.sidebar.success(f"✅ {len(memoria_data)} registros carregados da memória")
            except Exception as e:
                logger.error(f"Erro ao carregar memória: {e}")
                st.warning(f"Não foi possível carregar a memória: {e}")
        
        for uploaded_file in uploaded_files:
            st.subheader(f"📄 Arquivo: {uploaded_file.name}")
            
            # Extrair texto do PDF
            with st.spinner("Extraindo texto do PDF..."):
                texto_pdf = extract_text_from_pdf(uploaded_file)
                texto_pdf_limpo = clean_text_for_ia(texto_pdf)
            
            # Detectar modelo do PDF
            modelo = detectar_modelo_pdf(texto_pdf)
            st.markdown(f"**🔍 Modelo PDF detectado:** `{modelo}`")
            st.markdown(f"**🔍 Modelo IA selecionado:** `{modelo_ia}`")
            
            # Mostrar texto extraído
            with st.expander("Ver texto extraído do PDF"):
                st.text(texto_pdf_limpo)
            
            # Gerar embedding para busca de similaridade
            embedding = []
            if client_openai:
                embedding = get_embedding(texto_pdf_limpo, client_openai)
            
            # Buscar contexto inteligente
            contexto = None
            contexto_extra = ""
            if usar_memoria and memoria_data and embedding:
                contexto, similaridade, fonte_contexto = buscar_contexto_inteligente(texto_pdf_limpo, embedding, memoria_data)
                
                if contexto:
                    st.markdown(f"**🧠 Memória utilizada como contexto:**")
                    st.markdown(f"*Fonte: {fonte_contexto}, Similaridade: {similaridade:.2f}*")
                    with st.expander("Ver contexto"):
                        st.code(json.dumps(contexto, indent=2))
                    
                    contexto_extra = f"<MEMORIA_ANTERIOR>\n{json.dumps(contexto)}\n</MEMORIA_ANTERIOR>\n"
            
            # Processar com IA ou usar memória
            reprocessar = forcar_reprocessamento or st.checkbox(f"🔁 Reprocessar IA para {uploaded_file.name}?", key=uploaded_file.name)
            
            if reprocessar:
                with st.spinner("Processando com IA..."):                    
                    ocr_text_topo = extract_ocr_text_first_page(uploaded_file)
                    fornecedor_ocr = detectar_fornecedor_ocr(ocr_text_topo)
                    print(f"Fornecedor detectado via OCR: {fornecedor_ocr}")
                    

                    resultado = processar_texto_com_ia(
                                texto_pdf_limpo, 
                                contexto_extra, 
                                modelo_ia, 
                                modelo, 
                                client_openai, 
                                client_groq
                            )
                     
                # Salvar no Supabase
                if supabase and not "erro" in resultado:
                    try:
                        supabase.table("memoria_pdf").insert({
                            "arquivo": uploaded_file.name,
                            "modelo_pdf": modelo,
                            "texto": texto_pdf_limpo,
                            "embedding": embedding,
                            "resultado_ia": resultado,
                            "modelo_ia": modelo_ia
                        }).execute()
                        st.success("✅ Resultado salvo na memória!")
                    except Exception as e:
                        logger.error(f"Erro ao salvar na memória: {e}")
                        st.warning(f"Não foi possível salvar na memória: {e}")
            else:
                if contexto:
                    st.info("⚠️ Usando resultado da memória.")
                    resultado = contexto
                else:
                    with st.spinner("Processando com IA (sem memória disponível)..."):
                        resultado = processar_texto_com_ia(
                            texto_pdf_limpo, 
                            contexto_extra, 
                            modelo_ia, 
                            modelo, 
                            client_openai, 
                            client_groq
                        )
            
            # Verificar se há erro no resultado
            if "erro" in resultado:
                st.error(f"❌ Erro no processamento: {resultado['erro']}")
            
            # Verificar se os dados estão no formato correto
            dados_validos = True
            campos_necessarios = ["Nome da empresa", "Número do contêiner", "Valor total"]
            for campo in campos_necessarios:
                if campo not in resultado["dados_principais"] or not resultado["dados_principais"][campo]:
                    dados_validos = False
                    break
            
            if not dados_validos:
                st.warning("⚠️ Alguns campos necessários estão ausentes ou vazios!")
            
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
            if st.button("🔄 Gerar SQL para inserção", key=f"sql_{uploaded_file.name}"):
                try:
                    # Implementar geração de SQL aqui
                    sql = gerar_sql_para_insercao(resultado)
                    st.code(sql, language="sql")
                    
                    # Opção para copiar SQL
                    st.download_button(
                        label="📋 Copiar SQL",
                        data=sql,
                        file_name=f"{uploaded_file.name.replace('.pdf', '')}_insert.sql",
                        mime="text/plain"
                    )
                except Exception as e:
                    st.error(f"Erro ao gerar SQL: {e}")
            
            st.markdown("---")

if __name__ == "__main__":
    main()
