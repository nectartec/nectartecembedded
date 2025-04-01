import openai
import streamlit as st
openai_key = st.secrets["OPENAI_API_KEY"] 
openai.api_key = openai_key
try:
    response = openai.models.list()
    print("OpenAI API funcionando corretamente!")
except Exception as e:
    print(f"Erro ao conectar à OpenAI: {e}")

thread = openai.beta.threads.create()
print(f"Thread criada: {thread}")  # Verifica se a thread foi criada corretamente

messages = openai.beta.threads.messages.list(thread_id=thread.id)
print(messages)
