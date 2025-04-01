import openai
import streamlit as st
from supabase import create_client, Client 

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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
 

print(f"Versão do OpenAI: {openai.__version__}") 