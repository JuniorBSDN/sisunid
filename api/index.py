from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request
import urllib.error
import mimetypes
import base64


class handler(BaseHTTPRequestHandler):

    def _set_headers(self, status=200):
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(200)

    def _obter_url_supabase(self):
        return os.environ.get('SUPABASE_URL', "https://scotyvkhwptckrvrjzdi.supabase.co")

    def _safe_int(self, value):
        try:
            return int(value) if value else None
        except Exception:
            return None

    def _executar_requisicao(self, url, method='GET', payload=None, headers_extra=None):
        sb_key = os.environ.get('SUPABASE_SERVICE_KEY', '')
        headers = {
            'apikey': sb_key,
            'Authorization': f'Bearer {sb_key}',
            'Content-Type': 'application/json'
        }
        if headers_extra:
            headers.update(headers_extra)

        data = json.dumps(payload).encode('utf-8') if payload else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        
        with urllib.request.urlopen(req) as response:
            res_body = response.read().decode('utf-8')
            return json.loads(res_body) if res_body else {}

    def do_POST(self):
    try:
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            self._set_headers(400)
            self.wfile.write(json.dumps({"erro": "Payload ausente"}).encode('utf-8'))
            return

        post_data = self.rfile.read(content_length)

        # Trata o decode prevenindo estouro de exceção por bytes binários brutos
    try:
        payload_str = post_data.decode('utf-8')
        except UnicodeDecodeError:
            self._set_headers(400)
            self.wfile.write(json.dumps({
                "erro": "O arquivo enviado não está no formato Base64 correto."
            }).encode('utf-8'))
            return

            dados = json.loads(payload_str)
            action = dados.get('action')

            sb_url = self._obter_url_supabase()
            sb_key = os.environ.get('SUPABASE_SERVICE_KEY', '')
            senha_mestra = os.environ.get('USER_SENHA', '')

        except Exception as e:
            self._set_headers(500)
            self.wfile.write(json.dumps({"erro": f"Erro interno do servidor: {str(e)}"}).encode('utf-8'))
            self._set_headers(200)
        

            # ==========================================
            # 1. ROTAS PAINEL MASTER (SUPER ADMIN)
            # ==========================================
            if action == 'verificar_senha_master':
                senha_digitada = dados.get('senha')
                self.wfile.write(json.dumps({"autorizado": senha_digitada == senha_mestra}).encode('utf-8'))
                return

            elif action == 'upload_logo':
                file_base64 = dados.get('file_base64')
                filename = dados.get('filename')
                file_bytes = base64.b64decode(file_base64.split(",")[-1])
                url_storage = f"{sb_url}/storage/v1/object/logos/{filename}"
                content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'

                req = urllib.request.Request(
                    url_storage, data=file_bytes,
                    headers={'apikey': sb_key, 'Authorization': f'Bearer {sb_key}', 'Content-Type': content_type},
                    method='POST'
                )
                try:
                    with urllib.request.urlopen(req):
                        pass
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        self.wfile.write(json.dumps({"erro": "O bucket 'logos' não existe no Supabase."}).encode('utf-8'))
                        return
                    raise e

                url_publica = f"{sb_url}/storage/v1/object/public/logos/{filename}"
                self.wfile.write(json.dumps({"sucesso": True, "url_logo": url_publica}).encode('utf-8'))
                return

            elif action == 'cadastrar_unidade':
                url = f"{sb_url}/rest/v1/unidades"
                payload = {
                    "nome_responsavel": dados.get('nome_responsavel'),
                    "nome_unidade": dados.get('nome_unidade'),
                    "whatsapp": dados.get('whatsapp'),
                    "email": dados.get('email'),
                    "documento": dados.get('documento'),
                    "data_inicio": dados.get('data_inicio'),
                    "endereco": dados.get('endereco'),
                    "senha_admin": dados.get('senha_admin'),
                    "cor_layout": dados.get('cor_layout'),
                    "url_logo": dados.get('url_logo'),
                    "status": "Ativo"
                }
                self._executar_requisicao(url, method='POST', payload=payload)
                self.wfile.write(json.dumps({"sucesso": True}).encode('utf-8'))
                return

            elif action == 'dados_dashboard_master':
                url = f"{sb_url}/rest/v1/unidades?select=id,nome_responsavel,nome_unidade,status,cor_layout,url_logo,whatsapp,email,documento,data_inicio,endereco,senha_admin&order=id.desc"
                unidades = self._executar_requisicao(url, method='GET')
                self.wfile.write(json.dumps({"unidades": unidades}).encode('utf-8'))
                return

            elif action == 'editar_unidade':
                uid = dados.get('id')
                url = f"{sb_url}/rest/v1/unidades?id=eq.{uid}"
                body = {
                    "nome_responsavel": dados.get('nome_responsavel'),
                    "nome_unidade": dados.get('nome_unidade'),
                    "whatsapp": dados.get('whatsapp'),
                    "email": dados.get('email'),
                    "documento": dados.get('documento'),
                    "data_inicio": dados.get('data_inicio'),
                    "endereco": dados.get('endereco'),
                    "cor_layout": dados.get('cor_layout')
                }
                if dados.get('url_logo'):
                    body["url_logo"] = dados.get('url_logo')

                self._executar_requisicao(url, method='PATCH', payload=body)
                self.wfile.write(json.dumps({"sucesso": True}).encode('utf-8'))
                return

            elif action == 'alterar_status_unidade':
                uid = dados.get('id')
                url = f"{sb_url}/rest/v1/unidades?id=eq.{uid}"
                self._executar_requisicao(url, method='PATCH', payload={"status": dados.get('status')})
                self.wfile.write(json.dumps({"sucesso": True}).encode('utf-8'))
                return

            elif action == 'excluir_unidade':
                uid = dados.get('id')
                url = f"{sb_url}/rest/v1/unidades?id=eq.{uid}"
                self._executar_requisicao(url, method='DELETE')
                self.wfile.write(json.dumps({"sucesso": True}).encode('utf-8'))
                return

            # ==========================================
            # 2. ROTAS PAINEL OPERACIONAL DA UNIDADE
            # ==========================================
            elif action == 'verificar_login_unidade':
                senha_input = dados.get('senha')
                url = f"{sb_url}/rest/v1/unidades?senha_admin=eq.{senha_input}&status=eq.Ativo&select=id,nome_unidade,cor_layout,url_logo"
                res_data = self._executar_requisicao(url, method='GET')

                if res_data and len(res_data) > 0:
                    self.wfile.write(json.dumps({"autorizado": True, "unidade": res_data[0]}).encode('utf-8'))
                else:
                    self.wfile.write(json.dumps({"autorizado": False, "mensagem": "Acesso suspenso ou credencial inválida."}).encode('utf-8'))
                return

            # --- COLABORADORES / EQUIPE ---
            elif action == 'listar_colaboradores':
                unidade_id = dados.get('unidade_id')
                url = f"{sb_url}/rest/v1/colaboradores?unidade_id=eq.{unidade_id}&order=id.desc"
                colabs = self._executar_requisicao(url, method='GET')
                self.wfile.write(json.dumps({"colaboradores": colabs}).encode('utf-8'))
                return

            elif action == 'cadastrar_colaborador':
                url = f"{sb_url}/rest/v1/colaboradores"
                payload = {
                    "nome": dados.get('nome'),
                    "cargo": dados.get('cargo'),
                    "whatsapp": dados.get('whatsapp'),
                    "email": dados.get('email'),
                    "documento": dados.get('documento'),
                    "data_nascimento": dados.get('data_nascimento'),
                    "endereco": dados.get('endereco'),
                    "conta_bancaria": dados.get('conta_bancaria'),
                    "url_foto": dados.get('url_foto'),
                    "unidade_id": self._safe_int(dados.get('unidade_id')),
                    "status": "Ativo"
                }
                self._executar_requisicao(url, method='POST', payload=payload, headers_extra={'Prefer': 'return=representation'})
                self.wfile.write(json.dumps({"sucesso": True}).encode('utf-8'))
                return

            # --- CLIENTES / LEADS ---
            elif action == 'salvar_cliente':
                url = f"{sb_url}/rest/v1/clientes"
                payload = {
                    "nome": dados.get('nome'),
                    "whatsapp": dados.get('whatsapp'),
                    "bairro": dados.get('bairro'),
                    "documento_cliente": dados.get('documento_cliente'),
                    "historico_demanda": dados.get('demanda'),
                    "unidade_id": self._safe_int(dados.get('unidade_id')),
                    "status": "Ativo"
                }
                self._executar_requisicao(url, method='POST', payload=payload, headers_extra={'Prefer': 'return=representation'})
                self.wfile.write(json.dumps({"sucesso": True}).encode('utf-8'))
                return

            elif action == 'listar_clientes_unidade':
                unidade_id = dados.get('unidade_id')
                url = f"{sb_url}/rest/v1/clientes?unidade_id=eq.{unidade_id}&order=id.desc"
                clientes = self._executar_requisicao(url, method='GET')
                self.wfile.write(json.dumps({"clientes": clientes}).encode('utf-8'))
                return

            # --- AGENDA / COMPROMISSOS ---
            elif action == 'listar_agenda_unidade':
                unidade_id = dados.get('unidade_id')
                url = f"{sb_url}/rest/v1/agenda?unidade_id=eq.{unidade_id}&order=data_evento.asc,hora_evento.asc"
                agenda = self._executar_requisicao(url, method='GET')
                self.wfile.write(json.dumps({"agenda": agenda}).encode('utf-8'))
                return

            elif action == 'cadastrar_agenda':
                url = f"{sb_url}/rest/v1/agenda"
                payload = {
                    "titulo": dados.get('titulo'),
                    "tipo": 'Compromisso',
                    "data_evento": dados.get('data'),
                    "hora_evento": dados.get('hora'),
                    "unidade_id": self._safe_int(dados.get('unidade_id')),
                    "status": 'Confirmado'
                }
                self._executar_requisicao(url, method='POST', payload=payload, headers_extra={'Prefer': 'return=representation'})
                self.wfile.write(json.dumps({"sucesso": True}).encode('utf-8'))
                return

            else:
                self.wfile.write(json.dumps({"erro": f"Ação desconhecida: {action}"}).encode('utf-8'))

        except Exception as e:
            self._set_headers(500)
            self.wfile.write(json.dumps({"erro": f"Erro interno do servidor: {str(e)}"}).encode('utf-8'))
