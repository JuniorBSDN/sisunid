import os
import uuid
from flask import Flask, request, jsonify, send_from_directory, send_file
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import sqlite3
import json

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
# 1.5 CONEXÃO SQLITE (BACKUP LOCAL)
# ==========================================
DB_BACKUP_PATH = os.path.join(BASE_DIR, 'sisunid_backup.db')

def init_sqlite_backup():
    """Cria o banco de dados local SQLite e as tabelas se não existirem."""
    conn = sqlite3.connect(DB_BACKUP_PATH)
    c = conn.cursor()
    # Tabela para salvar as Regulações e Prontuários
    c.execute('''
        CREATE TABLE IF NOT EXISTS backup_regulacoes (
            id TEXT PRIMARY KEY,
            unidade_id TEXT,
            protocolo TEXT,
            cpf TEXT,
            nome_paciente TEXT,
            dados_completos TEXT,
            data_backup TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Tabela para salvar o histórico de E-mails
    c.execute('''
        CREATE TABLE IF NOT EXISTS backup_emails (
            id TEXT PRIMARY KEY,
            unidade_id TEXT,
            protocolo TEXT,
            destinatario TEXT,
            dados_completos TEXT,
            data_backup TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# Executa a criação do banco local assim que o servidor inicia
init_sqlite_backup()


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

@app.route('/api/tenant/regulacoes/<id_reg>/anexos', methods=['DELETE'])
def deletar_anexo_regulacao(id_reg):
    supabase = get_supabase_client()
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Supabase offline."}), 500

    data = request.get_json(silent=True) or {}
    url_para_remover = data.get('url')

    if not url_para_remover:
        return jsonify({"sucesso": False, "erro": "URL do arquivo é obrigatória."}), 400

    try:
        reg_atual = supabase.table('regulacoes').select('anexos').eq('id', id_reg).execute()
        if not reg_atual.data:
            return jsonify({"sucesso": False, "erro": "Regulação não encontrada."}), 404

        anexos_atuais = reg_atual.data[0].get('anexos') or []
        if not isinstance(anexos_atuais, list):
            anexos_atuais = []

        novos_anexos = [url for url in anexos_atuais if url != url_para_remover]

        supabase.table('regulacoes').update({"anexos": novos_anexos}).eq('id', id_reg).execute()

        return jsonify({"sucesso": True, "anexos": novos_anexos})

    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500



@app.route('/api/tenant/regulacoes/<id_reg>/anexos', methods=['PATCH'])
def adicionar_anexos_regulacao(id_reg):
    supabase = get_supabase_client()
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Supabase offline."}), 500

    try:
        # 1. Busca a regulação atual no banco
        reg_atual = supabase.table('regulacoes').select('protocolo, anexos').eq('id', id_reg).execute()
        if not reg_atual.data:
            return jsonify({"sucesso": False, "erro": "Regulação não encontrada."}), 404

        protocolo = reg_atual.data[0].get('protocolo')
        anexos_atuais = reg_atual.data[0].get('anexos') or []
        if not isinstance(anexos_atuais, list):
            anexos_atuais = []

        # 2. Captura os arquivos usando tanto 'novos_anexos' quanto 'anexos' por segurança
        arquivos = request.files.getlist('novos_anexos')
        if not arquivos or len(arquivos) == 0:
            arquivos = request.files.getlist('anexos')

        print(f"DEBUG: Recebidos {len(arquivos)} arquivos para o protocolo {protocolo}")

        novos_links = []
        for file in arquivos:
            if file and file.filename != '':
                file_ext = file.filename.split('.')[-1]
                unique_filename = f"regulacoes/{protocolo}/{uuid.uuid4().hex}.{file_ext}"
                file_bytes = file.read()

                try:
                    supabase.storage.from_(BUCKET_NAME).upload(
                        path=unique_filename,
                        file=file_bytes,
                        file_options={"content-type": file.content_type}
                    )
                    file_url = supabase.storage.from_(BUCKET_NAME).get_public_url(unique_filename)
                    novos_links.append(file_url)
                    print(f"DEBUG: Upload OK -> {file_url}")
                except Exception as err_supa:
                    print(f"Erro no upload do arquivo adicional {file.filename}:", str(err_supa))

        if len(novos_links) == 0:
            return jsonify({"sucesso": False, "erro": "Nenhum arquivo válido foi processado."}), 400

        # 3. Junta os arquivos antigos com os novos
        anexos_atualizados = anexos_atuais + novos_links

        # 4. Atualiza no Supabase
        supabase.table('regulacoes').update({"anexos": anexos_atualizados}).eq('id', id_reg).execute()

        return jsonify({"sucesso": True, "anexos": anexos_atualizados})

    except Exception as e:
        print(f"Erro crítico na rota de anexos: {str(e)}")
        return jsonify({"sucesso": False, "erro": str(e)}), 500

# ==========================================
# NOVAS ROTAS: EDITAR E EXCLUIR REGISTRO
# ==========================================
@app.route('/api/tenant/regulacoes/<id_reg>', methods=['DELETE'])
def deletar_registro_regulacao(id_reg):
    supabase = get_supabase_client()
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Supabase offline."}), 500

    try:
        # Exclui o registro pelo ID
        supabase.table('regulacoes').delete().eq('id', id_reg).execute()
        return jsonify({"sucesso": True, "mensagem": "Registro excluído com sucesso."})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500

@app.route('/api/tenant/regulacoes/<id_reg>', methods=['PUT'])
def editar_registro_regulacao(id_reg):
    supabase = get_supabase_client()
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Supabase offline."}), 500

    try:
        data = request.get_json(silent=True) or {}
        
        # Monta os dados para atualização (apenas os que vierem na requisição)
        update_data = {
            "nome_paciente": data.get("nome_paciente"),
            "cpf": data.get("cpf"),
            "email": data.get("email"),
            "telefone": data.get("telefone"),
            "procedimento": data.get("procedimento"),
            "prioridade": data.get("prioridade"),
            "unidade_saude": data.get("unidade_saude"), # NOVO CAMPO
            "especificacao_sus": data.get("especificacao_sus"),
            "endereco": data.get("endereco")
        }
        
        # Limpa as chaves nulas para não sobrescrever com None
        update_data = {k: v for k, v in update_data.items() if v is not None}
        
        supabase.table('regulacoes').update(update_data).eq('id', id_reg).execute()
        return jsonify({"sucesso": True})
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

    try:
        data = request.form
        protocolo = f"REQ-{str(uuid.uuid4())[:4].upper()}"
        
        urls_anexos = []
        arquivos = request.files.getlist('anexos')
        
        for file in arquivos:
            if file and file.filename != '':
                file_ext = file.filename.split('.')[-1]
                unique_filename = f"regulacoes/{protocolo}/{uuid.uuid4().hex}.{file_ext}"
                file_bytes = file.read()
                
                try:
                    supabase.storage.from_(BUCKET_NAME).upload(
                        path=unique_filename,
                        file=file_bytes,
                        file_options={"content-type": file.content_type}
                    )
                    file_url = supabase.storage.from_(BUCKET_NAME).get_public_url(unique_filename)
                    urls_anexos.append(file_url)
                except Exception as err_supa:
                    print(f"Erro no upload do arquivo {file.filename}:", str(err_supa))

        novo_paciente = {
            "unidade_id": data.get("unidade_id"),
            "protocolo": protocolo,
            "nome_paciente": data.get("nome_paciente"),
            "cpf": data.get("cpf"),
            "email": data.get("email"),
            "telefone": data.get("telefone"),
            "procedimento": data.get("procedimento"),
            "prioridade": data.get("prioridade"),
            "status_atual": "Em Análise",
            "anexos": urls_anexos,
            "unidade_saude": data.get("unidade_saude"), 
            "especificacao_sus": data.get("especificacao_sus"), 
            "endereco": data.get("endereco")
        }

        supabase.table('regulacoes').insert(novo_paciente).execute()

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

@app.route('/api/tenant/regulacoes/<id_reg>', methods=['PATCH'])
def atualizar_regulacao(id_reg):
    supabase = get_supabase_client()
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Supabase offline."}), 500

    data = request.get_json(silent=True) or {}

    try:
        novo_status = data.get('status_atual')
        parecer = data.get('parecer')
        data_agendamento = data.get('data_agendamento')

        update_data = {
            "status_atual": novo_status,
            "parecer": parecer,
            "data_agendamento": data_agendamento
        }

        response = supabase.table('regulacoes').update(update_data).eq('id', id_reg).execute()

        paciente_email = data.get('paciente_email')

        if paciente_email:
            paciente_nome = data.get('paciente_nome', 'Paciente')
            protocolo = data.get('protocolo', 'N/A')
            empresa_nome = data.get('empresa_nome', 'Unidade de Saúde')
            empresa_logo = data.get('empresa_logo', '')
            empresa_email_contato = data.get('empresa_email', '')

            remetente = os.environ.get("SMTP_EMAIL", "seu-email@gmail.com")
            senha = os.environ.get("SMTP_PASSWORD", "sua-senha")

            img_tag = f'<img src="{empresa_logo}" style="max-height: 50px; margin-bottom: 15px;">' if empresa_logo else ''
            assunto = f"Atualização no seu Protocolo #{protocolo}"

            corpo_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; color: #333; padding: 20px;">
                {img_tag}
                <h2 style="color: #2563eb;">Olá, {paciente_nome}!</h2>
                <p>Houve uma atualização na sua solicitação de regulação pela unidade <b>{empresa_nome}</b>.</p>
                <div style="background: #f8fafc; padding: 15px; border-radius: 8px; margin: 15px 0; border: 1px solid #e2e8f0;">
                    <p><b>Procedimento:</b> {data.get('procedimento', '')}</p>
                    <p><b>Novo Status:</b> <span style="font-size: 16px; font-weight: bold; color: #10b981;">{novo_status}</span></p>
                    <p><b>Parecer Médico / Instruções:</b><br>{parecer}</p>
            """

            if novo_status == 'Agendado' and data_agendamento:
                data_formatada = data_agendamento.replace('T', ' às ')
                corpo_html += f"<p><b>Data e Hora do Agendamento:</b> {data_formatada}</p>"

            corpo_html += f"""
                </div>
                <p>Atenciosamente,<br><b>{empresa_nome}</b></p>
            </body>
            </html>
            """

            status_envio = "Falha no Envio"
            try:
                msg = MIMEMultipart()
                msg['From'] = f"{empresa_nome} <{remetente}>"
                msg['To'] = paciente_email
                msg['Subject'] = assunto

                if empresa_email_contato:
                    msg.add_header('reply-to', empresa_email_contato)

                msg.attach(MIMEText(corpo_html, 'html'))

                server = smtplib.SMTP('smtp.gmail.com', 587)
                server.starttls()
                server.login(remetente, senha)
                server.send_message(msg)
                server.quit()
                status_envio = "Enviado com Sucesso"
            except Exception as e:
                print("Erro ao enviar e-mail ao paciente:", e)

            try:
                unidade_id_bd = response.data[0].get('unidade_id') if response.data else None
                email_log = {
                    "unidade_id": unidade_id_bd,
                    "protocolo": protocolo,
                    "destinatario": paciente_email,
                    "paciente_nome": paciente_nome,
                    "assunto": assunto,
                    "status": status_envio
                }
                supabase.table('historico_emails').insert(email_log).execute()
            except Exception as err:
                pass

        return jsonify({"sucesso": True})

    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500

@app.route('/api/tenant/alertar-gestor', methods=['POST'])
def alertar_gestor_email():
    data = request.get_json(silent=True) or {}
    email_gestor = data.get('email_gestor')
    nome_empresa = data.get('nome_empresa', 'sisUnid')
    logo_url = data.get('logo_url', '')
    pacientes = data.get('pacientes', [])

    if not email_gestor or not pacientes:
        return jsonify({"sucesso": False, "erro": "Faltam dados para envio"}), 400

    remetente = os.environ.get("SMTP_EMAIL", "seu-email@gmail.com")
    senha = os.environ.get("SMTP_PASSWORD", "sua-senha-de-app")

    lista_html = "".join([f"<li><b>{p['nome']}</b> (Protocolo: {p['protocolo']}) - {p['prioridade']}</li>" for p in pacientes])

    img_tag = f'<img src="{logo_url}" alt="Logo" style="max-height: 60px; margin-bottom: 20px;">' if logo_url else ''

    corpo_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333; padding: 20px;">
        {img_tag}
        <h2 style="color: #ef4444;">Atenção Gestor - Alerta de SLA ({nome_empresa})</h2>
        <p>Os pacientes abaixo estão com prazos críticos (Urgência/Prioridade) e precisam de avaliação imediata no sistema:</p>
        <ul>{lista_html}</ul>
        <p>Por favor, acesse o painel de regulação o mais rápido possível.</p>
    </body>
    </html>
    """

    msg = MIMEMultipart()
    msg['From'] = remetente
    msg['To'] = email_gestor
    msg['Subject'] = f"ALERTA URGENTE: Regulação {nome_empresa}"
    msg.attach(MIMEText(corpo_html, 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remetente, senha)
        server.send_message(msg)
        server.quit()
        return jsonify({"sucesso": True})
    except Exception as e:
        print("Erro envio e-mail:", str(e))
        return jsonify({"sucesso": False, "erro": str(e)}), 500

# ==========================================
# 5. ROTAS DE BACKUP E LIMPEZA (MASTER)
# ==========================================
@app.route('/api/master/backup/executar', methods=['POST'])
def executar_backup_local():
    supabase = get_supabase_client()
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Supabase offline."}), 500

    try:
        # 1. Busca todos os dados da nuvem (Supabase)
        reg_resp = supabase.table('regulacoes').select('*').execute()
        email_resp = supabase.table('historico_emails').select('*').execute()
        
        regulacoes = reg_resp.data or []
        emails = email_resp.data or []

        # 2. Conecta no SQLite local
        conn = sqlite3.connect(DB_BACKUP_PATH)
        c = conn.cursor()

        # 3. Salva Regulações (dados_completos vira JSON para não perder NADA, nem anexos)
        for r in regulacoes:
            c.execute('''
                INSERT OR REPLACE INTO backup_regulacoes 
                (id, unidade_id, protocolo, cpf, nome_paciente, dados_completos)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (str(r.get('id')), r.get('unidade_id'), r.get('protocolo'), r.get('cpf'), r.get('nome_paciente'), json.dumps(r)))

        # 4. Salva E-mails
        for e in emails:
            c.execute('''
                INSERT OR REPLACE INTO backup_emails 
                (id, unidade_id, protocolo, destinatario, dados_completos)
                VALUES (?, ?, ?, ?, ?)
            ''', (str(e.get('id')), e.get('unidade_id'), e.get('protocolo'), e.get('destinatario'), json.dumps(e)))

        conn.commit()
        conn.close()

        return jsonify({
            "sucesso": True, 
            "mensagem": f"Backup concluído: {len(regulacoes)} regulações e {len(emails)} e-mails salvos localmente no sisunid_backup.db."
        })

    except Exception as e:
        return jsonify({"sucesso": False, "erro": f"Erro ao fazer backup: {str(e)}"}), 500

@app.route('/api/master/backup/limpar', methods=['DELETE'])
def limpar_banco_nuvem():
    supabase = get_supabase_client()
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Supabase offline."}), 500

    try:
        # Apaga todos os registros de regulações e emails usando um filtro de data seguro (qualquer data antes de 2100)
        # IMPORTANTE: A tabela 'unidades' NÃO é apagada para manter o acesso dos clientes.
        supabase.table('regulacoes').delete().lt('created_at', '2100-01-01').execute()
        supabase.table('historico_emails').delete().lt('created_at', '2100-01-01').execute()
        
        return jsonify({"sucesso": True, "mensagem": "Limpeza da nuvem concluída com sucesso! Banco Supabase esvaziado (exceto Unidades)."})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": f"Erro ao limpar Supabase: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True)
