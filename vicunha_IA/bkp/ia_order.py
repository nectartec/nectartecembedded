import streamlit as st
import pdfplumber
import pandas as pd
import re
import pytesseract
from pdf2image import convert_from_bytes
from io import BytesIO
import openai
import json
import numpy as np
from datetime import datetime
from openai import OpenAI, RateLimitError, APIConnectionError
from supabase import create_client, Client

# Configurar Tesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

# Conectar ao Supabase
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Instanciar cliente OpenAI com API moderna
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# Funções auxiliares para embeddings e similaridade
def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def get_embedding(text):
    response = client.embeddings.create(input=[text], model="text-embedding-ada-002")
    return response.data[0].embedding

st.set_page_config(page_title="AccountsaleBot PDF Reader", layout="wide")
st.title("🤖 AccountsaleBot - Leitor de PDFs com IA")

INSTRUCAO_BASE = """
<INSTRUCAO>
Você deve interpretar o conteúdo dos PDFs de venda de diferentes fornecedores (Accountsale) e retornar os dados estruturados. 

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

Ignore seções irrelevantes como: taxas, transporte, comissão, frete, inspeções, banco, pagamentos antecipados, EOP, assinatura, IBAN, dados de banco ou rodapé fiscal.
</INSTRUCAO>
"""

uploaded_files = st.file_uploader("📎 Envie os arquivos PDF", type="pdf", accept_multiple_files=True)

if uploaded_files:
    for uploaded_file in uploaded_files:
        st.subheader(f"📄 Arquivo: {uploaded_file.name}")

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
            texto_lower = texto.lower()
            if "panorama produce" in texto_lower:
                return "PANORAMA"
            elif "dirbeck" in texto_lower:
                return "DIRBECK"
            elif "bratzler" in texto_lower:
                return "BRATZLER"
            elif "dayka hackett" in texto_lower:
                return "DAYKA"
            elif "gottmann" in texto_lower:
                return "GOTTMANN"
            return "GENERIC"

        texto_pdf = extract_text_from_pdf(uploaded_file)
        texto_pdf_limpo = clean_text_for_ia(texto_pdf)
        modelo = detectar_modelo_pdf(texto_pdf)

        st.markdown(f"**🔍 Modelo detectado:** `{modelo}`")

        reprocessar = st.checkbox(f"🔁 Reprocessar IA para {uploaded_file.name}?", key=uploaded_file.name)

        embedding = get_embedding(texto_pdf_limpo)
        memoria = supabase.table("memoria_pdf").select("id, texto, resultado_ia, embedding, arquivo, modelo, data_processamento").execute()
        similares = []
        if memoria.data:
            for item in memoria.data:
                if item["embedding"]:
                    emb_mem = item["embedding"]
                    if isinstance(emb_mem, str):
                        emb_mem = json.loads(emb_mem)
                    sim = cosine_similarity(emb_mem, embedding)
                    similares.append((sim, item))

            similares.sort(reverse=True, key=lambda x: x[0])
            top_contexto = similares[0][1]["resultado_ia"] if similares else None
        else:
            top_contexto = None

        contexto_extra = ""
        if top_contexto:
            st.markdown("**🧠 Memória mais semelhante usada como contexto:**")
            st.code(json.dumps(top_contexto, indent=2))
            contexto_extra = f"<MEMORIA_ANTERIOR>\n{json.dumps(top_contexto)}\n</MEMORIA_ANTERIOR>\n"

        def chamar_ia_com_gpt(prompt_instrucao, texto_pdf):
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Meu nome é AccountsaleBot. Use a memória fornecida se relevante. Não responda nada que não esteja dentro de <INSTRUCAO></INSTRUCAO>"},
                        {"role": "user", "content": contexto_extra + prompt_instrucao + texto_pdf}
                    ],
                    temperature=0.5,
                    top_p=1
                )
                content = response.choices[0].message.content
                try:
                    return json.loads(content)
                except:
                    return {"dados_principais": {}, "produtos": []}
            except Exception as e:
                st.error(f"Erro ao processar com IA: {e}")
                return {"dados_principais": {}, "produtos": []}

        resultado = chamar_ia_com_gpt(INSTRUCAO_BASE, texto_pdf_limpo) if reprocessar else None

        if not resultado or resultado == {"dados_principais": {}, "produtos": []}:
            st.info("⚠️ Usando resultado mais próximo salvo na memória.")
            resultado = top_contexto or {"dados_principais": {}, "produtos": []}

        if reprocessar:
            supabase.table("memoria_pdf").insert({
                "arquivo": uploaded_file.name,
                "modelo": modelo,
                "texto": texto_pdf_limpo,
                "embedding": embedding,
                "resultado_ia": resultado
            }).execute()

        df_main = pd.DataFrame([resultado["dados_principais"]])
        df_products = pd.DataFrame(resultado["produtos"])

        st.markdown("**📊 Dados principais extraídos:**")
        st.dataframe(df_main, use_container_width=True)

        st.markdown("**🔹 Lista de produtos extraída:**")
        if not df_products.empty:
            st.dataframe(df_products, use_container_width=True)
        else:
            st.info("Nenhum produto encontrado pela IA ou via padrão alternativo.")

        st.download_button(
            label="📅 Baixar dados principais (CSV)",
            data=df_main.to_csv(index=False).encode('utf-8'),
            file_name=f"dados_principais_{uploaded_file.name}.csv",
            mime='text/csv'
        )

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

    st.markdown("## 📚 Histórico completo de PDFs processados")
    if memoria.data:
        historico_df = pd.DataFrame([{
            "Arquivo": item["arquivo"],
            "Modelo": item["modelo"],
            "Data": item["data_processamento"]
        } for item in memoria.data])
        st.dataframe(historico_df.sort_values("Data", ascending=False), use_container_width=True)
    else:
        st.info("Nenhum histórico encontrado no Supabase.")
