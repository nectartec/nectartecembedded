import os
import sys
import streamlit as st
import tempfile
import re
import json
import logging
import traceback
import time
import datetime
from datetime import datetime
import pandas as pd
from pdf2image import convert_from_path
import pytesseract
from PIL import Image
import io

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Verificar versão da API OpenAI
is_new_api = False
try:
    import pkg_resources
    openai_version = pkg_resources.get_distribution("openai").version
    is_new_api = int(openai_version.split('.')[0]) >= 1
    logger.info(f"Versão da OpenAI: {openai_version}, API nova: {is_new_api}")
except Exception as e:
    logger.warning(f"Não foi possível determinar a versão da OpenAI: {str(e)}")

# Importar OpenAI com tratamento de versão
try:
    import openai
    if is_new_api:
        from openai import OpenAI
except ImportError:
    logger.warning("Biblioteca OpenAI não encontrada. Instale com: pip install openai")

# Configurar página Streamlit
st.set_page_config(
    page_title="Extrator Inteligente de PDFs com OpenAI",
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
if 'pdf_content' not in st.session_state:
    st.session_state.pdf_content = None
if 'pdf_images' not in st.session_state:
    st.session_state.pdf_images = []
if 'pdf_text' not in st.session_state:
    st.session_state.pdf_text = None
if 'extraction_method' not in st.session_state:
    st.session_state.extraction_method = "auto"
if 'debug_mode' not in st.session_state:
    st.session_state.debug_mode = False
if 'page' not in st.session_state:
    st.session_state.page = "main"
if 'extraction_history' not in st.session_state:
    st.session_state.extraction_history = []
if 'status_treinamento' not in st.session_state:
    st.session_state.status_treinamento = {
        "ultimo_treinamento": "",
        "pdfs_treinados": [],
        "historico_treinamentos": []
    }

# Carregar credenciais do arquivo secrets.toml
try:
    if 'openai' in st.secrets:
        # Verificar se as credenciais são placeholders
        api_key_placeholder = st.secrets["openai"]["api_key"] in ["sua_chave_api_aqui", "your_api_key_here"]
        assistant_id_placeholder = st.secrets["openai"]["assistant_id"] in ["seu_assistant_id_aqui", "your_assistant_id_here"]
        
        # Só carregar se não forem placeholders
        if not api_key_placeholder and ('api_key' not in st.session_state or not st.session_state.api_key):
            st.session_state.api_key = st.secrets["openai"]["api_key"]
            logger.info("Chave de API OpenAI carregada do arquivo secrets.toml")
        
        if not assistant_id_placeholder and ('assistant_id' not in st.session_state or not st.session_state.assistant_id):
            st.session_state.assistant_id = st.secrets["openai"]["assistant_id"]
            logger.info("ID do assistente OpenAI carregado do arquivo secrets.toml")
except Exception as e:
    logger.warning(f"Não foi possível carregar credenciais do arquivo secrets.toml: {str(e)}")

# Inicializar como None se não existirem no secrets ou forem placeholders
if 'api_key' not in st.session_state:
    st.session_state.api_key = None
if 'assistant_id' not in st.session_state:
    st.session_state.assistant_id = None

# Funções para gerenciar o status de treinamento
def exibir_status_treinamento():
    """Exibe o status de treinamento na interface"""
    st.subheader("Status de Treinamento do Assistente")
    
    # Exibir informações de status
    col1, col2 = st.columns(2)
    
    with col1:
        if st.session_state.status_treinamento["ultimo_treinamento"]:
            st.info(f"Último treinamento: {st.session_state.status_treinamento['ultimo_treinamento']}")
        else:
            st.warning("Nenhum treinamento realizado ainda")
        
        st.metric("PDFs treinados", len(st.session_state.status_treinamento["pdfs_treinados"]))
    
    with col2:
        if st.session_state.status_treinamento["pdfs_treinados"]:
            st.success("PDFs usados para treinamento:")
            for pdf in st.session_state.status_treinamento["pdfs_treinados"]:
                st.text(f"• {pdf}")
        else:
            st.info("Nenhum PDF usado para treinamento ainda")
    
    # Exibir histórico de treinamentos
    if st.session_state.status_treinamento["historico_treinamentos"]:
        st.subheader("Histórico de Treinamentos")
        
        # Converter para DataFrame para exibição
        historico_df = pd.DataFrame(st.session_state.status_treinamento["historico_treinamentos"])
        st.dataframe(historico_df, use_container_width=True)
    
    # Adicionar botão para limpar histórico
    if st.button("Limpar Histórico de Treinamentos"):
        st.session_state.status_treinamento["historico_treinamentos"] = []
        st.success("Histórico de treinamentos limpo com sucesso!")
        st.rerun()

def atualizar_status_treinamento(nome_pdf, status="sucesso"):
    """Atualiza o status de treinamento"""
    # Atualizar informações
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.status_treinamento["ultimo_treinamento"] = agora
    
    if nome_pdf not in st.session_state.status_treinamento["pdfs_treinados"]:
        st.session_state.status_treinamento["pdfs_treinados"].append(nome_pdf)
    
    st.session_state.status_treinamento["historico_treinamentos"].append({
        "data": agora,
        "pdf": nome_pdf,
        "status": status
    })
    
    return st.session_state.status_treinamento

class PDFExtractor:
    def __init__(self, api_key=None, assistant_id=None):
        """
        Inicializa o extrator de PDFs
        
        Args:
            api_key (str, optional): Chave de API da OpenAI
            assistant_id (str, optional): ID do assistente OpenAI
        """
        self.api_key = api_key
        self.assistant_id = assistant_id
        self.openai_client = None
        
        # Inicializar cliente OpenAI se a chave de API estiver disponível
        if self.api_key:
            try:
                if is_new_api:
                    # Nova API (v1.0+)
                    self.openai_client = OpenAI(api_key=self.api_key)
                else:
                    # API antiga (v0.x)
                    openai.api_key = self.api_key
                    self.openai_client = openai
                logger.info("Cliente OpenAI inicializado")
            except Exception as e:
                logger.error(f"Erro ao inicializar cliente OpenAI: {str(e)}")
        
        # Estrutura padrão para dados extraídos
        self.estrutura_padrao = {
            "dados_principais": {
                "Nome da empresa": "",
                "Número do contêiner": "",
                "Comissão %": "",
                "Comissão Valor": "",
                "Valor total": "",
                "Net Amount": "",
                "Moeda": ""
            },
            "produtos": []
        }
    
    def extrair_texto_de_pdf(self, caminho_pdf):
        """
        Extrai texto de um arquivo PDF
        
        Args:
            caminho_pdf (str): Caminho para o arquivo PDF
            
        Returns:
            str: Texto extraído do PDF
        """
        logger.info(f"Extraindo texto de {caminho_pdf}")
        
        try:
            # Usar pdftotext (poppler-utils)
            import subprocess
            resultado = subprocess.run(
                ["pdftotext", "-layout", caminho_pdf, "-"],
                capture_output=True,
                text=True,
                check=True
            )
            texto = resultado.stdout
            logger.info(f"Texto extraído com pdftotext: {len(texto)} caracteres")
            return texto
        except Exception as e:
            logger.warning(f"Erro ao extrair texto com pdftotext: {str(e)}")
            
            try:
                # Alternativa: usar OCR com pytesseract
                logger.info("Tentando extrair texto com OCR")
                images = convert_from_path(caminho_pdf)
                texto = ""
                for i, image in enumerate(images):
                    texto += pytesseract.image_to_string(image, lang='eng')
                logger.info(f"Texto extraído com OCR: {len(texto)} caracteres")
                return texto
            except Exception as e2:
                logger.error(f"Erro ao extrair texto com OCR: {str(e2)}")
                return ""
    
    def detectar_tipo_documento(self, texto):
        """
        Detecta o tipo de documento com base no texto
        
        Args:
            texto (str): Texto do documento
            
        Returns:
            str: Tipo de documento detectado
        """
        logger.info("Detectando tipo de documento")
        
        # Verificar padrões específicos
        if "Settlement Report" in texto or "Settlement" in texto:
            logger.info("Tipo de documento detectado: settlement_report")
            return "settlement_report"
        elif "CUENTA DE VENTAS" in texto and ("FINOBRASA" in texto or "FINOBRA" in texto):
            logger.info("Tipo de documento detectado: cuenta_ventas_finobrasa")
            return "cuenta_ventas_finobrasa"
        else:
            logger.info("Tipo de documento não identificado, usando genérico")
            return "generico"
    
    def extrair_dados(self, caminho_pdf, metodo="auto"):
        """
        Extrai dados de um arquivo PDF
        
        Args:
            caminho_pdf (str): Caminho para o arquivo PDF
            metodo (str, optional): Método de extração (auto, ocr, openai)
            
        Returns:
            dict: Dicionário com os dados extraídos
        """
        logger.info(f"Extraindo dados de {caminho_pdf} com método {metodo}")
        
        # Extrair texto do PDF
        texto = self.extrair_texto_de_pdf(caminho_pdf)
        if not texto:
            logger.error("Não foi possível extrair texto do PDF")
            return None
        
        # Detectar tipo de documento
        tipo_doc = self.detectar_tipo_documento(texto)
        
        # Extrair dados com base no método selecionado
        if metodo == "auto":
            # Tentar primeiro com OpenAI, depois com OCR e regex
            if self.openai_client and self.assistant_id:
                # Verificar se as credenciais são placeholders
                if self.api_key in ["sua_chave_api_aqui", "your_api_key_here"] or self.assistant_id in ["seu_assistant_id_aqui", "your_assistant_id_here"]:
                    logger.warning("Credenciais OpenAI são placeholders")
                    st.warning("""
                    ⚠️ **Atenção**: As credenciais da OpenAI parecem ser placeholders.
                    
                    Por favor, edite o arquivo `.streamlit/secrets.toml` e insira suas credenciais reais:
                    ```
                    [openai]
                    api_key = "sua_chave_api_real_aqui"
                    assistant_id = "seu_assistant_id_real_aqui"
                    ```
                    
                    Ou insira suas credenciais diretamente nos campos acima.
                    """)
                    # Recorrer a OCR e regex como fallback
                    logger.info("Recorrendo a OCR e regex devido a credenciais inválidas")
                    return self.extrair_com_ocr_e_regex(texto, tipo_doc, caminho_pdf)
                
                logger.info("Tentando extrair com OpenAI")
                try:
                    dados = self.extrair_com_openai(caminho_pdf, texto)
                    if dados:
                        return dados
                except Exception as e:
                    logger.error(f"Erro ao extrair com OpenAI: {str(e)}")
            
            # Recorrer a OCR e regex como fallback
            logger.info("Recorrendo a OCR e regex como fallback")
            return self.extrair_com_ocr_e_regex(texto, tipo_doc, caminho_pdf)
        
        elif metodo == "ocr":
            logger.info("Usando OCR e regex para extração")
            return self.extrair_com_ocr_e_regex(texto, tipo_doc, caminho_pdf)
        
        elif metodo == "openai":
            # Usar apenas OpenAI
            if self.openai_client and self.assistant_id:
                # Verificar se as credenciais são placeholders
                if self.api_key in ["sua_chave_api_aqui", "your_api_key_here"] or self.assistant_id in ["seu_assistant_id_aqui", "your_assistant_id_here"]:
                    logger.warning("Credenciais OpenAI são placeholders")
                    st.warning("""
                    ⚠️ **Atenção**: As credenciais da OpenAI parecem ser placeholders.
                    
                    Por favor, edite o arquivo `.streamlit/secrets.toml` e insira suas credenciais reais:
                    ```
                    [openai]
                    api_key = "sua_chave_api_real_aqui"
                    assistant_id = "seu_assistant_id_real_aqui"
                    ```
                    
                    Ou insira suas credenciais diretamente nos campos acima.
                    """)
                    # Recorrer a OCR e regex como fallback
                    logger.info("Recorrendo a OCR e regex devido a credenciais inválidas")
                    return self.extrair_com_ocr_e_regex(texto, tipo_doc, caminho_pdf)
                
                logger.info("Usando OpenAI para extração")
                try:
                    dados = self.extrair_com_openai(caminho_pdf, texto)
                    if dados:
                        return dados
                except Exception as e:
                    logger.error(f"Erro ao extrair com OpenAI: {str(e)}")
                    st.error(f"Erro ao extrair com OpenAI: {str(e)}")
            else:
                logger.warning("OpenAI não configurado")
                st.warning("""
                ⚠️ **Atenção**: Credenciais da OpenAI não configuradas.
                
                Por favor, configure a chave de API e o ID do assistente de uma das seguintes formas:
                
                1. Edite o arquivo `.streamlit/secrets.toml`:
                ```
                [openai]
                api_key = "sua_chave_api_aqui"
                assistant_id = "seu_assistant_id_aqui"
                ```
                
                2. Ou insira suas credenciais diretamente nos campos acima.
                
                Usando OCR e regex como método alternativo por enquanto.
                """)
            
            # Recorrer a OCR e regex como fallback
            logger.info("Recorrendo a OCR e regex como fallback")
            return self.extrair_com_ocr_e_regex(texto, tipo_doc, caminho_pdf)
        
        else:
            logger.error(f"Método de extração desconhecido: {metodo}")
            return None
    
    def extrair_com_ocr_e_regex(self, texto, tipo_doc, arquivo_pdf):
        """
        Extrai dados do PDF usando OCR e regex
        
        Args:
            texto (str): Texto já extraído do PDF
            tipo_doc (str): Tipo de documento detectado
            arquivo_pdf (str): Caminho para o arquivo PDF
            
        Returns:
            dict: Dicionário com os dados extraídos
        """
        logger.info(f"Extraindo dados com OCR e regex para documento tipo {tipo_doc}")
        
        dados_extraidos = {
            "dados_principais": self.estrutura_padrao["dados_principais"].copy(),
            "produtos": [],
            "metodo_extracao": "ocr_regex"
        }
        
        # Extrair número do contêiner do nome do arquivo
        nome_arquivo = os.path.basename(arquivo_pdf).upper()
        container_match = re.search(r'([A-Z]{4}\d{7})', nome_arquivo)
        if container_match:
            dados_extraidos["dados_principais"]["Número do contêiner"] = container_match.group(1)
            logger.info(f"Número do contêiner encontrado no nome do arquivo: {container_match.group(1)}")
        
        # Extrair dados específicos com base no tipo de documento
        if tipo_doc == "settlement_report":
            # Extrair nome da empresa
            padrao_empresa = r"(Robinson Fresh|C\.H\. Robinson)"
            match_empresa = re.search(padrao_empresa, texto)
            if match_empresa:
                dados_extraidos["dados_principais"]["Nome da empresa"] = match_empresa.group(1)
            
            # Extrair número do contêiner se não encontrado no nome do arquivo
            if not dados_extraidos["dados_principais"]["Número do contêiner"]:
                padrao_container = r"Container\s+No\.?\s*:?\s*([A-Z]{4}\d{7})"
                match_container = re.search(padrao_container, texto)
                if match_container:
                    dados_extraidos["dados_principais"]["Número do contêiner"] = match_container.group(1)
            
            # Extrair valor total
            padrao_valor_total = r"Grand\s+Total\s*:?\s*(\$?\s*[\d,.]+)"
            match_valor_total = re.search(padrao_valor_total, texto)
            if match_valor_total:
                valor = match_valor_total.group(1).replace("$", "").replace(",", "").strip()
                dados_extraidos["dados_principais"]["Valor total"] = valor
                dados_extraidos["dados_principais"]["Net Amount"] = valor
            
            # Extrair moeda
            padrao_moeda = r"Currency\s*:?\s*([A-Z]{3})"
            match_moeda = re.search(padrao_moeda, texto)
            if match_moeda:
                dados_extraidos["dados_principais"]["Moeda"] = match_moeda.group(1)
            else:
                # Verificar símbolo de moeda
                if "$" in texto:
                    dados_extraidos["dados_principais"]["Moeda"] = "USD"
                elif "€" in texto:
                    dados_extraidos["dados_principais"]["Moeda"] = "EUR"
            
            # Extrair taxa de câmbio
            padrao_taxa = r"Currency\s+Rate\s*:?\s*([\d,.]+)"
            match_taxa = re.search(padrao_taxa, texto)
            currency_rate = match_taxa.group(1) if match_taxa else ""
            
            # Extrair produtos
            # Dividir texto em linhas
            linhas = texto.split('\n')
            produto_atual = None
            
            # Detectar tabela de produtos
            inicio_tabela = False
            fim_tabela = False
            linhas_tabela = []
            
            # Procurar por cabeçalhos de tabela comuns
            cabecalhos = ["ITEM", "QTY", "QUANTITY", "DESCRIPTION", "UNIT", "PRICE", "AMOUNT", "TOTAL", "CURRENCY", "SUM", "CONVERTED"]
            
            # Detectar formato de relatório de liquidação (settlement report)
            is_settlement_report = "Settlement Report" in texto or "Settlement" in texto
            
            # Caso especial para relatórios de liquidação
            if is_settlement_report:
                logger.info("Detectado formato de relatório de liquidação (settlement report)")
                
                # Padrão para produtos em relatórios de liquidação
                produtos_encontrados = []
                
                # Padrão para linhas de produtos com descrição longa e valores
                padrao_settlement = r"([A-Za-z][A-Za-z0-9\s]+(Carton|CT|Box|Package|Container)[A-Za-z0-9\s]+)\s+(\d+)\s+[\d,.]+\s+([\d,.]+)\s+€\s+([\d,.]+)"
                
                # Padrão alternativo para produtos com referência
                padrao_settlement_alt = r"([A-Za-z][A-Za-z0-9\s]+(Carton|CT|Box|Package|Container)[A-Za-z0-9\s]+)\s+(\d+)\s+[\d,.]+\s+(\d+)\s+€\s+([\d,.]+)"
                
                # Padrão para linhas de total de produto
                padrao_total = r"([A-Za-z][A-Za-z0-9\s]+(Carton|CT|Box|Package|Container)[A-Za-z0-9\s]+Total)\s+(\d+)\s+€\s+([\d,.]+)\s+€\s+([\d,.]+)"
                
                # Extrair taxa de câmbio global
                padrao_taxa_global = r"Currency\s+Rate\s*:?\s*([\d,.]+)"
                match_taxa_global = re.search(padrao_taxa_global, texto)
                currency_rate_global = match_taxa_global.group(1) if match_taxa_global else ""
                
                # Primeiro passo: identificar todos os produtos e seus totais
                produtos_com_total = {}
                produto_base = None
                
                for linha in linhas:
                    # Verificar se é uma linha de produto individual
                    match_produto = re.search(padrao_settlement, linha)
                    if not match_produto:
                        match_produto = re.search(padrao_settlement_alt, linha)
                    
                    if match_produto:
                        nome_produto = match_produto.group(1).strip()
                        ref = match_produto.group(3).strip() if len(match_produto.groups()) >= 3 else ""
                        quantidade = match_produto.group(3) if len(match_produto.groups()) >= 3 else ""
                        preco_total = match_produto.group(5).replace(",", ".") if len(match_produto.groups()) >= 5 else "0"
                        
                        # Extrair taxa de câmbio específica da linha
                        taxa_match = re.search(r"([\d,.]+)", linha)
                        currency_rate = taxa_match.group(1) if taxa_match else currency_rate_global
                        
                        # Extrair nome base do produto (sem o número de CT/quantidade)
                        produto_base_match = re.match(r"([A-Za-z][A-Za-z0-9\s]+)(Carton|CT|Box|Package|Container)([A-Za-z0-9\s]+)", nome_produto)
                        if produto_base_match:
                            produto_base = produto_base_match.group(1).strip() + " " + produto_base_match.group(2).strip()
                        else:
                            produto_base = nome_produto
                        
                        # Armazenar informações do produto
                        if produto_base not in produtos_com_total:
                            produtos_com_total[produto_base] = {
                                "produtos": [],
                                "total": None
                            }
                        
                        produtos_com_total[produto_base]["produtos"].append({
                            "nome": nome_produto,
                            "ref": ref,
                            "quantidade": quantidade,
                            "preco_total": preco_total,
                            "currency_rate": currency_rate
                        })
                        
                        logger.info(f"Produto individual encontrado: {nome_produto}, Quantidade: {quantidade}, Preço: {preco_total}")
                    
                    # Verificar se é uma linha de total
                    match_total = re.search(padrao_total, linha)
                    if match_total:
                        nome_total = match_total.group(1).strip()
                        quantidade_total = match_total.group(3)
                        preco_total = match_total.group(4).replace(",", ".")
                        preco_unitario = match_total.group(5).replace(",", ".") if len(match_total.groups()) >= 5 else "0"
                        
                        # Extrair nome base do produto (sem "Total")
                        produto_base = nome_total.replace("Total", "").strip()
                        
                        if produto_base in produtos_com_total:
                            produtos_com_total[produto_base]["total"] = {
                                "quantidade": quantidade_total,
                                "preco_total": preco_total,
                                "preco_unitario": preco_unitario
                            }
                            logger.info(f"Total encontrado para {produto_base}: Quantidade: {quantidade_total}, Preço Total: {preco_total}, Preço Unitário: {preco_unitario}")
                
                # Segundo passo: criar produtos finais com preços unitários calculados
                for produto_base, info in produtos_com_total.items():
                    for produto_individual in info["produtos"]:
                        # Usar preço unitário do total se disponível, ou calcular
                        preco_unitario = "0"
                        if info["total"] and info["total"]["preco_unitario"]:
                            preco_unitario = info["total"]["preco_unitario"]
                        elif produto_individual["quantidade"] and float(produto_individual["quantidade"]) > 0:
                            try:
                                preco_unitario = str(float(produto_individual["preco_total"]) / float(produto_individual["quantidade"]))
                            except:
                                preco_unitario = "0"
                        
                        produto = {
                            "tipo": produto_individual["nome"],
                            "tamanho": "",
                            "quantidade": produto_individual["quantidade"],
                            "preço unitário": preco_unitario,
                            "preço total": produto_individual["preco_total"],
                            "moeda": dados_extraidos["dados_principais"]["Moeda"],
                            "referencia": produto_individual["ref"],
                            "currency_rate": produto_individual["currency_rate"]
                        }
                        
                        dados_extraidos["produtos"].append(produto)
                
                # Se não encontrou produtos com o método específico, continuar com os métodos genéricos
                if not dados_extraidos["produtos"]:
                    logger.info("Nenhum produto encontrado com o padrão de relatório de liquidação, tentando métodos genéricos")
                else:
                    logger.info(f"Extração de relatório de liquidação concluída. Encontrados {len(dados_extraidos['produtos'])} produtos.")
                    return dados_extraidos
            
            # Método genérico para outros tipos de documentos
            for i, linha in enumerate(linhas):
                # Verificar se a linha contém vários cabeçalhos de tabela
                if sum(1 for cab in cabecalhos if cab in linha.upper()) >= 2 and not inicio_tabela:
                    inicio_tabela = True
                    logger.info(f"Início da tabela de produtos detectado na linha {i}: {linha}")
                    continue
                
                # Se estamos dentro da tabela, coletar linhas
                if inicio_tabela and not fim_tabela:
                    # Verificar se chegamos ao fim da tabela (linhas vazias ou totais)
                    if ("TOTAL" in linha.upper() or "GRAND" in linha.upper()) and len(linha.strip()) < 30:
                        fim_tabela = True
                        logger.info(f"Fim da tabela de produtos detectado na linha {i}: {linha}")
                        continue
                    
                    if linha.strip():  # Ignorar linhas vazias
                        linhas_tabela.append(linha)
            
            logger.info(f"Encontradas {len(linhas_tabela)} linhas na tabela de produtos")
            
            # Processar linhas da tabela
            for linha in linhas_tabela:
                # Padrões mais flexíveis para linhas de produtos
                # Padrão 1: Quantidade + Tipo + Valores numéricos
                padrao_produto1 = r"(\d+)\s+([A-Za-z0-9]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)"
                # Padrão 2: Quantidade + Tipo com espaços + Valores numéricos
                padrao_produto2 = r"(\d+)\s+([A-Za-z0-9][A-Za-z0-9\s]+?)\s+([\d,.]+)\s+([\d,.]+)"
                # Padrão 3: Apenas números e valores
                padrao_produto3 = r"(\d+)\s+(\d+)\s+([\d,.]+)\s+([\d,.]+)"
                
                match_produto = re.search(padrao_produto1, linha)
                if not match_produto:
                    match_produto = re.search(padrao_produto2, linha)
                if not match_produto:
                    match_produto = re.search(padrao_produto3, linha)
                
                if match_produto:
                    quantidade = match_produto.group(1)
                    tipo = match_produto.group(2).strip()
                    
                    # Determinar preço unitário e total com base no padrão encontrado
                    if len(match_produto.groups()) >= 5:  # Padrão 1
                        preco_unitario = match_produto.group(3).replace(",", ".")
                        preco_total = match_produto.group(5).replace(",", ".")
                    else:  # Padrão 2 ou 3
                        preco_unitario = match_produto.group(3).replace(",", ".")
                        preco_total = match_produto.group(4).replace(",", ".")
                    
                    produto = {
                        "tipo": tipo,
                        "tamanho": "",
                        "quantidade": quantidade,
                        "preço unitário": preco_unitario,
                        "preço total": preco_total,
                        "moeda": dados_extraidos["dados_principais"]["Moeda"],
                        "referencia": tipo,
                        "currency_rate": currency_rate
                    }
                    
                    dados_extraidos["produtos"].append(produto)
                    logger.info(f"Produto encontrado: {tipo}")
                else:
                    # Tentar extrair usando um padrão mais simples para linhas que podem ter sido quebradas
                    numeros = re.findall(r'\d+(?:[,.]\d+)?', linha)
                    if len(numeros) >= 3 and any(c.isalpha() for c in linha):
                        # Extrair texto (não numérico) como tipo
                        texto_tipo = re.sub(r'\d+(?:[,.]\d+)?', '', linha).strip()
                        texto_tipo = re.sub(r'[^\w\s]', '', texto_tipo).strip()
                        
                        if texto_tipo and len(numeros) >= 3:
                            quantidade = numeros[0]
                            preco_unitario = numeros[-2].replace(",", ".")
                            preco_total = numeros[-1].replace(",", ".")
                            
                            produto = {
                                "tipo": texto_tipo,
                                "tamanho": "",
                                "quantidade": quantidade,
                                "preço unitário": preco_unitario,
                                "preço total": preco_total,
                                "moeda": dados_extraidos["dados_principais"]["Moeda"],
                                "referencia": texto_tipo,
                                "currency_rate": currency_rate
                            }
                            
                            dados_extraidos["produtos"].append(produto)
                            logger.info(f"Produto encontrado (padrão alternativo): {texto_tipo}")
            
            # Se não encontrou produtos com os métodos anteriores, tentar abordagem baseada em espaçamento
            if not dados_extraidos["produtos"]:
                logger.info("Tentando extração baseada em espaçamento")
                for linha in linhas:
                    # Verificar se a linha tem pelo menos 3 números e algum texto
                    numeros = re.findall(r'\d+(?:[,.]\d+)?', linha)
                    if len(numeros) >= 3 and any(c.isalpha() for c in linha):
                        # Dividir a linha por espaços múltiplos
                        partes = re.split(r'\s{2,}', linha.strip())
                        
                        if len(partes) >= 3:
                            # Tentar identificar quantidade, tipo e preços
                            quantidade = ""
                            tipo = ""
                            preco_unitario = ""
                            preco_total = ""
                            
                            # Primeira parte geralmente é quantidade ou tipo
                            if partes[0].isdigit():
                                quantidade = partes[0]
                                tipo = partes[1] if len(partes) > 1 else ""
                            else:
                                tipo = partes[0]
                                # Procurar quantidade nas outras partes
                                for parte in partes[1:]:
                                    if parte.isdigit():
                                        quantidade = parte
                                        break
                            
                            # Últimas partes geralmente são preços
                            for parte in reversed(partes):
                                if re.match(r'^[\d,.]+$', parte):
                                    if not preco_total:
                                        preco_total = parte.replace(",", ".")
                                    elif not preco_unitario:
                                        preco_unitario = parte.replace(",", ".")
                            
                            if quantidade and tipo and (preco_unitario or preco_total):
                                produto = {
                                    "tipo": tipo,
                                    "tamanho": "",
                                    "quantidade": quantidade,
                                    "preço unitário": preco_unitario or "0",
                                    "preço total": preco_total or "0",
                                    "moeda": dados_extraidos["dados_principais"]["Moeda"],
                                    "referencia": tipo,
                                    "currency_rate": currency_rate
                                }
                                
                                dados_extraidos["produtos"].append(produto)
                                logger.info(f"Produto encontrado (espaçamento): {tipo}")
            
            # Último recurso: procurar por linhas que contenham "Mango", "Carton", etc.
            if not dados_extraidos["produtos"]:
                logger.info("Tentando extração baseada em palavras-chave de produtos")
                palavras_chave = ["Mango", "Carton", "Box", "Container", "Package", "Crate", "Pallet"]
                
                for linha in linhas:
                    if any(palavra in linha for palavra in palavras_chave):
                        # Extrair números da linha
                        numeros = re.findall(r'\d+(?:[,.]\d+)?', linha)
                        if len(numeros) >= 2:
                            # Extrair texto como tipo de produto
                            tipo = re.sub(r'\d+(?:[,.]\d+)?', '', linha).strip()
                            tipo = re.sub(r'[^\w\s]', ' ', tipo).strip()
                            tipo = re.sub(r'\s+', ' ', tipo).strip()
                            
                            # Tentar identificar quantidade e preço
                            quantidade = numeros[0] if len(numeros) > 0 else "1"
                            preco_total = numeros[-1].replace(",", ".") if len(numeros) > 1 else "0"
                            preco_unitario = "0"
                            
                            # Tentar calcular preço unitário
                            if len(numeros) > 2 and float(quantidade) > 0:
                                try:
                                    preco_unitario = str(float(preco_total) / float(quantidade))
                                except:
                                    preco_unitario = numeros[-2].replace(",", ".")
                            
                            produto = {
                                "tipo": tipo,
                                "tamanho": "",
                                "quantidade": quantidade,
                                "preço unitário": preco_unitario,
                                "preço total": preco_total,
                                "moeda": dados_extraidos["dados_principais"]["Moeda"],
                                "referencia": tipo,
                                "currency_rate": currency_rate
                            }
                            
                            dados_extraidos["produtos"].append(produto)
                            logger.info(f"Produto encontrado (palavras-chave): {tipo}")
            
            logger.info(f"Extração concluída. Encontrados {len(dados_extraidos['produtos'])} produtos.")
        
        elif tipo_doc == "cuenta_ventas_finobrasa":
            # Extrair nome da empresa
            padrao_empresa = r"(FINOBRASA|FINOBRA[SZ]A)"
            match_empresa = re.search(padrao_empresa, texto)
            if match_empresa:
                dados_extraidos["dados_principais"]["Nome da empresa"] = match_empresa.group(1)
            
            # Extrair valor total
            padrao_valor_total = r"TOTAL\s+([\d.,]+)"
            match_valor_total = re.search(padrao_valor_total, texto)
            if match_valor_total:
                valor = match_valor_total.group(1).replace(".", "").replace(",", ".")
                dados_extraidos["dados_principais"]["Valor total"] = valor
                dados_extraidos["dados_principais"]["Net Amount"] = valor
            
            # Extrair comissão %
            padrao_comissao_pct = r"Comision\s+(\d+)%"
            match_comissao_pct = re.search(padrao_comissao_pct, texto)
            if match_comissao_pct:
                dados_extraidos["dados_principais"]["Comissão %"] = match_comissao_pct.group(1)
            
            # Extrair comissão valor
            padrao_comissao_valor = r"Comision\s+\d+%\s+€\s+([\d.,]+)"
            match_comissao_valor = re.search(padrao_comissao_valor, texto)
            if match_comissao_valor:
                dados_extraidos["dados_principais"]["Comissão Valor"] = match_comissao_valor.group(1).replace(".", "").replace(",", ".")
            
            # Extrair moeda
            padrao_moeda = r"[€$]"
            match_moeda = re.search(padrao_moeda, texto)
            if match_moeda:
                moeda = match_moeda.group(0)
                if moeda == "€":
                    dados_extraidos["dados_principais"]["Moeda"] = "EUR"
                elif moeda == "$":
                    dados_extraidos["dados_principais"]["Moeda"] = "USD"
            
            # Extrair produtos
            linhas = texto.split('\n')
            for linha in linhas:
                # Padrão para produtos em cuenta de ventas
                padrao_produto = r"(MA[PE]\d[A-Z]+\d*)\s+(\d+)\s+(\d+)\s+(\d+[,.]?\d*)\s+(\d+[,.]?\d*)\s+€\s+([\d.,]+)"
                match_produto = re.search(padrao_produto, linha)
                
                if match_produto:
                    tipo = match_produto.group(1)
                    formato = match_produto.group(2)
                    quantidade = match_produto.group(3)
                    preco_unitario = match_produto.group(5).replace(",", ".")
                    preco_total = match_produto.group(6).replace(".", "").replace(",", ".")
                    
                    produto = {
                        "tipo": tipo,
                        "tamanho": formato,
                        "quantidade": quantidade,
                        "preço unitário": preco_unitario,
                        "preço total": preco_total,
                        "moeda": dados_extraidos["dados_principais"]["Moeda"],
                        "referencia": tipo,
                        "currency_rate": ""
                    }
                    
                    dados_extraidos["produtos"].append(produto)
                    logger.info(f"Produto encontrado: {tipo}")
        
        # Outros tipos de documentos podem ser adicionados aqui
        
        return dados_extraidos
    
    def extrair_com_openai(self, caminho_pdf, texto_pdf=None):
        """
        Extrai dados do PDF usando o assistente OpenAI
        
        Args:
            caminho_pdf (str): Caminho para o arquivo PDF
            texto_pdf (str, optional): Texto já extraído do PDF
            
        Returns:
            dict: Dicionário com os dados extraídos
        """
        logger.info("Extraindo dados com OpenAI")
        
        # Verificar se o cliente OpenAI está disponível
        if not self.openai_client:
            logger.error("Cliente OpenAI não inicializado")
            return None
        
        # Verificar se o ID do assistente está disponível
        if not self.assistant_id:
            logger.error("ID do assistente não configurado")
            return None
        
        try:
            # Compatibilidade com diferentes versões da API OpenAI
            if is_new_api:
                # Nova API (v1.0+)
                return self._extrair_com_openai_v1(caminho_pdf, texto_pdf)
            else:
                # API antiga (v0.x)
                return self._extrair_com_openai_v0(caminho_pdf, texto_pdf)
        
        except Exception as e:
            logger.error(f"Erro ao extrair dados com OpenAI: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    
    def _extrair_com_openai_v1(self, caminho_pdf, texto_pdf=None):
        """
        Extrai dados do PDF usando o assistente OpenAI (API v1.0+)
        
        Args:
            caminho_pdf (str): Caminho para o arquivo PDF
            texto_pdf (str, optional): Texto já extraído do PDF
            
        Returns:
            dict: Dicionário com os dados extraídos
        """
        logger.info("Usando API OpenAI v1.0+")
        
        try:
            # Criar thread
            thread = self.openai_client.beta.threads.create()
            logger.info(f"Thread criado: {thread.id}")
            
            # Fazer upload do arquivo PDF
            try:
                file = self.openai_client.files.create(
                    file=open(caminho_pdf, "rb"),
                    purpose="assistants"
                )
                logger.info(f"Arquivo enviado: {file.id}")
                
                # Adicionar mensagem com o arquivo
                message = self.openai_client.beta.threads.messages.create(
                    thread_id=thread.id,
                    role="user",
                    content="Extraia todos os dados deste PDF, incluindo dados principais e produtos. Retorne em formato JSON.",
                    file_ids=[file.id]
                )
            except Exception as e:
                logger.warning(f"Erro ao enviar arquivo: {str(e)}")
                
                # Alternativa: enviar texto extraído
                if texto_pdf:
                    message = self.openai_client.beta.threads.messages.create(
                        thread_id=thread.id,
                        role="user",
                        content=f"Extraia todos os dados deste texto extraído de um PDF, incluindo dados principais e produtos. Retorne em formato JSON.\n\nTexto do PDF:\n{texto_pdf}"
                    )
                else:
                    raise Exception("Não foi possível enviar o arquivo nem o texto extraído")
            
            # Executar o assistente
            run = self.openai_client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=self.assistant_id
            )
            logger.info(f"Run criado: {run.id}")
            
            # Aguardar conclusão
            max_retries = 60
            retry_count = 0
            while retry_count < max_retries:
                run = self.openai_client.beta.threads.runs.retrieve(
                    thread_id=thread.id,
                    run_id=run.id
                )
                
                if run.status == "completed":
                    logger.info("Run concluído com sucesso")
                    break
                elif run.status in ["failed", "cancelled", "expired"]:
                    logger.error(f"Run falhou com status: {run.status}")
                    raise Exception(f"Run falhou com status: {run.status}")
                
                logger.info(f"Aguardando conclusão do run (status: {run.status})...")
                time.sleep(1)
                retry_count += 1
            
            if retry_count >= max_retries:
                logger.error("Timeout ao aguardar conclusão do run")
                raise Exception("Timeout ao aguardar conclusão do run")
            
            # Obter mensagens
            messages = self.openai_client.beta.threads.messages.list(
                thread_id=thread.id
            )
            
            # Processar resposta
            for message in messages.data:
                if message.role == "assistant":
                    for content in message.content:
                        if content.type == "text":
                            text = content.text.value
                            
                            # Extrair JSON da resposta
                            json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
                            if json_match:
                                json_str = json_match.group(1)
                            else:
                                # Tentar encontrar JSON sem marcadores de código
                                json_match = re.search(r'({.*})', text, re.DOTALL)
                                if json_match:
                                    json_str = json_match.group(1)
                                else:
                                    json_str = text
                            
                            try:
                                dados = json.loads(json_str)
                                logger.info("Dados extraídos com sucesso")
                                
                                # Atualizar status de treinamento
                                nome_pdf = os.path.basename(caminho_pdf)
                                atualizar_status_treinamento(nome_pdf, "sucesso")
                                
                                return dados
                            except json.JSONDecodeError as e:
                                logger.error(f"Erro ao decodificar JSON: {str(e)}")
                                logger.error(f"Texto recebido: {text}")
            
            logger.error("Nenhuma resposta válida encontrada")
            return None
        
        except Exception as e:
            logger.error(f"Erro ao extrair dados com OpenAI v1.0+: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Atualizar status de treinamento com falha
            nome_pdf = os.path.basename(caminho_pdf)
            atualizar_status_treinamento(nome_pdf, "falha")
            
            return None
    
    def _extrair_com_openai_v0(self, caminho_pdf, texto_pdf=None):
        """
        Extrai dados do PDF usando a API OpenAI (API v0.x)
        
        Args:
            caminho_pdf (str): Caminho para o arquivo PDF
            texto_pdf (str, optional): Texto já extraído do PDF
            
        Returns:
            dict: Dicionário com os dados extraídos
        """
        logger.info("Usando API OpenAI v0.x")
        
        try:
            # Preparar prompt
            if not texto_pdf:
                texto_pdf = self.extrair_texto_de_pdf(caminho_pdf)
            
            prompt = f"""
            Extraia todos os dados deste PDF, incluindo dados principais e produtos. Retorne em formato JSON.
            
            Texto do PDF:
            {texto_pdf}
            
            Formato de saída:
            ```json
            {{
                "dados_principais": {{
                    "Nome da empresa": "",
                    "Número do contêiner": "",
                    "Comissão %": "",
                    "Comissão Valor": "",
                    "Valor total": "",
                    "Net Amount": "",
                    "Moeda": ""
                }},
                "produtos": [
                    {{
                        "tipo": "",
                        "tamanho": "",
                        "quantidade": "",
                        "preço unitário": "",
                        "preço total": "",
                        "moeda": "",
                        "referencia": "",
                        "currency_rate": ""
                    }}
                ]
            }}
            ```
            """
            
            # Fazer chamada à API
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Você é um assistente especializado em extrair dados de PDFs."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=4000
            )
            
            # Processar resposta
            text = response.choices[0].message.content
            
            # Extrair JSON da resposta
            json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Tentar encontrar JSON sem marcadores de código
                json_match = re.search(r'({.*})', text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    json_str = text
            
            try:
                dados = json.loads(json_str)
                logger.info("Dados extraídos com sucesso")
                
                # Atualizar status de treinamento
                nome_pdf = os.path.basename(caminho_pdf)
                atualizar_status_treinamento(nome_pdf, "sucesso")
                
                return dados
            except json.JSONDecodeError as e:
                logger.error(f"Erro ao decodificar JSON: {str(e)}")
                logger.error(f"Texto recebido: {text}")
                return None
        
        except Exception as e:
            logger.error(f"Erro ao extrair dados com OpenAI v0.x: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Atualizar status de treinamento com falha
            nome_pdf = os.path.basename(caminho_pdf)
            atualizar_status_treinamento(nome_pdf, "falha")
            
            return None
    
    def treinar_assistente(self, caminho_pdf, dados_corrigidos):
        """
        Treina o assistente OpenAI com um PDF e dados corrigidos
        
        Args:
            caminho_pdf (str): Caminho para o arquivo PDF
            dados_corrigidos (dict): Dados corrigidos pelo usuário
            
        Returns:
            bool: True se o treinamento foi bem-sucedido, False caso contrário
        """
        logger.info(f"Treinando assistente com {caminho_pdf}")
        
        # Verificar se o cliente OpenAI está disponível
        if not self.openai_client:
            logger.error("Cliente OpenAI não inicializado")
            return False
        
        # Verificar se o ID do assistente está disponível
        if not self.assistant_id:
            logger.error("ID do assistente não configurado")
            return False
        
        try:
            # Compatibilidade com diferentes versões da API OpenAI
            if is_new_api:
                # Nova API (v1.0+)
                return self._treinar_assistente_v1(caminho_pdf, dados_corrigidos)
            else:
                # API antiga (v0.x)
                return self._treinar_assistente_v0(caminho_pdf, dados_corrigidos)
        
        except Exception as e:
            logger.error(f"Erro ao treinar assistente: {str(e)}")
            logger.error(traceback.format_exc())
            return False
    
    def _treinar_assistente_v1(self, caminho_pdf, dados_corrigidos):
        """
        Treina o assistente OpenAI com um PDF e dados corrigidos (API v1.0+)
        
        Args:
            caminho_pdf (str): Caminho para o arquivo PDF
            dados_corrigidos (dict): Dados corrigidos pelo usuário
            
        Returns:
            bool: True se o treinamento foi bem-sucedido, False caso contrário
        """
        logger.info("Usando API OpenAI v1.0+ para treinamento")
        
        try:
            # Criar thread
            thread = self.openai_client.beta.threads.create()
            logger.info(f"Thread criado: {thread.id}")
            
            # Fazer upload do arquivo PDF
            try:
                file = self.openai_client.files.create(
                    file=open(caminho_pdf, "rb"),
                    purpose="assistants"
                )
                logger.info(f"Arquivo enviado: {file.id}")
                
                # Adicionar mensagem com o arquivo e dados corrigidos
                message = self.openai_client.beta.threads.messages.create(
                    thread_id=thread.id,
                    role="user",
                    content=f"Este é um exemplo de extração correta para este PDF. Use estas informações para melhorar suas extrações futuras:\n\n```json\n{json.dumps(dados_corrigidos, indent=2, ensure_ascii=False)}\n```",
                    file_ids=[file.id]
                )
            except Exception as e:
                logger.warning(f"Erro ao enviar arquivo: {str(e)}")
                
                # Alternativa: enviar apenas os dados corrigidos
                message = self.openai_client.beta.threads.messages.create(
                    thread_id=thread.id,
                    role="user",
                    content=f"Este é um exemplo de extração correta para um PDF. Use estas informações para melhorar suas extrações futuras:\n\n```json\n{json.dumps(dados_corrigidos, indent=2, ensure_ascii=False)}\n```"
                )
            
            # Executar o assistente
            run = self.openai_client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=self.assistant_id
            )
            logger.info(f"Run criado: {run.id}")
            
            # Aguardar conclusão
            max_retries = 60
            retry_count = 0
            while retry_count < max_retries:
                run = self.openai_client.beta.threads.runs.retrieve(
                    thread_id=thread.id,
                    run_id=run.id
                )
                
                if run.status == "completed":
                    logger.info("Run concluído com sucesso")
                    
                    # Atualizar status de treinamento
                    nome_pdf = os.path.basename(caminho_pdf)
                    atualizar_status_treinamento(nome_pdf, "sucesso")
                    
                    return True
                elif run.status in ["failed", "cancelled", "expired"]:
                    logger.error(f"Run falhou com status: {run.status}")
                    
                    # Atualizar status de treinamento com falha
                    nome_pdf = os.path.basename(caminho_pdf)
                    atualizar_status_treinamento(nome_pdf, "falha")
                    
                    return False
                
                logger.info(f"Aguardando conclusão do run (status: {run.status})...")
                time.sleep(1)
                retry_count += 1
            
            if retry_count >= max_retries:
                logger.error("Timeout ao aguardar conclusão do run")
                
                # Atualizar status de treinamento com falha
                nome_pdf = os.path.basename(caminho_pdf)
                atualizar_status_treinamento(nome_pdf, "timeout")
                
                return False
        
        except Exception as e:
            logger.error(f"Erro ao treinar assistente com OpenAI v1.0+: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Atualizar status de treinamento com falha
            nome_pdf = os.path.basename(caminho_pdf)
            atualizar_status_treinamento(nome_pdf, "falha")
            
            return False
    
    def _treinar_assistente_v0(self, caminho_pdf, dados_corrigidos):
        """
        Simula treinamento do assistente com API antiga (v0.x)
        
        Args:
            caminho_pdf (str): Caminho para o arquivo PDF
            dados_corrigidos (dict): Dados corrigidos pelo usuário
            
        Returns:
            bool: True se o treinamento foi bem-sucedido, False caso contrário
        """
        logger.info("Usando API OpenAI v0.x para treinamento (simulado)")
        
        try:
            # A API v0.x não suporta assistentes, então apenas simulamos o treinamento
            logger.info("Treinamento simulado concluído com sucesso")
            
            # Atualizar status de treinamento
            nome_pdf = os.path.basename(caminho_pdf)
            atualizar_status_treinamento(nome_pdf, "simulado")
            
            return True
        
        except Exception as e:
            logger.error(f"Erro ao simular treinamento com OpenAI v0.x: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Atualizar status de treinamento com falha
            nome_pdf = os.path.basename(caminho_pdf)
            atualizar_status_treinamento(nome_pdf, "falha")
            
            return False

def display_pdf(caminho_pdf):
    """
    Exibe um PDF na interface
    
    Args:
        caminho_pdf (str): Caminho para o arquivo PDF
    """
    if caminho_pdf:
        try:
            # Converter PDF para imagens
            images = convert_from_path(caminho_pdf)
            st.session_state.pdf_images = images
            
            # Exibir a primeira página
            if images:
                st.image(images[0], caption=f"Página 1 de {len(images)}", use_container_width=True)
                
                # Seletor de página se houver mais de uma
                if len(images) > 1:
                    page_num = st.selectbox("Selecionar página:", range(1, len(images) + 1))
                    st.image(images[page_num - 1], caption=f"Página {page_num} de {len(images)}", use_container_width=True)
        except Exception as e:
            logger.error(f"Erro ao converter PDF para imagens: {str(e)}")
            
            # Alternativa: exibir PDF como iframe
            try:
                with open(caminho_pdf, "rb") as f:
                    base64_pdf = base64.b64encode(f.read()).decode('utf-8')
                pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
                st.markdown(pdf_display, unsafe_allow_html=True)
            except Exception as e2:
                logger.error(f"Erro ao exibir PDF como iframe: {str(e2)}")
                st.error(f"Não foi possível exibir o PDF: {str(e)}")

def show_main_page():
    """Exibe a página principal"""
    st.title("Extrator Inteligente de PDFs com OpenAI")
    
    # Barra lateral
    with st.sidebar:
        st.subheader("Configurações")
        
        # Upload de PDF
        pdf_file = st.file_uploader("Selecione um PDF", type=["pdf"])
        
        # Chave da API OpenAI
        api_key = st.text_input(
            "Chave da API OpenAI",
            value=st.session_state.api_key if st.session_state.api_key else "",
            type="password",
            help="Você pode definir esta chave no arquivo .streamlit/secrets.toml"
        )
        
        if api_key and api_key != st.session_state.api_key:
            st.session_state.api_key = api_key
            st.success("Chave de API atualizada!")
        
        # ID do assistente OpenAI
        assistant_id = st.text_input(
            "ID do Assistente OpenAI",
            value=st.session_state.assistant_id if st.session_state.assistant_id else "",
            help="Você pode definir este ID no arquivo .streamlit/secrets.toml"
        )
        
        if assistant_id and assistant_id != st.session_state.assistant_id:
            st.session_state.assistant_id = assistant_id
            st.success("ID do assistente atualizado!")
        
        # Método de extração
        extraction_method = st.radio(
            "Método de Extração",
            ["auto", "ocr", "openai"],
            index=["auto", "ocr", "openai"].index(st.session_state.extraction_method)
        )
        
        if extraction_method != st.session_state.extraction_method:
            st.session_state.extraction_method = extraction_method
        
        # Botão de processamento
        process_button = st.button("Processar PDF")
        
        # Modo de debug
        debug_mode = st.checkbox("Modo de Debug", value=st.session_state.debug_mode)
        if debug_mode != st.session_state.debug_mode:
            st.session_state.debug_mode = debug_mode
    
    # Navegação
    with st.sidebar:
        st.subheader("Navegação")
        
        if st.button("Página Principal"):
            st.session_state.page = "main"
            st.rerun()
        
        if st.button("Configuração do Assistente OpenAI"):
            st.session_state.page = "assistant_config"
            st.rerun()
        
        if st.button("Histórico de Extrações"):
            st.session_state.page = "extraction_history"
            st.rerun()
        
        if st.button("Guia do Assistente OpenAI"):
            st.session_state.page = "assistant_guide"
            st.rerun()
        
        if st.button("Status de Treinamento"):
            st.session_state.page = "training_status"
            st.rerun()
    
    # Processar PDF
    if pdf_file is not None:
        # Salvar PDF temporariamente
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(pdf_file.getvalue())
            pdf_path = tmp_file.name
        
        st.session_state.pdf_path = pdf_path
        st.session_state.pdf_name = pdf_file.name
        
        # Exibir PDF
        st.subheader(f"PDF: {pdf_file.name}")
        display_pdf(pdf_path)
        
        # Processar PDF quando o botão é clicado
        if process_button:
            with st.spinner("Processando PDF..."):
                # Criar extrator
                extractor = PDFExtractor(
                    api_key=st.session_state.api_key,
                    assistant_id=st.session_state.assistant_id
                )
                
                # Extrair dados
                dados = extractor.extrair_dados(
                    caminho_pdf=pdf_path,
                    metodo=st.session_state.extraction_method
                )
                
                if dados:
                    st.session_state.pdf_data = dados
                    
                    # Adicionar ao histórico de extrações
                    st.session_state.extraction_history.append({
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "pdf_name": pdf_file.name,
                        "method": st.session_state.extraction_method,
                        "data": dados
                    })
                    
                    # Exibir dados extraídos
                    st.subheader("Dados Extraídos")
                    
                    # Dados principais
                    st.write("### Dados Principais")
                    dados_principais_df = pd.DataFrame(list(dados["dados_principais"].items()), columns=["Campo", "Valor"])
                    st.dataframe(dados_principais_df, use_container_width=True)
                    
                    # Produtos
                    st.write("### Produtos")
                    if dados["produtos"]:
                        produtos_df = pd.DataFrame(dados["produtos"])
                        st.dataframe(produtos_df, use_container_width=True)
                        
                        # Exibir número de produtos encontrados
                        st.success(f"Encontrados {len(dados['produtos'])} produtos")
                    else:
                        st.warning("Nenhum produto encontrado")
                    
                    # Formulário para edição
                    st.subheader("Editar Dados")
                    
                    with st.form(key="editable_form"):
                        # Dados principais
                        st.write("#### Dados Principais")
                        dados_principais_editados = {}
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            dados_principais_editados["Nome da empresa"] = st.text_input(
                                "Nome da empresa",
                                value=dados["dados_principais"].get("Nome da empresa", "")
                            )
                            dados_principais_editados["Número do contêiner"] = st.text_input(
                                "Número do contêiner",
                                value=dados["dados_principais"].get("Número do contêiner", "")
                            )
                            dados_principais_editados["Comissão %"] = st.text_input(
                                "Comissão %",
                                value=dados["dados_principais"].get("Comissão %", "")
                            )
                        
                        with col2:
                            dados_principais_editados["Comissão Valor"] = st.text_input(
                                "Comissão Valor",
                                value=dados["dados_principais"].get("Comissão Valor", "")
                            )
                            dados_principais_editados["Valor total"] = st.text_input(
                                "Valor total",
                                value=dados["dados_principais"].get("Valor total", "")
                            )
                            dados_principais_editados["Net Amount"] = st.text_input(
                                "Net Amount",
                                value=dados["dados_principais"].get("Net Amount", "")
                            )
                            dados_principais_editados["Moeda"] = st.text_input(
                                "Moeda",
                                value=dados["dados_principais"].get("Moeda", "")
                            )
                        
                        # Produtos
                        st.write("#### Produtos")
                        produtos_editados = []
                        
                        for i, produto in enumerate(dados["produtos"]):
                            st.write(f"##### Produto {i+1}")
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                tipo = st.text_input(
                                    f"Tipo {i+1}",
                                    value=produto.get("tipo", ""),
                                    key=f"tipo_{i}"
                                )
                                tamanho = st.text_input(
                                    f"Tamanho {i+1}",
                                    value=produto.get("tamanho", ""),
                                    key=f"tamanho_{i}"
                                )
                                quantidade = st.text_input(
                                    f"Quantidade {i+1}",
                                    value=produto.get("quantidade", ""),
                                    key=f"quantidade_{i}"
                                )
                                referencia = st.text_input(
                                    f"Referência {i+1}",
                                    value=produto.get("referencia", ""),
                                    key=f"referencia_{i}"
                                )
                            
                            with col2:
                                preco_unitario = st.text_input(
                                    f"Preço Unitário {i+1}",
                                    value=produto.get("preço unitário", ""),
                                    key=f"preco_unitario_{i}"
                                )
                                preco_total = st.text_input(
                                    f"Preço Total {i+1}",
                                    value=produto.get("preço total", ""),
                                    key=f"preco_total_{i}"
                                )
                                moeda = st.text_input(
                                    f"Moeda {i+1}",
                                    value=produto.get("moeda", ""),
                                    key=f"moeda_{i}"
                                )
                                currency_rate = st.text_input(
                                    f"Taxa de Câmbio {i+1}",
                                    value=produto.get("currency_rate", ""),
                                    key=f"currency_rate_{i}"
                                )
                            
                            produtos_editados.append({
                                "tipo": tipo,
                                "tamanho": tamanho,
                                "quantidade": quantidade,
                                "preço unitário": preco_unitario,
                                "preço total": preco_total,
                                "moeda": moeda,
                                "referencia": referencia,
                                "currency_rate": currency_rate
                            })
                        
                        # Botão para adicionar novo produto
                        if st.checkbox("Adicionar Novo Produto"):
                            st.write("##### Novo Produto")
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                tipo_novo = st.text_input(
                                    "Tipo (Novo)",
                                    value="",
                                    key="tipo_novo"
                                )
                                tamanho_novo = st.text_input(
                                    "Tamanho (Novo)",
                                    value="",
                                    key="tamanho_novo"
                                )
                                quantidade_novo = st.text_input(
                                    "Quantidade (Novo)",
                                    value="",
                                    key="quantidade_novo"
                                )
                                referencia_novo = st.text_input(
                                    "Referência (Novo)",
                                    value="",
                                    key="referencia_novo"
                                )
                            
                            with col2:
                                preco_unitario_novo = st.text_input(
                                    "Preço Unitário (Novo)",
                                    value="",
                                    key="preco_unitario_novo"
                                )
                                preco_total_novo = st.text_input(
                                    "Preço Total (Novo)",
                                    value="",
                                    key="preco_total_novo"
                                )
                                moeda_novo = st.text_input(
                                    "Moeda (Novo)",
                                    value=dados["dados_principais"].get("Moeda", ""),
                                    key="moeda_novo"
                                )
                                currency_rate_novo = st.text_input(
                                    "Taxa de Câmbio (Novo)",
                                    value="",
                                    key="currency_rate_novo"
                                )
                            
                            if tipo_novo and quantidade_novo:
                                produtos_editados.append({
                                    "tipo": tipo_novo,
                                    "tamanho": tamanho_novo,
                                    "quantidade": quantidade_novo,
                                    "preço unitário": preco_unitario_novo,
                                    "preço total": preco_total_novo,
                                    "moeda": moeda_novo,
                                    "referencia": referencia_novo,
                                    "currency_rate": currency_rate_novo
                                })
                        
                        # Botão para salvar correções
                        save_clicked = st.form_submit_button("Salvar Correções")
                        
                        if save_clicked:
                            logger.info("Botão Salvar Correções clicado via callback")
                            
                            # Atualizar dados
                            dados_corrigidos = {
                                "dados_principais": dados_principais_editados,
                                "produtos": produtos_editados,
                                "metodo_extracao": dados.get("metodo_extracao", "manual")
                            }
                            
                            # Atualizar dados na sessão
                            st.session_state.pdf_data = dados_corrigidos
                            
                            # Atualizar histórico de extrações
                            for item in st.session_state.extraction_history:
                                if item["pdf_name"] == pdf_file.name:
                                    item["data"] = dados_corrigidos
                                    item["corrected"] = True
                                    break
                            
                            st.success("Correções salvas com sucesso!")
                    
                    # Botão para treinar assistente
                    if st.button("Treinar Assistente com Este PDF e Correções"):
                        with st.spinner("Treinando assistente..."):
                            # Criar extrator
                            extractor = PDFExtractor(
                                api_key=st.session_state.api_key,
                                assistant_id=st.session_state.assistant_id
                            )
                            
                            # Treinar assistente
                            success = extractor.treinar_assistente(
                                caminho_pdf=pdf_path,
                                dados_corrigidos=st.session_state.pdf_data
                            )
                            
                            if success:
                                st.success("Assistente treinado com sucesso!")
                            else:
                                st.error("Erro ao treinar assistente. Verifique os logs para mais detalhes.")
                    
                    # Botão para exportar dados
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Exportar como JSON"):
                            # Converter para JSON
                            json_str = json.dumps(st.session_state.pdf_data, indent=2, ensure_ascii=False)
                            
                            # Criar arquivo para download
                            st.download_button(
                                label="Baixar JSON",
                                data=json_str,
                                file_name=f"{pdf_file.name.replace('.pdf', '')}_dados.json",
                                mime="application/json"
                            )
                    
                    with col2:
                        if st.button("Exportar como CSV"):
                            # Converter produtos para CSV
                            produtos_df = pd.DataFrame(st.session_state.pdf_data["produtos"])
                            csv = produtos_df.to_csv(index=False)
                            
                            # Criar arquivo para download
                            st.download_button(
                                label="Baixar CSV",
                                data=csv,
                                file_name=f"{pdf_file.name.replace('.pdf', '')}_produtos.csv",
                                mime="text/csv"
                            )
                    
                    # Exibir dados em formato JSON (modo debug)
                    if st.session_state.debug_mode:
                        st.subheader("Dados em JSON (Debug)")
                        st.json(st.session_state.pdf_data)
                else:
                    st.error("Não foi possível extrair dados do PDF. Verifique os logs para mais detalhes.")
    else:
        st.info("Carregue um PDF para começar a extração.")

def show_assistant_config_page():
    """Exibe a página de configuração do assistente OpenAI"""
    st.title("Configuração do Assistente OpenAI")
    
    # Verificar se a biblioteca OpenAI está instalada
    try:
        import openai
    except ImportError:
        st.error("Biblioteca OpenAI não encontrada. Instale com:")
        st.code("""
        pip install --upgrade openai>=1.0.0
        """)
    
    # Configuração da API
    st.subheader("Configuração da API")
    
    # Informação sobre secrets.toml
    st.info("As credenciais são carregadas automaticamente do arquivo `.streamlit/secrets.toml`. Você também pode inserir ou atualizar as credenciais abaixo.")
    
    # Chave da API
    api_key = st.text_input(
        "Chave da API OpenAI",
        value=st.session_state.api_key if st.session_state.api_key else "",
        type="password",
        help="Você pode definir esta chave no arquivo .streamlit/secrets.toml"
    )
    
    if api_key and api_key != st.session_state.api_key:
        st.session_state.api_key = api_key
        st.success("Chave de API atualizada!")
    
    # ID do assistente
    assistant_id = st.text_input(
        "ID do Assistente OpenAI",
        value=st.session_state.assistant_id if st.session_state.assistant_id else "",
        help="Você pode definir este ID no arquivo .streamlit/secrets.toml"
    )
    
    if assistant_id and assistant_id != st.session_state.assistant_id:
        st.session_state.assistant_id = assistant_id
        st.success("ID do assistente atualizado!")
    
    # Criar novo assistente
    st.subheader("Criar Novo Assistente")
    
    if st.button("Criar Assistente"):
        if not st.session_state.api_key:
            st.error("Chave de API não configurada")
        else:
            with st.spinner("Criando assistente..."):
                try:
                    # Verificar versão da API
                    if is_new_api:
                        # Nova API (v1.0+)
                        client = OpenAI(api_key=st.session_state.api_key)
                        
                        # Criar assistente
                        assistant = client.beta.assistants.create(
                            name="Extrator de PDFs",
                            description="Assistente especializado em extrair dados de PDFs",
                            instructions="""
                            Você é um assistente especializado em extrair dados de PDFs.
                            
                            Sua tarefa é extrair informações estruturadas de PDFs, incluindo:
                            1. Dados principais como nome da empresa, número do contêiner, valores, etc.
                            2. Lista de produtos com suas propriedades (tipo, quantidade, preços, etc.)
                            
                            Sempre retorne os dados em formato JSON seguindo esta estrutura:
                            ```json
                            {
                                "dados_principais": {
                                    "Nome da empresa": "",
                                    "Número do contêiner": "",
                                    "Comissão %": "",
                                    "Comissão Valor": "",
                                    "Valor total": "",
                                    "Net Amount": "",
                                    "Moeda": ""
                                },
                                "produtos": [
                                    {
                                        "tipo": "",
                                        "tamanho": "",
                                        "quantidade": "",
                                        "preço unitário": "",
                                        "preço total": "",
                                        "moeda": "",
                                        "referencia": "",
                                        "currency_rate": ""
                                    }
                                ]
                            }
                            ```
                            
                            Aprenda com os exemplos fornecidos para melhorar suas extrações futuras.
                            """,
                            model="gpt-4-turbo",
                            tools=[{"type": "file_search"}]
                        )
                        
                        # Atualizar ID do assistente
                        st.session_state.assistant_id = assistant.id
                        
                        st.success(f"Assistente criado com sucesso! ID: {assistant.id}")
                    else:
                        # API antiga (v0.x)
                        st.warning("A API OpenAI v0.x não suporta a criação de assistentes. Atualize para a versão 1.0+ para usar esta funcionalidade.")
                except Exception as e:
                    st.error(f"Erro ao criar assistente: {str(e)}")
    
    # Testar assistente
    st.subheader("Testar Assistente")
    
    if st.button("Testar Conexão com Assistente"):
        if not st.session_state.api_key or not st.session_state.assistant_id:
            st.error("Chave de API ou ID do assistente não configurados")
        else:
            with st.spinner("Testando conexão..."):
                try:
                    # Verificar versão da API
                    if is_new_api:
                        # Nova API (v1.0+)
                        client = OpenAI(api_key=st.session_state.api_key)
                        
                        # Obter assistente
                        assistant = client.beta.assistants.retrieve(
                            assistant_id=st.session_state.assistant_id
                        )
                        
                        st.success(f"Conexão bem-sucedida! Assistente: {assistant.name}")
                        
                        # Exibir detalhes do assistente
                        st.write("#### Detalhes do Assistente")
                        st.write(f"Nome: {assistant.name}")
                        st.write(f"Modelo: {assistant.model}")
                        st.write(f"Descrição: {assistant.description}")
                    else:
                        # API antiga (v0.x)
                        st.warning("A API OpenAI v0.x não suporta a verificação de assistentes. Atualize para a versão 1.0+ para usar esta funcionalidade.")
                except Exception as e:
                    st.error(f"Erro ao testar conexão: {str(e)}")

def show_extraction_history_page():
    """Exibe a página de histórico de extrações"""
    st.title("Histórico de Extrações")
    
    if not st.session_state.extraction_history:
        st.info("Nenhuma extração realizada ainda.")
    else:
        # Exibir histórico em ordem cronológica inversa
        for i, item in enumerate(reversed(st.session_state.extraction_history)):
            with st.expander(f"{item['pdf_name']} - {item['timestamp']} ({item['method']})"):
                # Dados principais
                st.write("### Dados Principais")
                dados_principais_df = pd.DataFrame(list(item["data"]["dados_principais"].items()), columns=["Campo", "Valor"])
                st.dataframe(dados_principais_df, use_container_width=True)
                
                # Produtos
                st.write("### Produtos")
                if item["data"]["produtos"]:
                    produtos_df = pd.DataFrame(item["data"]["produtos"])
                    st.dataframe(produtos_df, use_container_width=True)
                    
                    # Exibir número de produtos encontrados
                    st.success(f"Encontrados {len(item['data']['produtos'])} produtos")
                else:
                    st.warning("Nenhum produto encontrado")
                
                # Botões para exportar
                col1, col2 = st.columns(2)
                with col1:
                    # Converter para JSON
                    json_str = json.dumps(item["data"], indent=2, ensure_ascii=False)
                    
                    # Criar arquivo para download
                    st.download_button(
                        label="Exportar como JSON",
                        data=json_str,
                        file_name=f"{item['pdf_name'].replace('.pdf', '')}_dados.json",
                        mime="application/json",
                        key=f"json_{i}"
                    )
                
                with col2:
                    if item["data"]["produtos"]:
                        # Converter produtos para CSV
                        produtos_df = pd.DataFrame(item["data"]["produtos"])
                        csv = produtos_df.to_csv(index=False)
                        
                        # Criar arquivo para download
                        st.download_button(
                            label="Exportar como CSV",
                            data=csv,
                            file_name=f"{item['pdf_name'].replace('.pdf', '')}_produtos.csv",
                            mime="text/csv",
                            key=f"csv_{i}"
                        )
        
        # Botão para limpar histórico
        if st.button("Limpar Histórico"):
            st.session_state.extraction_history = []
            st.success("Histórico limpo com sucesso!")
            st.rerun()

def show_assistant_guide_page():
    """Exibe a página de guia do assistente OpenAI"""
    st.title("Guia do Assistente OpenAI")
    
    st.write("""
    ## O que é o Assistente OpenAI?
    
    O Assistente OpenAI é um modelo de linguagem avançado que pode ser treinado para realizar tarefas específicas. Neste caso, o assistente é especializado em extrair dados de PDFs, incluindo informações sobre empresas, contêineres, valores e produtos.
    
    ## Como funciona o aprendizado contínuo?
    
    O aprendizado contínuo permite que o assistente melhore suas extrações com base nas correções feitas pelos usuários. Quando você corrige os dados extraídos e treina o assistente, ele aprende com essas correções e aplica esse conhecimento em extrações futuras de PDFs similares.
    
    ## Como usar o assistente?
    
    1. **Configuração inicial**:
       - Obtenha uma chave de API da OpenAI em [platform.openai.com](https://platform.openai.com)
       - Crie um assistente na página "Configuração do Assistente OpenAI" ou use um existente
       - Configure a chave de API e o ID do assistente
    
    2. **Extração de dados**:
       - Carregue um PDF na página principal
       - Selecione o método de extração (auto, ocr, openai)
       - Clique em "Processar PDF"
       - Revise os dados extraídos
    
    3. **Correção e treinamento**:
       - Corrija os dados extraídos se necessário
       - Clique em "Salvar Correções"
       - Clique em "Treinar Assistente com Este PDF e Correções"
    
    4. **Verificação de progresso**:
       - Acesse a página "Status de Treinamento" para verificar o progresso do aprendizado
       - Veja quais PDFs foram usados para treinamento
       - Acompanhe o histórico de treinamentos
    
    ## Dicas para melhores resultados
    
    - **Use PDFs de qualidade**: PDFs com texto selecionável produzem melhores resultados
    - **Treine com exemplos variados**: Quanto mais exemplos diferentes você fornecer, melhor será o desempenho do assistente
    - **Corrija todos os campos**: Certifique-se de corrigir todos os campos incorretos antes de treinar o assistente
    - **Seja consistente**: Use o mesmo formato para dados similares em diferentes PDFs
    
    ## Considerações sobre custos
    
    O uso da API OpenAI tem custos associados:
    
    - A extração de dados com o método "openai" consome tokens da sua conta
    - O treinamento do assistente também consome tokens
    - O custo varia de acordo com o tamanho do PDF e a complexidade dos dados
    
    Recomendamos monitorar o uso da API em [platform.openai.com](https://platform.openai.com) para evitar custos inesperados.
    """)

def show_training_status_page():
    """Exibe a página de status de treinamento"""
    st.title("Status de Treinamento do Assistente")
    
    # Exibir status de treinamento
    exibir_status_treinamento()
    
# Função principal
def main():
    if "page" not in st.session_state:
        st.session_state.page = "main"
    # Exibir página de acordo com a seleção
    if st.session_state.page == "main":
        show_main_page()
    elif st.session_state.page == "assistant_config":
        show_assistant_config_page()
    elif st.session_state.page == "extraction_history":
        show_extraction_history_page()
    elif st.session_state.page == "assistant_guide":
        show_assistant_guide_page()
    elif st.session_state.page == "training_status":
        show_training_status_page()

# Executar aplicação
if __name__ == "__main__":
    main()
