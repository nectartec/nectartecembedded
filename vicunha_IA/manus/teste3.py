import fitz  # PyMuPDF
import openai
import os
import base64
from dotenv import load_dotenv
import pandas as pd
import streamlit as st
# 🔐 Carregar chave da API
load_dotenv()
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "")
openai.api_key = OPENAI_API_KEY

# 📂 Pasta onde estão os PDFs
pdf_folder = "pdf"  # <-- coloque sua pasta de PDFs aqui

# 📂 Pasta para salvar as imagens extraídas
output_folder = "imagens_extraidas"


# 🧠 Funções

def extract_header_from_text(text, num_lines=30):
    linhas = text.splitlines()
    header = "\n".join(linhas[:num_lines])
    return header


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
            image_path = os.path.join(
                output_folder, f"{os.path.basename(pdf_path)}_page{page_index + 1}_img{img_index + 1}.{image_ext}"
            )

            with open(image_path, "wb") as image_file:
                image_file.write(image_bytes)

            image_paths.append(image_path)

    pdf_file.close()
    return image_paths


def extract_text_from_pdf(pdf_path):
    pdf_file = fitz.open(pdf_path)
    text = ""
    for page in pdf_file:
        text += page.get_text()
    pdf_file.close()
    return text


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


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
                        },
                    },
                ],
            }
        ],
        max_tokens=500,
    )
    return response["choices"][0]["message"]["content"]


def ask_gpt4o_about_text(text, question):
    context = "\n\nAtenção: Este documento é uma fatura comercial internacional. Por favor, informe apenas o nome da EMPRESA que EMITIU este documento (o FORNECEDOR). Ignore o nome da empresa que RECEBE este documento (o cliente ou importador).\n\n"
    prompt = f"{question}\n{context}\nTexto do PDF:\n{text}"

    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": prompt}
        ],
        max_tokens=500,
    )
    return response["choices"][0]["message"]["content"]


# 🚀 Processamento de múltiplos PDFs

resultados = []

for filename in os.listdir(pdf_folder):
    if filename.lower().endswith(".pdf"):
        pdf_path = os.path.join(pdf_folder, filename)
        print(f"\n🔍 Processando: {filename}")

        # 1️⃣ Tentar com imagem
        fornecedor = ""
        imagens = extract_images_from_pdf(pdf_path, output_folder)

        if imagens:
            try:
                fornecedor = ask_gpt4o_about_image(
                    imagens[0],
                    "Qual é o nome do fornecedor nesta imagem?"
                )
                print(f"✅ Fornecedor pela imagem: {fornecedor}")
            except Exception as e:
                print(f"⚠️ Erro na leitura da imagem: {e}")
        else:
            print("❌ Nenhuma imagem encontrada no PDF.")

        # 2️⃣ Se não achou pela imagem, tenta pelo texto
        if not fornecedor or fornecedor.strip() == "":
            try:
                texto_pdf = extract_text_from_pdf(pdf_path)
                header = extract_header_from_text(texto_pdf)

                fornecedor = ask_gpt4o_about_text(
                    header,
                    "Qual é o nome da empresa que EMITIU este documento (o fornecedor)?"
                )
                print(f"✅ Fornecedor pelo texto: {fornecedor}")
            except Exception as e:
                print(f"⚠️ Erro na leitura do texto: {e}")

        resultados.append({"arquivo": filename, "fornecedor": fornecedor.strip()})

# 📝 Gerar DataFrame com os resultados
df = pd.DataFrame(resultados)
print("\n📄 Resultado final:")
print(df)

# 💾 Salvar em Excel
df.to_excel("resultado_fornecedores.xlsx", index=False)
print("\n✅ Arquivo 'resultado_fornecedores.xlsx' salvo com sucesso!")
