import os
import uuid
from flask import Flask, request, jsonify
from pymongo import MongoClient
from supabase import create_client, Client
from bson.objectid import ObjectId

app = Flask(__name__)

# ==========================================
# 1. CONEXÕES COM BANCOS E VARIÁVEIS (VERCEL)
# ==========================================
MONGO_URI = os.environ.get("MONGO_URI")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
MASTER_PASSWORD = os.environ.get("MASTER_PASSWORD").strip()

# Inicializa MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["sisunid"] # Nome do banco de dados

# Inicializa Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
BUCKET_NAME = "uploads" # O nome do Bucket que você deve criar no Supabase Storage

# Helper para converter ObjectId do Mongo para String (JSON amigável)
def format_mongo_doc(doc):
    if doc and '_id' in doc:
        doc['_id'] = str(doc['_id'])
    return doc

# ==========================================
# 2. ROTAS DO PAINEL MASTER (SUPER ADMIN)
# ==========================================

@app.route('/api/master/login', methods=['POST'])
def master_login():
    data = request.json
    if data.get('senha') == MASTER_PASSWORD:
        return jsonify({"sucesso": True})
    return jsonify({"sucesso": False, "erro": "Senha incorreta"}), 401

@app.route('/api/master/unidades', methods=['GET'])
def get_unidades():
    try:
        # Busca todas as unidades no Mongo
        unidades = list(db.unidades.find())
        unidades_formatadas = [format_mongo_doc(u) for u in unidades]
        return jsonify({"sucesso": True, "unidades": unidades_formatadas})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500

@app.route('/api/master/unidades', methods=['POST'])
def criar_unidade():
    try:
        # 1. Captura os textos do FormData
        nome_empresa = request.form.get('nome_empresa')
        cnpj = request.form.get('cnpj')
        gestor = request.form.get('gestor')
        data_inicio = request.form.get('data_inicio')
        telefone = request.form.get('telefone')
        email = request.form.get('email')
        endereco = request.form.get('endereco')
        slogan = request.form.get('slogan')
        tema_primaria = request.form.get('tema_primaria')
        senha_acesso = request.form.get('senha_acesso')
        
        logo_url = None
        
        # 2. Captura a imagem, se houver
        if 'logo' in request.files:
            file = request.files['logo']
            if file.filename != '':
                # Gera um nome único para não sobreescrever
                file_ext = file.filename.split('.')[-1]
                unique_filename = f"{uuid.uuid4()}.{file_ext}"
                
                # Lê os bytes e envia pro Supabase
                file_bytes = file.read()
                res = supabase.storage.from_(BUCKET_NAME).upload(
                    path=unique_filename,
                    file=file_bytes,
                    file_options={"content-type": file.content_type}
                )
                
                # Pega o link público da imagem gerada
                logo_url = supabase.storage.from_(BUCKET_NAME).get_public_url(unique_filename)

        # 3. Salva tudo no MongoDB
        nova_unidade = {
            "nome_empresa": nome_empresa,
            "cnpj": cnpj,
            "gestor": gestor,
            "data_inicio": data_inicio,
            "telefone": telefone,
            "email": email,
            "endereco": endereco,
            "slogan": slogan,
            "tema": {"primaria": tema_primaria},
            "senha_acesso": senha_acesso,
            "logo_url": logo_url,
            "status": "ativa"
        }
        
        db.unidades.insert_one(nova_unidade)
        return jsonify({"sucesso": True, "mensagem": "Unidade criada com sucesso!"})

    except Exception as e:
        # Se quebrar, a Vercel joga isso nos Logs e nosso front-end alerta
        print("Erro Crítico ao Salvar:", str(e))
        return jsonify({"sucesso": False, "erro": str(e)}), 500

# ==========================================
# 3. ROTAS DO PAINEL DO CLIENTE (TENANT)
# ==========================================

@app.route('/api/tenant/login', methods=['POST'])
def tenant_login():
    data = request.json
    cnpj = data.get('cnpj')
    senha = data.get('senha')
    
    # Busca a empresa pelo CNPJ e Senha
    unidade = db.unidades.find_one({"cnpj": cnpj, "senha_acesso": senha, "status": "ativa"})
    
    if unidade:
        return jsonify({
            "sucesso": True,
            "unidade_id": str(unidade['_id']),
            "empresa": {
                "nome": unidade.get('nome_empresa'),
                "gestor": unidade.get('gestor'),
                "slogan": unidade.get('slogan'),
                "tema": unidade.get('tema'),
                "logo_url": unidade.get('logo_url')
            }
        })
    return jsonify({"sucesso": False, "erro": "CNPJ ou Senha inválidos, ou unidade bloqueada."}), 401

@app.route('/api/tenant/regulacoes', methods=['GET'])
def get_regulacoes():
    unidade_id = request.args.get('unidade_id')
    if not unidade_id:
        return jsonify({"sucesso": False, "erro": "ID da unidade é obrigatório"}), 400
        
    try:
        # Busca apenas os pacientes daquela unidade específica
        regulacoes = list(db.regulacoes.find({"unidade_id": unidade_id}))
        regs_formatadas = [format_mongo_doc(r) for r in regulacoes]
        return jsonify({"sucesso": True, "regulacoes": regs_formatadas})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500

@app.route('/api/tenant/regulacoes', methods=['POST'])
def criar_regulacao():
    data = request.json
    try:
        # Gera um número de protocolo simples (Ex: REQ-A1B2)
        protocolo = f"REQ-{str(uuid.uuid4())[:4].upper()}"
        
        novo_paciente = {
            "unidade_id": data.get("unidade_id"),
            "protocolo": protocolo,
            "nome_paciente": data.get("nome_paciente"),
            "cpf": data.get("cpf"),
            "email": data.get("email"),
            "telefone": data.get("telefone"),
            "procedimento": data.get("procedimento"),
            "prioridade": data.get("prioridade"),
            "status_atual": "Em Análise"
        }
        
        db.regulacoes.insert_one(novo_paciente)
        return jsonify({"sucesso": True, "protocolo": protocolo})
        
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500

# Necessário para a Vercel entender como rodar o app Flask
if __name__ == '__main__':
    app.run(debug=True)
