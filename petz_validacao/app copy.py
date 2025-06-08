import streamlit as st
import pandas as pd
import os
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import FAISS
from langchain.embeddings import OpenAIEmbeddings
from langchain.llms import OpenAI
from langchain.chains import RetrievalQA
import pickle


# ================================
# CONFIGURAÇÕES GERAIS
# ================================
st.set_page_config(page_title="PDF Q&A", layout="wide")
st.title("📄🔍 Perguntas e Respostas com Base nos PDFs")

VECTOR_DIR = "vectorstore"
os.makedirs(VECTOR_DIR, exist_ok=True)

# ================================
# API KEY OPENAI
# ================================ 
# Configure sua chave da OpenAI (melhor usar st.secrets em produção)
openai_api_key  = st.secrets["OPENAI_API_KEY"] if "OPENAI_API_KEY" in st.secrets else "sua-chave-aqui"
# ================================
# FUNÇÕES
# ================================

def criar_vectorstore(pdfs, openai_api_key):
    """Cria o vetor a partir dos PDFs"""
    all_texts = []
    for pdf in pdfs:
        loader = PyPDFLoader(pdf)
        documents = loader.load()
        all_texts.extend(documents)

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    docs = splitter.split_documents(all_texts)

    embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key)
    vectorstore = FAISS.from_documents(docs, embeddings)

    vectorstore.save_local(VECTOR_DIR)
    st.success("✅ Vetor criado e salvo com sucesso.")
    return vectorstore


def carregar_vectorstore(openai_api_key):
    """Carrega o vetor se existir"""
    embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key)
    try:
        vectorstore = FAISS.load_local(VECTOR_DIR, embeddings)
        st.success("📦 Vetor carregado com sucesso.")
        return vectorstore
    except:
        st.warning("⚠️ Vetor não encontrado, faça o upload dos PDFs para criar.")
        return None


# ================================
# INTERFACE - ETAPA 1: Vetorização dos PDFs
# ================================
st.subheader("1️⃣ Carregar ou Criar Base de Conhecimento dos PDFs")

col1, col2 = st.columns(2)

with col1:
    if os.path.exists(f"{VECTOR_DIR}/index.faiss"):
        st.info("✅ Vetor já existente. Você pode carregar.")
        if st.button("📥 Carregar Vetor"):
            vectorstore = carregar_vectorstore(openai_api_key)
    else:
        st.warning("❌ Nenhum vetor encontrado. Faça upload dos PDFs para criar.")

with col2:
    uploaded_pdfs = st.file_uploader(
        "📄 Faça upload dos PDFs (pode ser múltiplo)", 
        type=["pdf"], 
        accept_multiple_files=True
    )
    if uploaded_pdfs:
        if st.button("🚀 Criar Vetor dos PDFs"):
            with st.spinner("🔧 Processando PDFs e criando vetor..."):
                vectorstore = criar_vectorstore(uploaded_pdfs, openai_api_key)


# ================================
# INTERFACE - ETAPA 2: Perguntas
# ================================
st.subheader("2️⃣ Fazer Perguntas com Base nos PDFs")

uploaded_excel = st.file_uploader(
    "📑 Upload do Excel com perguntas (coluna chamada 'pergunta')", 
    type=["xlsx"]
)

if st.button("🤖 Gerar Respostas"):
    if not openai_api_key:
        st.error("❌ Informe sua OpenAI API Key.")
        st.stop()
    if not uploaded_excel:
        st.error("❌ Faça upload do Excel com perguntas.")
        st.stop()

    # Verificar vetor carregado
    try:
        vectorstore
    except NameError:
        st.error("❌ Vetor não carregado. Crie ou carregue o vetor primeiro.")
        st.stop()

    with st.spinner("📊 Lendo Excel..."):
        perguntas_df = pd.read_excel(uploaded_excel)
        if 'pergunta' not in perguntas_df.columns:
            st.error("❌ O Excel precisa ter uma coluna chamada 'pergunta'.")
            st.stop()

    with st.spinner("🤖 Gerando respostas..."):
        llm = OpenAI(openai_api_key=openai_api_key, temperature=0)
        qa = RetrievalQA.from_chain_type(llm=llm, retriever=vectorstore.as_retriever())

        respostas = []
        for pergunta in perguntas_df['pergunta']:
            resposta = qa.run(pergunta)
            respostas.append({'pergunta': pergunta, 'resposta': resposta})

        respostas_df = pd.DataFrame(respostas)

    st.success("✅ Respostas geradas com sucesso!")

    st.dataframe(respostas_df)

    # Download CSV
    csv = respostas_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="⬇️ Baixar CSV com Respostas",
        data=csv,
        file_name='respostas.csv',
        mime='text/csv',
    )
