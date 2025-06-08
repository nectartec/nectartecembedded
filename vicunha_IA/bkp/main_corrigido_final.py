import os
import sys
import streamlit as st
import pandas as pd
import json
import tempfile
import logging
import time
import traceback
from datetime import datetime
import pytesseract
# Configurar Tesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Importar o extrator
try:
    from bkp.extrator_pdf_learning_fixed import ExtratorPDFLearning
    from model_database_corrigido import ModelDatabase
    logger.info("Módulos importados com sucesso")
except Exception as e:
    logger.error(f"Erro ao importar módulos: {str(e)}")
    logger.error(traceback.format_exc())

# Configuração da página
st.set_page_config(
    page_title="Extrator Universal de PDFs com Aprendizado",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicializar variáveis de sessão
if 'pdf_data' not in st.session_state:
    st.session_state.pdf_data = None
if 'pdf_path' not in st.session_state:
    st.session_state.pdf_path = None
if 'pdf_name' not in st.session_state:
    st.session_state.pdf_name = None
if 'pdf_signature' not in st.session_state:
    st.session_state.pdf_signature = None
if 'model_saved' not in st.session_state:
    st.session_state.model_saved = False
if 'save_clicked' not in st.session_state:
    st.session_state.save_clicked = False
if 'debug_mode' not in st.session_state:
    st.session_state.debug_mode = False
if 'product_editor' not in st.session_state:
    st.session_state.product_editor = {
        'edited_rows': {},
        'added_rows': [],
        'deleted_rows': []
    }

# Função para salvar o modelo quando o botão for clicado
def on_save_button_click():
    logger.info("Botão 'Salvar Correções' clicado via callback")
    st.session_state.save_clicked = True
    logger.info(f"Estado save_clicked atualizado para: {st.session_state.save_clicked}")

# Função para processar o PDF
def process_pdf(pdf_file, api_key=None):
    try:
        logger.info(f"Processando PDF: {pdf_file.name}")
        
        # Salvar o arquivo temporariamente
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_file.write(pdf_file.getvalue())
            temp_path = temp_file.name
        
        # Inicializar o extrator
        extrator = ExtratorPDFLearning(api_key=api_key)
        
        # Extrair dados
        dados = extrator.extrair_dados(temp_path)
        
        # Gerar assinatura do PDF
        pdf_signature = extrator.generate_signature(temp_path)
        
        # Limpar arquivo temporário
        os.unlink(temp_path)
        
        # Armazenar dados na sessão
        st.session_state.pdf_data = dados
        st.session_state.pdf_name = pdf_file.name
        st.session_state.pdf_signature = pdf_signature
        st.session_state.pdf_path = temp_path
        st.session_state.model_saved = False
        st.session_state.save_clicked = False
        
        logger.info(f"PDF processado com sucesso: {pdf_file.name}")
        return dados
        
    except Exception as e:
        logger.error(f"Erro ao processar PDF: {str(e)}")
        logger.error(traceback.format_exc())
        st.error(f"Erro ao processar o PDF: {str(e)}")
        return None

# Função para salvar o modelo
def save_model():
    try:
        logger.info("Iniciando salvamento do modelo")
        
        # Verificar se há dados para salvar
        if not st.session_state.pdf_data:
            logger.warning("Nenhum dado para salvar")
            st.warning("Nenhum dado para salvar. Processe um PDF primeiro.")
            return False
        
        # Obter dados editados
        dados_originais = st.session_state.pdf_data
        dados_editados = {
            "dados_principais": {},
            "produtos": []
        }
        
        # Copiar dados principais editados
        for campo in dados_originais["dados_principais"]:
            campo_key = f"main_{campo.replace(' ', '_').replace('%', 'Pct')}"
            if campo_key in st.session_state:
                dados_editados["dados_principais"][campo] = st.session_state[campo_key]
            else:
                dados_editados["dados_principais"][campo] = dados_originais["dados_principais"][campo]
        
        # Copiar produtos editados
        if 'produtos_df' in st.session_state:
            produtos_df = st.session_state.produtos_df
            for i, row in produtos_df.iterrows():
                produto = {}
                for col in row.index:
                    produto[col] = row[col]
                dados_editados["produtos"].append(produto)
        else:
            dados_editados["produtos"] = dados_originais["produtos"]
        
        # Criar padrões de extração
        extraction_patterns = {
            "field_corrections": {},
            "product_patterns": []
        }
        
        # Adicionar correções de campos
        for campo, valor_original in dados_originais["dados_principais"].items():
            valor_editado = dados_editados["dados_principais"][campo]
            if valor_original != valor_editado:
                extraction_patterns["field_corrections"][campo] = {
                    "original": valor_original,
                    "corrected": valor_editado
                }
        
        # Adicionar padrões de produtos
        extraction_patterns["product_patterns"] = dados_editados["produtos"]
        
        # Inicializar o banco de dados
        db = ModelDatabase("pdf_models.db")
        
        # Verificar se o banco de dados foi inicializado corretamente
        if not db:
            logger.error("Falha ao inicializar o banco de dados")
            st.error("Falha ao inicializar o banco de dados")
            return False
        
        # Verificar se já existe um modelo para este PDF
        existing_model = db.find_model_by_signature(st.session_state.pdf_signature)
        
        if existing_model:
            # Atualizar modelo existente
            logger.info(f"Atualizando modelo existente: {existing_model['name']}")
            
            model_id = existing_model["id"]
            model_name = existing_model["name"]
            confidence_score = existing_model["confidence_score"] + 0.1
            
            # Atualizar modelo
            success = db.update_model(
                model_id=model_id,
                name=model_name,
                pdf_signature=st.session_state.pdf_signature,
                extraction_patterns=extraction_patterns,
                confidence_score=min(confidence_score, 1.0)
            )
            
            if success:
                logger.info(f"Modelo atualizado com sucesso: {model_name}")
                
                # Registrar extração no histórico
                db.add_extraction_history(
                    model_id=model_id,
                    pdf_name=st.session_state.pdf_name,
                    extraction_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    original_data=json.dumps(dados_originais),
                    corrected_data=json.dumps(dados_editados)
                )
                
                st.session_state.model_saved = True
                return True
            else:
                logger.error("Falha ao atualizar modelo")
                st.error("Falha ao atualizar modelo")
                return False
        else:
            # Criar novo modelo
            model_name = f"Modelo para {st.session_state.pdf_name}"
            logger.info(f"Criando novo modelo: {model_name}")
            
            # Inserir modelo
            model_id = db.add_model(
                name=model_name,
                pdf_signature=st.session_state.pdf_signature,
                extraction_patterns=extraction_patterns,
                confidence_score=0.7
            )
            
            if model_id:
                logger.info(f"Novo modelo criado com sucesso: {model_name}, ID: {model_id}")
                
                # Registrar extração no histórico
                db.add_extraction_history(
                    model_id=model_id,
                    pdf_name=st.session_state.pdf_name,
                    extraction_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    original_data=json.dumps(dados_originais),
                    corrected_data=json.dumps(dados_editados)
                )
                
                st.session_state.model_saved = True
                return True
            else:
                logger.error("Falha ao criar novo modelo")
                st.error("Falha ao criar novo modelo")
                return False
    
    except Exception as e:
        logger.error(f"Erro ao salvar modelo: {str(e)}")
        logger.error(traceback.format_exc())
        st.error(f"Erro ao salvar modelo: {str(e)}")
        return False

# Interface principal
def main():
    st.title("Extrator Universal de PDFs com Aprendizado")
    
    # Barra lateral
    with st.sidebar:
        st.header("Configurações")
        
        # Upload de PDF
        pdf_file = st.file_uploader("Selecione um PDF", type=["pdf"])
        
        # Chave da API OpenAI (opcional)
        api_key = st.text_input("Chave da API OpenAI (opcional)", type="password")
        
        # Botão de processamento
        if st.button("Processar PDF"):
            if pdf_file:
                with st.spinner("Processando PDF..."):
                    process_pdf(pdf_file, api_key)
            else:
                st.warning("Por favor, selecione um arquivo PDF.")
        
        # Modo de debug
        st.session_state.debug_mode = st.checkbox("Modo de Debug", value=st.session_state.debug_mode)
        
        # Opções adicionais
        st.subheader("Opções")
        
        if st.button("Gerenciar Modelos"):
            st.session_state.page = "manage_models"
        
        if st.button("Exportar/Importar Modelos"):
            st.session_state.page = "export_import"
    
    # Conteúdo principal
    if st.session_state.pdf_data:
        # Exibir dados extraídos
        st.header(f"Dados Extraídos: {st.session_state.pdf_name}")
        
        # Informações sobre modelo usado
        if "modelo_usado" in st.session_state.pdf_data and st.session_state.pdf_data["modelo_usado"]:
            st.info(f"Modelo utilizado: {st.session_state.pdf_data['modelo_usado']} (Confiança: {st.session_state.pdf_data['confianca']:.2f})")
        
        # Formulário para edição de dados principais
        with st.form(key="editable_form"):
            st.subheader("Dados Principais")
            
            # Criar campos editáveis para dados principais
            for campo, valor in st.session_state.pdf_data["dados_principais"].items():
                # Criar chave única para o campo
                campo_key = f"main_{campo.replace(' ', '_').replace('%', 'Pct')}"
                
                # Inicializar valor na sessão se não existir
                if campo_key not in st.session_state:
                    st.session_state[campo_key] = valor
                
                # Criar campo editável
                st.session_state[campo_key] = st.text_input(campo, value=st.session_state[campo_key])
            
            # Exibir produtos em tabela editável
            st.subheader("Produtos")
            
            # Converter lista de produtos para DataFrame
            if 'produtos_df' not in st.session_state and st.session_state.pdf_data["produtos"]:
                st.session_state.produtos_df = pd.DataFrame(st.session_state.pdf_data["produtos"])
            
            # Exibir tabela editável
            if 'produtos_df' in st.session_state and not st.session_state.produtos_df.empty:
                edited_df = st.data_editor(
                    st.session_state.produtos_df,
                    num_rows="dynamic",
                    key="product_editor"
                )
                st.session_state.produtos_df = edited_df
            else:
                st.warning("Nenhum produto encontrado.")
            
            # Opção para salvar como modelo
            save_as_model = st.checkbox("Salvar correções como modelo", value=True)
            
            # Botão de salvar
            submit_button = st.form_submit_button(
                label="Salvar Correções",
                on_click=on_save_button_click
            )
    
    # Verificar se o botão de salvar foi clicado
    if st.session_state.save_clicked:
        logger.info("Detectado clique no botão de salvar, iniciando salvamento")
        
        with st.spinner("Salvando correções..."):
            # Salvar modelo
            if save_model():
                st.success("Correções salvas com sucesso!")
                logger.info("Correções salvas com sucesso")
            else:
                st.error("Falha ao salvar correções.")
                logger.error("Falha ao salvar correções")
        
        # Resetar flag
        st.session_state.save_clicked = False
        logger.info("Flag save_clicked resetado")
    
    # Modo de debug
    if st.session_state.debug_mode:
        st.header("Informações de Debug")
        
        # Estado da sessão
        with st.expander("Estado da Sessão", expanded=True):
            st.json({k: str(v) if isinstance(v, pd.DataFrame) else v for k, v in st.session_state.items()})
        
        # Banco de dados
        with st.expander("Banco de Dados", expanded=True):
            try:
                db = ModelDatabase("pdf_models.db")
                
                # Tabela models
                st.subheader("Tabela: models")
                models = db.get_all_models()
                if models:
                    models_df = pd.DataFrame(models)
                    st.dataframe(models_df)
                else:
                    st.info("Tabela models está vazia")
                
                # Tabela extraction_history
                st.subheader("Tabela: extraction_history")
                history = db.get_extraction_history()
                if history:
                    history_df = pd.DataFrame(history)
                    st.dataframe(history_df)
                else:
                    st.info("Tabela extraction_history está vazia")
                
            except Exception as e:
                st.error(f"Erro ao acessar banco de dados: {str(e)}")
        
        # Logs
        with st.expander("Logs", expanded=True):
            try:
                with open("app.log", "r") as log_file:
                    logs = log_file.readlines()
                    st.code("".join(logs[-50:]))  # Mostrar últimas 50 linhas
            except Exception as e:
                st.error(f"Erro ao ler logs: {str(e)}")

if __name__ == "__main__":
    main()
