import os
import logging
import json
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("test_db_save.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Importar a classe ModelDatabase corrigida
try:
    from model_database_corrigido import ModelDatabase
    logger.info("Módulo ModelDatabase importado com sucesso")
except Exception as e:
    logger.error(f"Erro ao importar ModelDatabase: {str(e)}")
    import traceback
    logger.error(traceback.format_exc())
    exit(1)

def test_save_model():
    """
    Testa o salvamento de um modelo no banco de dados
    """
    logger.info("Iniciando teste de salvamento de modelo")
    
    # Criar instância do banco de dados
    db_path = "test_save.db"
    
    # Remover banco de dados de teste anterior se existir
    if os.path.exists(db_path):
        os.remove(db_path)
        logger.info(f"Banco de dados anterior removido: {db_path}")
    
    db = ModelDatabase(db_path)
    logger.info(f"Banco de dados criado: {db_path}")
    
    # Dados de teste
    test_name = "Modelo de Teste"
    test_signature = "TEST_SIGNATURE_123"
    test_extraction_patterns = {
        "field_corrections": {
            "Nome da empresa": {
                "original": "Empresa Original",
                "corrected": "Empresa Corrigida"
            },
            "Número do contêiner": {
                "original": "CONT123",
                "corrected": "CONT456"
            }
        },
        "product_patterns": [
            {
                "tipo": "Manga",
                "tamanho": "Grande",
                "quantidade": "10",
                "preço unitário": "5.00",
                "preço total": "50.00"
            }
        ]
    }
    
    # Testar método add_model
    logger.info("Testando método add_model")
    model_id = db.add_model(
        name=test_name,
        pdf_signature=test_signature,
        extraction_patterns=test_extraction_patterns,
        confidence_score=0.8
    )
    
    if model_id:
        logger.info(f"Modelo adicionado com sucesso, ID: {model_id}")
    else:
        logger.error("Falha ao adicionar modelo")
        return False
    
    # Verificar se o modelo foi salvo
    logger.info("Verificando se o modelo foi salvo")
    model = db.find_model_by_signature(test_signature)
    
    if model:
        logger.info(f"Modelo encontrado: {model['name']}, ID: {model['id']}")
        logger.info(f"Padrões de extração: {json.dumps(model['extraction_patterns'], indent=2)}")
    else:
        logger.error("Modelo não encontrado após salvamento")
        return False
    
    # Testar método update_model
    logger.info("Testando método update_model")
    test_extraction_patterns["field_corrections"]["Nome da empresa"]["corrected"] = "Empresa Atualizada"
    
    success = db.update_model(
        model_id=model_id,
        name=test_name,
        pdf_signature=test_signature,
        extraction_patterns=test_extraction_patterns,
        confidence_score=0.9
    )
    
    if success:
        logger.info("Modelo atualizado com sucesso")
    else:
        logger.error("Falha ao atualizar modelo")
        return False
    
    # Verificar se o modelo foi atualizado
    logger.info("Verificando se o modelo foi atualizado")
    updated_model = db.get_model_by_id(model_id)
    
    if updated_model:
        logger.info(f"Modelo atualizado encontrado: {updated_model['name']}, ID: {updated_model['id']}")
        logger.info(f"Confiança atualizada: {updated_model['confidence_score']}")
        logger.info(f"Padrões de extração atualizados: {json.dumps(updated_model['extraction_patterns'], indent=2)}")
        
        # Verificar se o campo foi realmente atualizado
        corrected_value = updated_model['extraction_patterns']['field_corrections']['Nome da empresa']['corrected']
        if corrected_value == "Empresa Atualizada":
            logger.info("Valor atualizado corretamente")
        else:
            logger.error(f"Valor não foi atualizado corretamente. Esperado: 'Empresa Atualizada', Atual: '{corrected_value}'")
            return False
    else:
        logger.error("Modelo atualizado não encontrado")
        return False
    
    # Testar método add_extraction_history
    logger.info("Testando método add_extraction_history")
    history_id = db.add_extraction_history(
        model_id=model_id,
        pdf_name="teste.pdf",
        extraction_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        original_data=json.dumps({"dados_originais": "teste"}),
        corrected_data=json.dumps({"dados_corrigidos": "teste"})
    )
    
    if history_id:
        logger.info(f"Histórico adicionado com sucesso, ID: {history_id}")
    else:
        logger.error("Falha ao adicionar histórico")
        return False
    
    # Verificar todos os modelos
    logger.info("Verificando todos os modelos")
    all_models = db.get_all_models()
    logger.info(f"Total de modelos: {len(all_models)}")
    
    # Verificar histórico de extrações
    logger.info("Verificando histórico de extrações")
    history = db.get_extraction_history()
    logger.info(f"Total de registros de histórico: {len(history)}")
    
    logger.info("Teste concluído com sucesso!")
    return True

if __name__ == "__main__":
    if test_save_model():
        print("✅ Teste de salvamento concluído com sucesso!")
    else:
        print("❌ Teste de salvamento falhou!")
