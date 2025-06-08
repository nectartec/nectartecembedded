import os
import json
import sys
import re
import tempfile
import hashlib
import logging
import traceback
from typing import Dict, List, Any, Optional, Tuple
import cv2
import numpy as np
import pytesseract
from pdf2image import convert_from_path
from PIL import Image

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("extrator.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ExtratorPDFLearning:
    """
    Extrator de dados de PDFs com capacidade de aprendizado contínuo
    """
    
    def __init__(self, api_key: Optional[str] = None, db_path: str = "pdf_models.db"):
        """
        Inicializa o extrator
        
        Args:
            api_key (str, optional): Chave de API da OpenAI para extração avançada
            db_path (str): Caminho para o banco de dados de modelos
        """
        self.api_key = api_key
        self.db_path = db_path
        
        # Importar o ModelDatabase aqui para evitar dependência circular
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from model_database_fixed import ModelDatabase
        self.db = ModelDatabase(db_path)
        
        # Padrões de expressões regulares para extração
        self.patterns = {
            "container_number": r"(?:Container|Contenedor|Container No|Container Number|Cont[.\s]?N[o°]?)[:\s]*([A-Z]{4}\s*\d{7})",
            "commission_percentage": r"(?:Commission|Comisión|Comissão)[:\s]*(\d+(?:[.,]\d+)?)\s*%",
            "commission_value": r"(?:Commission|Comisión|Comissão)[:\s]*(?:€|EUR|USD|\$|£|R\$)?\s*(\d+(?:[.,]\d+)?)",
            "total_value": r"(?:Total|Total Amount|Valor Total|Monto Total)[:\s]*(?:€|EUR|USD|\$|£|R\$)?\s*(\d+(?:[.,]\d+)?)",
            "net_amount": r"(?:Net Amount|Neto|Valor Neto|Valor Líquido)[:\s]*(?:€|EUR|USD|\$|£|R\$)?\s*(\d+(?:[.,]\d+)?)",
            "currency": r"(?:Currency|Moneda|Moeda)[:\s]*([A-Z]{3}|€|USD|\$|£|R\$)",
        }
        
        # Padrões para diferentes idiomas
        self.language_patterns = {
            "en": {
                "company_name": r"(?:Company|Supplier|Vendor|Grower)[:\s]*([A-Za-z0-9\s&.]+)",
                "product_pattern": r"(?:Product|Item|Description)[:\s]*([A-Za-z0-9\s]+)",
                "size_pattern": r"(?:Size|Caliber)[:\s]*([A-Za-z0-9\s]+)",
                "quantity_pattern": r"(?:Quantity|Qty|Amount)[:\s]*(\d+(?:[.,]\d+)?)",
                "unit_price_pattern": r"(?:Unit Price|Price)[:\s]*(?:€|EUR|USD|\$|£|R\$)?\s*(\d+(?:[.,]\d+)?)",
                "total_price_pattern": r"(?:Total Price|Price|Amount)[:\s]*(?:€|EUR|USD|\$|£|R\$)?\s*(\d+(?:[.,]\d+)?)",
            },
            "es": {
                "company_name": r"(?:Empresa|Proveedor|Vendedor|Productor)[:\s]*([A-Za-z0-9\s&.]+)",
                "product_pattern": r"(?:Producto|Artículo|Descripción)[:\s]*([A-Za-z0-9\s]+)",
                "size_pattern": r"(?:Tamaño|Calibre)[:\s]*([A-Za-z0-9\s]+)",
                "quantity_pattern": r"(?:Cantidad|Cant|Monto)[:\s]*(\d+(?:[.,]\d+)?)",
                "unit_price_pattern": r"(?:Precio Unitario|Precio)[:\s]*(?:€|EUR|USD|\$|£|R\$)?\s*(\d+(?:[.,]\d+)?)",
                "total_price_pattern": r"(?:Precio Total|Precio|Monto)[:\s]*(?:€|EUR|USD|\$|£|R\$)?\s*(\d+(?:[.,]\d+)?)",
            },
            "pt": {
                "company_name": r"(?:Empresa|Fornecedor|Vendedor|Produtor)[:\s]*([A-Za-z0-9\s&.]+)",
                "product_pattern": r"(?:Produto|Item|Descrição)[:\s]*([A-Za-z0-9\s]+)",
                "size_pattern": r"(?:Tamanho|Calibre)[:\s]*([A-Za-z0-9\s]+)",
                "quantity_pattern": r"(?:Quantidade|Qtd|Valor)[:\s]*(\d+(?:[.,]\d+)?)",
                "unit_price_pattern": r"(?:Preço Unitário|Preço)[:\s]*(?:€|EUR|USD|\$|£|R\$)?\s*(\d+(?:[.,]\d+)?)",
                "total_price_pattern": r"(?:Preço Total|Preço|Valor)[:\s]*(?:€|EUR|USD|\$|£|R\$)?\s*(\d+(?:[.,]\d+)?)",
            }
        }
        
        # Palavras-chave para identificar o tipo de documento
        self.document_keywords = {
            "settlement_report": ["settlement", "report", "liquidation", "account", "sale"],
            "cuenta_ventas": ["cuenta", "ventas", "liquidación", "venta"],
            "accountsale": ["accountsale", "account", "sale", "settlement"],
            "liquidacion": ["liquidación", "liquidacion", "cuenta", "venta"]
        }
        
        # Palavras-chave para identificar o idioma
        self.language_keywords = {
            "en": ["total", "amount", "quantity", "price", "container", "commission"],
            "es": ["total", "cantidad", "precio", "contenedor", "comisión"],
            "pt": ["total", "quantidade", "preço", "contêiner", "comissão"]
        }
        
        # Empresas conhecidas
        self.known_companies = [
            "Robinson Fresh", "Finobrasa", "CGH", "Nature's Pride", "Cultipalta",
            "CH Robinson", "C.H. Robinson", "C.H.Robinson", "CH ROBINSON", "C.H. ROBINSON"
        ]
    
    def extrair_dados(self, pdf_path: str) -> Dict[str, Any]:
        """
        Extrai dados de um arquivo PDF
        
        Args:
            pdf_path (str): Caminho para o arquivo PDF
            
        Returns:
            Dict[str, Any]: Dados extraídos do PDF
        """
        logger.info(f"Iniciando extração do PDF: {pdf_path}")
        
        # Gerar assinatura do PDF
        pdf_signature = self.generate_signature(pdf_path)
        
        # Verificar se existe um modelo para este PDF
        existing_model = self.db.find_model_by_signature(pdf_signature)
        modelo_usado = None
        confianca = 0.0
        
        # Extrair texto do PDF
        texto_completo = self.extrair_texto_pdf(pdf_path)
        
        # Detectar idioma e tipo de documento
        idioma = self.detectar_idioma(texto_completo)
        tipo_documento = self.detectar_tipo_documento(texto_completo)
        
        logger.info(f"Idioma detectado: {idioma}")
        logger.info(f"Tipo de documento detectado: {tipo_documento}")
        
        # Inicializar estrutura de dados
        dados = {
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
        
        # Se existe um modelo, aplicar correções
        if existing_model:
            logger.info(f"Modelo encontrado: {existing_model['name']}")
            modelo_usado = existing_model['name']
            confianca = existing_model['confidence_score']
            
            # Incrementar contador de uso do modelo
            self.db.update_model_usage(existing_model['id'])
            
            # Extrair dados básicos
            dados = self.extrair_dados_basicos(texto_completo, idioma, tipo_documento)
            
            # Aplicar correções do modelo
            dados = self.aplicar_modelo(dados, existing_model)
        else:
            # Extrair dados básicos
            dados = self.extrair_dados_basicos(texto_completo, idioma, tipo_documento)
            
            # Se tiver API key da OpenAI, tentar extração avançada
            if self.api_key:
                try:
                    dados_openai = self.extrair_com_openai(pdf_path, texto_completo)
                    if dados_openai:
                        # Mesclar dados da OpenAI com os dados básicos
                        dados = self.mesclar_dados(dados, dados_openai)
                except Exception as e:
                    logger.error(f"Erro na extração com OpenAI: {str(e)}")
        
        # Adicionar informações sobre o modelo usado
        if modelo_usado:
            dados["modelo_usado"] = modelo_usado
            dados["confianca"] = confianca
        
        logger.info(f"Extração concluída. Encontrados {len(dados['produtos'])} produtos.")
        return dados
    
    def extrair_texto_pdf(self, pdf_path: str) -> str:
        """
        Extrai texto de um arquivo PDF usando OCR se necessário
        
        Args:
            pdf_path (str): Caminho para o arquivo PDF
            
        Returns:
            str: Texto extraído do PDF
        """
        try:
            # Primeiro, tentar extrair texto diretamente
            texto = self.extrair_texto_direto(pdf_path)
            
            # Se o texto estiver vazio ou for muito curto, usar OCR
            if not texto or len(texto) < 100:
                logger.info("Texto extraído diretamente é insuficiente. Usando OCR...")
                texto = self.extrair_texto_ocr(pdf_path)
            
            return texto
        except Exception as e:
            logger.error(f"Erro ao extrair texto do PDF: {str(e)}")
            # Em caso de erro, tentar OCR como fallback
            return self.extrair_texto_ocr(pdf_path)
    
    def extrair_texto_direto(self, pdf_path: str) -> str:
        """
        Extrai texto diretamente do PDF usando pdftotext
        
        Args:
            pdf_path (str): Caminho para o arquivo PDF
            
        Returns:
            str: Texto extraído do PDF
        """
        try:
            with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as temp_txt:
                temp_txt_path = temp_txt.name
            
            # Usar pdftotext para extrair o texto
            os.system(f'pdftotext -layout "{pdf_path}" "{temp_txt_path}"')
            
            # Ler o texto extraído
            with open(temp_txt_path, 'r', encoding='utf-8', errors='ignore') as f:
                texto = f.read()
            
            # Remover arquivo temporário
            os.unlink(temp_txt_path)
            
            return texto
        except Exception as e:
            logger.error(f"Erro ao extrair texto diretamente: {str(e)}")
            return ""
    
    def extrair_texto_ocr(self, pdf_path: str) -> str:
        """
        Extrai texto do PDF usando OCR
        
        Args:
            pdf_path (str): Caminho para o arquivo PDF
            
        Returns:
            str: Texto extraído do PDF
        """
        try:
            # Converter PDF para imagens
            images = convert_from_path(pdf_path)
            
            texto_completo = ""
            
            # Processar cada página
            for i, image in enumerate(images):
                # Converter para formato compatível com OpenCV
                img_np = np.array(image)
                img_cv = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
                
                # Pré-processamento para melhorar OCR
                img_gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
                img_thresh = cv2.threshold(img_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
                
                # Aplicar OCR
                texto_pagina = pytesseract.image_to_string(img_thresh, lang='eng+spa+por')
                texto_completo += texto_pagina + "\n\n"
            
            return texto_completo
        except Exception as e:
            logger.error(f"Erro ao extrair texto com OCR: {str(e)}")
            return ""
    
    def detectar_idioma(self, texto: str) -> str:
        """
        Detecta o idioma do texto
        
        Args:
            texto (str): Texto para detectar o idioma
            
        Returns:
            str: Código do idioma detectado (en, es, pt)
        """
        texto_lower = texto.lower()
        
        # Contar ocorrências de palavras-chave para cada idioma
        contagens = {}
        for idioma, palavras in self.language_keywords.items():
            contagem = sum(1 for palavra in palavras if palavra in texto_lower)
            contagens[idioma] = contagem
        
        # Retornar o idioma com mais ocorrências
        if not contagens:
            return "en"  # Padrão para inglês
        
        return max(contagens, key=contagens.get)
    
    def detectar_tipo_documento(self, texto: str) -> str:
        """
        Detecta o tipo de documento
        
        Args:
            texto (str): Texto para detectar o tipo de documento
            
        Returns:
            str: Tipo de documento detectado
        """
        texto_lower = texto.lower()
        
        # Contar ocorrências de palavras-chave para cada tipo de documento
        contagens = {}
        for tipo, palavras in self.document_keywords.items():
            contagem = sum(1 for palavra in palavras if palavra in texto_lower)
            contagens[tipo] = contagem
        
        # Retornar o tipo com mais ocorrências
        if not contagens:
            return "settlement_report"  # Padrão
        
        return max(contagens, key=contagens.get)
    
    def extrair_dados_basicos(self, texto: str, idioma: str, tipo_documento: str) -> Dict[str, Any]:
        """
        Extrai dados básicos do texto
        
        Args:
            texto (str): Texto extraído do PDF
            idioma (str): Idioma detectado
            tipo_documento (str): Tipo de documento detectado
            
        Returns:
            Dict[str, Any]: Dados extraídos
        """
        # Inicializar estrutura de dados
        dados = {
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
        
        # Extrair dados principais
        dados["dados_principais"]["Número do contêiner"] = self.extrair_padrao(texto, self.patterns["container_number"])
        dados["dados_principais"]["Comissão %"] = self.extrair_padrao(texto, self.patterns["commission_percentage"])
        dados["dados_principais"]["Comissão Valor"] = self.extrair_padrao(texto, self.patterns["commission_value"])
        dados["dados_principais"]["Valor total"] = self.extrair_padrao(texto, self.patterns["total_value"])
        dados["dados_principais"]["Net Amount"] = self.extrair_padrao(texto, self.patterns["net_amount"])
        dados["dados_principais"]["Moeda"] = self.extrair_padrao(texto, self.patterns["currency"])
        
        # Extrair nome da empresa
        dados["dados_principais"]["Nome da empresa"] = self.extrair_nome_empresa(texto, idioma)
        
        # Extrair produtos
        dados["produtos"] = self.extrair_produtos(texto, idioma, tipo_documento)
        
        return dados
    
    def extrair_nome_empresa(self, texto: str, idioma: str) -> str:
        """
        Extrai o nome da empresa do texto
        
        Args:
            texto (str): Texto extraído do PDF
            idioma (str): Idioma detectado
            
        Returns:
            str: Nome da empresa
        """
        # Primeiro, verificar empresas conhecidas
        for empresa in self.known_companies:
            if empresa.lower() in texto.lower():
                return empresa
        
        # Se não encontrar, tentar extrair usando padrão
        if idioma in self.language_patterns:
            padrao = self.language_patterns[idioma]["company_name"]
            return self.extrair_padrao(texto, padrao)
        
        return ""
    
    def extrair_produtos(self, texto: str, idioma: str, tipo_documento: str) -> List[Dict[str, str]]:
        """
        Extrai produtos do texto
        
        Args:
            texto (str): Texto extraído do PDF
            idioma (str): Idioma detectado
            tipo_documento (str): Tipo de documento detectado
            
        Returns:
            List[Dict[str, str]]: Lista de produtos extraídos
        """
        produtos = []
        
        # Selecionar padrões de acordo com o idioma
        if idioma not in self.language_patterns:
            idioma = "en"  # Padrão para inglês
        
        patterns = self.language_patterns[idioma]
        
        # Dividir o texto em linhas
        linhas = texto.split('\n')
        
        # Identificar linhas que podem conter produtos
        for i, linha in enumerate(linhas):
            # Verificar se a linha contém informações de produto
            if any(keyword in linha.lower() for keyword in ["mango", "manga", "palmer", "kent", "keitt", "tommy"]):
                produto = {
                    "tipo": "",
                    "tamanho": "",
                    "quantidade": "",
                    "preço unitário": "",
                    "preço total": "",
                    "moeda": "",
                    "referencia": "",
                    "currency_rate": ""
                }
                
                # Extrair tipo de produto
                produto["tipo"] = self.extrair_padrao(linha, patterns["product_pattern"]) or self.extrair_tipo_produto(linha)
                
                # Extrair tamanho
                produto["tamanho"] = self.extrair_padrao(linha, patterns["size_pattern"]) or self.extrair_tamanho(linha)
                
                # Extrair quantidade
                produto["quantidade"] = self.extrair_padrao(linha, patterns["quantity_pattern"]) or self.extrair_quantidade(linha)
                
                # Extrair preço unitário
                produto["preço unitário"] = self.extrair_padrao(linha, patterns["unit_price_pattern"]) or self.extrair_preco_unitario(linha)
                
                # Extrair preço total
                produto["preço total"] = self.extrair_padrao(linha, patterns["total_price_pattern"]) or self.extrair_preco_total(linha)
                
                # Extrair moeda (usar a mesma da extração principal)
                produto["moeda"] = self.extrair_padrao(linha, self.patterns["currency"])
                
                # Extrair referência (código do produto)
                produto["referencia"] = self.extrair_referencia(linha)
                
                # Se encontrou pelo menos tipo ou tamanho, adicionar à lista
                if produto["tipo"] or produto["tamanho"]:
                    produtos.append(produto)
                
                # Verificar também a próxima linha (pode conter informações complementares)
                if i + 1 < len(linhas):
                    proxima_linha = linhas[i + 1]
                    
                    # Se a linha atual tem tipo mas não tem tamanho, verificar na próxima
                    if produto["tipo"] and not produto["tamanho"]:
                        produto["tamanho"] = self.extrair_padrao(proxima_linha, patterns["size_pattern"]) or self.extrair_tamanho(proxima_linha)
                    
                    # Se a linha atual tem tipo mas não tem quantidade, verificar na próxima
                    if produto["tipo"] and not produto["quantidade"]:
                        produto["quantidade"] = self.extrair_padrao(proxima_linha, patterns["quantity_pattern"]) or self.extrair_quantidade(proxima_linha)
                    
                    # Se a linha atual tem tipo mas não tem preço, verificar na próxima
                    if produto["tipo"] and not produto["preço unitário"]:
                        produto["preço unitário"] = self.extrair_padrao(proxima_linha, patterns["unit_price_pattern"]) or self.extrair_preco_unitario(proxima_linha)
                    
                    # Se a linha atual tem tipo mas não tem preço total, verificar na próxima
                    if produto["tipo"] and not produto["preço total"]:
                        produto["preço total"] = self.extrair_padrao(proxima_linha, patterns["total_price_pattern"]) or self.extrair_preco_total(proxima_linha)
        
        # Se não encontrou produtos, tentar abordagem alternativa
        if not produtos:
            produtos = self.extrair_produtos_alternativo(texto, idioma, tipo_documento)
        
        return produtos
    
    def extrair_produtos_alternativo(self, texto: str, idioma: str, tipo_documento: str) -> List[Dict[str, str]]:
        """
        Método alternativo para extrair produtos quando a abordagem principal falha
        
        Args:
            texto (str): Texto extraído do PDF
            idioma (str): Idioma detectado
            tipo_documento (str): Tipo de documento detectado
            
        Returns:
            List[Dict[str, str]]: Lista de produtos extraídos
        """
        produtos = []
        
        # Dividir o texto em linhas
        linhas = texto.split('\n')
        
        # Procurar por tabelas de produtos
        tabela_iniciada = False
        cabecalho_encontrado = False
        
        for i, linha in enumerate(linhas):
            linha_lower = linha.lower()
            
            # Detectar início de tabela de produtos
            if not tabela_iniciada and any(keyword in linha_lower for keyword in ["product", "producto", "produto", "item", "description", "descripción", "descrição"]):
                tabela_iniciada = True
                cabecalho_encontrado = True
                continue
            
            # Se estamos em uma tabela, processar linhas
            if tabela_iniciada:
                # Pular linhas vazias e cabeçalhos
                if not linha.strip() or cabecalho_encontrado:
                    cabecalho_encontrado = False
                    continue
                
                # Verificar se a linha contém números (possível produto)
                if re.search(r'\d', linha):
                    # Dividir a linha em colunas
                    colunas = re.split(r'\s{2,}', linha.strip())
                    
                    # Se temos pelo menos 3 colunas, pode ser um produto
                    if len(colunas) >= 3:
                        produto = {
                            "tipo": "",
                            "tamanho": "",
                            "quantidade": "",
                            "preço unitário": "",
                            "preço total": "",
                            "moeda": "",
                            "referencia": "",
                            "currency_rate": ""
                        }
                        
                        # Tentar identificar o conteúdo de cada coluna
                        for j, coluna in enumerate(colunas):
                            # Primeira coluna geralmente é o tipo/descrição
                            if j == 0:
                                produto["tipo"] = coluna.strip()
                            
                            # Verificar se a coluna contém um número
                            elif re.search(r'\d+(?:[.,]\d+)?', coluna):
                                # Se já temos quantidade, pode ser preço unitário
                                if produto["quantidade"] and not produto["preço unitário"]:
                                    produto["preço unitário"] = re.search(r'\d+(?:[.,]\d+)?', coluna).group()
                                
                                # Se já temos preço unitário, pode ser preço total
                                elif produto["preço unitário"] and not produto["preço total"]:
                                    produto["preço total"] = re.search(r'\d+(?:[.,]\d+)?', coluna).group()
                                
                                # Se não temos quantidade, assumir que é quantidade
                                else:
                                    produto["quantidade"] = re.search(r'\d+(?:[.,]\d+)?', coluna).group()
                            
                            # Verificar se a coluna contém um possível tamanho
                            elif re.search(r'(?:size|tamaño|tamanho|calibre)\s*[:=]?\s*([a-zA-Z0-9]+)', coluna.lower()):
                                produto["tamanho"] = re.search(r'(?:size|tamaño|tamanho|calibre)\s*[:=]?\s*([a-zA-Z0-9]+)', coluna.lower()).group(1)
                        
                        # Se temos pelo menos tipo e quantidade, adicionar à lista
                        if produto["tipo"] and produto["quantidade"]:
                            produtos.append(produto)
                
                # Verificar se chegamos ao fim da tabela
                if any(keyword in linha_lower for keyword in ["total", "subtotal", "sum", "suma"]):
                    tabela_iniciada = False
        
        return produtos
    
    def extrair_tipo_produto(self, texto: str) -> str:
        """
        Extrai o tipo de produto do texto
        
        Args:
            texto (str): Texto para extrair o tipo de produto
            
        Returns:
            str: Tipo de produto extraído
        """
        # Padrões para tipos de manga
        padroes = [
            r'(?:MANGO|MANGA)\s+([A-Za-z]+)',
            r'([A-Za-z]+)\s+(?:MANGO|MANGA)',
            r'(?:MANGUE|MANGOES)\s+([A-Za-z]+)',
            r'([A-Za-z]+)\s+(?:MANGUE|MANGOES)'
        ]
        
        for padrao in padroes:
            match = re.search(padrao, texto, re.IGNORECASE)
            if match:
                return f"MANGO {match.group(1).upper()}"
        
        # Verificar palavras-chave específicas
        keywords = ["PALMER", "KENT", "KEITT", "TOMMY", "ATKINS", "HADEN"]
        for keyword in keywords:
            if keyword in texto.upper():
                return f"MANGO {keyword}"
        
        return ""
    
    def extrair_tamanho(self, texto: str) -> str:
        """
        Extrai o tamanho do produto do texto
        
        Args:
            texto (str): Texto para extrair o tamanho
            
        Returns:
            str: Tamanho extraído
        """
        # Padrões para tamanhos
        padroes = [
            r'(?:SIZE|TAMAÑO|TAMANHO|CALIBRE)\s*[:=]?\s*([a-zA-Z0-9]+)',
            r'([0-9]+)(?:\s*-\s*[0-9]+)?\s*(?:CT|KG)',
            r'CAL(?:IBRE)?\s*\.?\s*([0-9]+)'
        ]
        
        for padrao in padroes:
            match = re.search(padrao, texto, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return ""
    
    def extrair_quantidade(self, texto: str) -> str:
        """
        Extrai a quantidade do produto do texto
        
        Args:
            texto (str): Texto para extrair a quantidade
            
        Returns:
            str: Quantidade extraída
        """
        # Padrões para quantidades
        padroes = [
            r'(?:QTY|QUANTITY|CANTIDAD|QUANTIDADE|QTD)\s*[:=]?\s*(\d+(?:[.,]\d+)?)',
            r'(\d+(?:[.,]\d+)?)\s*(?:KG|CT|PCS|UNITS|UNIDADES)'
        ]
        
        for padrao in padroes:
            match = re.search(padrao, texto, re.IGNORECASE)
            if match:
                return match.group(1)
        
        # Procurar por números isolados que podem ser quantidades
        numeros = re.findall(r'(?<!\S)(\d+(?:[.,]\d+)?)(?!\S)', texto)
        if numeros:
            return numeros[0]
        
        return ""
    
    def extrair_preco_unitario(self, texto: str) -> str:
        """
        Extrai o preço unitário do produto do texto
        
        Args:
            texto (str): Texto para extrair o preço unitário
            
        Returns:
            str: Preço unitário extraído
        """
        # Padrões para preços unitários
        padroes = [
            r'(?:UNIT PRICE|PRECIO UNITARIO|PREÇO UNITÁRIO|UNIT)\s*[:=]?\s*(?:€|EUR|USD|\$|£|R\$)?\s*(\d+(?:[.,]\d+)?)',
            r'(?:€|EUR|USD|\$|£|R\$)\s*(\d+(?:[.,]\d+)?)\s*(?:/|PER)\s*(?:KG|CT|UNIT)'
        ]
        
        for padrao in padroes:
            match = re.search(padrao, texto, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return ""
    
    def extrair_preco_total(self, texto: str) -> str:
        """
        Extrai o preço total do produto do texto
        
        Args:
            texto (str): Texto para extrair o preço total
            
        Returns:
            str: Preço total extraído
        """
        # Padrões para preços totais
        padroes = [
            r'(?:TOTAL PRICE|PRECIO TOTAL|PREÇO TOTAL|AMOUNT|TOTAL)\s*[:=]?\s*(?:€|EUR|USD|\$|£|R\$)?\s*(\d+(?:[.,]\d+)?)',
            r'(?:€|EUR|USD|\$|£|R\$)\s*(\d+(?:[.,]\d+)?)\s*(?:TOTAL)'
        ]
        
        for padrao in padroes:
            match = re.search(padrao, texto, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return ""
    
    def extrair_referencia(self, texto: str) -> str:
        """
        Extrai a referência (código) do produto do texto
        
        Args:
            texto (str): Texto para extrair a referência
            
        Returns:
            str: Referência extraída
        """
        # Padrões para referências
        padroes = [
            r'(?:REF|REFERENCE|REFERENCIA|REFERÊNCIA|CODE|CÓDIGO)\s*[:=]?\s*([A-Za-z0-9]+)',
            r'([A-Z]{3}[0-9]{1,2}[A-Z]{2}[0-9]{2})'  # Padrão como MAP1BR08
        ]
        
        for padrao in padroes:
            match = re.search(padrao, texto, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return ""
    
    def extrair_padrao(self, texto: str, padrao: str) -> str:
        """
        Extrai um valor usando um padrão de expressão regular
        
        Args:
            texto (str): Texto para extrair o valor
            padrao (str): Padrão de expressão regular
            
        Returns:
            str: Valor extraído
        """
        match = re.search(padrao, texto, re.IGNORECASE)
        if match:
            return match.group(1)
        return ""
    
    def aplicar_modelo(self, dados: Dict[str, Any], modelo: Dict[str, Any]) -> Dict[str, Any]:
        """
        Aplica correções de um modelo aos dados extraídos
        
        Args:
            dados (Dict[str, Any]): Dados extraídos
            modelo (Dict[str, Any]): Modelo com correções
            
        Returns:
            Dict[str, Any]: Dados corrigidos
        """
        try:
            # Extrair padrões de extração do modelo
            extraction_patterns = modelo.get("extraction_patterns", {})
            
            # Aplicar correções nos campos principais
            field_corrections = extraction_patterns.get("field_corrections", {})
            for campo, correcao in field_corrections.items():
                valor_original = correcao.get("original", "")
                valor_corrigido = correcao.get("corrected", "")
                
                # Se o campo existe nos dados principais
                if campo in dados["dados_principais"]:
                    # Se o valor atual é igual ao valor original no modelo, aplicar correção
                    if dados["dados_principais"][campo] == valor_original:
                        dados["dados_principais"][campo] = valor_corrigido
                    # Se o campo está vazio, usar o valor corrigido
                    elif not dados["dados_principais"][campo]:
                        dados["dados_principais"][campo] = valor_corrigido
            
            # Aplicar correções nos produtos
            # Se o modelo tem padrões de produtos e os dados atuais não têm produtos
            # ou se o modelo indica que a detecção de produtos foi melhorada
            if (extraction_patterns.get("product_patterns") and 
                (not dados["produtos"] or extraction_patterns.get("product_detection_improved", False))):
                dados["produtos"] = extraction_patterns.get("product_patterns", [])
            
            return dados
        except Exception as e:
            logger.error(f"Erro ao aplicar modelo: {str(e)}")
            return dados
    
    def extrair_com_openai(self, pdf_path: str, texto_completo: str) -> Dict[str, Any]:
        """
        Extrai dados usando a API da OpenAI
        
        Args:
            pdf_path (str): Caminho para o arquivo PDF
            texto_completo (str): Texto extraído do PDF
            
        Returns:
            Dict[str, Any]: Dados extraídos pela OpenAI
        """
        if not self.api_key:
            return {}
        
        try:
            import openai
            
            # Configurar cliente OpenAI
            openai.api_key = self.api_key
            
            # Preparar prompt
            prompt = f"""
            Extraia os seguintes dados deste relatório de liquidação/venda de mangas:
            
            1. Nome da empresa
            2. Número do contêiner
            3. Comissão (percentual e valor)
            4. Valor total
            5. Valor líquido (Net Amount)
            6. Moeda
            7. Lista de produtos com:
               - Tipo de manga
               - Tamanho/calibre
               - Quantidade
               - Preço unitário
               - Preço total
               - Moeda
               - Referência/código
            
            Texto do relatório:
            {texto_completo[:4000]}  # Limitar para não exceder o contexto
            
            Responda apenas em formato JSON, seguindo exatamente esta estrutura:
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
            """
            
            # Fazer chamada à API
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Você é um assistente especializado em extrair dados estruturados de relatórios de liquidação e vendas de frutas."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            
            # Extrair resposta
            resposta = response.choices[0].message.content
            
            # Extrair JSON da resposta
            json_match = re.search(r'```json\s*(.*?)\s*```', resposta, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = resposta
            
            # Limpar e carregar JSON
            json_str = re.sub(r'[^\x00-\x7F]+', '', json_str)  # Remover caracteres não ASCII
            dados = json.loads(json_str)
            
            return dados
        except Exception as e:
            logger.error(f"Erro na extração com OpenAI: {str(e)}")
            return {}
    
    def mesclar_dados(self, dados_basicos: Dict[str, Any], dados_openai: Dict[str, Any]) -> Dict[str, Any]:
        """
        Mescla dados extraídos por diferentes métodos
        
        Args:
            dados_basicos (Dict[str, Any]): Dados extraídos pelo método básico
            dados_openai (Dict[str, Any]): Dados extraídos pela OpenAI
            
        Returns:
            Dict[str, Any]: Dados mesclados
        """
        dados_mesclados = dados_basicos.copy()
        
        # Mesclar dados principais
        for campo, valor in dados_openai.get("dados_principais", {}).items():
            # Se o campo está vazio nos dados básicos e tem valor nos dados da OpenAI
            if not dados_mesclados["dados_principais"].get(campo) and valor:
                dados_mesclados["dados_principais"][campo] = valor
        
        # Mesclar produtos
        # Se não temos produtos nos dados básicos mas temos nos dados da OpenAI
        if not dados_mesclados["produtos"] and dados_openai.get("produtos"):
            dados_mesclados["produtos"] = dados_openai.get("produtos", [])
        # Se temos menos produtos nos dados básicos do que nos dados da OpenAI
        elif len(dados_mesclados["produtos"]) < len(dados_openai.get("produtos", [])):
            dados_mesclados["produtos"] = dados_openai.get("produtos", [])
        # Se temos o mesmo número ou mais produtos, complementar informações
        else:
            for i, produto_openai in enumerate(dados_openai.get("produtos", [])):
                if i < len(dados_mesclados["produtos"]):
                    produto_mesclado = dados_mesclados["produtos"][i]
                    
                    # Complementar campos vazios
                    for campo, valor in produto_openai.items():
                        if not produto_mesclado.get(campo) and valor:
                            produto_mesclado[campo] = valor
        
        return dados_mesclados
    
    def generate_signature(self, pdf_path: str) -> str:
        """
        Gera uma assinatura única para o PDF baseada em seu conteúdo
        
        Args:
            pdf_path (str): Caminho para o arquivo PDF
            
        Returns:
            str: Assinatura única do PDF
        """
        try:
            # Ler o conteúdo do arquivo
            with open(pdf_path, 'rb') as f:
                content = f.read()
            
            # Criar hash do conteúdo
            content_hash = hashlib.md5(content).hexdigest()
            
            # Criar hash do nome do arquivo
            filename = os.path.basename(pdf_path)
            name_hash = hashlib.md5(filename.encode('utf-8')).hexdigest()
            
            # Combinar os hashes para criar uma assinatura única
            signature = f"{content_hash[:16]}_{name_hash[:8]}"
            return signature
        except Exception as e:
            logger.error(f"Erro ao gerar assinatura do PDF: {str(e)}")
            return hashlib.md5(pdf_path.encode('utf-8')).hexdigest()

# Função para teste
def test_extrator():
    """
    Função para testar o extrator
    """
    import sys
    
    if len(sys.argv) < 2:
        print("Uso: python extrator_pdf_learning_fixed.py <caminho_do_pdf>")
        return
    
    pdf_path = sys.argv[1]
    api_key = sys.argv[2] if len(sys.argv) > 2 else None
    
    extrator = ExtratorPDFLearning(api_key=api_key)
    dados = extrator.extrair_dados(pdf_path)
    
    print(json.dumps(dados, indent=4, ensure_ascii=False))

if __name__ == "__main__":
    test_extrator()
