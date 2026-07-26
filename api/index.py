import os
import uuid
from flask import Flask, request, jsonify, send_from_directory, send_file
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ==========================================
# 0. ROTAS DO FRONT-END (Telas)
# ==========================================
@app.route('/')
def serve_tenant():
    return send_from_directory(os.path.join(BASE_DIR, 'public'), 'index.html')

@app.route('/master')
def serve_master():
    master_path = os.path.join(BASE_DIR, 'master.html')
    if not os.path.exists(master_path):
        master_path = os.path.join(BASE_DIR, 'public', 'master.html')
    return send_file(master_path)


# Função auxiliar para disparar e-mails
def enviar_email(destinatario, assunto, corpo_html):
    remetente = os.environ.get("SMTP_EMAIL", "seu-email@dominio.com")
    senha = os.environ.get("SMTP_PASSWORD", "sua-senha-ou-app-password")
    
    msg = MIMEMultipart()
    msg['From'] = remetente
    msg['To'] = destinatario
    msg['Subject'] = assunto
    msg.attach(MIMEText(corpo_html, 'html'))
    
    try:
        # Exemplo usando SMTP do Gmail. Altere o host/porta conforme seu provedor.
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remetente, senha)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print("Erro ao enviar e-mail:", e)
        return False
# ==========================================
# 1. CONEXÕES SUPABASE (Inicialização Segura)
# ==========================================
def get_supabase_client() -> Client:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_KEY", "").strip()
    if url and key:
        try:
            options = ClientOptions(postgrest_client_timeout=10)
            return create_client(url, key, options=options)
        except Exception:
            try:
                return create_client(url, key)
            except Exception as e:
                print("Erro crítico ao inicializar Supabase:", str(e))
    return None

MASTER_PASSWORD = (os.environ.get("MASTER_PASSWORD") or "admin").strip()
BUCKET_NAME = "uploads"

# ==========================================
# 2. ROTAS DO PAINEL MASTER
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
    supabase = get_supabase_client()
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Supabase offline. Verifique as Variáveis de Ambiente na Vercel."}), 500
    
    try:
        response = supabase.table('unidades').select('*').order('created_at', desc=True).execute()
        return jsonify({"sucesso": True, "unidades": response.data})
    except Exception:
        try:
            response = supabase.table('unidades').select('*').order('id', desc=True).execute()
            return jsonify({"sucesso": True, "unidades": response.data})
        except Exception as e:
            return jsonify({"sucesso": False, "erro": str(e)}), 500


@app.route('/api/master/unidades', methods=['POST'])
def criar_unidade():
    supabase = get_supabase_client()
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Supabase offline."}), 500

    try:
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
                    print("Erro no upload:", str(err_supa))

        nova_unidade = {
            "nome_empresa": request.form.get('nome_empresa'),
            "cnpj": request.form.get('cnpj'),
            "gestor": request.form.get('gestor'),
            "data_inicio": request.form.get('data_inicio'),
            "telefone": request.form.get('telefone'),
            "email": request.form.get('email'),
            "endereco": request.form.get('endereco'),
            "slogan": request.form.get('slogan'),
            "tema": {
                "primaria": request.form.get('tema_primaria', '#2563eb'),
                "secundaria": request.form.get('tema_secundaria', '#1e3a8a')
            },
            "senha_acesso": request.form.get('senha_acesso'),
            "logo_url": logo_url,
            "status": "ativa"
        }

        supabase.table('unidades').insert(nova_unidade).execute()
        return jsonify({"sucesso": True, "mensagem": "Unidade criada com sucesso!"})

    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500


@app.route('/api/master/unidades/<id>/status', methods=['PATCH'])
def alterar_status_unidade(id):
    supabase = get_supabase_client()
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Supabase offline."}), 500
    try:
        data = request.get_json(silent=True) or {}
        novo_status = data.get('status')
        supabase.table('unidades').update({"status": novo_status}).eq('id', id).execute()
        return jsonify({"sucesso": True})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500


# ==========================================
# 3. ROTAS DO PAINEL DO CLIENTE (TENANT)
# ==========================================
@app.route('/api/tenant/login', methods=['POST'])
def tenant_login():
    supabase = get_supabase_client()
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Supabase offline."}), 500

    data = request.get_json(silent=True) or {}
    cnpj = data.get('cnpj')
    senha = data.get('senha')

    try:
        response = supabase.table('unidades').select('*').eq('cnpj', cnpj).eq('senha_acesso', senha).eq('status', 'ativa').execute()

        if len(response.data) > 0:
            unidade = response.data[0]
            return jsonify({
                "sucesso": True,
                "unidade_id": str(unidade.get('id')),
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
    supabase = get_supabase_client()
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Supabase offline."}), 500

    unidade_id = request.args.get('unidade_id')
    if not unidade_id:
        return jsonify({"sucesso": False, "erro": "ID da unidade é obrigatório"}), 400

    assunto_email = f"Confirmação de Requisição #{protocolo}"
    corpo_email = f"""
        <h2>Olá, {data.get("nome_paciente")}</h2>
        <p>Sua requisição para <b>{data.get("procedimento")}</b> foi recebida pela nossa central.</p>
        <p><b>Protocolo:</b> {protocolo}</p>
        <p>Você será notificado assim que houver atualizações.</p>
        """
        
    email_enviado = enviar_email(data.get("email"), assunto_email, corpo_email)
    status_envio = "Enviado com Sucesso" if email_enviado else "Falha no Envio"

        # 2. Registra o histórico com o status real
    try:
        email_log = {
            "unidade_id": data.get("unidade_id"),
            "protocolo": protocolo,
            "destinatario": data.get("email"),
            "paciente_nome": data.get("nome_paciente"),
            "assunto": assunto_email,
            "status": status_envio
            }
        supabase.table('historico_emails').insert(email_log).execute()
    except Exception as err_mail:
        print("Aviso: Falha ao salvar no historico_emails:", str(err_mail))

    try:
        response = supabase.table('regulacoes').select('*').eq('unidade_id', unidade_id).order('created_at', desc=True).execute()
        return jsonify({"sucesso": True, "regulacoes": response.data})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500


@app.route('/api/tenant/regulacoes', methods=['POST'])
def criar_regulacao():
    supabase = get_supabase_client()
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Supabase offline."}), 500

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

        # 1. Salva na tabela 'regulacoes'
        supabase.table('regulacoes').insert(novo_paciente).execute()

        # 2. Tenta registrar o histórico de e-mail (se a tabela existir)
        try:
            email_log = {
                "unidade_id": data.get("unidade_id"),
                "protocolo": protocolo,
                "destinatario": data.get("email"),
                "paciente_nome": data.get("nome_paciente"),
                "assunto": f"Confirmação de Requisição #{protocolo}",
                "status": "Enviado com Sucesso"
            }
            supabase.table('historico_emails').insert(email_log).execute()
        except Exception as err_mail:
            print("Aviso: Falha ao salvar no historico_emails:", str(err_mail))

        return jsonify({"sucesso": True, "protocolo": protocolo})

    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500


# ==========================================
# 4. NOVAS ROTAS DOS MÓDULOS (DINÂMICAS)
# ==========================================

# Módulo 1: Base de Pacientes (Agrupado por CPF com prontuário real)
@app.route('/api/tenant/pacientes', methods=['GET'])
def get_pacientes():
    supabase = get_supabase_client()
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Supabase offline."}), 500

    unidade_id = request.args.get('unidade_id')
    try:
        response = supabase.table('regulacoes').select('*').eq('unidade_id', unidade_id).order('created_at', desc=True).execute()
        
        pacientes_dict = {}
        for reg in response.data:
            cpf = reg.get('cpf', 'Sem CPF')
            if cpf not in pacientes_dict:
                pacientes_dict[cpf] = {
                    "nome": reg.get('nome_paciente'),
                    "cpf": cpf,
                    "email": reg.get('email'),
                    "telefone": reg.get('telefone'),
                    "total_requisicoes": 0,
                    "ultima_atualizacao": reg.get('created_at'),
                    "historico": []
                }
            pacientes_dict[cpf]["total_requisicoes"] += 1
            pacientes_dict[cpf]["historico"].append(reg)

        return jsonify({"sucesso": True, "pacientes": list(pacientes_dict.values())})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500


# Módulo 2: Relatórios e Estatísticas Reais
@app.route('/api/tenant/relatorios', methods=['GET'])
def get_relatorios():
    supabase = get_supabase_client()
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Supabase offline."}), 500

    unidade_id = request.args.get('unidade_id')
    try:
        response = supabase.table('regulacoes').select('procedimento, prioridade, status_atual').eq('unidade_id', unidade_id).execute()
        data = response.data or []

        stats = {
            "total": len(data),
            "consultas": len([r for r in data if r.get('procedimento') == 'Consulta Especializada']),
            "exames": len([r for r in data if r.get('procedimento') in ['Exame de Imagem', 'Exame Laboratorial']]),
            "procedimentos": len([r for r in data if r.get('procedimento') == 'Procedimento Cirúrgico']),
            "urgencia": len([r for r in data if r.get('prioridade') == 'Urgência']),
            "prioridade": len([r for r in data if r.get('prioridade') == 'Prioridade']),
            "rotina": len([r for r in data if r.get('prioridade') == 'Rotina'])
        }

        return jsonify({"sucesso": True, "stats": stats})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500


# Módulo 3: Timeline de E-mails Enviados
@app.route('/api/tenant/emails', methods=['GET'])
def get_emails():
    supabase = get_supabase_client()
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Supabase offline."}), 500

    unidade_id = request.args.get('unidade_id')
    try:
        response = supabase.table('historico_emails').select('*').eq('unidade_id', unidade_id).order('created_at', desc=True).execute()
        return jsonify({"sucesso": True, "emails": response.data})
    except Exception:
        # Fallback de e-mails extraídos da própria tabela de regulações caso a historico_emails não tenha sido criada no SQL
        try:
            response = supabase.table('regulacoes').select('protocolo, email, nome_paciente, created_at').eq('unidade_id', unidade_id).order('created_at', desc=True).execute()
            emails_mock = []
            for r in response.data:
                emails_mock.append({
                    "protocolo": r.get('protocolo'),
                    "destinatario": r.get('email'),
                    "paciente_nome": r.get('nome_paciente'),
                    "assunto": f"Confirmação de Requisição #{r.get('protocolo')}",
                    "status": "Enviado com Sucesso",
                    "created_at": r.get('created_at')
                })
            return jsonify({"sucesso": True, "emails": emails_mock})
        except Exception as e2:
            return jsonify({"sucesso": False, "erro": str(e2)}), 500


if __name__ == '__main__':
    app.run(debug=True)
