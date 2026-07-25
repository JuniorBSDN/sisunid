import os
import uuid
from flask import Flask, request, jsonify, send_from_directory, send_file
from supabase import create_client, Client

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
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()

# Trata a senha master com valor fallback para não quebrar no boot
MASTER_PASSWORD = (os.environ.get("MASTER_PASSWORD") or "admin").strip()

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print("Aviso: Falha ao inicializar Supabase:", str(e))

BUCKET_NAME = "uploads"


def adaptar_id_para_frontend(doc):
    """
    Mantém a compatibilidade com o Frontend que esperava o '_id' do MongoDB.
    Clona a chave 'id' do Supabase para '_id'.
    """
    if doc and 'id' in doc:
        doc['_id'] = str(doc['id'])
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
    if supabase is None:
        return jsonify({"sucesso": False, "erro": "Banco de dados Supabase offline."}), 500
    try:
        # Busca ordenando pelo ID de forma decrescente (mais recentes primeiro)
        response = supabase.table("unidades").select("*").order("id", desc=True).execute()
        unidades = response.data
        
        unidades_formatadas = [adaptar_id_para_frontend(u) for u in unidades]
        return jsonify({"sucesso": True, "unidades": unidades_formatadas})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500


@app.route('/api/master/unidades', methods=['POST'])
def criar_unidade():
    if supabase is None:
        return jsonify({"sucesso": False, "erro": "Banco de dados Supabase offline."}), 500

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

        if 'logo' in request.files:
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

        supabase.table("unidades").insert(nova_unidade).execute()
        return jsonify({"sucesso": True, "mensagem": "Unidade criada com sucesso!"})

    except Exception as e:
        print("Erro ao Salvar Unidade:", str(e))
        return jsonify({"sucesso": False, "erro": str(e)}), 500


@app.route('/api/master/unidades/<id>/status', methods=['PATCH'])
def alterar_status_unidade(id):
    if supabase is None:
        return jsonify({"sucesso": False, "erro": "Banco offline."}), 500
    try:
        data = request.get_json(silent=True) or {}
        novo_status = data.get('status')

        supabase.table("unidades").update({"status": novo_status}).eq("id", id).execute()
        
        return jsonify({"sucesso": True})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500


# ==========================================
# 3. ROTAS DO PAINEL DO CLIENTE (TENANT)
# ==========================================

@app.route('/api/tenant/login', methods=['POST'])
def tenant_login():
    if supabase is None:
        return jsonify({"sucesso": False, "erro": "Banco offline."}), 500

    data = request.get_json(silent=True) or {}
    cnpj = data.get('cnpj')
    senha = data.get('senha')

    try:
        response = supabase.table("unidades").select("*")\
            .eq("cnpj", cnpj)\
            .eq("senha_acesso", senha)\
            .eq("status", "ativa")\
            .execute()
            
        unidades = response.data

        if unidades and len(unidades) > 0:
            unidade = unidades[0]
            return jsonify({
                "sucesso": True,
                "unidade_id": str(unidade['id']),  # Mantido string para o JS
                "empresa": {
                    "nome": unidade.get('nome_empresa'),
                    "gestor": unidade.get('gestor'),
                    "slogan": unidade.get('slogan'),
                    "tema": unidade.get('tema'),
                    "logo_url": unidade.get('logo_url')
                }
            })
            
        return jsonify({"sucesso": False, "erro": "CNPJ ou Senha inválidos, ou unidade bloqueada."}), 401
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500


@app.route('/api/tenant/regulacoes', methods=['GET'])
def get_regulacoes():
    if supabase is None:
        return jsonify({"sucesso": False, "erro": "Banco offline."}), 500

    unidade_id = request.args.get('unidade_id')
    if not unidade_id:
        return jsonify({"sucesso": False, "erro": "ID da unidade é obrigatório"}), 400

    try:
        response = supabase.table("regulacoes").select("*").eq("unidade_id", unidade_id).order("id", desc=True).execute()
        regulacoes = response.data
        
        regs_formatadas = [adaptar_id_para_frontend(r) for r in regulacoes]
        return jsonify({"sucesso": True, "regulacoes": regs_formatadas})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500


@app.route('/api/tenant/regulacoes', methods=['POST'])
def criar_regulacao():
    if supabase is None:
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

        supabase.table("regulacoes").insert(novo_paciente).execute()
        return jsonify({"sucesso": True, "protocolo": protocolo})

    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
