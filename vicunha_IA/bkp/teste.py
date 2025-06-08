from pdf2image import convert_from_bytes
from PIL import Image
import pytesseract
# Configurar Tesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

def detectar_fornecedor_por_imagem(pdf_bytes):
    # Converter a primeira página do PDF para imagem
    imagens = convert_from_bytes(pdf_bytes)
    primeira_pagina = imagens[0]

    # Cortar o topo da imagem (onde geralmente está o logo)
    largura, altura = primeira_pagina.size
    topo = primeira_pagina.crop((0, 0, largura, int(altura * 0.2)))  # top 20%

    # OCR no topo
    texto_topo = pytesseract.image_to_string(topo)

    # Detectar fornecedor por palavras-chave
    fornecedores = {
        "FRUTTITAL": ["fruttital"],
        "BRATZLER": ["bratzler"],
        # ... outros se quiser
    }

    texto_lower = texto_topo.lower()
    for fornecedor, palavras in fornecedores.items():
        if any(p in texto_lower for p in palavras):
            return fornecedor

    return "GENERIC"

with open("OTPU6177294.pdf", "rb") as f:
    fornecedor = detectar_fornecedor_por_imagem(f.read())
    print("Fornecedor detectado:", fornecedor)