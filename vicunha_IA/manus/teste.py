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

uploaded_files = st.file_uploader("📎 Envie os arquivos PDF", type="pdf", accept_multiple_files=True)
    
if uploaded_files:
    for uploaded_file in uploaded_files:
        ocr_text_topo = extract_ocr_text_first_page(uploaded_file)
        fornecedor_ocr = detectar_fornecedor_ocr(ocr_text_topo)
        print(f"Fornecedor detectado via OCR:  {ocr_text_topo}")