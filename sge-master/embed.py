from flask import Flask, render_template_string, jsonify
import sqlite3
import requests

app = Flask(__name__)

# Can be set to 'MasterUser' or 'ServicePrincipal'
AUTHENTICATION_MODE = 'ServicePrincipal'

# Workspace Id in which the report is present
workspace_id = '017CDE99-646A-4FD2-8C54-17E2E33A8BC9'

# Report Id for which Embed token needs to be generated
report_id = '1a8338f0-8a78-4d27-be71-82a121a784cc'

# Id of the Azure tenant in which AAD app and Power BI report is hosted. Required only for ServicePrincipal authentication mode.
tenant_id = '71029506-45c7-4577-b71e-19beb180170f'

# Client Id (Application Id) of the AAD app
client_id = 'ec07d040-09ee-48e6-8604-3c23787e27cf'

# Client Secret (App Secret) of the AAD app. Required only for ServicePrincipal authentication mode.
client_secret = 'bqa8Q~iTCuy1jqrTvvFEsdFhvSEFpxACCnkJWdrW'

id_gerente = 1494

dataset_id = '27e67599-7017-4b2d-af39-dc01c3ba9a3a'


def get_access_token(client_id, client_secret, tenant_id):
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default"
    }
    
    response = requests.post(url, headers=headers, data=data)
    
    # Verifica se a resposta é válida antes de tentar converter para JSON
    if response.status_code != 200:
        print("Erro ao obter Access Token:", response.text)
        return None
    print ( response)
    try:
        return response.json().get("token")
    except requests.exceptions.JSONDecodeError:
        print("Resposta inválida ao obter Access Token:", response.text)
        return None



@app.route('/report/')
def report():
     
    access_token = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6ImltaTBZMnowZFlLeEJ0dEFxS19UdDVoWUJUayIsImtpZCI6ImltaTBZMnowZFlLeEJ0dEFxS19UdDVoWUJUayJ9.eyJhdWQiOiJodHRwczovL2FuYWx5c2lzLndpbmRvd3MubmV0L3Bvd2VyYmkvYXBpIiwiaXNzIjoiaHR0cHM6Ly9zdHMud2luZG93cy5uZXQvNzEwMjk1MDYtNDVjNy00NTc3LWI3MWUtMTliZWIxODAxNzBmLyIsImlhdCI6MTc0MDQ5NTEyOSwibmJmIjoxNzQwNDk1MTI5LCJleHAiOjE3NDA0OTkwMjksImFpbyI6ImsyUmdZSGk5dVhqVDUrTnlCYmFXNlhJQlYwcmtBUT09IiwiYXBwaWQiOiJlYzA3ZDA0MC0wOWVlLTQ4ZTYtODYwNC0zYzIzNzg3ZTI3Y2YiLCJhcHBpZGFjciI6IjEiLCJpZHAiOiJodHRwczovL3N0cy53aW5kb3dzLm5ldC83MTAyOTUwNi00NWM3LTQ1NzctYjcxZS0xOWJlYjE4MDE3MGYvIiwiaWR0eXAiOiJhcHAiLCJvaWQiOiJjOGM2YjgyMC00MDc1LTRhYjUtYjU3Yi02NGY0MTE4NTQzNWQiLCJyaCI6IjEuQVVZQUJwVUNjY2RGZDBXM0hobS1zWUFYRHdrQUFBQUFBQUFBd0FBQUFBQUFBQUNBQUFCR0FBLiIsInN1YiI6ImM4YzZiODIwLTQwNzUtNGFiNS1iNTdiLTY0ZjQxMTg1NDM1ZCIsInRpZCI6IjcxMDI5NTA2LTQ1YzctNDU3Ny1iNzFlLTE5YmViMTgwMTcwZiIsInV0aSI6IjZDZWwtbVBfSzB1VVU0TklKM0pPQUEiLCJ2ZXIiOiIxLjAiLCJ4bXNfaWRyZWwiOiIxNCA3In0.dPsyeeWdS7P4vYDYMGERsGyyKAeBOCnZwuw_lBUZrXfZcgcCUicR9pcKQmIZA4-H7qwZ0nEyq9C00XBOsF1_xPTtdFkn3bq4NMzfpq5tH4Okm_RZhnUG9X3qo-UxW291wTYYuoOHh4mylHsv7rTx0v4AdUNCu1rOcPhD1yvvPLIaKCveCcHtPAOIyrUDsCAEv940lqXXIkEgIYYoQ25wNJa212C-Hw1h92BH2LMV4TWOZyVrPT3El3Onei0ybG84Ht1TohkJGbnzDn28BeeWybFVt-Qfy-4hC2PQW7LYjkgJVYhG1hqQE2p8tIuJUcFZPyVyUyFEs-RfoBXIM7QI3g'

    url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/reports/{report_id}/GenerateToken"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    data = {
            "accessLevel": "View",
            "identities": [
                {
                    "username": str(id_gerente),  # 🔥 Passa o ID do gerente para o Power BI
                    "roles": ["rls_cliente"],  # 🔥 Nome da Role configurada no Power BI
                    "datasets": [dataset_id]
                }
            ]
        }
    response = requests.post(url, headers=headers, json=data)
    
    print("aqui:", response.text)

    if response.status_code != 200:
        print("Erro ao obter Embed Token:", response.text) 

    embed_token =  response.json().get("token")
    if not embed_token:
        return "Falha ao gerar o Embed Token.", 500
    
    #embed_url = f"https://app.powerbi.com/reportEmbed?reportId={report_id}"
    embed_url = f"https://app.powerbi.com/reportEmbed?reportId={report_id}&groupId={workspace_id}"

    
    html_template = """
    <!DOCTYPE html>
    <html lang="pt-br">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Relatório Power BI</title>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/powerbi-client/2.19.0/powerbi.min.js"></script>
    </head>
    <body>
        <h1>Relatório da Empresa {{ company_id }}</h1>
        <div id="reportContainer" style="width: 800px; height: 600px;"></div>

        <script>
            document.addEventListener("DOMContentLoaded", function() {
            if (typeof powerbi === "undefined") {
                console.error("Power BI SDK não carregado corretamente.");
                return;
            }

            var models = window['powerbi-client'].models;
            var embedConfiguration = {
                type: 'report',
                id: '{{ report_id }}',
                embedUrl: '{{ embed_url }}',
                accessToken: '{{ embed_token }}',
                tokenType: models.TokenType.Embed,  // Corrigindo a referência
                settings: {
                    filterPaneEnabled: false,
                    navContentPaneEnabled: true
                }
            };

            var reportContainer = document.getElementById("reportContainer");
            powerbi.embed(reportContainer, embedConfiguration);
        });

        </script>
    </body>
    </html>

    """
    return render_template_string(html_template, report_id=report_id, embed_url=embed_url, embed_token=embed_token)

if __name__ == '__main__':
    app.run(debug=True)
