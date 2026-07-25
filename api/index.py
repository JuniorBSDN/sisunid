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
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
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

    # ==========================================
    # ROTAS GET (Resolve Erro 501/500 no navegador)
    # ==========================================
    def do_GET(self):
        try:
            self._set_headers(200)
            sb_url = self._obter_url_supabase()
            
            # Suporte para requisições do dashboard/unidades
            if 'unidades' in self.path or 'master' in self.path:
                url = f"{sb_url}/rest/v1/unidades?select=id,nome_responsavel,nome_unidade,status,cor_layout,url_logo,whatsapp,email,documento,data_inicio,endereco,senha_admin&order=id.desc"
                unidades = self._executar_requisicao(url, method='GET')
                self.wfile.write(json.dumps({"unidades": unidades}).encode('utf-8'))
            else:
                self.wfile.write(json.dumps({"status": "API Online", "versao": "2.0.0"}).encode('utf-8'))
        except Exception as e:
            self._set_headers(500)
            self.wfile.write(json.dumps({"erro": f"Erro interno no GET: {str(e)}"}).encode('utf-8'))

    # ==========================================
    # ROTAS POST (Processamento Seguro de JSON)
    # ==========================================
    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self._set_headers(400)
                self.wfile.write(json.dumps({"erro": "Payload ausente"}).encode('utf-8'))
                return

            post_data = self.rfile.read(content_length)

            # Tratamento estrito contra envio de bytes binários puros
            try:
                payload_str = post_data.decode('utf-8')
                dados = json.loads(payload_str)
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._set_headers(400)
                self.wfile.write(json.dumps({
                    "erro": "Payload inválido. Certifique-se de converter imagens para Base64 antes do envio."
                }).encode('utf-8'))
                return

            action = dados.get('action')
            sb_url = self._obter_url_supabase()
            sb_key = os.environ.get('SUPABASE_SERVICE_KEY', '')
            senha_mestra = os.environ.get('USER_SENHA', '')

            self._set_headers(200)

            # --- AUTENTICAÇÃO E MASTER ---
            if action == 'verificar_senha_master':
                senha_digitada = dados.get('senha')
                self.wfile.write(json.dumps({"autorizado": senha_digitada == senha_mestra}).encode('utf-8'))
                return

            elif action == 'upload_logo':
                file_base64 = dados.get('file_base64', '')
                filename = dados.get('filename', 'logo.png')
                
                if not file_base64 or "," not in file_base64:
                    self.wfile.write(json.dumps({"erro": "String Base64 malformada ou ausente."}).encode('utf-8'))
                    return

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
                        self.wfile.write(json.dumps({"erro": "A pasta/bucket 'logos' não existe no Supabase Storage."}).encode('utf-8'))
                        return
                    raise e

                url_publica = f"{sb_url}/storage/v1/object/public/logos/{filename}"
                self.wfile.write(json.dumps({"sucesso": True, "url_logo": url_publica}).encode('utf-8'))
                return

            elif action == 'cadastrar_unidade':
                url = f"{sb_url}/rest/v1/unidades"
                payload = {
                    "nome_responsavel": dados.get('nome_responsavel'),
                    "nome_unidade": dados.get('nome_gabinete') or dados.get('nome_unidade'),
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
                    "nome_unidade": dados.get('nome_gabinete') or dados.get('nome_unidade'),
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

            else:
                self.wfile.write(json.dumps({"erro": f"Ação '{action}' não implementada."}).encode('utf-8'))

        except Exception as e:
            self._set_headers(500)
            self.wfile.write(json.dumps({"erro": f"Erro interno do servidor: {str(e)}"}).encode('utf-8'))
