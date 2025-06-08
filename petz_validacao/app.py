import os
import tempfile
import streamlit as st
import pandas as pd

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain.chains import RetrievalQA
import time
from openai import RateLimitError
# 📍 Pasta onde ficará salvo o vetor
VECTOR_DIR = "vectorstore"

# ========================
# 🎨 Configuração da Página
st.set_page_config(page_title="Perguntas e Respostas com PDFs", layout="wide")
st.title("🤖📄 Perguntas e Respostas com PDFs")


# ========================
# 🔑 API Key
openai_api_key  = st.secrets["OPENAI_API_KEY"] if "OPENAI_API_KEY" in st.secrets else "sua-chave-aqui"


if not openai_api_key:
    st.sidebar.warning("🔐 Informe sua OpenAI API Key.")
    st.stop()

# ========================
# 🚩 Estado da Sessão
if 'vectorstore' not in st.session_state:
    st.session_state.vectorstore = None


# ========================
# 🚀 Funções

def executar_com_retry(func, *args, **kwargs):
    while True:
        try:
            return func(*args, **kwargs)
        except RateLimitError as e:
            st.warning(f"⏳ Rate limit atingido. Aguardando 10 segundos... {e}")
            time.sleep(10)

def criar_vectorstore(pdfs, openai_api_key):
    """Cria vetor dos PDFs"""
    all_texts = []

    for pdf in pdfs:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(pdf.read())
            tmp_path = tmp_file.name

        loader = PyPDFLoader(tmp_path)
        documents = loader.load()
        all_texts.extend(documents)

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    docs = splitter.split_documents(all_texts)

    embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key)
    vectorstore = FAISS.from_documents(docs, embeddings)

    vectorstore.save_local(VECTOR_DIR)
    return vectorstore


def carregar_vectorstore(openai_api_key):
    """Carrega vetor salvo"""
    embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key)
    try:
        vectorstore = FAISS.load_local(
            VECTOR_DIR,
            embeddings,
            allow_dangerous_deserialization=True
        )
        return vectorstore
    except Exception as e:
        st.warning(f"⚠️ Vetor não encontrado: {e}")
        return None


# ========================
# 📦 Criação ou Carregamento do Vetor

st.subheader("1️⃣ Carregar ou Criar Base de Conhecimento dos PDFs")

pdf_files = st.file_uploader(
    "📑 Envie um ou mais arquivos PDF",
    type=["pdf"],
    accept_multiple_files=True
)

col1, col2 = st.columns(2)

with col1:
    if st.button("📚 Criar Vetor dos PDFs"):
        if pdf_files:
            st.info("🔄 Processando PDFs e criando vetor...")
            vectorstore = criar_vectorstore(pdf_files, openai_api_key)
            st.session_state.vectorstore = vectorstore
            st.success("✅ Vetor criado e salvo com sucesso!")
        else:
            st.warning("⚠️ Envie pelo menos um PDF.")

with col2:
    if os.path.exists(VECTOR_DIR):
        st.info("✅ Vetor já existente. Você pode carregar.")
        if st.button("📥 Carregar Vetor"):
            vectorstore = carregar_vectorstore(openai_api_key)
            if vectorstore:
                st.session_state.vectorstore = vectorstore
                st.success("📦 Vetor carregado com sucesso.")
    else:
        st.warning("❌ Nenhum vetor existente encontrado.")


# ========================
# 📄 Perguntas via Excel

st.subheader("2️⃣ Responder Perguntas do Excel")

excel_file = st.file_uploader(
    "📥 Envie o arquivo Excel com as perguntas (coluna 'pergunta')",
    type=["xlsx"]
)

if excel_file and st.session_state.vectorstore is not None:
    df_perguntas = pd.read_excel(excel_file)

    if "pergunta" not in df_perguntas.columns:
        st.error("❌ O Excel precisa ter uma coluna chamada 'pergunta'.")
        st.stop()

    st.dataframe(df_perguntas)

    if st.button("🚀 Gerar Respostas"):
        st.info("🔍 Consultando...")

        llm = ChatOpenAI(
            openai_api_key=openai_api_key,
            model="gpt-3.5-turbo",
            temperature=0
        )

        qa = RetrievalQA.from_chain_type(
            llm=llm,
            retriever=st.session_state.vectorstore.as_retriever()
        )

        respostas = []
        for pergunta in df_perguntas["pergunta"]:
            # CORREÇÃO: Mudança de qa.run para qa.invoke
            resposta = executar_com_retry(qa.invoke, {"query": pergunta})
            # Extrai apenas o texto da resposta se necessário
            if isinstance(resposta, dict) and "result" in resposta:
                respostas.append(resposta["result"])
            else:
                respostas.append(str(resposta))

        df_perguntas["resposta"] = respostas

        st.success("✅ Respostas geradas!")
        st.dataframe(df_perguntas)

        # 📥 Download CSV
        csv = df_perguntas.to_csv(index=False, sep=";").encode("utf-8")
        st.download_button(
            label="📥 Baixar Respostas em CSV",
            data=csv,
            file_name="respostas.csv",
            mime="text/csv" 
        )

else:
    if excel_file and st.session_state.vectorstore is None:
        st.warning("⚠️ Vetor não carregado. Crie ou carregue o vetor primeiro.")