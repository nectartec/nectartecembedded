import streamlit as st
import pdfplumber
import pandas as pd
import re
import pytesseract
from pdf2image import convert_from_bytes
from io import BytesIO
import json
import numpy as np
from datetime import datetime
import platform
import logging
from typing import Dict, List, Tuple, Optional
import openai
from openai import OpenAI


# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configurar Tesseract baseado no sistema operacional
if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

class PDFExtractor:
    def __init__(self, openai_api_key: Optional[str] = None):
        self.openai_client = None
        if openai_api_key:
            try:
                self.openai_client = OpenAI(api_key=openai_api_key)
            except Exception as e:
                logger.error(f"Erro ao configurar OpenAI: {e}")
        
        # Padrões de detecção de fornecedores
        self.fornecedor_patterns = {
            "TROPICO_SPAIN": {
                "keywords": ["tropico spain", "exceltrop", "cuenta de ventas", "finobrasa", "caiu", "cgmu"],
                "container_pattern": r"(CAIU|CGMU|MSCU|TCLU)\d{7}",
                "commission_pattern": r"comision\s*(\d+)%",
                "total_pattern": r"total\s*€?\s*([\d,\.]+)\s*€?",
                "moeda": "EUR"
            },
            "CULTIPALTA": {
                "keywords": ["cultipalta", "liquidación", "finobrasa", "mango palmer"],
                "container_pattern": r"(CGMU|CAIU|MSCU|TCLU)\d{7}",
                "commission_pattern": r"(\d+\.?\d*)%\s*comisión",
                "total_pattern": r"total\s*ventas\s*€?\s*([\d,\.]+)",
                "moeda": "EUR"
            },
            "PANORAMA": {
                "keywords": ["panorama produce", "account sale"],
                "container_pattern": r"container[:\s]*([A-Z]{4}\d{7})",
                "commission_pattern": r"commission[:\s]*(\d+\.?\d*)%",
                "total_pattern": r"total[:\s]*\$?([\d,\.]+)",
                "moeda": "USD"
            },
            "DIRBECK": {
                "keywords": ["anton durbeck", "account sale", "kommission"],
                "container_pattern": r"container[:\s]*([A-Z]{4}\d{7})",
                "commission_pattern": r"kommission[:\s]*(\d+\.?\d*)\s*%",
                "total_pattern": r"total.*eur[:\s]*([\d,\.]+)",
                "moeda": "EUR"
            },
            "NATURES_PRIDE": {
                "keywords": ["nature's pride", "accountsale", "sea container"],
                "container_pattern": r"sea container no\.?[:\s]*([A-Z]{4}\d{7})",
                "commission_pattern": r"commission[:\s]*(\d+\.?\d*)\s*%",
                "total_pattern": r"total[:\s]*([\d,\.]+)",
                "moeda": "EUR"
            }
        }
    
    def extract_text_from_pdf(self, file) -> str:
        """Extração de texto aprimorada com fallback para OCR"""
        text = ""
        try:
            # Primeiro tenta extrair texto diretamente
            with pdfplumber.open(file) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            
            # Se não conseguiu extrair texto suficiente, usa OCR
            if len(text.strip()) < 100:
                logger.info("Texto insuficiente, aplicando OCR...")
                file.seek(0)
                images = convert_from_bytes(file.read())
                ocr_text = ""
                for img in images:
                    ocr_text += pytesseract.image_to_string(img, config='--psm 6') + "\n"
                
                # Usa o texto do OCR se for mais completo
                if len(ocr_text.strip()) > len(text.strip()):
                    text = ocr_text
                    
        except Exception as e:
            logger.error(f"Erro na extração: {e}")
            return f"Erro na extração: {str(e)}"
        
        return text.strip()
    
    def clean_text(self, text: str) -> str:
        """Limpeza e normalização do texto"""
        if not text:
            return ""
        
        # Normalizar quebras de linha e espaços
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n\s*\n', '\n', text)
        
        # Remover caracteres especiais problemáticos
        text = re.sub(r'[^\w\s\.,\-\+\(\)\[\]€$%:/]', ' ', text)
        
        return text.strip()
    
    def detect_supplier(self, text: str) -> Tuple[str, Dict]:
        """Detecta o fornecedor baseado no conteúdo do texto"""
        text_lower = text.lower()
        
        for supplier, patterns in self.fornecedor_patterns.items():
            score = 0
            # Contar palavras-chave encontradas
            for keyword in patterns["keywords"]:
                if keyword in text_lower:
                    score += 1
            
            # Se encontrou pelo menos 2 palavras-chave, considera como match
            if score >= 2:
                return supplier, patterns
        
        # Fallback para detecção genérica
        return "GENERIC", {
            "keywords": [],
            "container_pattern": r"([A-Z]{4}\d{7})",
            "commission_pattern": r"(\d+\.?\d*)\s*%",
            "total_pattern": r"([\d,\.]+)",
            "moeda": "EUR"
        }
    
    def extract_with_patterns(self, text: str, patterns: Dict) -> Dict:
        """Extrai dados usando padrões regex específicos do fornecedor"""
        resultado = {
            "dados_principais": {},
            "produtos": []
        }
        
        # Extrair número do contêiner
        container_match = re.search(patterns["container_pattern"], text, re.IGNORECASE)
        if container_match:
            resultado["dados_principais"]["Número do contêiner"] = container_match.group(1)
        
        # Extrair comissão
        commission_match = re.search(patterns["commission_pattern"], text, re.IGNORECASE)
        if commission_match:
            resultado["dados_principais"]["Comissão %"] = commission_match.group(1)
        
        # Extrair valor total
        total_match = re.search(patterns["total_pattern"], text, re.IGNORECASE)
        if total_match:
            valor_total = total_match.group(1).replace(',', '.')
            resultado["dados_principais"]["Valor total"] = valor_total
        
        # Definir moeda
        resultado["dados_principais"]["Moeda"] = patterns.get("moeda", "EUR")
        
        return resultado
    
    def extract_products_advanced(self, text: str, supplier: str) -> List[Dict]:
        """Extração avançada de produtos baseada no fornecedor ou de forma genérica."""
        produtos = []
        
        # --- Lógica específica para fornecedores existentes (manter se necessário) ---
        if supplier == "TROPICO_SPAIN":
            pattern = r"(MAP\d+BR\d*)\s+(\d+)\s+(\d+)\s+([\d,\.]+)\s*€\s+([\d,\.]+)\s*€"
            matches = re.findall(pattern, text)
            for match in matches:
                produto = {
                    "tipo": f"Mango {match[0]}",
                    "tamanho": "4KG",
                    "quantidade": match[2],
                    "preco_unitario": match[3].replace(',', '.'),
                    "preco_total": match[4].replace(',', '.'),
                    "moeda": "EUR",
                    "referencia": "N/A" # Adicionar campo de referência
                }
                produtos.append(produto)
            # Retorna se encontrou produtos específicos do fornecedor
            if produtos: return produtos
        
        # --- Lógica genérica para relatórios como o "Settlement Report" (Finobrasa/Robinson Fresh) ---
        # Definir a seção onde os produtos geralmente estão
        # O padrão pode precisar de ajuste dependendo de onde exatamente os produtos começam/terminam
        # Tente encontrar o bloco entre 'Freight - Charge to Grower' e o primeiro 'Total' de produto,
        # ou antes de 'Pick & Pack Recovery'
        
        # Padrão para linhas de produto (tentando ser mais genérico para "Mango Carton")
        # Captura: Descrição, ref, Currency Rate, Sum of invcqnt, Sum of Currency Converted Total Amount
        # Ex: Mango Carton 6CT 4KG Palmer Conventional Brazil   0.907826   619477   €   560   3,640.00
        
        # Refinando o padrão para ser mais robusto:
        # A descrição do produto pode ter espaços e ser longa
        # O ref pode ser um número (619477)
        # O Currency Rate pode ser um float
        # A moeda é €
        # Sum of invcqnt pode ser um número
        # Sum of Currency Converted Total Amount pode ser um número com vírgula/ponto
        
        # Padrão ajustado para capturar as linhas de produto individuais:
        # Pega "Mango Carton" até "Brazil"
        # Opcional: captura o ref
        # Opcional: captura o Currency Rate
        # A moeda (€)
        # A quantidade
        # O valor total
        product_line_pattern = r"(Mango Carton\s+\d+CT\s+\d+KG\s+Palmer\s+Conventional\s+Brazil)\s+(?:(\d+\.?\d*)\s+)?(?:(\d+\.?\d*)\s+)?€\s+(\d+)\s+([\d,\.]+)"
        
        # O padrão acima pode ser muito complexo, vamos tentar extrair as linhas e depois parseá-las.
        # Primeiro, identificar a seção de produtos.
        # No seu PDF, começa após 'Freight - Charge to Grower' e termina antes de 'Pick & Pack Recovery upon shipment' ou 'Repacking Charges'.
        
        product_section_match = re.search(r"Freight - Charge to Grower.*?((?:Mango Carton.*?EUR|\s*\d+\s*€\s*[\d,\.]+\s*)+)(?:\s*Pick & Pack Recovery upon shipment|\s*Repacking Charges|Grand Total)", text, re.DOTALL | re.IGNORECASE)
        
        if product_section_match:
            product_block = product_section_match.group(1)
            # Dividir o bloco em linhas para processamento
            lines = product_block.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if "Mango Carton" in line and "Total" not in line and "€" in line:
                    # Padrão mais flexível para capturar os campos relevantes em uma linha
                    # Ex: Mango Carton 6CT 4KG Palmer Conventional Brazil 0.907826 619477 € 560 3,640.00
                    # Ex: Mango Carton 8CT 4KG Palmer Conventional Brazil 619357 0.92704 € 168
                    # Os campos podem variar de posição (ref, rate)
                    
                    # Regex para capturar os grupos de dados:
                    # 1: Descrição do produto (e.g., "Mango Carton 6CT 4KG Palmer Conventional Brazil")
                    # 2: Opcional: ref (619477) ou Currency Rate (0.907826) ou quantidade inicial
                    # 3: Opcional: o segundo valor numérico (pode ser o que sobrou, ou ref, ou rate)
                    # ...
                    # 4: Quantidade (Sum of invcqnt - o número antes do € na sua imagem)
                    # 5: Preço Total (Sum of Currency Converted Total Amount)
                    
                    # Tentativa de pattern para capturar: descrição, um ou dois números intermediários (rate/ref), moeda, quantidade, total
                    match = re.search(r"(Mango Carton\s+\d+CT\s+\d+KG\s+Palmer\s+Conventional\s+Brazil)\s+(?:([\d,\.]+)\s+)?(?:([\d,\.]+)\s+)?€\s+(\d+)\s+([\d,\.]+)", line, re.IGNORECASE)
                    
                    if match:
                        tipo_produto = match.group(1).strip()
                        # Tenta extrair CT e KG do tipo_produto
                        ct_match = re.search(r"(\d+)CT", tipo_produto, re.IGNORECASE)
                        kg_match = re.search(r"(\d+)KG", tipo_produto, re.IGNORECASE)
                        
                        tamanho_str = ""
                        if ct_match: tamanho_str += f"{ct_match.group(1)}CT "
                        if kg_match: tamanho_str += f"{kg_match.group(1)}KG"
                        tamanho_str = tamanho_str.strip()
                        
                        quantidade = match.group(4)
                        preco_total = match.group(5).replace(',', '.') # Substituir vírgula por ponto para float
                        
                        # Os grupos 2 e 3 podem ser Currency Rate ou Shipper Ref.
                        # Precisamos de uma lógica para discernir. No seu PDF, 'ref' vem *antes* de 'Currency Rate' em algumas linhas
                        # e depois em outras. Isso é um desafio para regex puro.
                        # Por exemplo:
                        # Mango Carton 6CT 4KG Palmer Conventional Brazil 0.907826 619477 € 560 3,640.00 -> Rate, Ref
                        # Mango Carton 8CT 4KG Palmer Conventional Brazil 619357 0.92704 € 168 -> Ref, Rate
                        
                        # Para simplificar, vamos extrair o que sabemos e o resto pode ser 'N/A'
                        # ou a IA pode ajudar a preencher.
                        
                        # Para este padrão específico, o grupo 2 seria o primeiro número (rate ou ref),
                        # o grupo 3 o segundo (ref ou rate).
                        # O PDF mostra o ref e a taxa de câmbio, não o preço unitário diretamente na linha de produto.
                        # O preço unitário seria o preco_total / quantidade.

                        preco_unitario = float(preco_total) / int(quantidade) if int(quantidade) > 0 else 0
                        
                        produto = {
                            "tipo": tipo_produto,
                            "tamanho": tamanho_str,
                            "quantidade": quantidade,
                            "preco_unitario": f"{preco_unitario:.2f}", # Formatar para 2 casas decimais
                            "preco_total": preco_total,
                            "moeda": "€",
                            "referencia": match.group(2) if match.group(2) else "N/A" # Ou tentar inferir ref/rate
                        }
                        produtos.append(produto)
                    
                    # Linhas que podem ter só o ref e a quantidade, sem o valor total (ex: 619357 € 52)
                    # Este é um problema, pois 'Sum of Currency Converted Total Amount' está em branco.
                    # Nesses casos, o PDF está incompleto ou o valor está implícito em outro lugar.
                    # Se você quer *todas* as linhas, mesmo as incompletas, o regex precisará ser mais permissivo.
                    # Atualmente, o padrão `([\d,\.]+)` espera um valor total.
                    # Se o valor total for opcional, o padrão seria `(?:([\d,\.]+))?`
                    # Mas para o exemplo do PDF, as linhas sem valor total não estão na mesma coluna.
                    # O "Mango Carton 6CT 4KG Palmer Conventional Brazil 619357 0.92704 € 52" é uma linha
                    # onde o valor "52" está na coluna `Sum of invcqnt` mas `Sum of Currency Converted Total Amount`
                    # está vazio. Isso significa que a coluna `Sum of invcqnt` e `Sum of Currency Converted Total Amount`
                    # são as colunas `Sum of invcqnt Sum of Currency Converted Total Amount`.
                    # Este layout é confuso no PDF.

                    # Para capturar as linhas que faltam o valor final, precisamos de um regex que permita isso.
                    # Ex: Mango Carton 6CT 4KG Palmer Conventional Brazil 619357 0.92704 € 52
                    # Aqui, "52" é a quantidade. O valor total está faltando.
                    # A melhor abordagem aqui é usar o `pdfplumber` para extrair tabelas, se ele conseguir.

        # Fallback para regex genérico de "Mango Carton" se não houver um fornecedor específico ou a extração falhar.
        # Esta é a seção que precisa de mais atenção para o seu PDF.
        # Tente capturar todas as linhas que começam com "Mango Carton" e não são totais.
        
        lines = text.split('\n')
        for line in lines:
            line_cleaned = line.strip()
            # Verifica se é uma linha de produto e não uma linha de total
            if "Mango Carton" in line_cleaned and "Total" not in line_cleaned and "€" in line_cleaned:
                # Regex mais genérico para capturar o que parece ser uma linha de produto
                # Tenta capturar descrição, um ou dois números como ref/rate, a moeda, a quantidade e o total (opcional)
                # O total é o último número antes da quebra de linha.
                
                # Exemplo de linha: "Mango Carton 6CT 4KG Palmer Conventional Brazil 0.907826 619477 € 560 3,640.00"
                # Exemplo de linha incompleta: "Mango Carton 6CT 4KG Palmer Conventional Brazil 619357 0.92704 € 52"
                
                match = re.search(r"^(Mango Carton.*?Brazil)\s+(?:([\d,\.]+)\s+)?(?:([\d,\.]+)\s+)?€\s+(\d+)\s*(?:([\d,\.]+))?$", line_cleaned, re.IGNORECASE)
                
                if match:
                    tipo_produto = match.group(1).strip()
                    quantidade = match.group(4)
                    preco_total = match.group(5) # Pode ser None se não houver valor
                    
                    tamanho_str = ""
                    ct_match = re.search(r"(\d+)CT", tipo_produto, re.IGNORECASE)
                    kg_match = re.search(r"(\d+)KG", tipo_produto, re.IGNORECASE)
                    if ct_match: tamanho_str += f"{ct_match.group(1)}CT "
                    if kg_match: tamanho_str += f"{kg_match.group(1)}KG"
                    tamanho_str = tamanho_str.strip()
                    
                    # Converter valores para float, tratando None ou vazio
                    quantidade_int = int(quantidade) if quantidade else 0
                    preco_total_float = float(preco_total.replace(',', '.')) if preco_total else 0.0
                    preco_unitario_float = preco_total_float / quantidade_int if quantidade_int > 0 else 0.0
                    
                    # Tenta discernir ref e currency rate
                    ref_or_rate_1 = match.group(2)
                    ref_or_rate_2 = match.group(3)
                    
                    referencia = "N/A"
                    currency_rate = "N/A"

                    # Uma heurística simples para tentar atribuir:
                    # Se um dos valores tem muitos dígitos e o outro é menor (0.something),
                    # o menor é provavelmente a taxa, o maior a referência.
                    if ref_or_rate_1 and ref_or_rate_2:
                        try:
                            val1 = float(ref_or_rate_1.replace(',', '.'))
                            val2 = float(ref_or_rate_2.replace(',', '.'))
                            if val1 < 1.0 and val2 > 100: # Val1 é taxa, Val2 é ref
                                currency_rate = ref_or_rate_1
                                referencia = ref_or_rate_2
                            elif val2 < 1.0 and val1 > 100: # Val2 é taxa, Val1 é ref
                                currency_rate = ref_or_rate_2
                                referencia = ref_or_rate_1
                            else: # Heurística mais complexa ou ambos são numéricos e não fica claro
                                referencia = ref_or_rate_1 # ou concatena, ou decide um padrão
                                currency_rate = ref_or_rate_2
                        except ValueError: # Um dos valores não é numérico (pode ser ref com letras, etc.)
                            referencia = ref_or_rate_1 if not re.match(r'^\d+\.\d+$', ref_or_rate_1) else ref_or_rate_2
                            currency_rate = ref_or_rate_2 if re.match(r'^\d+\.\d+$', ref_or_rate_2) else ref_or_rate_1

                    elif ref_or_rate_1: # Se apenas um número intermediário
                        # Assumir que é referência se não for claramente uma taxa
                        if float(ref_or_rate_1.replace(',', '.')) < 2.0 and '.' in ref_or_rate_1:
                            currency_rate = ref_or_rate_1
                        else:
                            referencia = ref_or_rate_1
                    
                    produto = {
                        "tipo": tipo_produto,
                        "tamanho": tamanho_str,
                        "quantidade": str(quantidade_int),
                        "preco_unitario": f"{preco_unitario_float:.2f}",
                        "preco_total": f"{preco_total_float:.2f}",
                        "moeda": "€",
                        "referencia": referencia,
                        "currency_rate": currency_rate # Adicionar a taxa de câmbio
                    }
                    produtos.append(produto)
        
        return produtos
    
    def _extract_size_from_text(self, text: str) -> str:
        """Extrai tamanho do produto do texto"""
        size_pattern = r"(\d+)\s*(KG|CT|SC)"
        match = re.search(size_pattern, text, re.IGNORECASE)
        return match.group(0) if match else "N/A"
    
    def _extract_price_from_parts(self, parts: List[str]) -> str:
        """Extrai preço unitário de uma lista de partes"""
        for part in parts:
            if re.match(r'^\d+[,\.]\d+$', part):
                return part.replace(',', '.')
        return "0"
    
    def _extract_total_from_parts(self, parts: List[str]) -> str:
        """Extrai preço total de uma lista de partes"""
        # Procura pelo maior valor numérico (geralmente é o total)
        max_value = 0
        max_str = "0"
        for part in parts:
            if re.match(r'^\d+[,\.]\d+$', part):
                try:
                    value = float(part.replace(',', '.'))
                    if value > max_value:
                        max_value = value
                        max_str = part.replace(',', '.')
                except:
                    continue
        return max_str
    
    def process_with_ai(self, text: str, supplier: str) -> Dict:
        """Processa o texto com IA quando disponível"""
        if not self.openai_client:
            return {"erro": "Cliente OpenAI não disponível"}
        
        system_prompt = f"""
        Você é um especialista em extrair dados de documentos de venda de produtos agrícolas.
        Extraia os seguintes dados do texto fornecido. Para os produtos, liste CADA LINHA INDIVIDUAL DE PRODUTO, mesmo que o nome do produto seja o mesmo, se os detalhes (como referência, quantidade, ou valor total) forem diferentes.

        1. Nome da empresa (fornecedor/produtor)
        2. Número do contêiner
        3. Percentual de comissão
        4. Valor da comissão
        5. Valor total da venda
        6. Valor líquido (Net Amount)
        7. Para CADA ITEM de produto (não apenas totais de grupo):
           - tipo (ex: "Mango Carton 6CT 4KG Palmer Conventional Brazil")
           - tamanho (ex: "6CT 4KG" - extraia do tipo)
           - quantidade (Sum of invcqnt)
           - preço unitário (Calcule a partir do preço total / quantidade, se possível, ou N/A)
           - preço total (Sum of Currency Converted Total Amount)
           - moeda
           - referência (Shipper Ref# ou outro código de referência para a linha de produto)
           - currency rate (a taxa de câmbio específica para a linha de produto)

        Tipo de documento detectado: {supplier}

        Retorne APENAS um JSON válido com a estrutura:
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
        # ... (restante do método process_with_ai)
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            
            content = response.choices[0].message.content
            
            # Tentar extrair JSON da resposta
            try:
                result = json.loads(content)
                return result
            except json.JSONDecodeError:
                # Tentar extrair JSON de dentro do texto
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(0))
                    return result
                else:
                    return {"erro": "Não foi possível extrair JSON válido da resposta da IA"}
                    
        except Exception as e:
            logger.error(f"Erro ao processar com IA: {e}")
            return {"erro": f"Erro na IA: {str(e)}"}
    
    def validate_and_clean_data(self, data: Dict) -> Dict:
        """Valida e limpa os dados extraídos"""
        if not isinstance(data, dict):
            return {"dados_principais": {}, "produtos": []}
        
        # Garantir estrutura básica
        if "dados_principais" not in data:
            data["dados_principais"] = {}
        if "produtos" not in data:
            data["produtos"] = []
        
        # Limpar valores numéricos
        campos_numericos = ["Comissão %", "Comissão Valor", "Valor total", "Net Amount"]
        for campo in campos_numericos:
            if campo in data["dados_principais"]:
                valor = str(data["dados_principais"][campo])
                # Remover caracteres não numéricos exceto ponto e vírgula
                valor_limpo = re.sub(r'[^\d,.]', '', valor)
                valor_limpo = valor_limpo.replace(',', '.')
                data["dados_principais"][campo] = valor_limpo
        
        # Validar produtos
        produtos_validos = []
        for produto in data["produtos"]:
            if isinstance(produto, dict) and produto.get("tipo"):
                # Garantir todos os campos
                produto_limpo = {
                    "tipo": produto.get("tipo", ""),
                    "tamanho": produto.get("tamanho", ""),
                    "quantidade": produto.get("quantidade", "0"),
                    "preço unitário": produto.get("preço unitário", "0"),
                    "preço total": produto.get("preço total", "0"),
                    "moeda": produto.get("moeda", "EUR")
                }
                produtos_validos.append(produto_limpo)
        
        data["produtos"] = produtos_validos
        return data
    
    def extract_data(self, file, use_ai: bool = True) -> Tuple[Dict, str]:
        """Método principal para extrair dados do PDF"""
        # Extrair texto
        text = self.extract_text_from_pdf(file)
        clean_text = self.clean_text(text)
        
        # Detectar fornecedor
        supplier, patterns = self.detect_supplier(clean_text)
        
        # Tentar extração com IA primeiro (se disponível)
        if use_ai and self.openai_client:
            resultado = self.process_with_ai(clean_text, supplier)
            if "erro" not in resultado:
                return self.validate_and_clean_data(resultado), supplier
        
        # Fallback para extração com regex
        resultado = self.extract_with_patterns(clean_text, patterns)
        
        # Extrair produtos
        produtos = self.extract_products_advanced(clean_text, supplier)
        resultado["produtos"] = produtos
        
        # Tentar extrair nome da empresa
        if supplier == "TROPICO_SPAIN" or supplier == "CULTIPALTA":
            resultado["dados_principais"]["Nome da empresa"] = "FINOBRASA"
        
        return self.validate_and_clean_data(resultado), supplier

def generate_sql_insert(data: Dict, supplier: str) -> str:
    """Gera SQL para inserção dos dados"""
    if not data or "dados_principais" not in data:
        return "-- Erro: Dados inválidos"
    
    dados = data["dados_principais"]
    produtos = data.get("produtos", [])
    
    sql = f"""-- Inserção de dados extraídos do PDF
-- Fornecedor detectado: {supplier}
-- Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

-- Inserir venda principal
INSERT INTO vendas (
    fornecedor,
    container,
    comissao_percentual,
    comissao_valor,
    valor_total,
    valor_liquido,
    moeda,
    tipo_documento,
    data_processamento
) VALUES (
    '{dados.get("Nome da empresa", "").replace("'", "''")}',
    '{dados.get("Número do contêiner", "").replace("'", "''")}',
    {dados.get("Comissão %", "0").replace(",", ".") or "0"},
    {dados.get("Comissão Valor", "0").replace(",", ".") or "0"},
    {dados.get("Valor total", "0").replace(",", ".") or "0"},
    {dados.get("Net Amount", "0").replace(",", ".") or "0"},
    '{dados.get("Moeda", "EUR")}',
    '{supplier}',
    CURRENT_TIMESTAMP
);

"""
    
    # Adicionar produtos se existirem
    if produtos:
        sql += "-- Inserir produtos\n"
        for i, produto in enumerate(produtos):
            sql += f"""INSERT INTO produtos_venda (
    venda_id,
    tipo_produto,
    tamanho,
    quantidade,
    preco_unitario,
    preco_total,
    moeda
) VALUES (
    LAST_INSERT_ID(),
    '{produto.get("tipo", "").replace("'", "''")}',
    '{produto.get("tamanho", "").replace("'", "''")}',
    {produto.get("quantidade", "0").replace(",", ".") or "0"},
    {produto.get("preço unitário", "0").replace(",", ".") or "0"},
    {produto.get("preço total", "0").replace(",", ".") or "0"},
    '{produto.get("moeda", "EUR")}'
);

"""
    
    return sql

def main():
    st.set_page_config(page_title="PDF Extractor Melhorado", layout="wide")
    st.title("🚀 PDF Extractor Melhorado")
    st.markdown("### Sistema inteligente de extração de dados de PDFs de fornecedores")
    
    # Configuração da API OpenAI
    OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "")
    openai_key = OPENAI_API_KEY #st.sidebar.text_input("🔑 OpenAI API Key", type="password")
    
    # Inicializar extrator
    extractor = PDFExtractor(openai_key if openai_key else None)
    
    # Opções
    use_ai = st.sidebar.checkbox("🤖 Usar IA (OpenAI)", value=bool(openai_key))
    show_details = st.sidebar.checkbox("🔍 Mostrar detalhes técnicos", value=False)
    
    # Upload de arquivos
    uploaded_files = st.file_uploader(
        "📎 Envie os arquivos PDF", 
        type="pdf", 
        accept_multiple_files=True
    )
    
    if uploaded_files:
        for uploaded_file in uploaded_files:
            st.subheader(f"📄 Processando: {uploaded_file.name}")
            
            try:
                # Extrair dados
                with st.spinner("Extraindo dados..."):
                    resultado, supplier = extractor.extract_data(uploaded_file, use_ai)
                
                # Mostrar fornecedor detectado
                st.success(f"🏢 Fornecedor detectado: **{supplier}**")
                
                # Mostrar dados principais
                st.markdown("#### 📊 Dados Principais")
                if resultado["dados_principais"]:
                    df_main = pd.DataFrame([resultado["dados_principais"]])
                    st.dataframe(df_main, use_container_width=True)
                else:
                    st.warning("Nenhum dado principal extraído")
                
                # Mostrar produtos
                st.markdown("#### 📦 Produtos")
                if resultado["produtos"]:
                    df_products = pd.DataFrame(resultado["produtos"])
                    st.dataframe(df_products, use_container_width=True)
                else:
                    st.info("Nenhum produto identificado")
                
                # Gerar SQL
                if st.button(f"🔄 Gerar SQL - {uploaded_file.name}", key=f"sql_{uploaded_file.name}"):
                    sql_code = generate_sql_insert(resultado, supplier)
                    st.code(sql_code, language="sql")
                    
                    # Download do SQL
                    st.download_button(
                        label="💾 Download SQL",
                        data=sql_code,
                        file_name=f"{uploaded_file.name.replace('.pdf', '')}_insert.sql",
                        mime="text/plain"
                    )
                
                # Mostrar detalhes técnicos
                if show_details:
                    with st.expander("🔧 Detalhes Técnicos"):
                        st.json(resultado)
                
                st.markdown("---")
                
            except Exception as e:
                st.error(f"❌ Erro ao processar {uploaded_file.name}: {str(e)}")
                logger.error(f"Erro no processamento: {e}")

if __name__ == "__main__":
    main()