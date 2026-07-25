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

        data = json.dumps(payload).encode('utf-8') if payload is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req) as response:
                res_body = response.read().decode('utf-8')
                return json.loads(res_body) if res_body else {}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8') if e.fp else ""
            raise Exception(f"HTTP {e.code}: {err_body or e.reason}")

    # ==========================================
    # ROTAS GET (Navegador e Consultas Diretas)
    # ==========================================
    def do_GET(self):
        try:
            self._set_headers(200)
            sb_url = self._obter_url_supabase()
            
            if 'unidades' in self.path or 'master' in self.path or 'gestores' in self.path:
                url = f"{sb_url}/rest/v1/unidades?select=id,nome_responsavel,nome_unidade,status,cor_layout,url_logo,whatsapp,email,documento,data_inicio,endereco,senha_admin&order=id.desc"
                try:
                    unidades = self._executar_requisicao(url, method='GET')
                except Exception:
                    # Fallback para schema antigo caso a tabela ainda se chame gestores
                    url_old = f"{sb_url}/rest/v1/gestores?select=id,nome_gestor,nome_campanha_gabinete,status,cor_layout,url_logo,whatsapp,email,documento,data_inicio,endereco,senha_admin&order=id.desc"
                    unidades = self._executar_requisicao(url_old, method='GET')
                
                self.wfile.write(json.dumps({"unidades": unidades, "gestores": unidades}).encode('utf-8'))
            else:
                self.wfile.write(json.dumps({"status": "API Online", "versao": "2.0.0"}).encode('utf-8'))
        except Exception as e:
            self._set_headers(500)
            self.wfile.write(json.dumps({"erro": f"Erro GET: {str(e)}"}).encode('utf-8'))

    # ==========================================
    # ROTAS POST (Ações do Sistema)
    # ==========================================
    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self._set_headers(400)
                self.wfile.write(json.dumps({"erro": "Payload ausente"}).encode('utf-8'))
                return

            post_data = self.rfile.read(content_length)

            # Proteção contra erros de encoding/binário
            try:
                payload_str = post_data.decode('utf-8')
                dados = json.loads(payload_str)
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._set_headers(400)
                self.wfile.write(json.dumps({
                    "erro": "O arquivo/dados enviados não estão no formato JSON UTF-8/Base64 correto."
                }).encode('utf-8'))
                return

            action = dados.get('action')
            sb_url = self._obter_url_supabase()
            sb_key = os.environ.get('SUPABASE_SERVICE_KEY', '')
            senha_mestra = os.environ.get('USER_SENHA', '')

            self._set_headers(200)

            # ------------------------------------------
            # 1. PAINEL MASTER (SUPER ADMIN)
            # ------------------------------------------
            if action == 'verificar_senha_master':
                senha_digitada = dados.get('senha')
                self.wfile.write(json.dumps({"autorizado": senha_digitada == senha_mestra}).encode('utf-8'))
                return

            elif action == 'upload_logo':
                file_base64 = dados.get('file_base64', '')
                filename = dados.get('filename', 'logo.png')
                
                if not file_base64 or "," not in file_base64:
                    self.wfile.write(json.dumps({"erro": "String Base64 de imagem inválida."}).encode('utf-8'))
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
                        self.wfile.write(json.dumps({"erro": "O bucket 'logos' não existe no Supabase Storage."}).encode('utf-8'))
                        return
                    raise e

                url_publica = f"{sb_url}/storage/v1/object/public/logos/{filename}"
                self.wfile.write(json.dumps({"sucesso": True, "url_logo": url_publica}).encode('utf-8'))
                return

            elif action in ['cadastrar_unidade', 'cadastrar_gestor']:
                url = f"{sb_url}/rest/v1/unidades"
                payload = {
                    "nome_responsavel": dados.get('nome_responsavel') or dados.get('nome_gestor'),
                    "nome_unidade": dados.get('nome_unidade') or dados.get('nome_gabinete'),
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
                try:
                    unidades = self._executar_requisicao(url, method='GET')
                except Exception:
                    url_old = f"{sb_url}/rest/v1/gestores?select=id,nome_gestor,nome_campanha_gabinete,status,cor_layout,url_logo,whatsapp,email,documento,data_inicio,endereco,senha_admin&order=id.desc"
                    unidades = self._executar_requisicao(url_old, method='GET')

                self.wfile.write(json.dumps({"unidades": unidades, "gestores": unidades}).encode('utf-8'))
                return

            elif action in ['editar_unidade', 'editar_gestor']:
                uid = dados.get('id')
                url = f"{sb_url}/rest/v1/unidades?id=eq.{uid}"
                body = {
                    "nome_responsavel": dados.get('nome_responsavel') or dados.get('nome_gestor'),
                    "nome_unidade": dados.get('nome_unidade') or dados.get('nome_gabinete'),
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

            elif action in ['alterar_status_unidade', 'alterar_status_gestor']:
                uid = dados.get('id')
                url = f"{sb_url}/rest/v1/unidades?id=eq.{uid}"
                self._executar_requisicao(url, method='PATCH', payload={"status": dados.get('status')})
                self.wfile.write(json.dumps({"sucesso": True}).encode('utf-8'))
                return

            elif action in ['excluir_unidade', 'excluir_gestor']:
                uid = dados.get('id')
                url = f"{sb_url}/rest/v1/unidades?id=eq.{uid}"
                self._executar_requisicao(url, method='DELETE')
                self.wfile.write(json.dumps({"sucesso": True}).encode('utf-8'))
                return

            # ------------------------------------------
            # 2. AUTENTICAÇÃO OPERACIONAL DA UNIDADE
            # ------------------------------------------
            elif action in ['verificar_login_unidade', 'verificar_login_gestor']:
                senha_input = dados.get('senha')
                url = f"{sb_url}/rest/v1/unidades?senha_admin=eq.{senha_input}&status=eq.Ativo&select=id,nome_unidade,cor_layout,url_logo"
                try:
                    res_data = self._executar_requisicao(url, method='GET')
                except Exception:
                    url_old = f"{sb_url}/rest/v1/gestores?senha_admin=eq.{senha_input}&status=eq.Ativo&select=id,nome_campanha_gabinete,cor_layout,url_logo"
                    res_data = self._executar_requisicao(url_old, method='GET')

                if res_data and len(res_data) > 0:
                    self.wfile.write(json.dumps({"autorizado": True, "unidade": res_data[0], "gestor": res_data[0]}).encode('utf-8'))
                else:
                    self.wfile.write(json.dumps({"autorizado": False, "mensagem": "Acesso suspenso ou credencial inválida."}).encode('utf-8'))
                return

            # ------------------------------------------
            # 3. EQUIPE / COLABORADORES (RH)
            # ------------------------------------------
            elif action == 'upload_foto':
                file_base64 = dados.get('file_base64', '')
                filename = dados.get('filename', 'foto.jpg')
                file_bytes = base64.b64decode(file_base64.split(",")[-1])
                url_storage = f"{sb_url}/storage/v1/object/documentos/{filename}"
                content_type = mimetypes.guess_type(filename)[0] or 'image/jpeg'

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
                        self.wfile.write(json.dumps({"erro": "Bucket 'documentos' não configurado no Supabase."}).encode('utf-8'))
                        return
                    raise e

                url_publica = f"{sb_url}/storage/v1/object/public/documentos/{filename}"
                self.wfile.write(json.dumps({"sucesso": True, "url_foto": url_publica}).encode('utf-8'))
                return

            elif action in ['listar_colaboradores', 'listar_funcionarios']:
                uid = dados.get('unidade_id') or dados.get('gestor_id')
                url = f"{sb_url}/rest/v1/colaboradores?unidade_id=eq.{uid}&order=id.desc"
                try:
                    colabs = self._executar_requisicao(url, method='GET')
                except Exception:
                    url_old = f"{sb_url}/rest/v1/funcionarios?gestor_id=eq.{uid}&order=id.desc"
                    colabs = self._executar_requisicao(url_old, method='GET')

                self.wfile.write(json.dumps({"colaboradores": colabs, "funcionarios": colabs}).encode('utf-8'))
                return

            elif action in ['cadastrar_colaborador', 'cadastrar_funcionario']:
                uid = self._safe_int(dados.get('unidade_id') or dados.get('gestor_id'))
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
                    "unidade_id": uid,
                    "gestor_id": uid,
                    "status": "Ativo"
                }
                url = f"{sb_url}/rest/v1/colaboradores"
                try:
                    self._executar_requisicao(url, method='POST', payload=payload, headers_extra={'Prefer': 'return=representation'})
                except Exception:
                    url_old = f"{sb_url}/rest/v1/funcionarios"
                    self._executar_requisicao(url_old, method='POST', payload=payload, headers_extra={'Prefer': 'return=representation'})

                self.wfile.write(json.dumps({"sucesso": True}).encode('utf-8'))
                return

            elif action in ['editar_colaborador', 'editar_funcionario']:
                fid = dados.get('id')
                payload = {
                    "nome": dados.get('nome'),
                    "cargo": dados.get('cargo'),
                    "whatsapp": dados.get('whatsapp'),
                    "email": dados.get('email'),
                    "documento": dados.get('documento'),
                    "data_nascimento": dados.get('data_nascimento'),
                    "endereco": dados.get('endereco'),
                    "conta_bancaria": dados.get('conta_bancaria')
                }
                if dados.get('url_foto'):
                    payload["url_foto"] = dados.get('url_foto')

                url = f"{sb_url}/rest/v1/colaboradores?id=eq.{fid}"
                try:
                    self._executar_requisicao(url, method='PATCH', payload=payload, headers_extra={'Prefer': 'return=representation'})
                except Exception:
                    url_old = f"{sb_url}/rest/v1/funcionarios?id=eq.{fid}"
                    self._executar_requisicao(url_old, method='PATCH', payload=payload, headers_extra={'Prefer': 'return=representation'})

                self.wfile.write(json.dumps({"sucesso": True}).encode('utf-8'))
                return

            elif action in ['alterar_status_colaborador', 'alterar_status_funcionario']:
                fid = dados.get('id')
                status_bruto = dados.get('status')
                novo_status = status_bruto.capitalize() if status_bruto else "Ativo"
                payload = {"status": novo_status}

                url = f"{sb_url}/rest/v1/colaboradores?id=eq.{fid}"
                try:
                    self._executar_requisicao(url, method='PATCH', payload=payload, headers_extra={'Prefer': 'return=representation'})
                except Exception:
                    url_old = f"{sb_url}/rest/v1/funcionarios?id=eq.{fid}"
                    self._executar_requisicao(url_old, method='PATCH', payload=payload, headers_extra={'Prefer': 'return=representation'})

                self.wfile.write(json.dumps({"sucesso": True}).encode('utf-8'))
                return

            elif action in ['excluir_colaborador', 'excluir_funcionario']:
                fid = dados.get('id')
                url = f"{sb_url}/rest/v1/colaboradores?id=eq.{fid}"
                try:
                    self._executar_requisicao(url, method='DELETE')
                except Exception:
                    url_old = f"{sb_url}/rest/v1/funcionarios?id=eq.{fid}"
                    self._executar_requisicao(url_old, method='DELETE')

                self.wfile.write(json.dumps({"sucesso": True}).encode('utf-8'))
                return

            # ------------------------------------------
            # 4. CLIENTES / LEADS / BASE
            # ------------------------------------------
            elif action in ['salvar_cliente', 'salvar_apoiador']:
                uid = self._safe_int(dados.get('unidade_id') or dados.get('gestor_id'))
                payload = {
                    "nome": dados.get('nome'),
                    "whatsapp": dados.get('whatsapp'),
                    "bairro": dados.get('bairro'),
                    "documento_cliente": dados.get('documento_cliente') or dados.get('titulo'),
                    "historico_demanda": dados.get('demanda'),
                    "titulo": dados.get('titulo'),
                    "demanda": dados.get('demanda'),
                    "unidade_id": uid,
                    "gestor_id": uid,
                    "status": "Ativo"
                }
                url = f"{sb_url}/rest/v1/clientes"
                try:
                    self._executar_requisicao(url, method='POST', payload=payload, headers_extra={'Prefer': 'return=representation'})
                except Exception:
                    url_old = f"{sb_url}/rest/v1/eleitores"
                    self._executar_requisicao(url_old, method='POST', payload=payload, headers_extra={'Prefer': 'return=representation'})

                self.wfile.write(json.dumps({"sucesso": True}).encode('utf-8'))
                return

            elif action in ['listar_clientes_unidade', 'listar_eleitores_gestor']:
                uid = dados.get('unidade_id') or dados.get('gestor_id')
                url = f"{sb_url}/rest/v1/clientes?unidade_id=eq.{uid}&order=id.desc"
                try:
                    clientes = self._executar_requisicao(url, method='GET')
                except Exception:
                    url_old = f"{sb_url}/rest/v1/eleitores?gestor_id=eq.{uid}&order=id.desc"
                    clientes = self._executar_requisicao(url_old, method='GET')

                self.wfile.write(json.dumps({"clientes": clientes, "eleitores": clientes}).encode('utf-8'))
                return

            elif action in ['alterar_status_cliente', 'alterar_status_eleitor']:
                cid = dados.get('id')
                payload = {"status": dados.get('status')}
                url = f"{sb_url}/rest/v1/clientes?id=eq.{cid}"
                try:
                    self._executar_requisicao(url, method='PATCH', payload=payload, headers_extra={'Prefer': 'return=representation'})
                except Exception:
                    url_old = f"{sb_url}/rest/v1/eleitores?id=eq.{cid}"
                    self._executar_requisicao(url_old, method='PATCH', payload=payload, headers_extra={'Prefer': 'return=representation'})

                self.wfile.write(json.dumps({"sucesso": True}).encode('utf-8'))
                return

            elif action in ['excluir_cliente', 'excluir_eleitor']:
                cid = dados.get('id')
                url = f"{sb_url}/rest/v1/clientes?id=eq.{cid}"
                try:
                    self._executar_requisicao(url, method='DELETE')
                except Exception:
                    url_old = f"{sb_url}/rest/v1/eleitores?id=eq.{cid}"
                    self._executar_requisicao(url_old, method='DELETE')

                self.wfile.write(json.dumps({"sucesso": True}).encode('utf-8'))
                return

            # ------------------------------------------
            # 5. AGENDA / COMPROMISSOS
            # ------------------------------------------
            elif action in ['listar_agenda_unidade', 'listar_agenda_gestor']:
                uid = dados.get('unidade_id') or dados.get('gestor_id')
                url = f"{sb_url}/rest/v1/agenda?unidade_id=eq.{uid}&order=data_evento.asc,hora_evento.asc"
                try:
                    agenda = self._executar_requisicao(url, method='GET')
                except Exception:
                    url_old = f"{sb_url}/rest/v1/agenda?gestor_id=eq.{uid}&order=data_evento.asc,hora_evento.asc"
                    try:
                        agenda = self._executar_requisicao(url_old, method='GET')
                    except Exception:
                        agenda = []

                self.wfile.write(json.dumps({"agenda": agenda}).encode('utf-8'))
                return

            elif action == 'cadastrar_agenda':
                uid = self._safe_int(dados.get('unidade_id') or dados.get('gestor_id'))
                payload = {
                    "titulo": dados.get('titulo'),
                    "tipo": 'Compromisso',
                    "data_evento": dados.get('data'),
                    "hora_evento": dados.get('hora'),
                    "unidade_id": uid,
                    "gestor_id": uid,
                    "status": 'Confirmado'
                }
                url = f"{sb_url}/rest/v1/agenda"
                self._executar_requisicao(url, method='POST', payload=payload, headers_extra={'Prefer': 'return=representation'})
                self.wfile.write(json.dumps({"sucesso": True}).encode('utf-8'))
                return

            elif action == 'alterar_status_agenda':
                aid = dados.get('id')
                update_data = {"status": dados.get('status')}

                if dados.get('data'): update_data["data_evento"] = dados.get('data')
                if dados.get('hora'): update_data["hora_evento"] = dados.get('hora')
                if 'justificativa' in dados: update_data["justificativa"] = dados.get('justificativa')

                url = f"{sb_url}/rest/v1/agenda?id=eq.{aid}"
                self._executar_requisicao(url, method='PATCH', payload=update_data, headers_extra={'Prefer': 'return=representation'})
                self.wfile.write(json.dumps({"sucesso": True}).encode('utf-8'))
                return

            elif action == 'excluir_agenda':
                aid = dados.get('id')
                url = f"{sb_url}/rest/v1/agenda?id=eq.{aid}"
                self._executar_requisicao(url, method='DELETE')
                self.wfile.write(json.dumps({"sucesso": True}).encode('utf-8'))
                return

            # ------------------------------------------
            # 6. DOCUMENTOS & ARQUIVOS
            # ------------------------------------------
            elif action == 'upload_documento':
                file_base64 = dados.get('file_base64', '')
                filename = dados.get('filename', 'documento.pdf')
                file_bytes = base64.b64decode(file_base64.split(",")[-1])
                url_storage = f"{sb_url}/storage/v1/object/documentos/{filename}"
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
                        self.wfile.write(json.dumps({"erro": "O bucket 'documentos' não existe no Supabase Storage."}).encode('utf-8'))
                        return
                    raise e

                url_publica = f"{sb_url}/storage/v1/object/public/documentos/{filename}"
                self.wfile.write(json.dumps({"sucesso": True, "url_arquivo": url_publica}).encode('utf-8'))
                return

            elif action in ['listar_documentos_unidade', 'listar_documentos_gestor']:
                uid = dados.get('unidade_id') or dados.get('gestor_id')
                url = f"{sb_url}/rest/v1/documentos?unidade_id=eq.{uid}&order=id.desc"
                try:
                    docs = self._executar_requisicao(url, method='GET')
                except Exception:
                    url_old = f"{sb_url}/rest/v1/documentos?gestor_id=eq.{uid}&order=id.desc"
                    try:
                        docs = self._executar_requisicao(url_old, method='GET')
                    except Exception:
                        docs = []

                self.wfile.write(json.dumps({"documentos": docs}).encode('utf-8'))
                return

            elif action == 'cadastrar_documento':
                uid = self._safe_int(dados.get('unidade_id') or dados.get('gestor_id'))
                payload = {
                    "titulo": dados.get('titulo'),
                    "categoria": dados.get('categoria'),
                    "url_arquivo": dados.get('url_arquivo'),
                    "unidade_id": uid,
                    "gestor_id": uid
                }
                url = f"{sb_url}/rest/v1/documentos"
                self._executar_requisicao(url, method='POST', payload=payload, headers_extra={'Prefer': 'return=representation'})
                self.wfile.write(json.dumps({"sucesso": True}).encode('utf-8'))
                return

            elif action == 'excluir_documento':
                did = dados.get('id')
                url = f"{sb_url}/rest/v1/documentos?id=eq.{did}"
                self._executar_requisicao(url, method='DELETE')
                self.wfile.write(json.dumps({"sucesso": True}).encode('utf-8'))
                return

            else:
                self.wfile.write(json.dumps({"erro": f"Ação '{action}' desconhecida."}).encode('utf-8'))

        except Exception as e:
            self._set_headers(500)
            self.wfile.write(json.dumps({"erro": f"Erro interno do servidor: {str(e)}"}).encode('utf-8'))
