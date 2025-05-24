import pytesseract
from pdf2image import convert_from_path
import os
import platform
# Configurar Tesseract baseado no sistema operacional
if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
# Caminho do PDF
pdf_path = "pdf\AMCU9310099.pdf"

# Converter páginas do PDF em imagens
pages = convert_from_path(pdf_path, 300)

# OCR em cada página
for i, page in enumerate(pages):
    image_path = f"page_{i + 1}.png"
    page.save(image_path, 'PNG')

    text = pytesseract.image_to_string(image_path, lang='eng')

    print(f"\n📝 Texto da página {i + 1}:\n{text}")

    # Opcional: remover imagem após OCR
    os.remove(image_path)
