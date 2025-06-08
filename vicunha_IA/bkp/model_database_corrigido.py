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
        
        # Verificar permissões de escrita
        if db_dir:
            test_file = os.path.join(db_dir, "test_write.tmp")
            try:
                with open(test_file, 'w') as f:
                    f.write("test")
                os.remove(test_file)
                logger.info(f"Permissão de escrita verificada em: {db_dir}")
            except Exception as e:
                logger.error(f"Sem permissão de escrita em: {db_dir}")
                logger.error(str(e))
        
        # Conectar ao banco de dados com suporte a múltiplas threads
        try:
            # Não usar isolation_level=None para permitir gerenciamento explícito de transações
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
    
    # NOVOS MÉTODOS IMPLEMENTADOS PARA COMPATIBILIDADE COM A INTERFACE
    
    def add_model(self, name, pdf_signature, extraction_patterns, confidence_score=0.7):
        """
        Adiciona um novo modelo ao banco de dados
        
        Args:
            name (str): Nome do modelo
            pdf_signature (str): Assinatura única do PDF
            extraction_patterns (dict): Padrões de extração
            confidence_score (float): Pontuação de confiança
            
        Returns:
            int: ID do modelo adicionado ou None em caso de erro
        """
        try:
            logger.info(f"Adicionando novo modelo: {name}, signature: {pdf_signature}")
            
            # Usar o método save_model existente
            description = f"Modelo para {name}"
            model_id = self.save_model(
                name=name,
                description=description,
                signature=pdf_signature,
                extraction_patterns=extraction_patterns,
                confidence_score=confidence_score
            )
            
            logger.info(f"Modelo adicionado com ID: {model_id}")
            return model_id
            
        except Exception as e:
            logger.error(f"Erro ao adicionar modelo: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    
    def update_model(self, model_id, name, pdf_signature, extraction_patterns, confidence_score):
        """
        Atualiza um modelo existente
        
        Args:
            model_id (int): ID do modelo
            name (str): Nome do modelo
            pdf_signature (str): Assinatura única do PDF
            extraction_patterns (dict): Padrões de extração
            confidence_score (float): Pontuação de confiança
            
        Returns:
            bool: True se o modelo foi atualizado com sucesso, False caso contrário
        """
        try:
            logger.info(f"Atualizando modelo ID: {model_id}")
            
            # Verificar se o modelo existe
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM models WHERE id = ?", (model_id,))
            existing_model = cursor.fetchone()
            
            if not existing_model:
                logger.error(f"Modelo ID: {model_id} não encontrado")
                return False
            
            # Serializar padrões de extração para JSON
            extraction_patterns_json = json.dumps(extraction_patterns, ensure_ascii=False)
            
            # Atualizar modelo
            cursor.execute('''
            UPDATE models
            SET name = ?, signature = ?, extraction_patterns = ?, 
                confidence_score = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            ''', (
                name, 
                pdf_signature, 
                extraction_patterns_json, 
                confidence_score,
                model_id
            ))
            
            # Commit explícito
            self.conn.commit()
            
            # Verificar se o modelo foi realmente atualizado
            cursor.execute("SELECT id FROM models WHERE id = ?", (model_id,))
            check = cursor.fetchone()
            
            if check:
                logger.info(f"Modelo ID: {model_id} atualizado com sucesso")
                return True
            else:
                logger.error(f"Falha ao atualizar modelo ID: {model_id}")
                return False
            
        except Exception as e:
            logger.error(f"Erro ao atualizar modelo: {str(e)}")
            logger.error(traceback.format_exc())
            return False
    
    def add_extraction_history(self, model_id, pdf_name, extraction_date, original_data, corrected_data):
        """
        Adiciona um registro ao histórico de extrações
        
        Args:
            model_id (int): ID do modelo
            pdf_name (str): Nome do arquivo PDF
            extraction_date (str): Data da extração
            original_data (str): Dados originais extraídos
            corrected_data (str): Dados corrigidos
            
        Returns:
            int: ID do registro adicionado ou None em caso de erro
        """
        try:
            logger.info(f"Adicionando histórico para modelo ID: {model_id}, PDF: {pdf_name}")
            
            cursor = self.conn.cursor()
            cursor.execute('''
            INSERT INTO extraction_history (model_id, pdf_name, original_extraction, corrected_extraction, extraction_date)
            VALUES (?, ?, ?, ?, ?)
            ''', (
                model_id,
                pdf_name,
                original_data,
                corrected_data,
                extraction_date
            ))
            
            # Commit explícito
            self.conn.commit()
            
            history_id = cursor.lastrowid
            logger.info(f"Histórico adicionado com ID: {history_id}")
            
            # Verificar se o histórico foi realmente adicionado
            cursor.execute("SELECT id FROM extraction_history WHERE id = ?", (history_id,))
            check = cursor.fetchone()
            
            if check:
                logger.info(f"Verificação: Histórico ID {history_id} encontrado no banco")
                return history_id
            else:
                logger.error(f"Verificação falhou: Histórico ID {history_id} não encontrado após inserção")
                return None
            
        except Exception as e:
            logger.error(f"Erro ao adicionar histórico: {str(e)}")
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
    
    def get_extraction_history(self):
        """
        Obtém todo o histórico de extrações
        
        Returns:
            list: Lista de registros de histórico
        """
        try:
            logger.info("Buscando histórico de extrações")
            cursor = self.conn.cursor()
            cursor.execute('''
            SELECT id, model_id, pdf_name, extraction_date, original_extraction, corrected_extraction
            FROM extraction_history
            ORDER BY extraction_date DESC
            ''')
            
            rows = cursor.fetchall()
            history = []
            
            for row in cursor.fetchall():
                history.append(dict(row))
            
            logger.info(f"Encontrados {len(history)} registros de histórico")
            return history
        except Exception as e:
            logger.error(f"Erro ao buscar histórico de extrações: {str(e)}")
            logger.error(traceback.format_exc())
            return []
    
    def execute_query(self, query, params=()):
        """
        Executa uma query SQL diretamente
        
        Args:
            query (str): Query SQL
            params (tuple): Parâmetros da query
            
        Returns:
            list: Resultado da query
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            
            result = []
            for row in cursor.fetchall():
                result.append(dict(row))
            
            return result
            
        except Exception as e:
            logger.error(f"Erro ao executar query: {str(e)}")
            logger.error(traceback.format_exc())
            return []
