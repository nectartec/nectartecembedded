import os
import fitz  # PyMuPDF
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import openai
import base64
from dotenv import load_dotenv
import pandas as pd
import streamlit as st
# 🔐 Carregar chave da API
load_dotenv()
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "")
openai.api_key = OPENAI_API_KEY


# 🚫 Lista de nomes proibidos (clientes, não fornecedores)
BLACKLIST = [
    "Finoagro",
    "Finobrasa Agroindustrial S.A.",
    "FINOBRASA-AGROINDUSTRIAL SA"
]


# 🧠 Funções Utilitárias

def limpar_fornecedor(nome):
    for proibido in BLACKLIST:
        if proibido.lower() in nome.lower():
            return ""
    return nome.strip()


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
    contexto = """
    Atenção: Este documento é uma fatura, invoice ou settlement report ou CUENTA DE VENTAS.
    Informe APENAS o nome da EMPRESA que EMITIU este documento (ou seja, o FORNECEDOR).
    Ignore COMPLETAMENTE nomes como 'Finoagro', 'Finobrasa Agroindustrial S.A.', 'FINOBRASA-AGROINDUSTRIAL SA' ou quaisquer clientes.
    Foque exclusivamente no FORNECEDOR que gerou este documento , pode estar escrito em espanhol  .
    **se encontrar palavras como "TropiCo Spain (Exceltrop S.L)" ou "Fruttital" ou "Robinson Fresh" este sera o fornecedor.
    """
    prompt = f"{question}\n\n{contexto}\n\nTexto do PDF:\n{text}"

    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": prompt}
        ],
        max_tokens=500,
    )
    return response["choices"][0]["message"]["content"]


def ocr_from_pdf(pdf_path):
    try:
        pages = convert_from_path(pdf_path, 300)
        text = ""
        for i, page in enumerate(pages):
            ocr_text = pytesseract.image_to_string(page, lang="eng")
            text += ocr_text + "\n"
        return text
    except Exception as e:
        print(f"Erro no OCR do PDF {pdf_path}: {e}")
        return ""


# 🚀 Processamento dos PDFs

pdf_folder = "pdfs"  # Pasta onde estão os PDFs
output_folder = "imagens_extraidas"

resultados = []

for filename in os.listdir(pdf_folder):
    if filename.lower().endswith(".pdf"):
        pdf_path = os.path.join(pdf_folder, filename)
        print(f"\n🔍 Processando: {filename}")

        fornecedor = ""

        # 1️⃣ Tentativa via texto embutido
        texto_pdf = extract_text_from_pdf(pdf_path)
        if texto_pdf.strip():
            header = extract_header_from_text(texto_pdf)
            try:
                fornecedor = ask_gpt4o_about_text(
                    header,
                    "Qual é o nome da empresa que EMITIU este documento (o fornecedor)?"
                )
                fornecedor = limpar_fornecedor(fornecedor)
                if fornecedor:
                    print(f"✅ Fornecedor pelo texto: {fornecedor}")
                else:
                    print("❌ Nome na blacklist ou não encontrado no texto.")
            except Exception as e:
                print(f"⚠️ Erro na leitura do texto: {e}")

        # 2️⃣ Se falhar, tenta pela imagem
        if not fornecedor.strip():
            imagens = extract_images_from_pdf(pdf_path, output_folder)
            if imagens:
                try:
                    fornecedor = ask_gpt4o_about_image(
                        imagens[0],
                        "Qual é o nome da empresa que EMITIU este documento (o fornecedor)?"
                    )
                    fornecedor = limpar_fornecedor(fornecedor)
                    if fornecedor:
                        print(f"✅ Fornecedor pela imagem: {fornecedor}")
                    else:
                        print("❌ Nome na blacklist ou não encontrado na imagem.")
                except Exception as e:
                    print(f"⚠️ Erro na leitura da imagem: {e}")
            else:
                print("❌ Nenhuma imagem encontrada no PDF.")

        # 3️⃣ Se falhar, tenta OCR da página inteira
        if not fornecedor.strip():
            try:
                ocr_text = ocr_from_pdf(pdf_path)
                if ocr_text.strip():
                    header = extract_header_from_text(ocr_text)
                    fornecedor = ask_gpt4o_about_text(
                        header,
                        "Qual é o nome da empresa que EMITIU este documento (o fornecedor)?"
                    )
                    fornecedor = limpar_fornecedor(fornecedor)
                    if fornecedor:
                        print(f"✅ Fornecedor pelo OCR: {fornecedor}")
                    else:
                        print("❌ Nome na blacklist ou não encontrado no OCR.")
                else:
                    print("❌ OCR não encontrou texto legível.")
            except Exception as e:
                print(f"⚠️ Erro no OCR: {e}")

        resultados.append({"arquivo": filename, "fornecedor": fornecedor.strip()})

# 📝 Salvar resultados no Excel
df = pd.DataFrame(resultados)
df.to_excel("resultado_fornecedores.xlsx", index=False)
print("\n✅ Arquivo 'resultado_fornecedores.xlsx' salvo com sucesso!")
