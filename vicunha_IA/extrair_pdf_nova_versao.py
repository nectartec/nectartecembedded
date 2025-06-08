import streamlit as st
import PyPDF2
import google.generativeai as genai
import os
from dotenv import load_dotenv # Mantido para compatibilidade, mas st.secrets é preferível
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import platform
import tempfile
import logging
import base64
import traceback
# --- Configuração Inicial do Streamlit (DEVE SER A PRIMEIRA CHAMADA) ---
st.set_page_config(page_title="Extrator de Dados de PDF com Gemini e OCR", layout="wide")

# --- Configura a API do Gemini ---
# Usando st.secrets para segurança da chave
try:
    GEMINI_API_KEY = st.secrets["GEMINI"]["GEMINI_API_KEY"]
except KeyError:
    st.error("Chave de API do Gemini não encontrada em `st.secrets`. Por favor, configure `GEMINI_API_KEY` em seu arquivo `.streamlit/secrets.toml`.")
    st.stop()
# Configurar Tesseract baseado no sistema operacional
if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
genai.configure(api_key=GEMINI_API_KEY)

# --- Configura o caminho para o executável do Tesseract OCR (AJUSTE CONFORME SUA INSTALAÇÃO) ---
# Se o Tesseract não estiver no PATH do seu sistema, descomente e ajuste a linha abaixo:
# No Windows, pode ser algo como: pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
# No Linux/macOS, pode ser: pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract' ou '/usr/local/bin/tesseract'
# Tente comentar a linha abaixo primeiro para ver se ele encontra no PATH automaticamente.
try:
    pytesseract.get_tesseract_version() # Testa se Tesseract está acessível
except pytesseract.TesseractNotFoundError:
    st.error("Tesseract OCR não encontrado. Por favor, instale-o (https://tesseract-ocr.github.io/tessdoc/Installation.html) e/ou configure o caminho em 'pytesseract.pytesseract.tesseract_cmd'.")
    st.stop()


# --- Função para listar modelos Gemini disponíveis (para depuração) ---
st.sidebar.subheader("Modelos Gemini Disponíveis:")
model_name = 'gemini-1.5-flash-latest' # Modelo mais recente e com bom custo-benefício
found_target_model = False
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            st.sidebar.write(f"- {m.name}")
            if m.name == f'models/{model_name}': # Verifica se o modelo alvo está na lista
                found_target_model = True
except Exception as e:
    st.sidebar.error(f"Erro ao listar modelos: {e}")

if not found_target_model:
    st.warning(f"O modelo '{model_name}' pode não estar disponível para sua conta/região. Tentando 'gemini-pro' como fallback.")
    model_name = 'gemini-pro' # Fallback para um modelo mais comum
    # Você pode adicionar mais lógica de fallback ou parar se nenhum modelo desejado for encontrado

try:
    model = genai.GenerativeModel(model_name)
except Exception as e:
    st.error(f"Erro ao inicializar o modelo '{model_name}': {e}")
    st.stop()
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
            st.error(f"Erro ao converter PDF para imagens: {str(e)}")
            
            # Alternativa: exibir PDF como iframe
            base64_pdf = base64.b64encode(pdf_file.getvalue()).decode('utf-8')
            pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
            st.markdown(pdf_display, unsafe_allow_html=True)
        
        # Limpar arquivo temporário
        os.unlink(temp_path)
        
    except Exception as e:
        st.error(f"Erro ao exibir PDF: {str(e)}")
        st.error(traceback.format_exc())
        st.error(f"Erro ao exibir o PDF: {str(e)}")
# --- Funções de Extração de Texto ---
def extract_text_from_native_pdf(uploaded_file_bytes_io):
    """Extrai texto de um PDF nativo (com texto selecionável) usando PyPDF2."""
    text = ""
    try:
        pdf_reader = PyPDF2.PdfReader(uploaded_file_bytes_io)
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            text += page.extract_text()
    except Exception as e:
        # Erros aqui podem indicar PDF corrompido ou que não é nativo, mas tentaremos OCR depois
        print(f"DEBUG: Erro PyPDF2 (pode ser benigno): {e}")
        pass
    return text

def extract_text_with_ocr(uploaded_file_bytes_io):
    """Extrai texto de um PDF usando OCR (para PDFs de imagem) com PyMuPDF e Tesseract."""
    text = ""
    try:
        # Resetar o ponteiro do arquivo para garantir que fitz possa lê-lo desde o início
        doc = fitz.open(stream=uploaded_file_bytes_io.read(), filetype="pdf")

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            # Renderiza a página como uma imagem (pixmap) com alta resolução para OCR
            # matrix=fitz.Matrix(3, 3) para 300 DPI, ajuste conforme necessário
            pix = page.get_pixmap(matrix=fitz.Matrix(3, 3))

            # Converte o pixmap para um objeto PIL Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # Realiza OCR na imagem (adicione mais idiomas se necessário, ex: 'por+eng+spa')
            page_text = pytesseract.image_to_string(img, lang='por+eng')
            text += page_text + "\n\n" # Adiciona quebra de linha entre páginas

        doc.close()
    except pytesseract.TesseractNotFoundError:
        st.error("Tesseract OCR não encontrado. Por favor, instale-o e/ou configure o caminho em 'pytesseract.pytesseract.tesseract_cmd'.")
        return None
    except Exception as e:
        st.error(f"Erro ao realizar OCR no PDF: {e}")
        st.info("Certifique-se de que o Tesseract OCR está instalado e acessível (verifique o PATH ou o caminho configurado).")
        return None
    return text

def get_gemini_extraction(text_content, extraction_prompt):
    """Envia o texto para o Gemini e retorna a extração."""
    if not text_content.strip():
        st.warning("Nenhum texto válido foi extraído do PDF para enviar ao Gemini.")
        return None

    # Ajustado o prompt para ser mais direto sobre o formato JSON e as instruções
    full_prompt = f"""
    Sua tarefa é analisar o texto fornecido de um PDF e extrair informações específicas.
    O texto pode conter dados de relatórios de liquidação, faturas ou documentos similares.
    
    Extraia os seguintes dados:
    
    1.  **Dados Principais (objeto JSON):**
        -   `empresa_ou_fornecedor`: Nome da empresa ou fornecedor.
        -   `numero_container`: O número do contêiner.
        -   `comissao_percentual`: A porcentagem da comissão (se encontrada).
        -   `comissao_valor`: O valor da comissão.
        -   `valor_total`: O valor total geral.
        -   `net_amount`: O valor líquido (se diferente do valor total).
        -   `moeda`: A moeda utilizada (ex: "€", "USD", "BRL").
    
    2.  **Lista de Produtos (array de objetos JSON):**
        Para cada produto ou item de linha encontrado na seção de produtos, extraia:
        -   `tipo`: Tipo do produto (ex: "Mango Carton").
        -   `tamanho`: Tamanho ou especificação do produto (ex: "6CT 4KG Palmer Conventional Brazil", "8CT 4KG").
        -   `quantidade`: A quantidade do produto.
        -   `preco_unitario`: O preço unitário (se disponível ou calculável).
        -   `preco_total_item`: O preço total para aquela linha de item.
        -   `moeda_item`: A moeda específica para o item (se diferente da moeda principal).
        -   `referencia`: O número de referência associado ao item.
        -   `currency_rate`: A taxa de câmbio (se disponível).
        
    **Formato da Saída:**
    Retorne **apenas** um objeto JSON no seguinte formato. Se um campo não for encontrado, use `null` para o valor.

    ```json
    {{
      "dados_principais": {{
        "empresa_ou_fornecedor": "...",
        "numero_container": "...",
        "comissao_percentual": null,
        "comissao_valor": null,
        "valor_total": null,
        "net_amount": null,
        "moeda": "..."
      }},
      "produtos": [
        {{
          "tipo": "...",
          "tamanho": "...",
          "quantidade": null,
          "preco_unitario": null,
          "preco_total_item": null,
          "moeda_item": "...",
          "referencia": "...",
          "currency_rate": null
        }}
        // ... outros produtos
      ]
    }}
    ```
    
    **Considerações:**
    -   Os campos podem estar em inglês, português ou espanhol. Normalize para as chaves JSON em português conforme o formato solicitado.
    -   Seja preciso na extração e mantenha os valores numéricos e de moeda originais.
    -   Ignore quaisquer linhas de 'Total' para categorias específicas de produtos.
    
    **Texto para Análise:**
    {text_content}
    """

    with st.spinner("Analisando o texto com Gemini... (Isso pode levar um tempo para PDFs grandes/complexos)"):
        try:
            response = model.generate_content(full_prompt)
            return response.text
        except Exception as e:
            st.error(f"Erro ao chamar a API do Gemini: {e}")
            st.info("Verifique se o seu prompt não é muito complexo ou se o modelo tem capacidade de tokens suficiente para o texto.")
            return None

# --- Interface Streamlit Principal ---
st.title("📄 Extrator de Dados de PDF com Gemini e OCR")
st.markdown("""
Este aplicativo permite que você carregue um PDF (nativo ou escaneado/imagem) e use a inteligência artificial do Google Gemini para extrair informações específicas do conteúdo.
""")

st.warning("""
**Atenção:** A qualidade da extração de PDFs escaneados (com OCR) depende muito da clareza da imagem e da precisão do Tesseract. Para PDFs muito complexos ou de baixa resolução, a extração pode ser imprecisa.
""")

uploaded_file = st.file_uploader("Carregue seu arquivo PDF", type="pdf")
st.session_state.pdf_content = uploaded_file
if uploaded_file is not None:
    st.success(f"PDF carregado: {uploaded_file.name}")
    
    # Exibir PDF
    if st.session_state.pdf_content:
        st.subheader("Visualização do PDF")
        display_pdf(st.session_state.pdf_content)

    # Para garantir que o arquivo possa ser lido várias vezes por diferentes libs,
    # armazene o conteúdo em um BytesIO
    file_content_bytes_io = io.BytesIO(uploaded_file.getvalue())

    pdf_text = ""
    extraction_method = "desconhecido"

    # Tenta extrair texto nativo primeiro
    pdf_text_native = extract_text_from_native_pdf(io.BytesIO(file_content_bytes_io.getvalue())) # Passa uma cópia para PyPDF2

    if pdf_text_native and pdf_text_native.strip(): # Se PyPDF2 extraiu texto válido
        pdf_text = pdf_text_native
        extraction_method = "Texto Nativo (PyPDF2)"
    else:
        st.info("Texto nativo não encontrado ou vazio. Tentando OCR para PDFs de imagem...")
        # Se não houver texto nativo, tenta OCR
        # Resetar o ponteiro do arquivo para o início para a função OCR
        file_content_bytes_io.seek(0)
        pdf_text_ocr = extract_text_with_ocr(file_content_bytes_io)
        if pdf_text_ocr and pdf_text_ocr.strip():
            pdf_text = pdf_text_ocr
            extraction_method = "OCR (PyMuPDF + Tesseract)"
        else:
            st.error("Não foi possível extrair texto do PDF usando texto nativo ou OCR. O arquivo pode estar vazio, corrompido, ou a qualidade da imagem é muito baixa para OCR.")
            st.stop() # Parar aqui se não houver texto para processar

    if pdf_text:
        st.subheader(f"Texto Extraído do PDF ({extraction_method})")
        # Ajustado para exibir mais texto caso o PDF seja grande e o OCR gere muito texto
        st.text_area("Pré-visualização do texto", pdf_text[:8000] + "\n\n..." if len(pdf_text) > 8000 else pdf_text, height=400)

        st.subheader("O que você deseja extrair?")
        st.info("""
        Seu prompt de extração é muito importante! Ele já está configurado no código para extrair
        'Dados Principais' e 'Lista de Produtos' no formato JSON.
        Você pode ajustar a descrição do prompt na função `get_gemini_extraction` se precisar de algo diferente.
        """)

        # O prompt de extração agora é fixo dentro da função get_gemini_extraction para
        # garantir o formato JSON desejado. O usuário não precisa digitá-lo toda vez.
        # Caso queira que o usuário personalize, descomente a linha abaixo e remova o prompt fixo da função.
        # extraction_prompt = st.text_area("Seu prompt personalizado (se precisar sobrescrever o padrão):", height=100)
        # Por enquanto, o prompt é enviado diretamente pelo código.

        if st.button("Extrair Dados com Gemini"):
            # O prompt agora é passado vazio ou fixo, dependendo da sua escolha
            extracted_data = get_gemini_extraction(pdf_text, "Use o prompt interno para extração.")
            if extracted_data:
                st.subheader("Dados Extraídos pelo Gemini:")
                # Use st.json se a saída for estritamente JSON para melhor visualização
                try:
                    import json
                    st.json(json.loads(extracted_data))
                except json.JSONDecodeError:
                    st.markdown(extracted_data) # Caso o Gemini não retorne JSON válido
            else:
                st.warning("Nenhum dado foi extraído. Tente refinar o prompt (se personalizável) ou verificar o texto extraído.")