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
import base64
from PIL import Image
import io
import requests
from pdf2image import convert_from_path
import pytesseract
import cv2
import re
import importlib
import pkg_resources

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

# Verificar versão da biblioteca OpenAI
try:
    openai_version = pkg_resources.get_distribution("openai").version
    logger.info(f"Versão da biblioteca OpenAI: {openai_version}")
    
    # Converter para versão numérica para comparação
    version_parts = openai_version.split('.')
    major_version = int(version_parts[0])
    is_new_api = major_version >= 1
    
    logger.info(f"Usando API OpenAI {'nova (v1+)' if is_new_api else 'antiga (v0.x)'}")
except Exception as e:
    logger.warning(f"Não foi possível determinar a versão da OpenAI: {str(e)}")
    is_new_api = False

# Configuração da página
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

class PDFExtractor:
    def __init__(self, api_key=None, assistant_id=None):
        """
        Inicializa o extrator de PDF com integração OpenAI
        
        Args:
            api_key (str, optional): Chave de API da OpenAI
            assistant_id (str, optional): ID do assistente OpenAI para extração
        """
        self.api_key = api_key
        self.assistant_id = assistant_id
        
        # Estrutura padrão para os dados extraídos
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
        
        # Inicializar OpenAI se a chave for fornecida
        if api_key:
            try:
                import openai
                
                # Verificar versão da API OpenAI
                if is_new_api:
                    # Nova API (v1.0+)
                    self.openai_client = openai.OpenAI(api_key=api_key)
                else:
                    # API antiga (v0.x)
                    openai.api_key = api_key
                    self.openai_client = openai
                
                logger.info("Cliente OpenAI inicializado com sucesso")
            except ImportError:
                logger.warning("Biblioteca OpenAI não encontrada. Instalando...")
                os.system("pip install openai")
                import openai
                
                # Verificar versão após instalação
                try:
                    openai_version = pkg_resources.get_distribution("openai").version
                    version_parts = openai_version.split('.')
                    major_version = int(version_parts[0])
                    is_new_api = major_version >= 1
                except:
                    is_new_api = False
                
                if is_new_api:
                    # Nova API (v1.0+)
                    self.openai_client = openai.OpenAI(api_key=api_key)
                else:
                    # API antiga (v0.x)
                    openai.api_key = api_key
                    self.openai_client = openai
                
                logger.info("Cliente OpenAI inicializado após instalação")
            except Exception as e:
                logger.error(f"Erro ao inicializar cliente OpenAI: {str(e)}")
                self.openai_client = None
        else:
            self.openai_client = None
    
    def extrair_dados(self, arquivo_pdf, metodo="auto"):
        """
        Extrai dados de um PDF usando o método especificado
        
        Args:
            arquivo_pdf: Caminho para o arquivo PDF
            metodo (str): Método de extração ('auto', 'ocr', 'openai')
            
        Returns:
            dict: Dicionário com os dados extraídos
        """
        logger.info(f"Iniciando extração do PDF com método: {metodo}")
        
        # Inicializar estrutura de dados
        dados_extraidos = {
            "dados_principais": self.estrutura_padrao["dados_principais"].copy(),
            "produtos": []
        }
        
        # Extrair texto do PDF
        texto_pdf = self.extrair_texto_com_ocr(arquivo_pdf)
        st.session_state.pdf_text = texto_pdf
        
        # Detectar tipo de documento
        tipo_doc = self.detectar_tipo_documento(texto_pdf, arquivo_pdf)
        logger.info(f"Tipo de documento detectado: {tipo_doc}")
        
        # Selecionar método de extração
        if metodo == "auto":
            # Tentar primeiro com OpenAI se disponível
            if self.openai_client and self.assistant_id:
                try:
                    logger.info("Tentando extração com OpenAI")
                    dados = self.extrair_com_openai(arquivo_pdf, texto_pdf)
                    if dados:
                        return dados
                except Exception as e:
                    logger.error(f"Erro ao extrair com OpenAI: {str(e)}")
            
            # Recorrer a OCR e regex
            logger.info("Recorrendo a OCR e regex")
            return self.extrair_com_ocr_e_regex(texto_pdf, tipo_doc, arquivo_pdf)
        
        elif metodo == "ocr":
            # Usar apenas OCR e regex
            logger.info("Usando OCR e regex para extração")
            return self.extrair_com_ocr_e_regex(texto_pdf, tipo_doc, arquivo_pdf)
        
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
                    return self.extrair_com_ocr_e_regex(texto_pdf, tipo_doc, arquivo_pdf)
                
                logger.info("Usando OpenAI para extração")
                try:
                    dados = self.extrair_com_openai(arquivo_pdf, texto_pdf)
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
            return self.extrair_com_ocr_e_regex(texto_pdf, tipo_doc, arquivo_pdf)
        
        else:
            logger.error(f"Método de extração desconhecido: {metodo}")
            return dados_extraidos
    
    def extrair_texto_com_ocr(self, caminho_pdf):
        """
        Extrai texto do PDF usando OCR
        
        Args:
            caminho_pdf (str): Caminho para o arquivo PDF
            
        Returns:
            str: Texto extraído do PDF
        """
        logger.info("Extraindo texto do PDF")
        
        try:
            # Primeiro, tentar extrair texto diretamente com pdftotext
            try:
                with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as temp_txt:
                    temp_txt_path = temp_txt.name
                
                os.system(f"pdftotext -layout '{caminho_pdf}' '{temp_txt_path}'")
                
                with open(temp_txt_path, 'r', encoding='utf-8', errors='ignore') as f:
                    texto = f.read()
                
                os.unlink(temp_txt_path)
                
                if texto.strip():
                    logger.info("Texto extraído com sucesso usando pdftotext")
                    return texto
            except Exception as e:
                logger.warning(f"Erro ao extrair texto com pdftotext: {str(e)}")
            
            # Se pdftotext falhar, usar OCR
            with tempfile.TemporaryDirectory() as temp_dir:
                # Converter PDF para imagens
                imagens = convert_from_path(caminho_pdf, 300)
                
                # Salvar imagens para visualização
                st.session_state.pdf_images = imagens
                
                texto_completo = ""
                for i, imagem in enumerate(imagens):
                    # Salvar imagem temporariamente
                    caminho_imagem = os.path.join(temp_dir, f'pagina_{i+1}.png')
                    imagem.save(caminho_imagem, 'PNG')
                    
                    # Processar imagem para melhorar OCR
                    img = cv2.imread(caminho_imagem)
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
                    
                    # Extrair texto com OCR
                    texto = pytesseract.image_to_string(thresh)
                    texto_completo += texto + "\n\n"
                    
                    logger.info(f"OCR concluído para página {i+1}")
                
                return texto_completo
                
        except Exception as e:
            logger.error(f"Erro ao extrair texto com OCR: {str(e)}")
            # Tentar método alternativo com PyPDF2
            try:
                import PyPDF2
                with open(caminho_pdf, 'rb') as file:
                    reader = PyPDF2.PdfReader(file)
                    texto_completo = ""
                    for page in reader.pages:
                        texto_completo += page.extract_text() + "\n\n"
                    return texto_completo
            except Exception as e2:
                logger.error(f"Erro ao extrair texto com PyPDF2: {str(e2)}")
                return ""
    
    def detectar_tipo_documento(self, texto, caminho_pdf):
        """
        Detecta o tipo de documento com base no texto extraído e nome do arquivo
        
        Args:
            texto (str): Texto extraído do PDF
            caminho_pdf (str): Caminho do arquivo PDF
            
        Returns:
            str: Tipo de documento detectado
        """
        # Palavras-chave para cada tipo de documento
        keywords = {
            "cuenta_ventas_finobrasa": ["CUENTA DE VENTAS", "FINOBRASA", "LLEGADA", "CALIBRE", "FORMATO"],
            "accountsale_cgh": ["Accountsale", "CGH", "Carl Gottmann", "Handelmaatschappij"],
            "accountsale_natures_pride": ["Nature's Pride", "Accountsale", "Specification Costs"],
            "liquidacion_cultipalta": ["Liquidación", "CULTIPALTA", "MANGO PALMER", "FACTURACIÓN FINAL"],
            "settlement_report": ["Settlement Report", "Robinson Fresh", "Grand Total", "Currency Rate"]
        }
        
        # Verificar nome do arquivo para contêiner
        nome_arquivo = os.path.basename(caminho_pdf).upper()
        container_match = re.search(r'([A-Z]{4}\d{7})', nome_arquivo)
        container_no = container_match.group(1) if container_match else ""
        
        # Contar ocorrências de palavras-chave para cada tipo
        scores = {}
        for doc_type, words in keywords.items():
            score = sum(1 for word in words if word.lower() in texto.lower())
            scores[doc_type] = score
        
        # Determinar o tipo com maior pontuação
        max_score = 0
        detected_type = "desconhecido"
        
        for doc_type, score in scores.items():
            if score > max_score:
                max_score = score
                detected_type = doc_type
        
        return detected_type
    
    def extrair_com_ocr_e_regex(self, texto, tipo_doc, caminho_pdf):
        """
        Extrai dados do texto usando expressões regulares específicas para cada tipo de documento
        
        Args:
            texto (str): Texto extraído do PDF
            tipo_doc (str): Tipo de documento detectado
            caminho_pdf (str): Caminho do arquivo PDF
            
        Returns:
            dict: Dicionário com os dados extraídos
        """
        logger.info(f"Extraindo dados com regex para documento do tipo {tipo_doc}")
        
        # Inicializar estrutura de dados
        dados_extraidos = {
            "dados_principais": self.estrutura_padrao["dados_principais"].copy(),
            "produtos": [],
            "metodo_extracao": "ocr_regex"
        }
        
        # Extrair número do contêiner do nome do arquivo
        nome_arquivo = os.path.basename(caminho_pdf).upper()
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
        # Criar um thread
        thread = self.openai_client.beta.threads.create()
        logger.info(f"Thread criado: {thread.id}")
        
        # Preparar mensagem com instruções
        instrucoes = """
        Extraia os seguintes dados do PDF:
        
        1. Dados principais:
           - Nome da empresa
           - Número do contêiner
           - Comissão %
           - Comissão Valor
           - Valor total
           - Net Amount
           - Moeda
        
        2. Lista de produtos, cada um com:
           - tipo
           - tamanho
           - quantidade
           - preço unitário
           - preço total
           - moeda
           - referencia
           - currency_rate
        
        Retorne os dados em formato JSON seguindo exatamente esta estrutura:
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
            ],
            "metodo_extracao": "openai"
        }
        """
        
        # Adicionar mensagem ao thread
        self.openai_client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=instrucoes
        )
        
        # Enviar o arquivo PDF
        with open(caminho_pdf, "rb") as file:
            file_data = file.read()
        
        file_obj = self.openai_client.files.create(
            file=io.BytesIO(file_data),
            purpose="assistants"
        )
        
        # Adicionar mensagem com o arquivo
        try:
            # Tentar com file_ids (versão mais recente)
            self.openai_client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content="Aqui está o PDF para extração de dados.",
                file_ids=[file_obj.id]
            )
        except Exception as e:
            logger.warning(f"Erro ao usar file_ids: {str(e)}")
            # Alternativa: adicionar mensagem sem arquivo e mencionar o ID do arquivo
            self.openai_client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=f"Aqui está o PDF para extração de dados. Use o arquivo com ID: {file_obj.id}"
            )
        
        # Executar o assistente
        run = self.openai_client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=self.assistant_id
        )
        
        # Aguardar a conclusão
        while True:
            run_status = self.openai_client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )
            
            if run_status.status == "completed":
                break
            elif run_status.status in ["failed", "cancelled", "expired"]:
                logger.error(f"Execução falhou com status: {run_status.status}")
                return None
            
            time.sleep(1)
        
        # Obter as mensagens
        messages = self.openai_client.beta.threads.messages.list(
            thread_id=thread.id
        )
        
        # Extrair a resposta JSON
        for message in messages.data:
            if message.role == "assistant":
                for content in message.content:
                    if content.type == "text":
                        # Tentar extrair JSON da resposta
                        texto_resposta = content.text.value
                        try:
                            # Procurar por JSON na resposta
                            json_match = re.search(r'```json\s*(.*?)\s*```', texto_resposta, re.DOTALL)
                            if json_match:
                                json_str = json_match.group(1)
                            else:
                                # Tentar encontrar JSON sem marcadores de código
                                json_match = re.search(r'({.*})', texto_resposta, re.DOTALL)
                                if json_match:
                                    json_str = json_match.group(1)
                                else:
                                    json_str = texto_resposta
                            
                            dados = json.loads(json_str)
                            
                            # Verificar se a estrutura está correta
                            if "dados_principais" in dados and "produtos" in dados:
                                logger.info("Dados extraídos com sucesso via OpenAI")
                                
                                # Adicionar método de extração
                                dados["metodo_extracao"] = "openai"
                                
                                return dados
                        except Exception as e:
                            logger.error(f"Erro ao processar resposta JSON: {str(e)}")
                            logger.error(f"Resposta recebida: {texto_resposta}")
        
        logger.error("Não foi possível extrair dados JSON da resposta")
        return None
    
    def _extrair_com_openai_v0(self, caminho_pdf, texto_pdf=None):
        """
        Extrai dados do PDF usando o assistente OpenAI (API v0.x)
        
        Args:
            caminho_pdf (str): Caminho para o arquivo PDF
            texto_pdf (str, optional): Texto já extraído do PDF
            
        Returns:
            dict: Dicionário com os dados extraídos
        """
        # Na API antiga, não há suporte direto para assistentes com arquivos
        # Vamos usar o GPT-4 diretamente com o texto extraído
        
        if not texto_pdf:
            texto_pdf = self.extrair_texto_com_ocr(caminho_pdf)
        
        # Preparar prompt
        prompt = f"""
        Extraia os seguintes dados do PDF cujo texto está abaixo:
        
        1. Dados principais:
           - Nome da empresa
           - Número do contêiner
           - Comissão %
           - Comissão Valor
           - Valor total
           - Net Amount
           - Moeda
        
        2. Lista de produtos, cada um com:
           - tipo
           - tamanho
           - quantidade
           - preço unitário
           - preço total
           - moeda
           - referencia
           - currency_rate
        
        Retorne os dados em formato JSON seguindo exatamente esta estrutura:
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
            ],
            "metodo_extracao": "openai"
        }}
        
        Texto do PDF:
        {texto_pdf}
        """
        
        # Fazer chamada à API
        try:
            response = self.openai_client.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Você é um assistente especializado em extrair dados estruturados de PDFs."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            
            # Extrair resposta
            resposta = response.choices[0].message.content
            
            # Tentar extrair JSON da resposta
            try:
                # Procurar por JSON na resposta
                json_match = re.search(r'```json\s*(.*?)\s*```', resposta, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    # Tentar encontrar JSON sem marcadores de código
                    json_match = re.search(r'({.*})', resposta, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(1)
                    else:
                        json_str = resposta
                
                dados = json.loads(json_str)
                
                # Verificar se a estrutura está correta
                if "dados_principais" in dados and "produtos" in dados:
                    logger.info("Dados extraídos com sucesso via OpenAI (API v0)")
                    
                    # Adicionar método de extração
                    dados["metodo_extracao"] = "openai"
                    
                    return dados
            except Exception as e:
                logger.error(f"Erro ao processar resposta JSON: {str(e)}")
                logger.error(f"Resposta recebida: {resposta}")
        
        except Exception as e:
            logger.error(f"Erro na chamada à API OpenAI: {str(e)}")
        
        return None

# Função para exibir PDF
def display_pdf(pdf_file):
    """
    Exibe o PDF na interface
    
    Args:
        pdf_file: Arquivo PDF carregado via Streamlit
    """
    try:
        # Salvar o arquivo temporariamente
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_file.write(pdf_file.getvalue())
            temp_path = temp_file.name
        
        # Converter PDF para imagens
        try:
            from pdf2image import convert_from_path
            images = convert_from_path(temp_path, 300)
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
            base64_pdf = base64.b64encode(pdf_file.getvalue()).decode('utf-8')
            pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
            st.markdown(pdf_display, unsafe_allow_html=True)
        
        # Limpar arquivo temporário
        os.unlink(temp_path)
        
    except Exception as e:
        logger.error(f"Erro ao exibir PDF: {str(e)}")
        logger.error(traceback.format_exc())
        st.error(f"Erro ao exibir o PDF: {str(e)}")

# Função para processar o PDF
def process_pdf(pdf_file, api_key=None, assistant_id=None, metodo="auto"):
    try:
        logger.info(f"Processando PDF: {pdf_file.name} com método: {metodo}")
        
        # Salvar o arquivo temporariamente
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_file.write(pdf_file.getvalue())
            temp_path = temp_file.name
        
        # Inicializar o extrator
        extrator = PDFExtractor(api_key=api_key, assistant_id=assistant_id)
        
        # Extrair dados
        dados = extrator.extrair_dados(temp_path, metodo)
        
        # Armazenar dados na sessão
        st.session_state.pdf_data = dados
        st.session_state.pdf_name = pdf_file.name
        st.session_state.pdf_path = temp_path
        st.session_state.pdf_content = pdf_file
        
        # Adicionar à história de extrações
        st.session_state.extraction_history.append({
            "pdf_name": pdf_file.name,
            "extraction_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "extraction_method": dados.get("metodo_extracao", metodo),
            "data": dados
        })
        
        # Exibir PDF
        display_pdf(pdf_file)
        
        logger.info(f"PDF processado com sucesso: {pdf_file.name}")
        return dados
        
    except Exception as e:
        logger.error(f"Erro ao processar PDF: {str(e)}")
        logger.error(traceback.format_exc())
        st.error(f"Erro ao processar o PDF: {str(e)}")
        return None

# Função para criar um assistente OpenAI
def create_openai_assistant(api_key, name="Extrator de PDFs", instructions=None):
    """
    Cria um novo assistente OpenAI para extração de PDFs
    
    Args:
        api_key (str): Chave de API da OpenAI
        name (str): Nome do assistente
        instructions (str): Instruções para o assistente
        
    Returns:
        str: ID do assistente criado
    """
    try:
        # Inicializar cliente OpenAI
        import openai
        
        # Instruções padrão se não fornecidas
        if not instructions:
            instructions = """
            Você é um assistente especializado em extrair dados estruturados de PDFs de documentos comerciais.
            
            Sua tarefa é analisar PDFs e extrair informações específicas como:
            
            1. Dados principais:
               - Nome da empresa
               - Número do contêiner
               - Comissão %
               - Comissão Valor
               - Valor total
               - Net Amount
               - Moeda
            
            2. Lista de produtos, cada um com:
               - tipo
               - tamanho
               - quantidade
               - preço unitário
               - preço total
               - moeda
               - referencia
               - currency_rate
            
            Você deve retornar os dados em formato JSON seguindo exatamente a estrutura solicitada.
            Seja preciso na extração e mantenha os valores originais (números, moedas, etc.).
            Quando um campo não estiver presente no documento, deixe-o vazio.
            """
        
        # Verificar versão da API OpenAI
        if is_new_api:
            # Nova API (v1.0+)
            client = openai.OpenAI(api_key=api_key)
            
            # Criar o assistente
            assistant = client.beta.assistants.create(
                name=name,
                instructions=instructions,
                model="gpt-4-turbo",
                tools=[{"type": "file_search"}]
            )
            
            logger.info(f"Assistente criado com ID: {assistant.id}")
            return assistant.id
        else:
            # API antiga (v0.x)
            # Não há suporte direto para assistentes na API antiga
            # Retornar um ID fictício para fins de compatibilidade
            logger.warning("API OpenAI v0.x não suporta assistentes. Usando GPT-4 diretamente.")
            return "gpt-4-direct"
    
    except Exception as e:
        logger.error(f"Erro ao criar assistente OpenAI: {str(e)}")
        logger.error(traceback.format_exc())
        st.error(f"Erro ao criar assistente OpenAI: {str(e)}")
        return None

# Função para treinar o assistente OpenAI com PDFs
def train_openai_assistant(api_key, assistant_id, pdf_file, feedback=None):
    """
    Treina o assistente OpenAI com um PDF e feedback opcional
    
    Args:
        api_key (str): Chave de API da OpenAI
        assistant_id (str): ID do assistente
        pdf_file: Arquivo PDF
        feedback (dict, optional): Feedback para melhorar a extração
        
    Returns:
        bool: True se o treinamento foi bem-sucedido
    """
    try:
        # Inicializar cliente OpenAI
        import openai
        
        # Verificar versão da API OpenAI
        if is_new_api:
            # Nova API (v1.0+)
            client = openai.OpenAI(api_key=api_key)
            
            # Criar um thread
            thread = client.beta.threads.create()
            
            # Salvar o arquivo temporariamente
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                temp_file.write(pdf_file.getvalue())
                temp_path = temp_file.name
            
            # Enviar o arquivo PDF
            with open(temp_path, "rb") as file:
                file_data = file.read()
            
            file_obj = client.files.create(
                file=io.BytesIO(file_data),
                purpose="assistants"
            )
            
            # Adicionar mensagem com o arquivo
            try:
                # Tentar com file_ids (versão mais recente)
                client.beta.threads.messages.create(
                    thread_id=thread.id,
                    role="user",
                    content="Este é um exemplo de PDF para você aprender a extrair dados.",
                    file_ids=[file_obj.id]
                )
            except Exception as e:
                logger.warning(f"Erro ao usar file_ids: {str(e)}")
                # Alternativa: adicionar mensagem sem arquivo e mencionar o ID do arquivo
                client.beta.threads.messages.create(
                    thread_id=thread.id,
                    role="user",
                    content=f"Este é um exemplo de PDF para você aprender a extrair dados. Use o arquivo com ID: {file_obj.id}"
                )
            
            # Se houver feedback, adicionar como mensagem
            if feedback:
                feedback_json = json.dumps(feedback, indent=2)
                client.beta.threads.messages.create(
                    thread_id=thread.id,
                    role="user",
                    content=f"Aqui está a extração correta para este PDF. Use isso para melhorar suas extrações futuras:\n\n```json\n{feedback_json}\n```"
                )
            
            # Executar o assistente
            run = client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=assistant_id
            )
            
            # Aguardar a conclusão
            while True:
                run_status = client.beta.threads.runs.retrieve(
                    thread_id=thread.id,
                    run_id=run.id
                )
                
                if run_status.status == "completed":
                    break
                elif run_status.status in ["failed", "cancelled", "expired"]:
                    logger.error(f"Execução falhou com status: {run_status.status}")
                    return False
                
                time.sleep(1)
            
            # Limpar arquivo temporário
            os.unlink(temp_path)
            
            logger.info(f"Assistente treinado com sucesso")
            return True
        
        else:
            # API antiga (v0.x)
            # Não há suporte direto para assistentes na API antiga
            # Simular treinamento bem-sucedido para fins de compatibilidade
            logger.warning("API OpenAI v0.x não suporta treinamento de assistentes. Simulando treinamento.")
            return True
    
    except Exception as e:
        logger.error(f"Erro ao treinar assistente OpenAI: {str(e)}")
        logger.error(traceback.format_exc())
        st.error(f"Erro ao treinar assistente OpenAI: {str(e)}")
        return False

# Página principal
def page_main():
    st.title("Extrator Inteligente de PDFs com OpenAI")
    
    # Conteúdo principal
    if st.session_state.pdf_data:
        # Exibir dados extraídos
        st.header(f"Dados Extraídos: {st.session_state.pdf_name}")
        
        # Exibir método de extração
        metodo = st.session_state.pdf_data.get("metodo_extracao", "desconhecido")
        st.info(f"Método de extração: {metodo}")
        
        # Exibir PDF
        if st.session_state.pdf_content:
            st.subheader("Visualização do PDF")
            display_pdf(st.session_state.pdf_content)
        
        # Exibir dados principais
        st.subheader("Dados Principais")
        
        # Criar colunas para melhor visualização
        col1, col2 = st.columns(2)
        
        with col1:
            for campo, valor in st.session_state.pdf_data["dados_principais"].items():
                st.text_input(campo, value=valor, key=f"main_{campo}")
        
        # Exibir produtos em tabela editável
        st.subheader("Produtos")
        
        if st.session_state.pdf_data["produtos"]:
            # Converter para DataFrame
            produtos_df = pd.DataFrame(st.session_state.pdf_data["produtos"])
            
            # Exibir tabela editável
            edited_df = st.data_editor(
                produtos_df,
                num_rows="dynamic",
                key="product_editor"
            )
            
            # Atualizar dados na sessão
            produtos_atualizados = []
            for i, row in edited_df.iterrows():
                produto = {}
                for col in row.index:
                    produto[col] = row[col]
                produtos_atualizados.append(produto)
            
            st.session_state.pdf_data["produtos"] = produtos_atualizados
        else:
            st.warning("Nenhum produto encontrado.")
        
        # Opções para treinar o assistente
        if st.session_state.api_key and st.session_state.assistant_id:
            st.subheader("Treinar Assistente")
            
            if st.button("Treinar Assistente com Este PDF e Correções"):
                with st.spinner("Treinando assistente..."):
                    success = train_openai_assistant(
                        api_key=st.session_state.api_key,
                        assistant_id=st.session_state.assistant_id,
                        pdf_file=st.session_state.pdf_content,
                        feedback=st.session_state.pdf_data
                    )
                    
                    if success:
                        st.success("Assistente treinado com sucesso!")
                    else:
                        st.error("Erro ao treinar assistente.")
        
        # Exportar dados
        st.subheader("Exportar Dados")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Exportar como JSON"):
                json_str = json.dumps(st.session_state.pdf_data, indent=2)
                st.download_button(
                    label="Baixar JSON",
                    data=json_str,
                    file_name=f"{st.session_state.pdf_name.replace('.pdf', '')}_dados.json",
                    mime="application/json"
                )
        
        with col2:
            if st.button("Exportar como CSV"):
                # Preparar dados para CSV
                dados_principais = st.session_state.pdf_data["dados_principais"]
                produtos = st.session_state.pdf_data["produtos"]
                
                # Criar DataFrame para produtos
                produtos_df = pd.DataFrame(produtos)
                
                # Adicionar dados principais como colunas
                for campo, valor in dados_principais.items():
                    produtos_df[f"principal_{campo}"] = valor
                
                # Converter para CSV
                csv = produtos_df.to_csv(index=False)
                
                st.download_button(
                    label="Baixar CSV",
                    data=csv,
                    file_name=f"{st.session_state.pdf_name.replace('.pdf', '')}_dados.csv",
                    mime="text/csv"
                )
    
    else:
        st.info("Carregue um PDF para começar a extração.")

# Página de configuração do assistente OpenAI
def page_openai_config():
    st.title("Configuração do Assistente OpenAI")
    
    # Informação sobre versão da API
    st.info(f"Versão da API OpenAI detectada: {'v1.0+' if is_new_api else 'v0.x'}")
    
    if not is_new_api:
        st.warning("""
        Você está usando uma versão antiga da API OpenAI (v0.x) que não suporta assistentes.
        
        O programa usará o GPT-4 diretamente para extração, sem recursos de assistentes.
        
        Para usar todas as funcionalidades, atualize a biblioteca OpenAI:
        ```
        pip install --upgrade openai>=1.0.0
        ```
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
    
    if not is_new_api:
        st.info("Na versão v0.x da API, não é possível criar assistentes. O programa usará o GPT-4 diretamente.")
    
    with st.form("create_assistant_form"):
        assistant_name = st.text_input("Nome do Assistente", value="Extrator de PDFs")
        
        assistant_instructions = st.text_area(
            "Instruções para o Assistente",
            value="""
            Você é um assistente especializado em extrair dados estruturados de PDFs de documentos comerciais.
            
            Sua tarefa é analisar PDFs e extrair informações específicas como:
            
            1. Dados principais:
               - Nome da empresa
               - Número do contêiner
               - Comissão %
               - Comissão Valor
               - Valor total
               - Net Amount
               - Moeda
            
            2. Lista de produtos, cada um com:
               - tipo
               - tamanho
               - quantidade
               - preço unitário
               - preço total
               - moeda
               - referencia
               - currency_rate
            
            Você deve retornar os dados em formato JSON seguindo exatamente a estrutura solicitada.
            Seja preciso na extração e mantenha os valores originais (números, moedas, etc.).
            Quando um campo não estiver presente no documento, deixe-o vazio.
            """
        )
        
        submit_button = st.form_submit_button("Criar Assistente")
        
        if submit_button:
            if not api_key:
                st.error("Por favor, configure a chave da API primeiro.")
            else:
                with st.spinner("Criando assistente..."):
                    new_assistant_id = create_openai_assistant(
                        api_key=api_key,
                        name=assistant_name,
                        instructions=assistant_instructions
                    )
                    
                    if new_assistant_id:
                        st.session_state.assistant_id = new_assistant_id
                        st.success(f"Assistente criado com sucesso! ID: {new_assistant_id}")
                    else:
                        st.error("Erro ao criar assistente.")
    
    # Testar conexão
    st.subheader("Testar Conexão")
    
    if st.button("Testar Conexão com OpenAI"):
        if not api_key:
            st.error("Por favor, configure a chave da API primeiro.")
        else:
            try:
                import openai
                
                if is_new_api:
                    # Nova API (v1.0+)
                    client = openai.OpenAI(api_key=api_key)
                    
                    # Testar com uma chamada simples
                    models = client.models.list()
                else:
                    # API antiga (v0.x)
                    openai.api_key = api_key
                    
                    # Testar com uma chamada simples
                    models = openai.Model.list()
                
                st.success("Conexão com OpenAI estabelecida com sucesso!")
                
                # Verificar assistente se ID fornecido
                if assistant_id and is_new_api:
                    try:
                        assistant = client.beta.assistants.retrieve(assistant_id)
                        st.success(f"Assistente encontrado: {assistant.name}")
                    except:
                        st.warning("Não foi possível encontrar o assistente com o ID fornecido.")
            
            except Exception as e:
                st.error(f"Erro ao conectar com OpenAI: {str(e)}")

# Página de histórico de extrações
def page_history():
    st.title("Histórico de Extrações")
    
    if not st.session_state.extraction_history:
        st.info("Nenhuma extração realizada ainda.")
        return
    
    # Exibir histórico em tabela
    history_data = []
    for i, entry in enumerate(st.session_state.extraction_history):
        history_data.append({
            "ID": i + 1,
            "PDF": entry["pdf_name"],
            "Data": entry["extraction_date"],
            "Método": entry["extraction_method"],
            "Produtos": len(entry["data"]["produtos"])
        })
    
    st.dataframe(pd.DataFrame(history_data))
    
    # Selecionar entrada para visualizar detalhes
    selected_id = st.selectbox(
        "Selecione uma extração para ver detalhes:",
        options=[i + 1 for i in range(len(st.session_state.extraction_history))],
        format_func=lambda x: f"{x}. {st.session_state.extraction_history[x-1]['pdf_name']} ({st.session_state.extraction_history[x-1]['extraction_date']})"
    )
    
    if selected_id:
        entry = st.session_state.extraction_history[selected_id - 1]
        
        st.subheader(f"Detalhes da Extração: {entry['pdf_name']}")
        
        # Exibir método
        st.info(f"Método de extração: {entry['extraction_method']}")
        
        # Exibir dados principais
        st.subheader("Dados Principais")
        
        for campo, valor in entry["data"]["dados_principais"].items():
            st.text_input(campo, value=valor, key=f"history_{selected_id}_{campo}", disabled=True)
        
        # Exibir produtos
        st.subheader("Produtos")
        
        if entry["data"]["produtos"]:
            st.dataframe(pd.DataFrame(entry["data"]["produtos"]))
        else:
            st.warning("Nenhum produto encontrado.")
        
        # Exportar dados
        st.subheader("Exportar Dados")
        
        col1, col2 = st.columns(2)
        
        with col1:
            json_str = json.dumps(entry["data"], indent=2)
            st.download_button(
                label="Baixar JSON",
                data=json_str,
                file_name=f"{entry['pdf_name'].replace('.pdf', '')}_dados.json",
                mime="application/json"
            )
        
        with col2:
            # Preparar dados para CSV
            dados_principais = entry["data"]["dados_principais"]
            produtos = entry["data"]["produtos"]
            
            if produtos:
                # Criar DataFrame para produtos
                produtos_df = pd.DataFrame(produtos)
                
                # Adicionar dados principais como colunas
                for campo, valor in dados_principais.items():
                    produtos_df[f"principal_{campo}"] = valor
                
                # Converter para CSV
                csv = produtos_df.to_csv(index=False)
                
                st.download_button(
                    label="Baixar CSV",
                    data=csv,
                    file_name=f"{entry['pdf_name'].replace('.pdf', '')}_dados.csv",
                    mime="text/csv"
                )

# Página de guia do assistente OpenAI
def page_openai_guide():
    st.title("Guia do Assistente OpenAI para Extração de PDFs")
    
    # Informação sobre versão da API
    st.info(f"Versão da API OpenAI detectada: {'v1.0+' if is_new_api else 'v0.x'}")
    
    if not is_new_api:
        st.warning("""
        Você está usando uma versão antiga da API OpenAI (v0.x) que não suporta assistentes.
        
        Para usar todas as funcionalidades, atualize a biblioteca OpenAI:
        ```
        pip install --upgrade openai>=1.0.0
        ```
        """)
    
    st.markdown("""
    ## Como Criar e Treinar um Assistente OpenAI para Extração de PDFs
    
    Este guia explica como configurar e treinar um assistente OpenAI para extrair dados de PDFs com aprendizado contínuo.
    
    ### 1. Criar uma Conta na OpenAI
    
    Se você ainda não tem uma conta na OpenAI:
    
    1. Acesse [platform.openai.com](https://platform.openai.com)
    2. Clique em "Sign up" e siga as instruções
    3. Complete a verificação e configure o método de pagamento
    
    ### 2. Obter uma Chave de API
    
    Para usar a API da OpenAI:
    
    1. Faça login na [plataforma da OpenAI](https://platform.openai.com)
    2. Clique em seu perfil no canto superior direito
    3. Selecione "API keys"
    4. Clique em "Create new secret key"
    5. Dê um nome à sua chave e copie-a (ela só será mostrada uma vez)
    
    ### 3. Criar um Assistente
    
    Você pode criar um assistente de duas formas:
    
    #### Opção 1: Usando a Interface da OpenAI
    
    1. Acesse [platform.openai.com/assistants](https://platform.openai.com/assistants)
    2. Clique em "Create"
    3. Configure seu assistente:
       - Nome: "Extrator de PDFs"
       - Instruções: Copie as instruções abaixo
       - Modelo: GPT-4 Turbo ou GPT-4o
       - Habilite a ferramenta "Retrieval" para processamento de arquivos
    4. Copie o ID do assistente (encontrado na URL ou nas configurações)
    
    #### Opção 2: Usando Este Aplicativo
    
    1. Vá para a página "Configuração do Assistente OpenAI"
    2. Insira sua chave de API
    3. Preencha o nome e as instruções (ou use os valores padrão)
    4. Clique em "Criar Assistente"
    
    ### 4. Instruções Recomendadas para o Assistente
    
    ```
    Você é um assistente especializado em extrair dados estruturados de PDFs de documentos comerciais.
    
    Sua tarefa é analisar PDFs e extrair informações específicas como:
    
    1. Dados principais:
       - Nome da empresa
       - Número do contêiner
       - Comissão %
       - Comissão Valor
       - Valor total
       - Net Amount
       - Moeda
    
    2. Lista de produtos, cada um com:
       - tipo
       - tamanho
       - quantidade
       - preço unitário
       - preço total
       - moeda
       - referencia
       - currency_rate
    
    Você deve retornar os dados em formato JSON seguindo exatamente a estrutura solicitada.
    Seja preciso na extração e mantenha os valores originais (números, moedas, etc.).
    Quando um campo não estiver presente no documento, deixe-o vazio.
    ```
    
    ### 5. Treinar o Assistente
    
    O treinamento do assistente ocorre naturalmente à medida que você:
    
    1. Carrega PDFs para extração
    2. Corrige os dados extraídos quando necessário
    3. Usa o botão "Treinar Assistente com Este PDF e Correções"
    
    Cada vez que você treina o assistente com correções, ele aprende a extrair melhor os dados de PDFs similares no futuro.
    
    ### 6. Processo de Aprendizado Contínuo
    
    O aprendizado contínuo funciona assim:
    
    1. **Extração inicial**: O assistente extrai dados do PDF usando seu conhecimento atual
    2. **Correção humana**: Você corrige quaisquer erros nos dados extraídos
    3. **Feedback**: Você envia as correções de volta ao assistente
    4. **Aprendizado**: O assistente aprende com suas correções
    5. **Melhoria contínua**: Com o tempo, o assistente se torna mais preciso para seus tipos específicos de documentos
    
    ### 7. Dicas para Melhores Resultados
    
    - **Comece com PDFs claros**: PDFs digitais são melhores que escaneados
    - **Treine com exemplos variados**: Inclua diferentes formatos e layouts
    - **Seja consistente nas correções**: Use o mesmo formato para dados similares
    - **Treine regularmente**: Quanto mais exemplos, melhor o aprendizado
    - **Verifique os resultados**: Mesmo após treinamento, sempre verifique a precisão
    
    ### 8. Considerações de Custo
    
    O uso da API da OpenAI tem custos baseados no modelo usado e no volume de tokens:
    
    - GPT-4 Turbo: $0.01/1K tokens de entrada, $0.03/1K tokens de saída
    - Armazenamento de arquivos: $0.20/GB por mês
    
    Para controlar custos:
    
    1. Monitore seu uso na [plataforma da OpenAI](https://platform.openai.com/usage)
    2. Configure limites de gastos em [platform.openai.com/settings/billing/limits](https://platform.openai.com/settings/billing/limits)
    3. Use o método de extração OCR para PDFs simples quando possível
    """)

# Interface principal
def main():
    # Barra lateral
    with st.sidebar:
        st.header("Configurações")
        
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
            options=["auto", "ocr", "openai"],
            index=0,
            help="Auto: tenta OpenAI primeiro, recorre a OCR se falhar. OCR: usa apenas OCR e regex. OpenAI: usa apenas o assistente OpenAI."
        )
        
        st.session_state.extraction_method = extraction_method
        
        # Botão de processamento
        if st.button("Processar PDF"):
            if pdf_file:
                with st.spinner("Processando PDF..."):
                    process_pdf(
                        pdf_file,
                        api_key=st.session_state.api_key,
                        assistant_id=st.session_state.assistant_id,
                        metodo=st.session_state.extraction_method
                    )
                    st.session_state.page = "main"
            else:
                st.warning("Por favor, selecione um arquivo PDF.")
        
        # Modo de debug
        st.session_state.debug_mode = st.checkbox("Modo de Debug", value=st.session_state.debug_mode)
        
        # Navegação
        st.subheader("Navegação")
        
        if st.button("Página Principal"):
            st.session_state.page = "main"
            st.experimental_rerun()
        
        if st.button("Configuração do Assistente OpenAI"):
            st.session_state.page = "openai_config"
            st.experimental_rerun()
        
        if st.button("Histórico de Extrações"):
            st.session_state.page = "history"
            st.experimental_rerun()
        
        if st.button("Guia do Assistente OpenAI"):
            st.session_state.page = "openai_guide"
            st.experimental_rerun()
    
    # Conteúdo principal com base na página atual
    if st.session_state.page == "main":
        page_main()
    elif st.session_state.page == "openai_config":
        page_openai_config()
    elif st.session_state.page == "history":
        page_history()
    elif st.session_state.page == "openai_guide":
        page_openai_guide()
    
    # Modo de debug
    if st.session_state.debug_mode:
        st.header("Informações de Debug")
        
        # Estado da sessão
        with st.expander("Estado da Sessão", expanded=True):
            # Converter objetos complexos para string para evitar erro de serialização
            session_dict = {}
            for k, v in st.session_state.items():
                if isinstance(v, pd.DataFrame):
                    session_dict[k] = "DataFrame"
                elif isinstance(v, Image.Image):
                    session_dict[k] = "Image"
                elif k == "pdf_images":
                    session_dict[k] = f"Lista com {len(v)} imagens" if v else "Vazio"
                elif k == "pdf_content":
                    session_dict[k] = "PDF Content" if v else "Vazio"
                elif k == "pdf_text":
                    session_dict[k] = f"Texto com {len(v)} caracteres" if v else "Vazio"
                else:
                    session_dict[k] = v
            
            st.json(session_dict)
        
        # Informações sobre a versão da OpenAI
        with st.expander("Informações da API OpenAI", expanded=True):
            st.write(f"**Versão da API OpenAI:** {'v1.0+' if is_new_api else 'v0.x'}")
            
            try:
                import openai
                openai_version = pkg_resources.get_distribution("openai").version
                st.write(f"**Versão da biblioteca OpenAI:** {openai_version}")
            except:
                st.write("**Versão da biblioteca OpenAI:** Não detectada")
        
        # Texto extraído do PDF
        if st.session_state.pdf_text:
            with st.expander("Texto Extraído do PDF", expanded=False):
                st.text_area("Texto", value=st.session_state.pdf_text, height=300)
        
        # Logs
        with st.expander("Logs", expanded=False):
            try:
                with open("app.log", "r") as log_file:
                    logs = log_file.readlines()
                    st.code("".join(logs[-50:]))  # Mostrar últimas 50 linhas
            except Exception as e:
                st.error(f"Erro ao ler logs: {str(e)}")

if __name__ == "__main__":
    main()
