import os
import uuid
from flask import Flask, request, jsonify, send_from_directory, send_file
from pymongo import MongoClient
from supabase import create_client, Client
from bson.objectid import ObjectId

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ==========================================
# 0. ROTAS DO FRONT-END (Telas)
# ==========================================
@app.route('/')
def serve_tenant():
    # Serve o index.html (tela do cliente) que está dentro da pasta public/
    return send_from_directory(os.path.join(BASE_DIR, 'public'), 'index.html')

@app.route('/master')
def serve_master():
    # Serve o master.html (tela do admin) que está na raiz
    return send_file(os.path.join(BASE_DIR, 'master.html'))

# ==========================================
# 1. CONEXÕES COM BANCOS E VARIÁVEIS (PROTEGIDAS)
# ==========================================
MONGO_URI = os.environ.get("MONGO_URI", "").strip()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()

# Trata a senha master com valor fallback para não quebrar no boot
MASTER_PASSWORD = (os.environ.get("MASTER_PASSWORD") or "admin").strip()

db = None
if MONGO_URI and "<db_username>" not in MONGO_URI:
    try:
        # Usa os certificados atualizados do certifi para ignorar o erro de handshake TLS
        mongo_client = MongoClient(
            MONGO_URI,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=5000
        )
        db = mongo_client["sisunid"]
    except Exception as e:
        print("Erro ao conectar no MongoDB:", str(e))

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print("Aviso: Falha ao inicializar Supabase:", str(e))

BUCKET_NAME = "uploads"

def format_mongo_doc(doc):
    if doc and '_id' in doc:
        doc['_id'] = str(doc['_id'])
    return doc

# ==========================================
# 2. ROTAS DO PAINEL MASTER (SUPER ADMIN)
# ==========================================

@app.route('/api/master/login', methods=['POST'])
def master_login():
    data = request.get_json(silent=True) or {}
    senha = str(data.get('senha', '')).strip()
    
    if senha == MASTER_PASSWORD:
        return jsonify({"sucesso": True})
    return jsonify({"sucesso": False, "erro": "Senha incorreta"}), 401

@app.route('/api/master/unidades', methods=['GET'])
def get_unidades():
    if db is None:
        return jsonify({"sucesso": False, "erro": "Banco de dados offline. Verifique a MONGO_URI."}), 500
    try:
        unidades = list(db.unidades.find().sort("_id", -1))
        unidades_formatadas = [format_mongo_doc(u) for u in unidades]
        return jsonify({"sucesso": True, "unidades": unidades_formatadas})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500

@app.route('/api/master/unidades', methods=['POST'])
def criar_unidade():
    if db is None:
        return jsonify({"sucesso": False, "erro": "Banco de dados offline."}), 500

    try:
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
        
        if 'logo' in request.files and supabase is not None:
            file = request.files['logo']
            if file and file.filename != '':
                file_ext = file.filename.split('.')[-1]
                unique_filename = f"logos/{uuid.uuid4().hex}.{file_ext}"
                file_bytes = file.read()
                
                try:
                    supabase.storage.from_(BUCKET_NAME).upload(
                        path=unique_filename,
                        file=file_bytes,
                        file_options={"content-type": file.content_type}
                    )
                    logo_url = supabase.storage.from_(BUCKET_NAME).get_public_url(unique_filename)
                except Exception as err_supa:
                    print("Erro no upload do Supabase:", str(err_supa))

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
        print("Erro ao Salvar Unidade:", str(e))
        return jsonify({"sucesso": False, "erro": str(e)}), 500

@app.route('/api/master/unidades/<id>/status', methods=['PATCH'])
def alterar_status_unidade(id):
    if db is None:
        return jsonify({"sucesso": False, "erro": "Banco offline."}), 500
    try:
        data = request.get_json(silent=True) or {}
        novo_status = data.get('status')
        
        db.unidades.update_one(
            {"_id": ObjectId(id)},
            {"$set": {"status": novo_status}}
        )
        return jsonify({"sucesso": True})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500

# ==========================================
# 3. ROTAS DO PAINEL DO CLIENTE (TENANT)
# ==========================================

@app.route('/api/tenant/login', methods=['POST'])
def tenant_login():
    if db is None:
        return jsonify({"sucesso": False, "erro": "Banco offline."}), 500

    data = request.get_json(silent=True) or {}
    cnpj = data.get('cnpj')
    senha = data.get('senha')
    
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
    if db is None:
        return jsonify({"sucesso": False, "erro": "Banco offline."}), 500

    unidade_id = request.args.get('unidade_id')
    if not unidade_id:
        return jsonify({"sucesso": False, "erro": "ID da unidade é obrigatório"}), 400
        
    try:
        regulacoes = list(db.regulacoes.find({"unidade_id": unidade_id}).sort("_id", -1))
        regs_formatadas = [format_mongo_doc(r) for r in regulacoes]
        return jsonify({"sucesso": True, "regulacoes": regs_formatadas})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500

@app.route('/api/tenant/regulacoes', methods=['POST'])
def criar_regulacao():
    if db is None:
        return jsonify({"sucesso": False, "erro": "Banco offline."}), 500

    data = request.get_json(silent=True) or {}
    try:
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

if __name__ == '__main__':
    app.run(debug=True)
