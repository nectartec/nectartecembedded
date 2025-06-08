import streamlit as st
import pdfplumber
import pytesseract
from pdf2image import convert_from_bytes
import layoutparser as lp
from sklearn.neighbors import KNeighborsClassifier
import numpy as np
import pandas as pd
import re
from io import BytesIO
import logging
import platform
# Setup do logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# Configurar Tesseract baseado no sistema operacional
if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
# --- Funções OCR e extração ---
def extract_text_with_ocr(file_bytes):
    try:
        images = convert_from_bytes(file_bytes)
        extracted_text = ""

        model = lp.Detectron2LayoutModel(
            'lp://PubLayNet/faster_rcnn_R_50_FPN_3x/config',
            extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", 0.5],
            label_map={0: "Text", 1: "Title", 2: "List", 3: "Table", 4: "Figure"}
        )

        for img in images:
            layout = model.detect(img)
            for block in layout:
                if block.type in ["Text", "Title"]:
                    segment = lp.extract_image(img, block, pad=5)
                    text = pytesseract.image_to_string(segment)
                    extracted_text += text + "\n"
        return extracted_text
    except Exception as e:
        logger.warning(f"Layout-parser não disponível ou falhou: {e}, usando OCR padrão.")
        images = convert_from_bytes(file_bytes)
        extracted_text = ""
        for img in images:
            extracted_text += pytesseract.image_to_string(img) + "\n"
        return extracted_text

def extract_text_combined(file_bytes):
    text = ""
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        logger.warning(f"pdfplumber falhou: {e}")

    if len(text.strip()) < 50:
        logger.info("Texto insuficiente via pdfplumber, aplicando OCR...")
        text = extract_text_with_ocr(file_bytes)
    else:
        logger.info("Texto suficiente extraído via pdfplumber.")

    return text.strip()

# --- Classificação ---
def treinar_classificador(memoria_data):
    embeddings = [item["embedding"] for item in memoria_data]
    labels = [item["modelo_pdf"] for item in memoria_data]
    knn = KNeighborsClassifier(n_neighbors=1)
    knn.fit(embeddings, labels)
    return knn

def prever_modelo(embedding, knn_model):
    return knn_model.predict([embedding])[0]

# --- Limpeza de texto ---
def clean_text(text):
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# --- Streamlit App ---
st.set_page_config(page_title="PDF Extractor", layout="wide")
st.title("🧠 PDF Extractor com IA e OCR")

uploaded_file = st.file_uploader("📄 Envie um PDF", type="pdf")

if uploaded_file:
    st.subheader(f"Arquivo: {uploaded_file.name}")

    file_bytes = uploaded_file.read()
    texto_pdf = extract_text_combined(file_bytes)
    texto_pdf_limpo = clean_text(texto_pdf)

    st.markdown("### 🔍 Texto extraído:")
    st.text_area("Texto", texto_pdf_limpo, height=300)

    # Simular embedding e memória
    embedding_pdf = [0.92, 0.85, 0.8, 0.9, 0.93]
    memoria_data = [
        {"modelo_pdf": "AMAZON", "embedding": [0.9, 0.8, 0.75, 0.88, 0.95]},
        {"modelo_pdf": "DIRBECK", "embedding": [0.1, 0.15, 0.2, 0.12, 0.18]},
        {"modelo_pdf": "NATURES_PRIDE", "embedding": [0.5, 0.55, 0.6, 0.52, 0.58]}
    ]

    knn_model = treinar_classificador(memoria_data)
    modelo_detectado = prever_modelo(embedding_pdf, knn_model)

    st.markdown(f"### 🏷️ Modelo detectado: `{modelo_detectado}`")

    dados_extraidos = {
        "dados_principais": {
            "Nome da empresa": "Finobrasa Agroindustrial S.A",
            "Número do contêiner": "AMCU9310099",
            "Comissão %": "10%",
            "Comissão Valor": "2453.66",
            "Trucking container": "6160.45",
            "Valor total": "11377.72",
            "Net Amount": "9000.00"
        },
        "produtos": [
            {
                "tipo": "Mango",
                "tamanho": "6CT 4KG",
                "quantidade": "1960",
                "preço unitário": "5.80",
                "preço total": "11377.72",
                "moeda": "EUR"
            }
        ]
    }

    st.markdown("### 📊 Dados principais:")
    df_main = pd.DataFrame([dados_extraidos["dados_principais"]])
    st.dataframe(df_main, use_container_width=True)

    st.markdown("### 📦 Produtos:")
    df_products = pd.DataFrame(dados_extraidos["produtos"])
    st.dataframe(df_products, use_container_width=True)

    with st.expander("🔧 Dados JSON"):
        st.json(dados_extraidos)

st.markdown("---")
st.markdown("Desenvolvido com ❤️ por PythonGPT")
