from flask import Flask, request, jsonify
from pymongo import MongoClient
import os
from datetime import datetime

# Inicializa o app Flask
app = Flask(__name__)

# ----------------------------------------------------
# CONEXÃO COM O MONGODB ATLAS
# A Vercel vai injetar o MONGO_URI automaticamente
# ----------------------------------------------------
MONGO_URI = os.environ.get("MONGO_URI")

# Verifica se a URI existe (evita quebrar se esquecer de configurar na Vercel)
if MONGO_URI:
    client = MongoClient(MONGO_URI)
    db = client["sisUnid"]  # Nome do seu banco de dados
else:
    db = None


# ----------------------------------------------------
# ROTA 1: LOGIN DO SUPER ADMIN (MASTER)
# ----------------------------------------------------
@app.route('/api/master/login', methods=['POST'])
def master_login():
    dados = request.json
    senha_digitada = dados.get('senha')

    # Puxa a senha secreta cadastrada na Vercel
    senha_mestra = os.environ.get("MASTER_PASSWORD")

    if senha_digitada == senha_mestra:
        return jsonify({"sucesso": True, "mensagem": "Acesso autorizado"}), 200
    else:
        return jsonify({"sucesso": False, "mensagem": "Acesso negado. Senha incorreta."}), 401


# ----------------------------------------------------
# ROTA 2: CADASTRAR E LISTAR UNIDADES (CLIENTES)
# ----------------------------------------------------
@app.route('/api/master/unidades', methods=['GET', 'POST'])
def gerenciar_unidades():
    if db is None:
        return jsonify({"sucesso": False, "erro": "Banco de dados não conectado"}), 500

    colecao_unidades = db["unidades"]

    if request.method == 'POST':
        # Recebe os dados do formulário do seu master.html
        nova_unidade = request.json
        nova_unidade["criado_em"] = datetime.utcnow()
        nova_unidade["status"] = "ativa"

        # Salva no MongoDB
        resultado = colecao_unidades.insert_one(nova_unidade)

        return jsonify({
            "sucesso": True,
            "mensagem": "Cliente cadastrado com sucesso",
            "id": str(resultado.inserted_id)
        }), 201

    elif request.method == 'GET':
        # Busca todos os clientes para mostrar na sua tabela
        # O argumento {"_id": 0} esconde o ID criptografado para facilitar o JSON no front
        unidades = list(colecao_unidades.find({}, {"_id": 0}))

        return jsonify({
            "sucesso": True,
            "total": len(unidades),
            "unidades": unidades
        }), 200


# Necessário para rodar o app localmente durante seus testes
if __name__ == '__main__':
    app.run(debug=True)