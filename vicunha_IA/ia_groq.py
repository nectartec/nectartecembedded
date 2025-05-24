import streamlit as st
from groq import Groq
import pdfplumber

# Configuração da API do Groq
GROQ_API_KEY = "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"  # Substitua com sua chave de API do Groq

def ler_pdf(file):
    texto = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            texto += page.extract_text()
    return texto

def processar_texto_groq(texto, prompt):
    # Inicialização do cliente Groq
    client = Groq(api_key=GROQ_API_KEY)
    
    # Parâmetros para o processamento
    messages = [
        {"role": "system", "content": "Meu nome é AccountsaleBot. Use a memória fornecida se relevante. Não responda nada que não esteja dentro de <INSTRUCAO></INSTRUCAO>"},
        {"role": "user", "content": prompt + texto} 
    ]
    
    try:
        # Chamada ao modelo
        completion = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=messages,
            temperature=0.7,  # Ajuste o temperature conforme necessário
        )
        
        if completion:
            # Acessando a resposta através de completion.choices[0].message.content
            return completion.choices[0].message.content
        else:
            return "Falha ao obter resposta do Groq."
            
    except Exception as e:
        return f"Erro ao processar o texto: {str(e)}"

def main():
    st.title("Leitura de PDFs com Groq")
    uploaded_file = st.file_uploader("Escolha um arquivo PDF", type=['pdf'])
    prompt = st.text_input("Digite o seu prompt:", "")
    
    if uploaded_file is not None:
        texto = ler_pdf(uploaded_file)
        st.write("Texto extraído do PDF:")
        st.write(texto)
        
        if st.button("Processar com Groq"):
            resultado = processar_texto_groq(texto, prompt)
            if resultado:
                st.write("Resultado do Groq:")
                st.write(resultado)
            else:
                st.error("Falha ao processar o texto com o Groq.")

if __name__ == "__main__":
    main()