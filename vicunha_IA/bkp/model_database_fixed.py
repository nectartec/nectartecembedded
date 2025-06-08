import sqlite3
import json
import os
import logging
from datetime import datetime
import traceback

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ModelDatabase:
    def __init__(self, db_path):
        """
        Inicializa o banco de dados de modelos
        
        Args:
            db_path (str): Caminho para o arquivo SQLite
        """
        logger.info(f"Inicializando banco de dados em: {db_path}")
        self.db_path = db_path
        
        # Verificar se o diretório existe
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
            logger.info(f"Diretório criado: {db_dir}")
        
        # Conectar ao banco de dados com suporte a múltiplas threads
        try:
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            logger.info(f"Conectado ao banco de dados: {db_path}")
        except Exception as e:
            logger.error(f"Erro ao conectar ao banco de dados: {str(e)}")
            logger.error(traceback.format_exc())
            raise
        
        # Criar tabelas
        self.create_tables()
    
    def create_tables(self):
        """
        Cria as tabelas necessárias no banco de dados
        """
        try:
            cursor = self.conn.cursor()
            
            # Tabela de modelos
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                signature TEXT NOT NULL,
                extraction_patterns TEXT NOT NULL,
                confidence_score REAL DEFAULT 0.7,
                usage_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Tabela de histórico de extrações
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS extraction_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id INTEGER,
                pdf_name TEXT NOT NULL,
                original_extraction TEXT NOT NULL,
                corrected_extraction TEXT NOT NULL,
                extraction_date TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES models (id)
            )
            ''')
            
            # Commit explícito
            self.conn.commit()
            logger.info("Tabelas criadas ou já existentes")
            
            # Verificar se as tabelas foram criadas
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            logger.info(f"Tabelas no banco de dados: {[table[0] for table in tables]}")
            
        except Exception as e:
            logger.error(f"Erro ao criar tabelas: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def save_model(self, name, description, signature, extraction_patterns, confidence_score=0.7):
        """
        Salva um novo modelo ou atualiza um existente
        
        Args:
            name (str): Nome do modelo
            description (str): Descrição do modelo
            signature (str): Assinatura única do PDF
            extraction_patterns (dict): Padrões de extração
            confidence_score (float): Pontuação de confiança
            
        Returns:
            int: ID do modelo
        """
        try:
            logger.info(f"Tentando salvar modelo: {name}, signature: {signature}")
            
            # Verificar conexão
            if self.conn is None:
                logger.error("Conexão com banco de dados não inicializada")
                self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
                self.conn.row_factory = sqlite3.Row
            
            cursor = self.conn.cursor()
            
            # Verificar se já existe um modelo com esta assinatura
            cursor.execute("SELECT id FROM models WHERE signature = ?", (signature,))
            existing_model = cursor.fetchone()
            
            # Serializar padrões de extração para JSON
            extraction_patterns_json = json.dumps(extraction_patterns, ensure_ascii=False)
            logger.info(f"Padrões de extração serializados: {extraction_patterns_json[:100]}...")
            
            if existing_model:
                # Atualizar modelo existente
                model_id = existing_model['id']
                logger.info(f"Atualizando modelo existente ID: {model_id}")
                
                cursor.execute('''
                UPDATE models
                SET name = ?, description = ?, extraction_patterns = ?, 
                    confidence_score = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                ''', (
                    name, 
                    description, 
                    extraction_patterns_json, 
                    confidence_score,
                    model_id
                ))
                
                # Commit explícito após atualização
                self.conn.commit()
                logger.info(f"Modelo atualizado com sucesso: {name} (ID: {model_id})")
            else:
                # Criar novo modelo
                logger.info(f"Criando novo modelo: {name}")
                
                cursor.execute('''
                INSERT INTO models (name, description, signature, extraction_patterns, confidence_score)
                VALUES (?, ?, ?, ?, ?)
                ''', (
                    name, 
                    description, 
                    signature, 
                    extraction_patterns_json, 
                    confidence_score
                ))
                
                # Commit explícito após inserção
                self.conn.commit()
                
                model_id = cursor.lastrowid
                logger.info(f"Novo modelo criado com sucesso: {name} (ID: {model_id})")
            
            # Verificar se o modelo foi realmente salvo
            cursor.execute("SELECT id FROM models WHERE id = ?", (model_id,))
            check = cursor.fetchone()
            if check:
                logger.info(f"Verificação de salvamento: Modelo ID {model_id} encontrado no banco")
            else:
                logger.error(f"Verificação de salvamento: Modelo ID {model_id} NÃO encontrado no banco!")
            
            return model_id
            
        except Exception as e:
            logger.error(f"Erro ao salvar modelo: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Tentar reconectar e salvar novamente
            try:
                logger.info("Tentando reconectar ao banco de dados...")
                self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
                self.conn.row_factory = sqlite3.Row
                
                # Tentar salvar novamente
                cursor = self.conn.cursor()
                
                # Verificar se já existe um modelo com esta assinatura
                cursor.execute("SELECT id FROM models WHERE signature = ?", (signature,))
                existing_model = cursor.fetchone()
                
                # Serializar padrões de extração para JSON
                extraction_patterns_json = json.dumps(extraction_patterns, ensure_ascii=False)
                
                if existing_model:
                    # Atualizar modelo existente
                    model_id = existing_model['id']
                    
                    cursor.execute('''
                    UPDATE models
                    SET name = ?, description = ?, extraction_patterns = ?, 
                        confidence_score = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    ''', (
                        name, 
                        description, 
                        extraction_patterns_json, 
                        confidence_score,
                        model_id
                    ))
                else:
                    # Criar novo modelo
                    cursor.execute('''
                    INSERT INTO models (name, description, signature, extraction_patterns, confidence_score)
                    VALUES (?, ?, ?, ?, ?)
                    ''', (
                        name, 
                        description, 
                        signature, 
                        extraction_patterns_json, 
                        confidence_score
                    ))
                    model_id = cursor.lastrowid
                
                # Commit explícito
                self.conn.commit()
                logger.info(f"Modelo salvo com sucesso após reconexão: {name} (ID: {model_id})")
                return model_id
                
            except Exception as e2:
                logger.error(f"Erro ao salvar modelo após reconexão: {str(e2)}")
                logger.error(traceback.format_exc())
                return None
    
    def update_model_usage(self, model_id):
        """
        Incrementa o contador de uso de um modelo
        
        Args:
            model_id (int): ID do modelo
            
        Returns:
            bool: True se atualizado com sucesso, False caso contrário
        """
        try:
            logger.info(f"Atualizando contador de uso para modelo ID: {model_id}")
            cursor = self.conn.cursor()
            cursor.execute('''
            UPDATE models
            SET usage_count = usage_count + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            ''', (model_id,))
            
            # Commit explícito
            self.conn.commit()
            
            # Verificar se a atualização foi bem-sucedida
            cursor.execute("SELECT usage_count FROM models WHERE id = ?", (model_id,))
            result = cursor.fetchone()
            if result:
                logger.info(f"Contador de uso atualizado para modelo ID: {model_id}, novo valor: {result['usage_count']}")
            else:
                logger.warning(f"Modelo ID: {model_id} não encontrado após atualização de uso")
            
            return True
        except Exception as e:
            logger.error(f"Erro ao atualizar contador de uso do modelo: {str(e)}")
            logger.error(traceback.format_exc())
            return False
    
    def find_model_by_signature(self, signature):
        """
        Busca um modelo pela assinatura do PDF
        
        Args:
            signature (str): Assinatura única do PDF
            
        Returns:
            dict: Modelo encontrado ou None
        """
        try:
            logger.info(f"Buscando modelo com assinatura: {signature}")
            cursor = self.conn.cursor()
            cursor.execute('''
            SELECT id, name, description, signature, extraction_patterns, 
                   confidence_score, usage_count, created_at, updated_at
            FROM models
            WHERE signature = ?
            ''', (signature,))
            
            row = cursor.fetchone()
            
            if row:
                logger.info(f"Modelo encontrado para a assinatura: {signature}, ID: {row['id']}")
                model = dict(row)
                try:
                    model['extraction_patterns'] = json.loads(model['extraction_patterns'])
                except json.JSONDecodeError as e:
                    logger.error(f"Erro ao decodificar padrões de extração: {str(e)}")
                    model['extraction_patterns'] = {}
                return model
            else:
                logger.info(f"Nenhum modelo encontrado para a assinatura: {signature}")
                return None
        except Exception as e:
            logger.error(f"Erro ao buscar modelo por assinatura: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    
    def get_model_by_id(self, model_id):
        """
        Busca um modelo pelo ID
        
        Args:
            model_id (int): ID do modelo
            
        Returns:
            dict: Modelo encontrado ou None
        """
        try:
            logger.info(f"Buscando modelo com ID: {model_id}")
            cursor = self.conn.cursor()
            cursor.execute('''
            SELECT id, name, description, signature, extraction_patterns, 
                   confidence_score, usage_count, created_at, updated_at
            FROM models
            WHERE id = ?
            ''', (model_id,))
            
            row = cursor.fetchone()
            
            if row:
                logger.info(f"Modelo encontrado com ID: {model_id}")
                model = dict(row)
                try:
                    model['extraction_patterns'] = json.loads(model['extraction_patterns'])
                except json.JSONDecodeError as e:
                    logger.error(f"Erro ao decodificar padrões de extração: {str(e)}")
                    model['extraction_patterns'] = {}
                return model
            else:
                logger.info(f"Nenhum modelo encontrado com ID: {model_id}")
                return None
        except Exception as e:
            logger.error(f"Erro ao buscar modelo por ID: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    
    def get_all_models(self):
        """
        Retorna todos os modelos
        
        Returns:
            list: Lista de modelos
        """
        try:
            logger.info("Buscando todos os modelos")
            cursor = self.conn.cursor()
            cursor.execute('''
            SELECT id, name, description, signature, extraction_patterns, 
                   confidence_score, usage_count, created_at, updated_at
            FROM models
            ORDER BY updated_at DESC
            ''')
            
            rows = cursor.fetchall()
            models = []
            
            for row in rows:
                model = dict(row)
                try:
                    model['extraction_patterns'] = json.loads(model['extraction_patterns'])
                except json.JSONDecodeError as e:
                    logger.error(f"Erro ao decodificar padrões de extração para modelo ID {row['id']}: {str(e)}")
                    model['extraction_patterns'] = {}
                models.append(model)
            
            logger.info(f"Encontrados {len(models)} modelos")
            return models
        except Exception as e:
            logger.error(f"Erro ao buscar todos os modelos: {str(e)}")
            logger.error(traceback.format_exc())
            return []
    
    def delete_model(self, model_id):
        """
        Exclui um modelo pelo ID
        
        Args:
            model_id (int): ID do modelo
            
        Returns:
            bool: True se excluído com sucesso, False caso contrário
        """
        try:
            logger.info(f"Excluindo modelo com ID: {model_id}")
            cursor = self.conn.cursor()
            
            # Excluir histórico de extrações relacionado
            cursor.execute("DELETE FROM extraction_history WHERE model_id = ?", (model_id,))
            
            # Excluir modelo
            cursor.execute("DELETE FROM models WHERE id = ?", (model_id,))
            
            # Commit explícito
            self.conn.commit()
            
            logger.info(f"Modelo ID: {model_id} excluído com sucesso")
            return True
        except Exception as e:
            logger.error(f"Erro ao excluir modelo: {str(e)}")
            logger.error(traceback.format_exc())
            return False
    
    def save_extraction_history(self, model_id, pdf_name, original_extraction, corrected_extraction):
        """
        Salva um registro de histórico de extração
        
        Args:
            model_id (int): ID do modelo
            pdf_name (str): Nome do arquivo PDF
            original_extraction (dict): Dados extraídos originalmente
            corrected_extraction (dict): Dados corrigidos pelo usuário
            
        Returns:
            int: ID do registro de histórico
        """
        try:
            logger.info(f"Salvando histórico de extração para modelo ID: {model_id}, PDF: {pdf_name}")
            cursor = self.conn.cursor()
            
            # Serializar extrações para JSON
            original_extraction_json = json.dumps(original_extraction, ensure_ascii=False)
            corrected_extraction_json = json.dumps(corrected_extraction, ensure_ascii=False)
            
            cursor.execute('''
            INSERT INTO extraction_history (model_id, pdf_name, original_extraction, corrected_extraction)
            VALUES (?, ?, ?, ?)
            ''', (
                model_id,
                pdf_name,
                original_extraction_json,
                corrected_extraction_json
            ))
            
            # Commit explícito
            self.conn.commit()
            
            history_id = cursor.lastrowid
            logger.info(f"Histórico de extração salvo com sucesso: {pdf_name} (ID: {history_id})")
            
            # Verificar se o histórico foi realmente salvo
            cursor.execute("SELECT id FROM extraction_history WHERE id = ?", (history_id,))
            check = cursor.fetchone()
            if check:
                logger.info(f"Verificação de salvamento: Histórico ID {history_id} encontrado no banco")
            else:
                logger.error(f"Verificação de salvamento: Histórico ID {history_id} NÃO encontrado no banco!")
            
            return history_id
        except Exception as e:
            logger.error(f"Erro ao salvar histórico de extração: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    
    def get_extraction_history(self, model_id=None, limit=10):
        """
        Retorna o histórico de extrações
        
        Args:
            model_id (int, optional): ID do modelo para filtrar
            limit (int): Limite de registros
            
        Returns:
            list: Lista de registros de histórico
        """
        try:
            logger.info(f"Buscando histórico de extração, modelo ID: {model_id}, limite: {limit}")
            cursor = self.conn.cursor()
            
            if model_id:
                cursor.execute('''
                SELECT id, model_id, pdf_name, original_extraction, corrected_extraction, extraction_date
                FROM extraction_history
                WHERE model_id = ?
                ORDER BY extraction_date DESC
                LIMIT ?
                ''', (model_id, limit))
            else:
                cursor.execute('''
                SELECT id, model_id, pdf_name, original_extraction, corrected_extraction, extraction_date
                FROM extraction_history
                ORDER BY extraction_date DESC
                LIMIT ?
                ''', (limit,))
            
            rows = cursor.fetchall()
            history = []
            
            for row in rows:
                record = dict(row)
                try:
                    record['original_extraction'] = json.loads(record['original_extraction'])
                except json.JSONDecodeError as e:
                    logger.error(f"Erro ao decodificar extração original para histórico ID {row['id']}: {str(e)}")
                    record['original_extraction'] = {}
                
                try:
                    record['corrected_extraction'] = json.loads(record['corrected_extraction'])
                except json.JSONDecodeError as e:
                    logger.error(f"Erro ao decodificar extração corrigida para histórico ID {row['id']}: {str(e)}")
                    record['corrected_extraction'] = {}
                
                history.append(record)
            
            logger.info(f"Encontrados {len(history)} registros de histórico")
            return history
        except Exception as e:
            logger.error(f"Erro ao buscar histórico de extração: {str(e)}")
            logger.error(traceback.format_exc())
            return []
    
    def export_models(self, output_path):
        """
        Exporta todos os modelos para um arquivo JSON
        
        Args:
            output_path (str): Caminho para salvar o arquivo JSON
            
        Returns:
            bool: True se exportado com sucesso, False caso contrário
        """
        try:
            logger.info(f"Exportando modelos para: {output_path}")
            models = self.get_all_models()
            
            # Adicionar histórico de extrações para cada modelo
            for model in models:
                model['extraction_history'] = self.get_extraction_history(model['id'])
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(models, f, ensure_ascii=False, indent=4)
            
            logger.info(f"Modelos exportados com sucesso: {len(models)} modelos")
            return True
        except Exception as e:
            logger.error(f"Erro ao exportar modelos: {str(e)}")
            logger.error(traceback.format_exc())
            return False
    
    def import_models(self, input_path):
        """
        Importa modelos de um arquivo JSON
        
        Args:
            input_path (str): Caminho do arquivo JSON
            
        Returns:
            int: Número de modelos importados
        """
        try:
            logger.info(f"Importando modelos de: {input_path}")
            with open(input_path, 'r', encoding='utf-8') as f:
                models = json.load(f)
            
            imported_count = 0
            
            for model in models:
                # Salvar modelo
                model_id = self.save_model(
                    name=model['name'],
                    description=model['description'],
                    signature=model['signature'],
                    extraction_patterns=model['extraction_patterns'],
                    confidence_score=model['confidence_score']
                )
                
                if model_id:
                    # Importar histórico de extrações
                    if 'extraction_history' in model:
                        for history in model['extraction_history']:
                            self.save_extraction_history(
                                model_id=model_id,
                                pdf_name=history['pdf_name'],
                                original_extraction=history['original_extraction'],
                                corrected_extraction=history['corrected_extraction']
                            )
                    
                    imported_count += 1
            
            logger.info(f"Modelos importados com sucesso: {imported_count} modelos")
            return imported_count
        except Exception as e:
            logger.error(f"Erro ao importar modelos: {str(e)}")
            logger.error(traceback.format_exc())
            return 0
    
    def close(self):
        """
        Fecha a conexão com o banco de dados
        """
        if self.conn:
            try:
                self.conn.commit()  # Commit final para garantir que todas as alterações sejam salvas
                self.conn.close()
                logger.info("Conexão com banco de dados fechada")
            except Exception as e:
                logger.error(f"Erro ao fechar conexão com banco de dados: {str(e)}")
                logger.error(traceback.format_exc())

# Função para teste direto
def test_database():
    """
    Função para testar o banco de dados diretamente
    """
    import sys
    
    # Criar banco de dados de teste
    db_path = "test_db.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    # Inicializar banco de dados
    db = ModelDatabase(db_path)
    
    # Criar modelo de teste
    model_id = db.save_model(
        name="Modelo de Teste",
        description="Modelo para teste",
        signature="test_signature",
        extraction_patterns={"field_corrections": {"campo1": {"original": "valor1", "corrected": "valor2"}}}
    )
    
    print(f"Modelo criado com ID: {model_id}")
    
    # Buscar modelo
    model = db.get_model_by_id(model_id)
    print(f"Modelo encontrado: {model}")
    
    # Salvar histórico
    history_id = db.save_extraction_history(
        model_id=model_id,
        pdf_name="teste.pdf",
        original_extraction={"dados": "originais"},
        corrected_extraction={"dados": "corrigidos"}
    )
    
    print(f"Histórico salvo com ID: {history_id}")
    
    # Buscar histórico
    history = db.get_extraction_history(model_id)
    print(f"Histórico encontrado: {history}")
    
    # Fechar conexão
    db.close()

if __name__ == "__main__":
    test_database()
