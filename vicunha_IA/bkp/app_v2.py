import streamlit as st
import os
import json
import re
import tempfile
import cv2
import numpy as np
from PIL import Image
import pytesseract
from pdf2image import convert_from_path
import base64
import logging
import sys
import io

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ExtratorPDF:
    def __init__(self, api_key=None):
        """
        Inicializa o extrator de PDF com opção de API key para OpenAI
        
        Args:
            api_key (str, optional): Chave de API da OpenAI
        """
        self.api_key = api_key
        if api_key:
            # Importar openai apenas se a chave for fornecida
            try:
                import openai
                openai.api_key = api_key
                self.openai = openai
                logger.info("API OpenAI configurada")
            except ImportError:
                st.warning("Biblioteca OpenAI não encontrada. Instalando...")
                os.system("pip install openai")
                import openai
                openai.api_key = api_key
                self.openai = openai
                logger.info("API OpenAI configurada após instalação")
        else:
            self.openai = None
        
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
    
    def extrair_dados(self, arquivo_pdf):
        """
        Extrai dados de um PDF usando múltiplas técnicas
        
        Args:
            arquivo_pdf: Arquivo PDF carregado via Streamlit
            
        Returns:
            dict: Dicionário com os dados extraídos
        """
        logger.info(f"Iniciando extração do PDF")
        
        # Inicializar estrutura de dados
        dados_extraidos = {
            "dados_principais": self.estrutura_padrao["dados_principais"].copy(),
            "produtos": []
        }
        
        # Salvar o arquivo temporariamente
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
            temp_pdf.write(arquivo_pdf.getvalue())
            temp_pdf_path = temp_pdf.name
        
        try:
            # Extrair texto com OCR
            texto_ocr = self.extrair_texto_com_ocr(temp_pdf_path)
            
            # Detectar idioma e tipo de documento
            idioma, tipo_doc = self.detectar_idioma_e_tipo(texto_ocr)
            logger.info(f"Idioma detectado: {idioma}, Tipo de documento: {tipo_doc}")
            
            # Se temos API key da OpenAI, usar para extrair dados estruturados
            if self.openai:
                logger.info("Usando OpenAI para extrair dados estruturados")
                try:
                    dados = self.extrair_com_openai(temp_pdf_path, texto_ocr, idioma, tipo_doc)
                    os.unlink(temp_pdf_path)  # Remover arquivo temporário
                    return dados
                except Exception as e:
                    logger.error(f"Erro ao processar com OpenAI: {str(e)}")
                    logger.info("Recorrendo ao método de OCR com regex")
                    dados = self.extrair_com_ocr_e_regex(texto_ocr, idioma, tipo_doc)
                    os.unlink(temp_pdf_path)  # Remover arquivo temporário
                    return dados
            else:
                logger.info("Usando OCR e processamento de texto para extrair dados")
                dados = self.extrair_com_ocr_e_regex(texto_ocr, idioma, tipo_doc)
                os.unlink(temp_pdf_path)  # Remover arquivo temporário
                return dados
        except Exception as e:
            logger.error(f"Erro ao extrair dados: {str(e)}")
            os.unlink(temp_pdf_path)  # Remover arquivo temporário
            return dados_extraidos
    
    def detectar_idioma_e_tipo(self, texto):
        """
        Detecta o idioma e tipo de documento com base no texto extraído
        
        Args:
            texto (str): Texto extraído do PDF
            
        Returns:
            tuple: (idioma, tipo_documento)
        """
        # Palavras-chave em espanhol
        palavras_espanhol = ["CUENTA DE VENTAS", "FACTURADOS", "LLEGADOS", "PRECIO", "PAGAR", "RESULTADO", "CONTENEDOR"]
        # Palavras-chave em inglês
        palavras_ingles = ["Settlement Report", "Grand Total", "Currency Rate", "Sum of", "Container Arrival date"]
        
        # Contar ocorrências
        count_espanhol = sum(1 for palavra in palavras_espanhol if palavra.lower() in texto.lower())
        count_ingles = sum(1 for palavra in palavras_ingles if palavra.lower() in texto.lower())
        
        # Determinar idioma
        idioma = "espanhol" if count_espanhol > count_ingles else "ingles"
        
        # Determinar tipo de documento
        if "CUENTA DE VENTAS" in texto:
            tipo_doc = "cuenta_ventas"
        elif "Settlement Report" in texto:
            tipo_doc = "settlement_report"
        else:
            tipo_doc = "desconhecido"
            
        return idioma, tipo_doc
    
    def extrair_texto_com_ocr(self, caminho_pdf):
        """
        Extrai texto do PDF usando OCR
        
        Args:
            caminho_pdf (str): Caminho para o arquivo PDF
            
        Returns:
            str: Texto extraído do PDF
        """
        logger.info("Convertendo PDF para imagens para OCR")
        
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
    
    def extrair_com_ocr_e_regex(self, texto, idioma="ingles", tipo_doc="settlement_report"):
        """
        Extrai dados do texto usando expressões regulares
        
        Args:
            texto (str): Texto extraído do PDF
            idioma (str): Idioma detectado do documento
            tipo_doc (str): Tipo de documento detectado
            
        Returns:
            dict: Dicionário com os dados extraídos
        """
        dados_extraidos = {
            "dados_principais": self.estrutura_padrao["dados_principais"].copy(),
            "produtos": []
        }
        
        logger.info(f"Extraindo dados com regex para documento em {idioma} do tipo {tipo_doc}")
        
        if tipo_doc == "settlement_report":
            return self.extrair_settlement_report(texto)
        elif tipo_doc == "cuenta_ventas":
            return self.extrair_cuenta_ventas(texto)
        else:
            # Tentar ambos os métodos e ver qual retorna mais dados
            dados_settlement = self.extrair_settlement_report(texto)
            dados_cuenta = self.extrair_cuenta_ventas(texto)
            
            # Verificar qual extração retornou mais produtos
            if len(dados_settlement["produtos"]) >= len(dados_cuenta["produtos"]):
                return dados_settlement
            else:
                return dados_cuenta
    
    def extrair_settlement_report(self, texto):
        """
        Extrai dados de um relatório de liquidação em inglês
        
        Args:
            texto (str): Texto extraído do PDF
            
        Returns:
            dict: Dicionário com os dados extraídos
        """
        dados_extraidos = {
            "dados_principais": self.estrutura_padrao["dados_principais"].copy(),
            "produtos": []
        }
        
        # Extrair dados principais
        # Nome da empresa
        padrao_empresa = r"(Robinson Fresh|C\.H\. ROBINSON|[A-Z][a-z]+ Fresh)"
        match_empresa = re.search(padrao_empresa, texto)
        if match_empresa:
            dados_extraidos["dados_principais"]["Nome da empresa"] = match_empresa.group(1)
            logger.info(f"Nome da empresa encontrado: {match_empresa.group(1)}")
        
        # Número do contêiner
        padrao_container = r"[A-Z]{4}\d{7}"
        match_container = re.search(padrao_container, texto)
        if match_container:
            dados_extraidos["dados_principais"]["Número do contêiner"] = match_container.group(0)
            logger.info(f"Número do contêiner encontrado: {match_container.group(0)}")
        
        # Valor total
        padrao_valor_total = r"Grand Total\s+[\d,]+\s+[€$]\s+([\d,.]+)"
        match_valor_total = re.search(padrao_valor_total, texto)
        if match_valor_total:
            dados_extraidos["dados_principais"]["Valor total"] = match_valor_total.group(1)
            dados_extraidos["dados_principais"]["Net Amount"] = match_valor_total.group(1)
            logger.info(f"Valor total encontrado: {match_valor_total.group(1)}")
        
        # Moeda
        padrao_moeda = r"[€$]"
        match_moeda = re.search(padrao_moeda, texto)
        if match_moeda:
            dados_extraidos["dados_principais"]["Moeda"] = match_moeda.group(0)
            logger.info(f"Moeda encontrada: {match_moeda.group(0)}")
        
        # Extrair produtos
        # Padrão para linhas de produtos
        padrao_produto = r"([A-Za-z]+ Carton \d+CT \d+KG [A-Za-z]+ [A-Za-z]+ [A-Za-z]+)\s+(\d{6})\s+([\d.]+)\s+(\d+)\s+[€$]\s+([\d,.]+)"
        produtos = []
        
        # Dividir texto em linhas e processar cada uma
        linhas = texto.split('\n')
        for linha in linhas:
            # Tentar diferentes padrões para capturar produtos
            match_produto = re.search(padrao_produto, linha)
            if match_produto:
                tipo = match_produto.group(1)
                referencia = match_produto.group(2)
                currency_rate = match_produto.group(3)
                quantidade = match_produto.group(4)
                preco_total = match_produto.group(5)
                
                # Extrair tamanho do tipo
                match_tamanho = re.search(r'(\d+CT \d+KG)', tipo)
                tamanho = match_tamanho.group(1) if match_tamanho else ""
                
                produto = {
                    "tipo": tipo,
                    "tamanho": tamanho,
                    "quantidade": quantidade,
                    "preço unitário": "",
                    "preço total": preco_total,
                    "moeda": dados_extraidos["dados_principais"]["Moeda"],
                    "referencia": referencia,
                    "currency_rate": currency_rate
                }
                
                produtos.append(produto)
                logger.info(f"Produto encontrado: {tipo}")
            
            # Padrão alternativo para produtos
            else:
                # Tentar outros padrões se o primeiro falhar
                alt_padrao = r"(Mango Carton \d+CT \d+KG [A-Za-z]+ [A-Za-z]+ [A-Za-z]+)"
                match_alt = re.search(alt_padrao, linha)
                if match_alt:
                    # Se encontrou o tipo, tentar extrair outros dados da linha
                    tipo = match_alt.group(1)
                    
                    # Extrair referência (6 dígitos)
                    ref_match = re.search(r'(\d{6})', linha)
                    referencia = ref_match.group(1) if ref_match else ""
                    
                    # Extrair currency rate (número decimal)
                    rate_match = re.search(r'(\d\.\d+)', linha)
                    currency_rate = rate_match.group(1) if rate_match else ""
                    
                    # Extrair quantidade (número inteiro)
                    qtd_match = re.search(r'\s(\d+)\s', linha)
                    quantidade = qtd_match.group(1) if qtd_match else ""
                    
                    # Extrair preço total (número com possíveis vírgulas e pontos)
                    preco_match = re.search(r'[€$]\s+([\d,.]+)', linha)
                    preco_total = preco_match.group(1) if preco_match else ""
                    
                    # Extrair tamanho
                    match_tamanho = re.search(r'(\d+CT \d+KG)', tipo)
                    tamanho = match_tamanho.group(1) if match_tamanho else ""
                    
                    produto = {
                        "tipo": tipo,
                        "tamanho": tamanho,
                        "quantidade": quantidade,
                        "preço unitário": "",
                        "preço total": preco_total,
                        "moeda": dados_extraidos["dados_principais"]["Moeda"],
                        "referencia": referencia,
                        "currency_rate": currency_rate
                    }
                    
                    # Só adicionar se tiver pelo menos tipo e referência
                    if tipo and referencia:
                        produtos.append(produto)
                        logger.info(f"Produto encontrado (padrão alternativo): {tipo}")
        
        dados_extraidos["produtos"] = produtos
        logger.info(f"Total de produtos encontrados: {len(produtos)}")
        
        return dados_extraidos
    
    def extrair_cuenta_ventas(self, texto):
        """
        Extrai dados de uma cuenta de ventas em espanhol
        
        Args:
            texto (str): Texto extraído do PDF
            
        Returns:
            dict: Dicionário com os dados extraídos
        """
        dados_extraidos = {
            "dados_principais": self.estrutura_padrao["dados_principais"].copy(),
            "produtos": []
        }
        
        # Extrair dados principais
        # Nome da empresa
        padrao_empresa = r"(FINOBRASA|FINOBRA[SZ]A)"
        match_empresa = re.search(padrao_empresa, texto)
        if match_empresa:
            dados_extraidos["dados_principais"]["Nome da empresa"] = match_empresa.group(1)
            logger.info(f"Nome da empresa encontrado: {match_empresa.group(1)}")
        
        # Número do contêiner
        padrao_container = r"([A-Z]{4}\d{7})"
        match_container = re.search(padrao_container, texto)
        if match_container:
            dados_extraidos["dados_principais"]["Número do contêiner"] = match_container.group(1)
            logger.info(f"Número do contêiner encontrado: {match_container.group(1)}")
        
        # Valor total
        padrao_valor_total = r"TOTAL\s+([\d.,]+)"
        match_valor_total = re.search(padrao_valor_total, texto)
        if match_valor_total:
            dados_extraidos["dados_principais"]["Valor total"] = match_valor_total.group(1).replace(".", "").replace(",", ".")
            dados_extraidos["dados_principais"]["Net Amount"] = match_valor_total.group(1).replace(".", "").replace(",", ".")
            logger.info(f"Valor total encontrado: {match_valor_total.group(1)}")
        
        # Comissão %
        padrao_comissao_pct = r"Comision\s+(\d+)%"
        match_comissao_pct = re.search(padrao_comissao_pct, texto)
        if match_comissao_pct:
            dados_extraidos["dados_principais"]["Comissão %"] = match_comissao_pct.group(1)
            logger.info(f"Comissão % encontrada: {match_comissao_pct.group(1)}")
        
        # Comissão Valor
        padrao_comissao_valor = r"Comision\s+\d+%\s+€\s+([\d.,]+)"
        match_comissao_valor = re.search(padrao_comissao_valor, texto)
        if match_comissao_valor:
            dados_extraidos["dados_principais"]["Comissão Valor"] = match_comissao_valor.group(1).replace(".", "").replace(",", ".")
            logger.info(f"Comissão Valor encontrada: {match_comissao_valor.group(1)}")
        
        # Moeda
        padrao_moeda = r"[€$]"
        match_moeda = re.search(padrao_moeda, texto)
        if match_moeda:
            dados_extraidos["dados_principais"]["Moeda"] = match_moeda.group(0)
            logger.info(f"Moeda encontrada: {match_moeda.group(0)}")
        
        # Extrair produtos
        # Padrão para linhas de produtos em espanhol
        produtos = []
        
        # Dividir texto em linhas e processar cada uma
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
                    "referencia": tipo,  # Usar o código do produto como referência
                    "currency_rate": ""
                }
                
                produtos.append(produto)
                logger.info(f"Produto encontrado: {tipo}")
        
        dados_extraidos["produtos"] = produtos
        logger.info(f"Total de produtos encontrados: {len(produtos)}")
        
        return dados_extraidos
    
    def extrair_com_openai(self, caminho_pdf, texto_ocr, idioma="ingles", tipo_doc="settlement_report"):
        """
        Extrai dados do PDF usando a API da OpenAI
        
        Args:
            caminho_pdf (str): Caminho para o arquivo PDF
            texto_ocr (str): Texto extraído do PDF via OCR
            idioma (str): Idioma detectado do documento
            tipo_doc (str): Tipo de documento detectado
            
        Returns:
            dict: Dicionário com os dados extraídos
        """
        logger.info("Enviando dados para processamento com OpenAI")
        
        # Ajustar prompt com base no idioma e tipo de documento
        if idioma == "espanhol":
            prompt = self.criar_prompt_espanhol(texto_ocr, tipo_doc)
        else:
            prompt = self.criar_prompt_ingles(texto_ocr, tipo_doc)
        
        try:
            # Chamar a API da OpenAI
            response = self.openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Você é um assistente especializado em extrair dados estruturados de documentos."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=2000
            )
            
            # Extrair resposta
            resposta = response.choices[0].message.content
            
            # Extrair JSON da resposta
            match = re.search(r'```json\s*(.*?)\s*```', resposta, re.DOTALL)
            if match:
                json_str = match.group(1)
            else:
                json_str = resposta
            
            # Limpar e carregar JSON
            json_str = re.sub(r'```.*?```', '', json_str, flags=re.DOTALL)
            
            # Remover caracteres não-JSON
            json_str = re.sub(r'[^\x00-\x7F]+', '', json_str)
            
            # Tentar carregar o JSON
            try:
                dados = json.loads(json_str)
                logger.info("Dados extraídos com sucesso usando OpenAI")
                return dados
            except json.JSONDecodeError as e:
                logger.error(f"Erro ao decodificar JSON da resposta OpenAI: {str(e)}")
                logger.debug(f"JSON com erro: {json_str}")
                # Tentar limpar mais o JSON
                json_str = re.sub(r'[^{}[\]"\',:.\d\w\s_-]', '', json_str)
                try:
                    dados = json.loads(json_str)
                    logger.info("Dados extraídos com sucesso após limpeza adicional")
                    return dados
                except:
                    logger.error("Falha ao decodificar JSON mesmo após limpeza")
                    raise
            
        except Exception as e:
            logger.error(f"Erro ao processar com OpenAI: {str(e)}")
            raise
    
    def criar_prompt_ingles(self, texto_ocr, tipo_doc):
        """
        Cria prompt para OpenAI para documentos em inglês
        
        Args:
            texto_ocr (str): Texto extraído do PDF
            tipo_doc (str): Tipo de documento
            
        Returns:
            str: Prompt para OpenAI
        """
        return f"""
        Extract the following data from this Settlement Report:
        
        1. Main data:
           - Company name
           - Container number
           - Commission % (if available)
           - Commission Value (if available)
           - Total value
           - Net Amount
           - Currency
        
        2. List of products with the following fields for each one:
           - type
           - size
           - quantity
           - unit price (if available)
           - total price
           - currency
           - reference
           - currency_rate
        
        Format the response as a valid JSON object with the following structure:
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
        
        Report text:
        {texto_ocr}
        """
    
    def criar_prompt_espanhol(self, texto_ocr, tipo_doc):
        """
        Cria prompt para OpenAI para documentos em espanhol
        
        Args:
            texto_ocr (str): Texto extraído do PDF
            tipo_doc (str): Tipo de documento
            
        Returns:
            str: Prompt para OpenAI
        """
        return f"""
        Extrae los siguientes datos de esta Cuenta de Ventas:
        
        1. Datos principales:
           - Nombre de la empresa
           - Número del contenedor
           - Comisión % (si está disponible)
           - Valor de la Comisión (si está disponible)
           - Valor total
           - Importe neto
           - Moneda
        
        2. Lista de productos con los siguientes campos para cada uno:
           - tipo (código del producto)
           - tamaño (formato)
           - cantidad
           - precio unitario
           - precio total
           - moneda
           - referencia (puede ser el mismo código del producto)
           - tasa de cambio (si está disponible)
        
        Formatea la respuesta como un objeto JSON válido con la siguiente estructura:
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
        
        Texto del informe:
        {texto_ocr}
        """

def get_download_link(json_data, filename="dados_extraidos.json"):
    """
    Gera um link para download do JSON
    """
    json_str = json.dumps(json_data, ensure_ascii=False, indent=4)
    b64 = base64.b64encode(json_str.encode('utf-8')).decode()
    href = f'<a href="data:file/json;base64,{b64}" download="{filename}">Baixar JSON</a>'
    return href

def main():
    st.set_page_config(
        page_title="Extrator de PDFs - Multilíngue",
        page_icon="📄",
        layout="wide"
    )
    
    st.title("📄 Extrator de PDFs - Multilíngue")
    st.markdown("""
    Esta aplicação extrai dados estruturados de relatórios em formato PDF.
    Suporta documentos em português, inglês e espanhol.
    """)
    
    # Sidebar para configurações
    st.sidebar.title("⚙️ Configurações")
    usar_openai = st.sidebar.checkbox("Usar OpenAI para extração (recomendado para maior precisão)")
    
    if usar_openai:
        api_key = st.sidebar.text_input("Chave de API da OpenAI", type="password")
        if not api_key:
            st.sidebar.warning("Por favor, insira sua chave de API da OpenAI para usar este recurso.")
    else:
        api_key = None
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("""
    ### 📋 Instruções
    1. Faça upload do PDF de relatório
    2. Aguarde o processamento
    3. Visualize os dados extraídos
    4. Baixe o JSON resultante
    
    ### 🌐 Formatos suportados
    - Settlement Reports (inglês)
    - Cuenta de Ventas (espanhol)
    """)
    
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
                # Inicializar extrator
                extrator = ExtratorPDF(api_key=api_key)
                
                # Extrair dados
                try:
                    dados = extrator.extrair_dados(uploaded_file)
                    
                    # Exibir resultados
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.subheader("Dados Principais")
                        for campo, valor in dados["dados_principais"].items():
                            if valor:  # Só mostrar campos com valor
                                st.text(f"{campo}: {valor}")
                    
                    with col2:
                        st.subheader("Resumo")
                        st.text(f"Total de produtos: {len(dados['produtos'])}")
                        if len(dados['produtos']) > 0:
                            tipos_unicos = set([p['tipo'] for p in dados['produtos'] if p.get('tipo')])
                            st.text(f"Tipos de produtos: {len(tipos_unicos)}")
                            if dados['dados_principais']['Valor total']:
                                st.text(f"Valor total: {dados['dados_principais']['Valor total']} {dados['dados_principais']['Moeda']}")
                    
                    # Tabela de produtos
                    st.subheader("Produtos")
                    
                    # Converter para DataFrame para melhor visualização
                    import pandas as pd
                    df_produtos = pd.DataFrame(dados["produtos"])
                    st.dataframe(df_produtos)
                    
                    # Link para download
                    st.markdown("### Download")
                    st.markdown(get_download_link(dados), unsafe_allow_html=True)
                    
                    # Mostrar JSON
                    with st.expander("Ver JSON completo", expanded=False):
                        st.json(dados)
                    
                except Exception as e:
                    st.error(f"Erro ao processar o PDF: {str(e)}")
                    st.info("Tente usar a opção OpenAI para melhor precisão ou verifique se o PDF está no formato esperado.")

if __name__ == "__main__":
    main()
