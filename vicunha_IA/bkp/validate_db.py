import os
import logging
import json
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("validate_db.log"),
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

def validate_database(db_path="pdf_models.db"):
    """
    Valida a integridade do banco de dados
    """
    logger.info(f"Validando banco de dados: {db_path}")
    
    # Verificar se o banco de dados existe
    if not os.path.exists(db_path):
        logger.error(f"Banco de dados não encontrado: {db_path}")
        return False
    
    # Conectar ao banco de dados
    try:
        db = ModelDatabase(db_path)
        logger.info(f"Conectado ao banco de dados: {db_path}")
    except Exception as e:
        logger.error(f"Erro ao conectar ao banco de dados: {str(e)}")
        return False
    
    # Validar tabelas
    try:
        cursor = db.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        logger.info(f"Tabelas encontradas: {tables}")
        
        required_tables = ['models', 'extraction_history']
        for table in required_tables:
            if table not in tables:
                logger.error(f"Tabela obrigatória não encontrada: {table}")
                return False
        
        logger.info("Todas as tabelas obrigatórias estão presentes")
    except Exception as e:
        logger.error(f"Erro ao validar tabelas: {str(e)}")
        return False
    
    # Validar estrutura da tabela models
    try:
        cursor.execute("PRAGMA table_info(models)")
        columns = [row[1] for row in cursor.fetchall()]
        logger.info(f"Colunas da tabela models: {columns}")
        
        required_columns = ['id', 'name', 'description', 'signature', 'extraction_patterns', 
                           'confidence_score', 'usage_count', 'created_at', 'updated_at']
        for column in required_columns:
            if column not in columns:
                logger.error(f"Coluna obrigatória não encontrada em models: {column}")
                return False
        
        logger.info("Todas as colunas obrigatórias estão presentes na tabela models")
    except Exception as e:
        logger.error(f"Erro ao validar estrutura da tabela models: {str(e)}")
        return False
    
    # Validar estrutura da tabela extraction_history
    try:
        cursor.execute("PRAGMA table_info(extraction_history)")
        columns = [row[1] for row in cursor.fetchall()]
        logger.info(f"Colunas da tabela extraction_history: {columns}")
        
        required_columns = ['id', 'model_id', 'pdf_name', 'original_extraction', 
                           'corrected_extraction', 'extraction_date']
        for column in required_columns:
            if column not in columns:
                logger.error(f"Coluna obrigatória não encontrada em extraction_history: {column}")
                return False
        
        logger.info("Todas as colunas obrigatórias estão presentes na tabela extraction_history")
    except Exception as e:
        logger.error(f"Erro ao validar estrutura da tabela extraction_history: {str(e)}")
        return False
    
    # Testar operações CRUD
    try:
        # Criar modelo de teste
        logger.info("Testando operações CRUD")
        
        test_name = "Modelo de Validação"
        test_signature = "VALIDATION_SIGNATURE_" + datetime.now().strftime("%Y%m%d%H%M%S")
        test_extraction_patterns = {
            "field_corrections": {
                "Nome da empresa": {
                    "original": "Empresa Teste",
                    "corrected": "Empresa Validada"
                }
            },
            "product_patterns": [
                {
                    "tipo": "Produto Teste",
                    "quantidade": "1",
                    "preço unitário": "10.00"
                }
            ]
        }
        
        # Adicionar modelo
        model_id = db.add_model(
            name=test_name,
            pdf_signature=test_signature,
            extraction_patterns=test_extraction_patterns,
            confidence_score=0.75
        )
        
        if not model_id:
            logger.error("Falha ao adicionar modelo de teste")
            return False
        
        logger.info(f"Modelo de teste adicionado com ID: {model_id}")
        
        # Buscar modelo
        model = db.get_model_by_id(model_id)
        if not model:
            logger.error(f"Falha ao buscar modelo com ID: {model_id}")
            return False
        
        logger.info(f"Modelo encontrado: {model['name']}")
        
        # Atualizar modelo
        test_extraction_patterns["field_corrections"]["Nome da empresa"]["corrected"] = "Empresa Atualizada"
        
        success = db.update_model(
            model_id=model_id,
            name=test_name,
            pdf_signature=test_signature,
            extraction_patterns=test_extraction_patterns,
            confidence_score=0.8
        )
        
        if not success:
            logger.error("Falha ao atualizar modelo de teste")
            return False
        
        logger.info("Modelo atualizado com sucesso")
        
        # Verificar atualização
        updated_model = db.get_model_by_id(model_id)
        if not updated_model:
            logger.error("Falha ao buscar modelo atualizado")
            return False
        
        corrected_value = updated_model['extraction_patterns']['field_corrections']['Nome da empresa']['corrected']
        if corrected_value != "Empresa Atualizada":
            logger.error(f"Valor não foi atualizado corretamente. Esperado: 'Empresa Atualizada', Atual: '{corrected_value}'")
            return False
        
        logger.info("Valor atualizado corretamente")
        
        # Adicionar histórico
        history_id = db.add_extraction_history(
            model_id=model_id,
            pdf_name="validacao.pdf",
            extraction_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            original_data=json.dumps({"dados_originais": "validacao"}),
            corrected_data=json.dumps({"dados_corrigidos": "validacao"})
        )
        
        if not history_id:
            logger.error("Falha ao adicionar histórico de teste")
            return False
        
        logger.info(f"Histórico adicionado com ID: {history_id}")
        
        # Excluir modelo (limpeza)
        success = db.delete_model(model_id)
        if not success:
            logger.error("Falha ao excluir modelo de teste")
            return False
        
        logger.info("Modelo de teste excluído com sucesso")
        
        # Verificar exclusão
        deleted_model = db.get_model_by_id(model_id)
        if deleted_model:
            logger.error("Modelo não foi excluído corretamente")
            return False
        
        logger.info("Modelo excluído corretamente")
        
    except Exception as e:
        logger.error(f"Erro ao testar operações CRUD: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False
    
    logger.info("Validação do banco de dados concluída com sucesso!")
    return True

if __name__ == "__main__":
    if validate_database():
        print("✅ Banco de dados validado com sucesso!")
    else:
        print("❌ Falha na validação do banco de dados!")
