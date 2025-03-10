import subprocess

# Defina os parâmetros
capacity_name = "nectartecembedded"
resource_group = "nectartec_embedded"

# Comando PowerShell para pausar a capacidade
command = f'Suspend-AzPowerBIEmbeddedCapacity -Name "{capacity_name}" -ResourceGroupName "{resource_group}" -PassThru'

try:
    # Executa o comando PowerShell a partir do Python
    result = subprocess.run(["powershell", "-Command", command], capture_output=True, text=True)
    
    if result.returncode == 0:
        print("Capacidade pausada com sucesso!")
        print(result.stdout)
    else:
        print("Erro ao pausar a capacidade:")
        print(result.stderr)
except Exception as e:
    print(f"Ocorreu um erro: {e}")
