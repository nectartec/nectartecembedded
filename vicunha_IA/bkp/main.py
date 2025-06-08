import os
import sys
import streamlit as st
import tempfile
import base64
import json
import pandas as pd
import logging
from datetime import datetime
import hashlib
import pytesseract
# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# Configurar Tesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
# Importar o extrator e a classe ModelDatabase
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bkp.extrator_pdf_learning_fixed import ExtratorPDFLearning
from model_database import ModelDatabase

class PDFExtractorApp:
    def __init__(self):
        """
        Inicializa a aplicação Streamlit para extração de PDFs com aprendizado contínuo
        """
        self.db_path = "pdf_models.db"
        self.db = ModelDatabase(self.db_path)
        self.setup_streamlit()
        
    def setup_streamlit(self):
        """
        Configura a interface Streamlit
        """
        st.set_page_config(
            page_title="Extrator Universal de PDFs com Aprendizado",
            page_icon="📄",
            layout="wide"
        )
        
        st.title("📄 Extrator Universal de PDFs com Aprendizado")
        st.markdown("""
        Esta aplicação extrai dados estruturados de relatórios de liquidação e vendas em formato PDF.
        Suporta múltiplos formatos, idiomas e fornecedores, e aprende com suas correções!
        """)
        
        # Sidebar para configurações
        st.sidebar.title("⚙️ Configurações")
        self.usar_openai = st.sidebar.checkbox("Usar OpenAI para extração (recomendado para maior precisão)")
        
        if self.usar_openai:
            self.api_key = st.sidebar.text_input("Chave de API da OpenAI", type="password")
            if not self.api_key:
                st.sidebar.warning("Por favor, insira sua chave de API da OpenAI para usar este recurso.")
        else:
            self.api_key = None
        
        # Opções de gerenciamento de modelos
        st.sidebar.markdown("---")
        st.sidebar.subheader("🧠 Gerenciamento de Modelos")
        
        sidebar_option = st.sidebar.radio(
            "Selecione uma opção:",
            ["Extrair PDF", "Gerenciar Modelos", "Exportar/Importar Modelos"]
        )
        
        if sidebar_option == "Extrair PDF":
            self.show_extraction_page()
        elif sidebar_option == "Gerenciar Modelos":
            self.show_model_management_page()
        elif sidebar_option == "Exportar/Importar Modelos":
            self.show_export_import_page()
        
        st.sidebar.markdown("---")
        st.sidebar.markdown("""
        ### 📋 Formatos suportados
        - Settlement Reports (Robinson Fresh)
        - Cuenta de Ventas (Finobrasa)
        - Accountsale (CGH)
        - Accountsale (Nature's Pride)
        - Liquidación (Cultipalta)
        
        ### 🌐 Idiomas suportados
        - Inglês
        - Espanhol
        - Português
        """)
    
    def show_extraction_page(self):
        """
        Exibe a página de extração de PDFs
        """
        # Upload do arquivo
        uploaded_file = st.file_uploader("Escolha um arquivo PDF", type="pdf")
        
        if uploaded_file is not None:
            # Mostrar o PDF
            with st.expander("Visualizar PDF", expanded=False):
                base64_pdf = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
                pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
                st.markdown(pdf_display, unsafe_allow_html=True)
            
            # Botão para processar
            if st.button("Processar PDF"):
                with st.spinner('Processando o PDF... Isso pode levar alguns segundos.'):
                    # Gerar assinatura do PDF
                    pdf_signature = self.generate_signature(uploaded_file.getvalue(), uploaded_file.name)
                    
                    # Verificar se já existe um modelo para este PDF
                    existing_model = self.db.find_model_by_signature(pdf_signature)
                    
                    # Inicializar extrator
                    extrator = ExtratorPDFLearning(api_key=self.api_key, db_path=self.db_path)
                    
                    # Extrair dados
                    try:
                        # Salvar o arquivo temporariamente
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
                            temp_pdf.write(uploaded_file.getvalue())
                            temp_pdf_path = temp_pdf.name
                        
                        # Extrair dados
                        dados = extrator.extrair_dados(temp_pdf_path)
                        os.unlink(temp_pdf_path)  # Remover arquivo temporário
                        
                        # Se existe um modelo, mostrar informações
                        if existing_model:
                            st.success(f"Modelo encontrado: {existing_model['name']}")
                            st.info(f"Confiança: {existing_model['confidence_score']:.2f}")
                        
                        # Armazenar os dados originais para comparação
                        st.session_state.original_data = dados.copy()
                        
                        # Exibir formulário para edição
                        self.show_editable_form(dados, pdf_signature, uploaded_file.name)
                        
                    except Exception as e:
                        st.error(f"Erro ao processar o PDF: {str(e)}")
                        st.info("Tente usar a opção OpenAI para melhor precisão ou verifique se o PDF está no formato esperado.")
    
    def show_editable_form(self, dados, pdf_signature, pdf_name):
        """
        Exibe um formulário editável com os dados extraídos
        
        Args:
            dados (dict): Dados extraídos do PDF
            pdf_signature (str): Assinatura única do PDF
            pdf_name (str): Nome do arquivo PDF
        """
        st.subheader("Dados Extraídos (Editáveis)")
        st.markdown("Revise e corrija os dados extraídos. O sistema aprenderá com suas correções.")
        
        # Mostrar informações sobre o modelo usado (se houver)
        if "modelo_usado" in dados and dados["modelo_usado"]:
            st.info(f"Modelo usado: {dados['modelo_usado']} (Confiança: {dados.get('confianca', 0.0):.2f})")
        
        # Remover campos internos antes de mostrar para edição
        dados_para_edicao = {
            "dados_principais": dados["dados_principais"].copy(),
            "produtos": dados["produtos"].copy() if "produtos" in dados else []
        }
        
        # Criar formulário
        with st.form(key="editable_form"):
            # Dados principais
            st.markdown("### Dados Principais")
            
            # Criar colunas para melhor organização
            col1, col2 = st.columns(2)
            
            # Dicionário para armazenar os valores editados
            edited_data = {"dados_principais": {}, "produtos": []}
            
            # Campos editáveis para dados principais
            with col1:
                for campo, valor in dados_para_edicao["dados_principais"].items():
                    edited_data["dados_principais"][campo] = st.text_input(
                        f"{campo}:", 
                        value=valor if valor else "",
                        key=f"main_{campo}"
                    )
            
            # Produtos
            st.markdown("### Produtos")
            
            # Converter para DataFrame para edição
            if dados_para_edicao["produtos"]:
                df = pd.DataFrame(dados_para_edicao["produtos"])
                
                # Editar DataFrame
                edited_df = st.data_editor(
                    df,
                    num_rows="dynamic",
                    key="product_editor"
                )
                
                # Converter DataFrame editado de volta para lista de dicionários
                edited_data["produtos"] = edited_df.to_dict('records')
            else:
                st.warning("Nenhum produto encontrado. Você pode adicionar produtos manualmente.")
                
                # Criar um DataFrame vazio para adicionar produtos
                empty_df = pd.DataFrame(columns=[
                    "tipo", "tamanho", "quantidade", "preço unitário", 
                    "preço total", "moeda", "referencia", "currency_rate"
                ])
                edited_df = st.data_editor(
                    empty_df,
                    num_rows="dynamic",
                    key="product_editor_empty"
                )
                edited_data["produtos"] = edited_df.to_dict('records')
            
            # Opções para salvar o modelo
            st.markdown("### Salvar como Modelo")
            save_as_model = st.checkbox("Salvar correções como modelo para futuros PDFs similares", value=True)
            
            if save_as_model:
                col1, col2 = st.columns(2)
                with col1:
                    model_name = st.text_input("Nome do modelo:", value=f"Modelo para {pdf_name}")
                with col2:
                    model_description = st.text_input("Descrição:", value=f"Modelo criado a partir de {pdf_name}")
            
            # Botão para salvar
            submit_button = st.form_submit_button(label="Salvar Correções")
            
            if submit_button:
                # Comparar dados originais com editados
                self.show_comparison(st.session_state.original_data, edited_data)
                
                # Salvar modelo se solicitado
                if save_as_model:
                    # Criar padrões de extração baseados nas correções
                    extraction_patterns = self.create_extraction_patterns(
                        st.session_state.original_data, 
                        edited_data
                    )
                    
                    # Salvar modelo
                    try:
                        model_id = self.db.save_model(
                            name=model_name,
                            description=model_description,
                            signature=pdf_signature,
                            extraction_patterns=extraction_patterns,
                            confidence_score=0.8  # Valor inicial de confiança
                        )
                        
                        # Salvar histórico de extração
                        self.db.save_extraction_history(
                            model_id=model_id,
                            pdf_name=pdf_name,
                            original_extraction=st.session_state.original_data,
                            corrected_extraction=edited_data
                        )
                        
                        st.success(f"Modelo '{model_name}' salvo com sucesso! ID: {model_id}")
                        
                        # Mostrar detalhes do modelo salvo
                        with st.expander("Ver detalhes do modelo salvo", expanded=False):
                            st.json(extraction_patterns)
                    
                    except Exception as e:
                        st.error(f"Erro ao salvar modelo: {str(e)}")
                        st.info("Verifique se o banco de dados está acessível e tente novamente.")
                
                # Gerar JSON para download
                st.markdown("### Download dos Dados Corrigidos")
                st.markdown(self.get_download_link(edited_data), unsafe_allow_html=True)
    
    def show_comparison(self, original_data, edited_data):
        """
        Exibe uma comparação entre os dados originais e editados
        
        Args:
            original_data (dict): Dados originais extraídos
            edited_data (dict): Dados editados pelo usuário
        """
        st.subheader("Comparação Antes/Depois")
        
        # Comparar dados principais
        st.markdown("#### Dados Principais")
        
        comparison_data = []
        for campo in original_data["dados_principais"].keys():
            original_value = original_data["dados_principais"].get(campo, "")
            edited_value = edited_data["dados_principais"].get(campo, "")
            
            # Verificar se houve alteração
            changed = original_value != edited_value
            
            comparison_data.append({
                "Campo": campo,
                "Valor Original": original_value,
                "Valor Corrigido": edited_value,
                "Alterado": "✓" if changed else ""
            })
        
        # Exibir comparação de dados principais
        df_comparison = pd.DataFrame(comparison_data)
        st.dataframe(df_comparison, use_container_width=True)
        
        # Comparar produtos
        st.markdown("#### Produtos")
        
        # Verificar se o número de produtos mudou
        if len(original_data.get("produtos", [])) != len(edited_data.get("produtos", [])):
            st.info(f"Número de produtos alterado: {len(original_data.get('produtos', []))} → {len(edited_data.get('produtos', []))}")
        
        # Exibir produtos originais e editados lado a lado
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Produtos Originais**")
            if original_data.get("produtos", []):
                st.dataframe(pd.DataFrame(original_data.get("produtos", [])), use_container_width=True)
            else:
                st.info("Nenhum produto encontrado originalmente")
        
        with col2:
            st.markdown("**Produtos Corrigidos**")
            if edited_data.get("produtos", []):
                st.dataframe(pd.DataFrame(edited_data.get("produtos", [])), use_container_width=True)
            else:
                st.info("Nenhum produto após correção")
    
    def show_model_management_page(self):
        """
        Exibe a página de gerenciamento de modelos
        """
        st.header("🧠 Gerenciamento de Modelos")
        
        # Obter todos os modelos
        models = self.db.get_all_models()
        
        if not models:
            st.info("Nenhum modelo encontrado. Processe PDFs e salve correções para criar modelos.")
            return
        
        # Exibir modelos em uma tabela
        st.subheader("Modelos Disponíveis")
        
        # Preparar dados para exibição
        model_display_data = []
        for model in models:
            model_display_data.append({
                "ID": model["id"],
                "Nome": model["name"],
                "Descrição": model["description"],
                "Confiança": f"{model['confidence_score']:.2f}",
                "Uso": model["usage_count"],
                "Última Atualização": model["updated_at"]
            })
        
        # Exibir tabela de modelos
        model_df = pd.DataFrame(model_display_data)
        selected_models = st.data_editor(
            model_df,
            disabled=["ID", "Confiança", "Uso", "Última Atualização"],
            hide_index=True,
            key="model_table"
        )
        
        # Opções para o modelo selecionado
        st.subheader("Ações")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Selecionar modelo para visualizar detalhes
            model_ids = [model["id"] for model in models]
            selected_model_id = st.selectbox("Selecione um modelo para ver detalhes:", model_ids)
            
            if st.button("Ver Detalhes"):
                selected_model = self.db.get_model_by_id(selected_model_id)
                if selected_model:
                    st.json(selected_model)
                else:
                    st.error("Modelo não encontrado")
        
        with col2:
            # Excluir modelo
            delete_model_id = st.selectbox("Selecione um modelo para excluir:", model_ids)
            
            if st.button("Excluir Modelo"):
                if st.warning(f"Tem certeza que deseja excluir o modelo {delete_model_id}?"):
                    if self.db.delete_model(delete_model_id):
                        st.success(f"Modelo {delete_model_id} excluído com sucesso!")
                        st.rerun()
                    else:
                        st.error("Erro ao excluir modelo")
        
        # Histórico de extrações
        st.subheader("Histórico de Extrações")
        
        # Obter histórico
        history = self.db.get_extraction_history(limit=10)
        
        if not history:
            st.info("Nenhum histórico de extração encontrado.")
            return
        
        # Preparar dados para exibição
        history_display_data = []
        for record in history:
            history_display_data.append({
                "ID": record["id"],
                "Modelo ID": record["model_id"],
                "PDF": record["pdf_name"],
                "Data": record["extraction_date"],
                "Produtos Originais": len(record["original_extraction"].get("produtos", [])),
                "Produtos Corrigidos": len(record["corrected_extraction"].get("produtos", []))
            })
        
        # Exibir tabela de histórico
        history_df = pd.DataFrame(history_display_data)
        st.dataframe(history_df, use_container_width=True)
        
        # Ver detalhes de um registro específico
        if history:
            history_ids = [record["id"] for record in history]
            selected_history_id = st.selectbox("Selecione um registro para ver detalhes:", history_ids)
            
            selected_record = next((record for record in history if record["id"] == selected_history_id), None)
            
            if selected_record and st.button("Ver Detalhes do Histórico"):
                # Mostrar comparação
                self.show_comparison(
                    selected_record["original_extraction"],
                    selected_record["corrected_extraction"]
                )
    
    def show_export_import_page(self):
        """
        Exibe a página de exportação e importação de modelos
        """
        st.header("📤 Exportar/Importar Modelos")
        
        # Exportar modelos
        st.subheader("Exportar Modelos")
        
        if st.button("Exportar Todos os Modelos"):
            # Criar arquivo temporário para exportação
            with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as temp_file:
                export_path = temp_file.name
            
            # Exportar modelos
            if self.db.export_models(export_path):
                # Ler o arquivo exportado
                with open(export_path, 'r', encoding='utf-8') as f:
                    models_json = f.read()
                
                # Criar link para download
                b64 = base64.b64encode(models_json.encode('utf-8')).decode()
                date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"pdf_models_export_{date_str}.json"
                href = f'<a href="data:file/json;base64,{b64}" download="{filename}">Baixar Modelos Exportados</a>'
                
                st.markdown(href, unsafe_allow_html=True)
                st.success(f"Modelos exportados com sucesso!")
            else:
                st.error("Erro ao exportar modelos")
            
            # Remover arquivo temporário
            os.unlink(export_path)
        
        # Importar modelos
        st.subheader("Importar Modelos")
        
        uploaded_json = st.file_uploader("Escolha um arquivo JSON de modelos", type="json")
        
        if uploaded_json is not None:
            if st.button("Importar Modelos"):
                # Salvar o arquivo temporariamente
                with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as temp_file:
                    temp_file.write(uploaded_json.getvalue())
                    import_path = temp_file.name
                
                # Importar modelos
                imported_count = self.db.import_models(import_path)
                
                if imported_count > 0:
                    st.success(f"{imported_count} modelos importados com sucesso!")
                else:
                    st.error("Erro ao importar modelos ou nenhum modelo encontrado no arquivo")
                
                # Remover arquivo temporário
                os.unlink(import_path)
    
    def generate_signature(self, pdf_content, pdf_name):
        """
        Gera uma assinatura única para o PDF baseada em seu conteúdo e nome
        
        Args:
            pdf_content (bytes): Conteúdo do arquivo PDF
            pdf_name (str): Nome do arquivo PDF
            
        Returns:
            str: Assinatura única do PDF
        """
        # Criar hash do conteúdo do PDF e nome
        content_hash = hashlib.md5(pdf_content).hexdigest()
        name_hash = hashlib.md5(pdf_name.encode('utf-8')).hexdigest()
        
        # Combinar os hashes para criar uma assinatura única
        signature = f"{content_hash[:16]}_{name_hash[:8]}"
        return signature
    
    def create_extraction_patterns(self, original_data, edited_data):
        """
        Cria padrões de extração baseados nas correções do usuário
        
        Args:
            original_data (dict): Dados originais extraídos
            edited_data (dict): Dados editados pelo usuário
            
        Returns:
            dict: Padrões de extração
        """
        patterns = {
            "field_corrections": {},
            "product_patterns": []
        }
        
        # Analisar correções nos dados principais
        for campo, valor_original in original_data.get("dados_principais", {}).items():
            valor_editado = edited_data.get("dados_principais", {}).get(campo, "")
            
            # Se houve correção, registrar
            if valor_original != valor_editado and valor_editado:
                patterns["field_corrections"][campo] = {
                    "original": valor_original,
                    "corrected": valor_editado
                }
        
        # Analisar correções nos produtos
        # Se o número de produtos mudou significativamente
        if abs(len(original_data.get("produtos", [])) - len(edited_data.get("produtos", []))) > 2:
            patterns["product_detection_improved"] = True
        
        # Registrar produtos corrigidos
        patterns["product_patterns"] = edited_data.get("produtos", [])
        
        return patterns
    
    def get_download_link(self, json_data, filename="dados_extraidos.json"):
        """
        Gera um link para download do JSON
        """
        json_str = json.dumps(json_data, ensure_ascii=False, indent=4)
        b64 = base64.b64encode(json_str.encode('utf-8')).decode()
        href = f'<a href="data:file/json;base64,{b64}" download="{filename}">Baixar JSON</a>'
        return href

if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # DON'T CHANGE THIS !!!
    app = PDFExtractorApp()
