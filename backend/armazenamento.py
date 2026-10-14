"""
armazenamento.py — guarda os anexos do chat no Supabase Storage (bucket PRIVADO).

Por que: os arquivos ficavam em backend/uploads, ou seja, só no computador que rodou o
servidor. Com o banco no Supabase, cada colega rodando em outro PC não via os anexos.
No Storage, todo mundo acessa os mesmos arquivos.

Segurança: o bucket é privado (sem link público). O navegador nunca fala com o Storage:
o backend confere quem está pedindo e só então busca o arquivo com a chave secreta,
que fica no backend/.env. Usa só a biblioteca padrão do Python (urllib).
"""
import json
import urllib.error
import urllib.parse
import urllib.request


class ErroArmazenamento(Exception):
    """Falha ao falar com o Supabase Storage (mensagem em português)."""


def ativo(cfg):
    return bool(cfg.SUPABASE_URL and cfg.SUPABASE_CHAVE_SECRETA)


def _cabecalhos(cfg, extras=None):
    chave = cfg.SUPABASE_CHAVE_SECRETA
    cabecalhos = {'apikey': chave}
    if not chave.startswith('sb_'):  # chave antiga "service_role" (JWT) vai também no Authorization
        cabecalhos['Authorization'] = f'Bearer {chave}'
    cabecalhos.update(extras or {})
    return cabecalhos


def _pedir(cfg, metodo, caminho, dados=None, extras=None, tempo=30):
    url = f'{cfg.SUPABASE_URL}/storage/v1/{caminho}'
    pedido = urllib.request.Request(url, data=dados, method=metodo, headers=_cabecalhos(cfg, extras))
    try:
        with urllib.request.urlopen(pedido, timeout=tempo) as resposta:
            return resposta.status, resposta.read()
    except urllib.error.HTTPError as erro:
        return erro.code, erro.read()
    except (urllib.error.URLError, OSError) as erro:
        raise ErroArmazenamento(f'Não consegui falar com o Supabase Storage ({getattr(erro, "reason", erro)}).') from None


def _caminho_objeto(cfg, caminho):
    return f'object/{urllib.parse.quote(cfg.SUPABASE_BUCKET)}/{urllib.parse.quote(caminho)}'


def _explicar(status, corpo):
    try:
        detalhe = json.loads(corpo or b'{}')
        detalhe = detalhe.get('message') or detalhe.get('error') or ''
    except ValueError:
        detalhe = ''
    if status in (401, 403):
        return 'o Supabase recusou a chave (use a "secret"/service_role em SUPABASE_CHAVE_SECRETA)'
    return f'erro {status}{": " + detalhe if detalhe else ""}'


def preparar(cfg):
    """Cria o bucket privado se ainda não existir. Devolve (ok, mensagem)."""
    corpo = json.dumps({'id': cfg.SUPABASE_BUCKET, 'name': cfg.SUPABASE_BUCKET, 'public': False,
                        'file_size_limit': (cfg.UPLOAD_MAX_MB + 1) * 1024 * 1024}).encode()
    try:
        status, resposta = _pedir(cfg, 'POST', 'bucket', corpo, {'Content-Type': 'application/json'}, tempo=15)
    except ErroArmazenamento as erro:
        return False, str(erro)
    texto = (resposta or b'').decode(errors='ignore').lower()
    if status in (200, 201) or 'already exists' in texto or 'duplicate' in texto or status == 409:
        return True, f'Supabase Storage pronto (bucket privado "{cfg.SUPABASE_BUCKET}").'
    return False, f'Supabase Storage: {_explicar(status, resposta)}.'


def enviar(cfg, caminho, dados, tipo_mime):
    status, resposta = _pedir(cfg, 'POST', _caminho_objeto(cfg, caminho), dados,
                              {'Content-Type': tipo_mime, 'x-upsert': 'false', 'cache-control': 'no-store'})
    if status not in (200, 201):
        raise ErroArmazenamento(f'Não consegui salvar o arquivo no Supabase Storage ({_explicar(status, resposta)}).')


def baixar(cfg, caminho):
    status, resposta = _pedir(cfg, 'GET', _caminho_objeto(cfg, caminho))
    if status == 404 or (status == 400 and b'not found' in (resposta or b'').lower()):
        return None
    if status != 200:
        raise ErroArmazenamento(f'Não consegui buscar o arquivo no Supabase Storage ({_explicar(status, resposta)}).')
    return resposta


def apagar(cfg, caminho):
    corpo = json.dumps({'prefixes': [caminho]}).encode()
    try:
        _pedir(cfg, 'DELETE', f'object/{urllib.parse.quote(cfg.SUPABASE_BUCKET)}', corpo,
               {'Content-Type': 'application/json'}, tempo=15)
    except ErroArmazenamento:
        pass  # limpeza: se falhar, só sobra um arquivo sem uso
