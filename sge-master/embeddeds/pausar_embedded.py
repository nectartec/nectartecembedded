import requests
from embeddeds.models import Embedded
from django.shortcuts import get_object_or_404
def pause_power_bi_embedded():
    # Defina suas credenciais
    url = "https://api.powerbi.com/v1.0/myorg/reports/{reportId}/"
    headers = {
        "Authorization": "Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    # Lógica para pausar o serviço
    response = requests.put(url, headers=headers, json={"status": "paused"})
    
    if response.status_code == 200:
        print("Power BI Embedded pausado com sucesso.")
    else:
        print("Erro ao pausar o Power BI:", response.content)


report = get_object_or_404(Embedded)
# Pega as credenciais do banco de dados
client_id =report.CLIENT_ID
client_secret = report.CLIENT_SECRET
tenant_id = report.TENANT_ID
workspace_id = report.WORKSPACE_ID
report_id = report.REPORT_ID
dataset_id = report.DATASET_ID
pause_power_bi_embedded()