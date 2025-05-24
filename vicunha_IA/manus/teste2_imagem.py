import fitz  # PyMuPDF
import openai
import os
import base64
from dotenv import load_dotenv
from PIL import Image
import streamlit as st
# 🔐 Carregar chave da API
load_dotenv()
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "")
openai.api_key = OPENAI_API_KEY

# 🗂️ Caminho do PDF
pdf_path = "TLLU1053660OK.pdf"

# 📤 Extrair imagens do PDF
def extract_images_from_pdf(pdf_path, output_folder="imagens_extraidas"):
    os.makedirs(output_folder, exist_ok=True)
    pdf_file = fitz.open(pdf_path)
    image_paths = []

    for page_index in range(len(pdf_file)):
        page = pdf_file[page_index]
        images = page.get_images(full=True)

        for img_index, img in enumerate(images):
            xref = img[0]
            base_image = pdf_file.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            image_path = os.path.join(output_folder, f"page{page_index + 1}_img{img_index + 1}.{image_ext}")

            with open(image_path, "wb") as image_file:
                image_file.write(image_bytes)

            image_paths.append(image_path)

    pdf_file.close()
    return image_paths

# 📦 Codificar imagem para base64
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# 🚀 Enviar imagem para GPT-4o
def ask_gpt4o_about_image(image_path, question):
    base64_image = encode_image(image_path)

    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64_image}"
                    }}
                ],
            }
        ],
        max_tokens=500,
    )
    return response["choices"][0]["message"]["content"]


# 🏃‍♂️ Executar tudo
if __name__ == "__main__":
    imagens = extract_images_from_pdf(pdf_path)

    if imagens:
        print(f"Imagens extraídas: {imagens}")
        resultado = ask_gpt4o_about_image(
            imagens[0],  # pode ajustar para a imagem correta
            "Qual é o nome da empresa que aparece nesta imagem?"
        )
        print("Resposta da IA:", resultado)
    else:
        print("Nenhuma imagem encontrada no PDF.")
