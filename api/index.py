import os
from datetime import datetime
from flask import Flask, request, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId

app = Flask(__name__)

# ==========================================
# CONEXÃO COM O MONGODB ATLAS
# ==========================================
MONGO_URI = os.environ.get("MONGO_URI")
db = None

if MONGO_URI:
    try:
        client = MongoClient(MONGO_URI)
        db = client["sisUnid"] # Nome do Banco de Dados
    except Exception as e:
        print(f"Erro ao conectar no MongoDB: {e}")

# Helper para converter _id do Mongo em String
def parse_json(data):
    if isinstance(data, list):
        for item in data:
            if '_id' in item:
                item['_id'] = str(item['_id'])
    elif isinstance(data, dict):
        if '_id' in data:
            data['_id'] = str(data['_id'])
    return data

# ==========================================
# ROTAS DO PAINEL MASTER (SaaS / SUPER ADMIN)
# ==========================================

@app.route('/api/master/login', methods=['POST'])
def master_login():
    dados = request.json
    senha_digitada = dados.get('senha')
    senha_mestra = os.environ.get("MASTER_PASSWORD")

    if senha_digitada == senha_mestra:
        return jsonify({"sucesso": True, "mensagem": "Acesso autorizado"}), 200
    return jsonify({"sucesso": False, "erro": "Senha incorreta"}), 401


@app.route('/api/master/unidades', methods=['GET', 'POST'])
def gerenciar_unidades():
    if db is None:
        return jsonify({"sucesso": False, "erro": "Banco de dados offline"}), 500
        
    colecao = db["unidades"]

    if request.method == 'POST':
        nova_unidade = request.json
        nova_unidade["criado_em"] = datetime.utcnow()
        nova_unidade["status"] = "ativa"
        
        resultado = colecao.insert_one(nova_unidade)
        return jsonify({"sucesso": True, "id": str(resultado.inserted_id)}), 201
        
    elif request.method == 'GET':
        unidades = list(colecao.find().sort("criado_em", -1))
        return jsonify({"sucesso": True, "unidades": parse_json(unidades)}), 200


# ==========================================
# ROTAS DO PAINEL DO CLIENTE (TENANT / ANTÔNIO)
# ==========================================

@app.route('/api/tenant/login', methods=['POST'])
def tenant_login():
    if db is None:
        return jsonify({"sucesso": False, "erro": "Banco de dados offline"}), 500

    dados = request.json
    cnpj = dados.get('cnpj')
    senha = dados.get('senha')

    colecao = db["unidades"]
    # Busca a unidade pelo CNPJ e Senha
    unidade = colecao.find_one({"cnpj": cnpj, "senha_acesso": senha})

    if unidade:
        if unidade.get("status") != "ativa":
            return jsonify({"sucesso": False, "erro": "Sua conta está inativa/bloqueada. Contate o suporte."}), 403
            
        return jsonify({
            "sucesso": True,
            "unidade_id": str(unidade["_id"]),
            "empresa": {
                "nome": unidade.get("nome_empresa"),
                "gestor": unidade.get("gestor"),
                "slogan": unidade.get("slogan"),
                "tema": unidade.get("tema")
            }
        }), 200
    
    return jsonify({"sucesso": False, "erro": "CNPJ ou Senha inválidos"}), 401


@app.route('/api/tenant/regulacoes', methods=['GET', 'POST'])
def gerenciar_regulacoes():
    if db is None:
        return jsonify({"sucesso": False, "erro": "Banco de dados offline"}), 500

    colecao = db["regulacoes"]

    if request.method == 'POST':
        nova_req = request.json
        
        # Gera um número de protocolo aleatório/sequencial (Ex: REQ-1A2B)
        import random, string
        codigo = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        nova_req["protocolo"] = f"REQ-{codigo}"
        nova_req["status_atual"] = "Em Análise"
        nova_req["criado_em"] = datetime.utcnow()
        
        resultado = colecao.insert_one(nova_req)
        return jsonify({"sucesso": True, "protocolo": nova_req["protocolo"], "id": str(resultado.inserted_id)}), 201
        
    elif request.method == 'GET':
        unidade_id = request.args.get('unidade_id')
        if not unidade_id:
            return jsonify({"sucesso": False, "erro": "ID da unidade é obrigatório"}), 400
            
        # Busca a fila apenas daquela unidade específica
        regulacoes = list(colecao.find({"unidade_id": unidade_id}).sort("criado_em", -1))
        return jsonify({"sucesso": True, "regulacoes": parse_json(regulacoes)}), 200


if __name__ == '__main__':
    app.run(debug=True)
