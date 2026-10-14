# ============================================================================
# CLASSMATCH — Backend em Python (Flask)
# ============================================================================
# Este arquivo é A PONTE entre o front-end (HTML/CSS/JS) e o banco MySQL
# (classmatch_db). O navegador nunca acessa o MySQL diretamente: ele chama
# estas rotas HTTP (ex.: GET /api/materias) e é este código Python que
# executa o SQL e devolve a resposta em JSON.
#
# Como rodar (Windows): duplo clique em backend/iniciar.bat
# Como rodar (terminal): cd backend  ->  python app.py
# O site abre em http://127.0.0.1:5000 (o próprio Flask entrega o frontend).
#
# Arquivos do backend:
#   app.py     -> rotas da API (este arquivo)
#   banco.py   -> conexão com o banco (MySQL ou Supabase/PostgreSQL) e erros em português
#   filtro.py  -> filtro automático do chat (telefone, @perfil, palavrão...)
#   config.py  -> lê o backend/.env
# ============================================================================
import sys

if sys.version_info < (3, 8):
    print('ERRO: o ClassMatch precisa do Python 3.8 ou mais novo.')
    print('Instale a versão atual em https://www.python.org/downloads/')
    sys.exit(1)

try:
    sys.stdout.reconfigure(errors='replace')
    sys.stderr.reconfigure(errors='replace')
except AttributeError:
    pass

# As bibliotecas (Flask, PyMySQL...) ficam em backend/bibliotecas, instaladas pelo
# instalar.bat. Não usamos venv: em computador de escola o Windows costuma bloquear
# o python.exe copiado para dentro do venv (WinError 1260, "política de grupo").
import os

PASTA_BIBLIOTECAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bibliotecas')
if os.path.isdir(PASTA_BIBLIOTECAS):
    sys.path.insert(0, PASTA_BIBLIOTECAS)

try:
    from flask import Flask, g, jsonify, request
    from flask.json.provider import DefaultJSONProvider
    from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
    from werkzeug.exceptions import HTTPException
    from werkzeug.security import check_password_hash, generate_password_hash
except ImportError as erro_import:
    print()
    print(f'ERRO: falta a biblioteca "{erro_import.name}".')
    print('  -> Windows: dê dois cliques em backend\\instalar.bat')
    print('  -> Terminal: cd backend  e depois')
    print('     python -m pip install -r requirements.txt --target bibliotecas')
    print()
    sys.exit(1)

import json
import logging
import mimetypes
import html
import re
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage
import socket
import threading
import time
import traceback
import urllib.request
import webbrowser
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import wraps

import config
import filtro
import armazenamento
from banco import (COLUNA_FALTANDO, ERROS_BANCO, TABELA_FALTANDO, Banco, ErroApi, ErroBanco,
                   arquivo_do_script, atualizar_banco, codigo_erro, conectar, criar_banco, traduzir_erro)

cfg = config.carregar()

NIVEIS = ('basico', 'intermediario', 'avancado')
TIPOS_COORDENACAO = ('coordenador', 'admin')
# 'aluno' e 'monitor' são a mesma conta de estudante: todo mundo pode pedir ajuda E ensinar.
# O papel vale por monitoria (quem pediu é o aluno dela, quem aceitou é o monitor).
ESTUDANTES = ('aluno', 'monitor')
VERSAO = '6.4'  # aparece no rodapé do site e na janela do servidor
VALIDADE_TOKEN = 7 * 24 * 3600  # 7 dias logado
MAX_PEDIDOS_PENDENTES = 3


# ----------------------------------------------------------------------------
# APP FLASK
# O Flask também entrega a pasta frontend/, então o site e a API ficam no
# mesmo endereço (http://127.0.0.1:5000) e o navegador não bloqueia nada.
# ----------------------------------------------------------------------------
class ProvedorJSON(DefaultJSONProvider):
    """Datas no formato ISO (o JavaScript entende no fuso local) e números do MySQL."""

    sort_keys = False
    ensure_ascii = False  # acentos legíveis no JSON

    @staticmethod
    def default(o):
        if isinstance(o, datetime):
            return o.isoformat(timespec='seconds')
        if isinstance(o, date):
            return o.isoformat()
        if isinstance(o, timedelta):  # colunas TIME chegam como timedelta
            total = int(o.total_seconds())
            return f'{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}'
        if isinstance(o, Decimal):
            return int(o) if o == o.to_integral_value() else float(o)
        if isinstance(o, (bytes, bytearray)):
            return o.decode('utf-8', 'replace')
        return DefaultJSONProvider.default(o)


# No Windows, o registro às vezes diz que .js é "text/plain" e o navegador
# ignora o arquivo (tela em branco). Aqui fixamos os tipos certos.
for _tipo, _extensao in (('text/javascript', '.js'), ('text/css', '.css'), ('text/html', '.html'),
                         ('image/svg+xml', '.svg'), ('application/json', '.json'), ('image/x-icon', '.ico')):
    mimetypes.add_type(_tipo, _extensao)

app = Flask(__name__, static_folder=config.PASTA_FRONTEND, static_url_path='')
app.json = ProvedorJSON(app)
# Limite por requisição: o chat é só texto, então 1 MB sobra.
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024

assinador = URLSafeTimedSerializer(cfg.SECRET_KEY, salt='classmatch-login')
assinador_senha = URLSafeTimedSerializer(cfg.SECRET_KEY, salt='classmatch-redefinir-senha')  # link do e-mail


@app.after_request
def cabecalhos(resposta):
    # CORS: permite abrir o frontend pelo Live Server (porta 5500) ou por duplo clique.
    resposta.headers['Access-Control-Allow-Origin'] = '*'
    resposta.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    resposta.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    resposta.headers['Access-Control-Allow-Private-Network'] = 'true'
    resposta.headers['Access-Control-Max-Age'] = '600'
    # "no-cache" nos arquivos do site: depois de editar um .js o navegador pega a versão nova.
    resposta.headers['Cache-Control'] = 'no-store' if request.path.startswith('/api/') else 'no-cache'
    return resposta


@app.route('/')
def pagina_inicial():
    return app.send_static_file('index.html')


# ----------------------------------------------------------------------------
# CONEXÃO COM O BANCO: uma por requisição, fechada automaticamente no final.
# O que não recebeu db().commit() é desfeito (rollback) se a rota der erro.
# ----------------------------------------------------------------------------
def db():
    if 'banco' not in g:
        g.banco = Banco(cfg)
    return g.banco


@app.teardown_request
def fechar_banco(_erro=None):
    banco_aberto = g.pop('banco', None)
    if banco_aberto is not None:
        banco_aberto.rollback()
        banco_aberto.fechar()


# ----------------------------------------------------------------------------
# ERROS: a API SEMPRE responde JSON {"erro": "mensagem"}, nunca página HTML.
# ----------------------------------------------------------------------------
@app.errorhandler(ErroApi)
def responder_erro_api(erro):
    return jsonify({'erro': erro.mensagem}), erro.status


@app.errorhandler(HTTPException)
def responder_erro_http(erro):
    if not request.path.startswith('/api/'):
        return erro
    mensagens = {
        400: 'Requisição inválida.',
        404: 'Essa rota não existe na API.',
        405: 'Método não permitido nesta rota.',
        413: 'Conteúdo grande demais.',
    }
    return jsonify({'erro': mensagens.get(erro.code, erro.description)}), erro.code


@app.errorhandler(413)
def arquivo_grande_demais(_erro):
    return jsonify({'erro': 'Conteúdo grande demais.'}), 413


@app.errorhandler(Exception)
def responder_erro_inesperado(erro):
    if isinstance(erro, ERROS_BANCO):
        mensagem = traduzir_erro(erro, cfg)
        if mensagem:
            print(f'[banco] {mensagem}')
            return jsonify({'erro': mensagem}), 503
    print(f'\n[ERRO] {request.method} {request.path}')
    traceback.print_exc()
    return jsonify({'erro': 'Erro interno no servidor. O detalhe apareceu na janela do servidor.'}), 500


# ----------------------------------------------------------------------------
# FUNÇÕES DE APOIO (validação dos dados que chegam do navegador)
# ----------------------------------------------------------------------------
def corpo():
    """JSON enviado pelo navegador (sempre um dicionário)."""
    dados = request.get_json(silent=True)
    if dados is None:
        if request.get_data(cache=True):
            raise ErroApi(400, 'O corpo da requisição não é um JSON válido.')
        return {}
    if not isinstance(dados, dict):
        raise ErroApi(400, 'Envie os dados como um objeto JSON.')
    return dados


def texto(dados, campo, rotulo, minimo=1, maximo=255):
    valor = dados.get(campo)
    valor = '' if valor is None else str(valor).strip()
    if not valor and minimo > 0:
        raise ErroApi(400, f'Preencha o campo "{rotulo}".')
    if len(valor) < minimo:
        raise ErroApi(400, f'"{rotulo}" precisa ter pelo menos {minimo} caracteres.')
    if len(valor) > maximo:
        raise ErroApi(400, f'"{rotulo}" pode ter no máximo {maximo} caracteres.')
    return valor


def inteiro(valor, rotulo):
    if isinstance(valor, bool):
        raise ErroApi(400, f'{rotulo}: valor inválido.')
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError):
        raise ErroApi(400, f'{rotulo}: valor inválido.') from None
    if numero < 1:
        raise ErroApi(400, f'{rotulo}: valor inválido.')
    return numero


def ler_nivel(valor):
    nivel = filtro.normalizar(str(valor or '').strip())
    if nivel not in NIVEIS:
        raise ErroApi(400, 'Escolha um nível: básico, intermediário ou avançado.')
    return nivel


def ler_data(valor):
    valor = str(valor or '').strip()
    for formato in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(valor, formato).date()
        except ValueError:
            pass
    raise ErroApi(400, 'Preencha a data de nascimento.')


def calcular_idade(nascimento, hoje=None):
    hoje = hoje or date.today()
    return hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))


def calcular_faixa_etaria(nascimento):
    idade = calcular_idade(nascimento)
    if idade < 15:
        return 'fundamental'
    if idade < 18:
        return 'medio'
    return 'superior'


def calcular_score(nivel_monitor, nivel_pedido):
    """Compatibilidade do match (0-100): nível do monitor x nível da dúvida."""
    try:
        diferenca = NIVEIS.index(nivel_monitor) - NIVEIS.index(nivel_pedido)
    except ValueError:
        return 70
    if diferenca == 0:
        return 100
    if diferenca > 0:
        return 85  # monitor sabe mais do que a dúvida exige
    return 60 if diferenca == -1 else 40


def gerar_hash_senha(senha):
    try:
        return generate_password_hash(senha)  # scrypt (padrão do Werkzeug)
    except (AttributeError, ValueError):
        return generate_password_hash(senha, method='pbkdf2:sha256:600000')


def conferir_senha(hash_salvo, senha):
    try:
        return bool(hash_salvo) and check_password_hash(hash_salvo, senha)
    except (ValueError, TypeError, AttributeError):
        return False  # hash em formato desconhecido (ex.: senha colocada "na mão" no banco)


HASH_FICTICIO = gerar_hash_senha('senha-que-nao-pertence-a-ninguem')

_cache_palavras = {'quando': 0.0, 'linhas': []}


def palavras_extras():
    """Linhas ativas da tabela palavras_filtradas (recarrega a cada 60 s)."""
    agora = time.monotonic()
    if not _cache_palavras['quando'] or agora - _cache_palavras['quando'] > 60:
        try:
            linhas = db().todos('SELECT padrao, tipo FROM palavras_filtradas WHERE ativo = TRUE')
        except ErroApi:
            linhas = []
        _cache_palavras.update(quando=agora, linhas=linhas)
    return _cache_palavras['linhas']


def filtrar(texto_original):
    """Filtro do chat, liberando e-mails do domínio da própria escola."""
    return filtro.filtrar_mensagem(texto_original, g.usuario['dominio_email'], palavras_extras())


def descrever_filtro(motivos, onde='mensagem'):
    if not motivos:
        return None
    return f'Parte da {onde} foi filtrada ({", ".join(motivos)}). O contato fica dentro do ClassMatch.'


# ----------------------------------------------------------------------------
# LOGIN POR TOKEN
# O login devolve um token assinado com a chave secreta do servidor. O navegador
# manda esse token em toda chamada (cabeçalho Authorization). Assim ninguém
# consegue "fingir" ser outro usuário trocando um id na URL, como era antes.
# ----------------------------------------------------------------------------
SQL_USUARIO = """
    SELECT u.id, u.instituicao_id, i.nome AS instituicao_nome, i.dominio_email,
           i.ativo AS instituicao_ativa, u.nome_completo, u.email_institucional,
           u.tipo_usuario, u.faixa_etaria, u.reputacao_media,
           u.status_conta, u.email_verificado, u.senha_hash, u.trocar_senha,
           (SELECT COUNT(*) FROM avaliacoes a WHERE a.avaliado_id = u.id) AS total_avaliacoes
    FROM usuarios u
    JOIN instituicoes i ON i.id = u.instituicao_id
"""


def buscar_usuario(usuario_id):
    return db().um(SQL_USUARIO + ' WHERE u.id = %s', (usuario_id,))


def publico(usuario):
    """Dados do usuário que podem ir para o navegador (nunca o hash da senha)."""
    dados = {chave: valor for chave, valor in usuario.items() if chave != 'senha_hash'}
    dados['instituicao_ativa'] = bool(dados.get('instituicao_ativa'))
    dados['email_verificado'] = bool(dados.get('email_verificado'))
    dados['trocar_senha'] = bool(dados.get('trocar_senha'))
    return dados


def criar_token(usuario_id):
    return assinador.dumps({'id': usuario_id})


def login_obrigatorio(*tipos):
    """Decorador: exige token válido e, se informado, um dos tipos de usuário."""

    def decorador(funcao):
        @wraps(funcao)
        def rota_protegida(*args, **kwargs):
            cabecalho = request.headers.get('Authorization', '')
            token = cabecalho[7:].strip() if cabecalho.lower().startswith('bearer ') else ''
            if not token:
                raise ErroApi(401, 'Faça login para continuar.')
            try:
                dados_token = assinador.loads(token, max_age=VALIDADE_TOKEN)
            except SignatureExpired:
                raise ErroApi(401, 'Sua sessão expirou. Entre de novo.') from None
            except BadSignature:
                raise ErroApi(401, 'Sessão inválida. Entre de novo.') from None

            usuario_id = dados_token.get('id') if isinstance(dados_token, dict) else None
            usuario = buscar_usuario(usuario_id) if isinstance(usuario_id, int) else None
            if not usuario:
                raise ErroApi(401, 'Conta não encontrada. Entre de novo.')
            if usuario['status_conta'] == 'banido':
                raise ErroApi(401, 'Sua conta foi suspensa pela coordenação da escola.')
            if not usuario['instituicao_ativa']:
                raise ErroApi(401, 'O acesso da sua escola ao ClassMatch está desativado.')
            if tipos and usuario['tipo_usuario'] not in tipos:
                raise ErroApi(403, 'Seu tipo de conta não tem acesso a esta função.')
            # Senha temporária (dada pela coordenação): só pode ver os próprios dados e trocar a senha.
            if usuario['trocar_senha'] and request.endpoint not in ('eu', 'trocar_senha'):
                raise ErroApi(403, 'Crie uma senha nova para continuar.')
            g.usuario = usuario
            return funcao(*args, **kwargs)

        return rota_protegida

    return decorador


def registrar_acesso(usuario_id, tentativa, sucesso):
    """Auditoria LGPD (tabela log_acesso). Se falhar, não impede o login."""
    try:
        db().inserir(
            """INSERT INTO log_acesso (usuario_id, email_tentativa, sucesso, ip_origem, user_agent)
               VALUES (%s, %s, %s, %s, %s)""",
            (usuario_id, tentativa[:150], bool(sucesso), (request.remote_addr or '')[:45],
             (request.headers.get('User-Agent') or '')[:255]),
        )
    except ErroApi:
        pass


def escolas_ativas():
    return db().todos('SELECT id, nome, cidade, estado, dominio_email FROM instituicoes '
                      'WHERE ativo = TRUE ORDER BY nome')


def dominio_bate(dominio, escola):
    """E-mail do domínio da escola (ou subdomínio, ex.: aluno@al.escola.sp.gov.br)."""
    oficial = (escola['dominio_email'] or '').lower()
    return bool(oficial) and (dominio == oficial or dominio.endswith('.' + oficial))


def escolher_instituicao(dominio, escolhida):
    """Escola do novo usuário. Aceita QUALQUER e-mail:
    - se a pessoa escolheu a escola no formulário, usa essa;
    - senão, se o domínio do e-mail é de uma escola, usa essa;
    - senão, se só existe uma escola no sistema, usa ela.
    Devolve (escola, email_verificado). E-mail do domínio da escola = conta verificada."""
    escolas = escolas_ativas()
    if not escolas:
        raise ErroApi(400, 'Nenhuma escola cadastrada no sistema ainda. Rode o database/banco.sql.')

    if escolhida not in (None, ''):
        escola_id = inteiro(escolhida, 'Escola')
        escola = next((e for e in escolas if e['id'] == escola_id), None)
        if not escola:
            raise ErroApi(400, 'Escolha a sua escola na lista.')
        return escola, dominio_bate(dominio, escola)

    pelo_dominio = [e for e in escolas if dominio_bate(dominio, e)]
    if pelo_dominio:
        return max(pelo_dominio, key=lambda e: len(e['dominio_email'])), True
    if len(escolas) == 1:
        return escolas[0], False
    raise ErroApi(400, 'Escolha a sua escola na lista.')


# ============================================================================
# ROTAS — SAÚDE (o frontend usa para saber se o servidor e o banco estão ok)
# ============================================================================
@app.get('/api/saude')
def saude():
    try:
        db().um('SELECT 1 AS ok')
        banco_ok, mensagem = True, None
    except ErroApi as erro:
        banco_ok, mensagem = False, erro.mensagem
    return jsonify({'app': 'classmatch', 'versao': VERSAO, 'servidor': 'ok',
                    'banco': 'ok' if banco_ok else 'erro', 'mensagem': mensagem})


# ============================================================================
# ROTAS — AUTENTICAÇÃO
# ============================================================================
@app.get('/api/escolas')
def listar_escolas():
    """Escolas ativas (o cadastro só mostra o campo "Escola" se houver mais de uma)."""
    return jsonify([{'id': e['id'], 'nome': e['nome'], 'cidade': e['cidade'], 'estado': e['estado']}
                    for e in escolas_ativas()])


def ler_cadastro(dados):
    """Confere o formulário de cadastro. Usado ao pedir o código e ao criar a conta."""
    nome = ' '.join(texto(dados, 'nome_completo', 'Nome completo', 3, 150).split())
    email = texto(dados, 'email_institucional', 'E-mail', 5, 150).lower()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
        raise ErroApi(400, 'Digite um e-mail válido, como nome@gmail.com.')
    nascimento = ler_data(dados.get('data_nascimento'))
    if nascimento > date.today() or not 6 <= calcular_idade(nascimento) <= 100:
        raise ErroApi(400, 'Confira a data de nascimento.')
    senha = str(dados.get('senha') or '')
    if len(senha) < 6:
        raise ErroApi(400, 'A senha precisa ter pelo menos 6 caracteres.')
    if len(senha) > 128:
        raise ErroApi(400, 'A senha pode ter no máximo 128 caracteres.')

    dominio = email.rsplit('@', 1)[1]
    instituicao, dominio_da_escola = escolher_instituicao(dominio, dados.get('instituicao_id'))
    if db().um('SELECT id FROM usuarios WHERE LOWER(email_institucional) = LOWER(%s)', (email,)):
        raise ErroApi(409, 'Já existe uma conta com esse e-mail. Use a aba "Entrar".')
    return nome, email, nascimento, senha, instituicao, dominio_da_escola


@app.post('/api/cadastro/codigo')
def cadastro_codigo():
    """1º passo do cadastro: confere os dados e manda um código de 6 números para o e-mail.
    Sem e-mail configurado no .env, devolve modo "direto" e o cadastro segue sem código."""
    nome, email, *_ = ler_cadastro(corpo())
    if not email_configurado():
        print(f'  [cadastro] {email}: e-mail não configurado no .env, conta criada SEM confirmação de e-mail.')
        return jsonify({'modo': 'direto'})
    enviar_codigo_email(email, 'cadastro', nome)
    return jsonify({'modo': 'email', 'email': mascarar_email(email),
                    'mensagem': f'Enviamos um código de 6 números para {mascarar_email(email)}. '
                                'Ele vale por 15 minutos (olhe também a caixa de spam).'})


@app.post('/api/cadastro')
def cadastro():
    """2º passo: com o código do e-mail (quando o envio de e-mail está configurado)."""
    dados = corpo()
    nome, email, nascimento, senha, instituicao, verificado = ler_cadastro(dados)
    tipo = 'aluno'  # conta de estudante: no painel a pessoa escolhe se quer aprender ou ensinar
    # Com e-mail configurado, só cria a conta com o código que chegou no e-mail (e-mail confirmado).
    # Sem e-mail configurado, vale a regra antiga: e-mail do domínio da escola = verificado.
    if email_configurado():
        conferir_codigo_email(email, 'cadastro', dados.get('codigo'))
        verificado = True

    novo_id = db().inserir(
        """INSERT INTO usuarios
           (instituicao_id, nome_completo, email_institucional, senha_hash,
            tipo_usuario, data_nascimento, faixa_etaria, email_verificado)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (instituicao['id'], nome, email, gerar_hash_senha(senha), tipo,
         nascimento, calcular_faixa_etaria(nascimento), verificado),
    )
    registrar_acesso(novo_id, email, True)
    db().commit()

    usuario = buscar_usuario(novo_id)
    return jsonify({'id': novo_id, 'mensagem': 'Cadastro realizado com sucesso.',
                    'token': criar_token(novo_id), 'usuario': publico(usuario)}), 201


@app.post('/api/login')
def login():
    dados = corpo()
    identificacao = str(dados.get('email_institucional') or dados.get('login') or '').strip().lower()
    senha = str(dados.get('senha') or '')
    if not identificacao or not senha:
        raise ErroApi(400, 'Informe o e-mail e a senha.')
    if '@' not in identificacao:
        raise ErroApi(400, 'Entre com o seu e-mail.')
    usuario = db().um(SQL_USUARIO + ' WHERE LOWER(u.email_institucional) = LOWER(%s)', (identificacao,))


    # Confere a senha mesmo quando o usuário não existe (tempo de resposta igual).
    senha_ok = conferir_senha(usuario['senha_hash'] if usuario else HASH_FICTICIO, senha)
    senha_ok = senha_ok and usuario is not None
    registrar_acesso(usuario['id'] if usuario else None, identificacao, senha_ok)
    db().commit()

    if not senha_ok:
        raise ErroApi(401, 'E-mail ou senha incorretos.')
    if usuario['status_conta'] == 'banido':
        raise ErroApi(403, 'Esta conta foi suspensa pela coordenação da escola.')
    if not usuario['instituicao_ativa']:
        raise ErroApi(403, 'O acesso da sua escola ao ClassMatch está desativado.')

    db().executar('UPDATE usuarios SET ultimo_login = NOW() WHERE id = %s', (usuario['id'],))
    db().commit()
    return jsonify({'token': criar_token(usuario['id']), 'usuario': publico(usuario)})


@app.get('/api/eu')
@login_obrigatorio()
def eu():
    """Dados atualizados de quem está logado (reputação, advertências...)."""
    usuario = publico(g.usuario)
    usuario['ultima_advertencia'] = db().um(
        """SELECT motivo, data_acao FROM acoes_moderacao
           WHERE usuario_alvo_id = %s AND tipo_acao = 'advertencia'
           ORDER BY id DESC LIMIT 1""",
        (usuario['id'],),
    )
    return jsonify(usuario)


# ============================================================================
# ROTAS — MATÉRIAS
# ============================================================================
@app.get('/api/materias')
@login_obrigatorio()
def listar_materias():
    """Todas as matérias + quantos monitores da escola ensinam cada uma."""
    return jsonify(db().todos(
        """SELECT m.id, m.nome, m.area,
                  (SELECT COUNT(*) FROM monitor_materias mm
                     JOIN usuarios u ON u.id = mm.usuario_id
                    WHERE mm.materia_id = m.id AND mm.ativo = TRUE
                      AND u.instituicao_id = %s
                      AND u.status_conta <> 'banido' AND u.id <> %s) AS total_monitores
           FROM materias m
           ORDER BY m.area, m.nome""",
        (g.usuario['instituicao_id'], g.usuario['id']),
    ))


# ============================================================================
# ROTAS — MONITOR x MATÉRIA ("Matérias que eu ensino")
# ============================================================================
@app.get('/api/monitor-materias')
@login_obrigatorio(*ESTUDANTES)
def listar_minhas_materias():
    return jsonify(db().todos(
        """SELECT mm.id, mm.materia_id, mm.nivel_conhecimento, m.nome AS materia_nome, m.area
           FROM monitor_materias mm
           JOIN materias m ON m.id = mm.materia_id
           WHERE mm.usuario_id = %s AND mm.ativo = TRUE
           ORDER BY m.nome""",
        (g.usuario['id'],),
    ))


@app.post('/api/monitor-materias')
@login_obrigatorio(*ESTUDANTES)
def adicionar_minha_materia():
    dados = corpo()
    materia_id = inteiro(dados.get('materia_id'), 'Matéria')
    nivel = ler_nivel(dados.get('nivel_conhecimento'))
    materia = db().um('SELECT id, nome FROM materias WHERE id = %s', (materia_id,))
    if not materia:
        raise ErroApi(404, 'Matéria não encontrada.')

    existente = db().um('SELECT id FROM monitor_materias WHERE usuario_id = %s AND materia_id = %s',
                        (g.usuario['id'], materia_id))
    if existente:
        db().executar('UPDATE monitor_materias SET nivel_conhecimento = %s, ativo = TRUE WHERE id = %s',
                      (nivel, existente['id']))
        db().commit()
        return jsonify({'id': existente['id'], 'mensagem': f'{materia["nome"]}: nível atualizado.'})

    novo_id = db().inserir(
        'INSERT INTO monitor_materias (usuario_id, materia_id, nivel_conhecimento) VALUES (%s, %s, %s)',
        (g.usuario['id'], materia_id, nivel),
    )
    db().commit()
    return jsonify({'id': novo_id, 'mensagem': f'{materia["nome"]} adicionada.'}), 201


@app.delete('/api/monitor-materias/<int:registro_id>')
@login_obrigatorio(*ESTUDANTES)
def remover_minha_materia(registro_id):
    afetadas = db().executar(
        'UPDATE monitor_materias SET ativo = FALSE WHERE id = %s AND usuario_id = %s AND ativo = TRUE',
        (registro_id, g.usuario['id']),
    )
    if not afetadas:
        raise ErroApi(404, 'Essa matéria não está na sua lista.')
    db().commit()
    return jsonify({'mensagem': 'Matéria removida da sua lista.'})


# ============================================================================
# ROTAS — SOLICITAÇÕES DE AJUDA
# Status: pendente -> em_match (monitor aceitou) -> atendida (monitoria encerrada)
#         pendente -> cancelada (o aluno desistiu)
# ============================================================================
@app.post('/api/solicitacoes')
@login_obrigatorio(*ESTUDANTES)
def criar_solicitacao():
    dados = corpo()
    materia_id = inteiro(dados.get('materia_id'), 'Matéria')
    nivel = ler_nivel(dados.get('nivel_dificuldade'))
    descricao = texto(dados, 'descricao_duvida', 'Descreva sua dúvida', 5, 500)
    descricao, motivos = filtrar(descricao)

    materia = db().um('SELECT id, nome FROM materias WHERE id = %s', (materia_id,))
    if not materia:
        raise ErroApi(404, 'Matéria não encontrada.')
    pendentes = db().um(
        "SELECT COUNT(*) AS total FROM solicitacoes_ajuda WHERE aluno_id = %s AND status = 'pendente'",
        (g.usuario['id'],),
    )['total']
    if pendentes >= MAX_PEDIDOS_PENDENTES:
        raise ErroApi(409, f'Você já tem {MAX_PEDIDOS_PENDENTES} pedidos esperando monitor. '
                           'Cancele um deles ou aguarde.')
    if db().um("""SELECT id FROM solicitacoes_ajuda
                  WHERE aluno_id = %s AND materia_id = %s AND status = 'pendente'""",
               (g.usuario['id'], materia_id)):
        raise ErroApi(409, f'Você já tem um pedido esperando monitor em {materia["nome"]}.')

    novo_id = db().inserir(
        """INSERT INTO solicitacoes_ajuda (aluno_id, materia_id, nivel_dificuldade, descricao_duvida)
           VALUES (%s, %s, %s, %s)""",
        (g.usuario['id'], materia_id, nivel, descricao),
    )
    db().executar(  # avisa os monitores dessa matéria na mesma escola
        """INSERT INTO notificacoes (usuario_id, tipo, texto, link)
           SELECT mm.usuario_id, 'pedido', %s, 'dashboard.html'
           FROM monitor_materias mm JOIN usuarios u ON u.id = mm.usuario_id
           WHERE mm.materia_id = %s AND mm.ativo = TRUE AND u.instituicao_id = %s
             AND u.status_conta <> 'banido' AND u.id <> %s""",
        (f'Novo pedido de ajuda em {materia["nome"]}.', materia_id, g.usuario['instituicao_id'], g.usuario['id']),
    )
    db().commit()
    return jsonify({'id': novo_id, 'aviso': descrever_filtro(motivos, 'descrição')}), 201


@app.get('/api/solicitacoes')
@login_obrigatorio(*ESTUDANTES)
def minhas_solicitacoes():
    return jsonify(db().todos(
        """SELECT s.id, s.materia_id, m.nome AS materia_nome, s.nivel_dificuldade,
                  s.descricao_duvida, s.status, s.data_criacao,
                  mt.id AS match_id, mt.status AS match_status,
                  um.nome_completo AS monitor_nome, c.id AS conversa_id
           FROM solicitacoes_ajuda s
           JOIN materias m ON m.id = s.materia_id
           LEFT JOIN matches mt ON mt.solicitacao_id = s.id AND mt.status IN ('aceito', 'concluido')
           LEFT JOIN usuarios um ON um.id = mt.monitor_id
           LEFT JOIN conversas c ON c.match_id = mt.id
           WHERE s.aluno_id = %s
           ORDER BY (s.status = 'pendente') DESC, s.data_criacao DESC, s.id DESC
           LIMIT 50""",
        (g.usuario['id'],),
    ))


@app.post('/api/solicitacoes/<int:solicitacao_id>/cancelar')
@login_obrigatorio(*ESTUDANTES)
def cancelar_solicitacao(solicitacao_id):
    afetadas = db().executar(
        """UPDATE solicitacoes_ajuda SET status = 'cancelada'
           WHERE id = %s AND aluno_id = %s AND status = 'pendente'""",
        (solicitacao_id, g.usuario['id']),
    )
    if not afetadas:
        pedido = db().um('SELECT status FROM solicitacoes_ajuda WHERE id = %s AND aluno_id = %s',
                         (solicitacao_id, g.usuario['id']))
        if not pedido:
            raise ErroApi(404, 'Pedido não encontrado.')
        raise ErroApi(409, 'Esse pedido já foi aceito por um monitor (ou encerrado) e não pode ser cancelado.')
    db().commit()
    return jsonify({'mensagem': 'Pedido cancelado.'})


@app.get('/api/solicitacoes/pendentes')
@login_obrigatorio(*ESTUDANTES)
def solicitacoes_pendentes():
    """Pedidos pendentes da MESMA escola, nas matérias que esse monitor ensina."""
    linhas = db().todos(
        """SELECT s.id, s.materia_id, m.nome AS materia_nome, s.nivel_dificuldade,
                  s.descricao_duvida, s.data_criacao, s.aluno_id, u.nome_completo AS aluno_nome,
                  u.faixa_etaria, mm.nivel_conhecimento AS meu_nivel
           FROM solicitacoes_ajuda s
           JOIN materias m ON m.id = s.materia_id
           JOIN usuarios u ON u.id = s.aluno_id
           JOIN monitor_materias mm ON mm.materia_id = s.materia_id
                                   AND mm.usuario_id = %s AND mm.ativo = TRUE
           WHERE s.status = 'pendente' AND u.instituicao_id = %s
             AND u.status_conta <> 'banido' AND s.aluno_id <> %s
           ORDER BY s.data_criacao ASC, s.id ASC
           LIMIT 100""",
        (g.usuario['id'], g.usuario['instituicao_id'], g.usuario['id']),
    )
    for linha in linhas:
        linha['score'] = calcular_score(linha['meu_nivel'], linha['nivel_dificuldade'])
    linhas.sort(key=lambda linha: -linha['score'])  # melhores matches primeiro (mais antigos antes)
    return jsonify(linhas)


# ============================================================================
# ROTAS — MATCHES (o monitor aceita um pedido -> nasce o match e a conversa)
# Score de compatibilidade: 100 se o nível do monitor é igual ao da dúvida,
# 85 se o monitor sabe mais, 60/40 se sabe menos.
# ============================================================================
@app.post('/api/matches')
@login_obrigatorio(*ESTUDANTES)
def criar_match():
    dados = corpo()
    solicitacao_id = inteiro(dados.get('solicitacao_id'), 'Pedido')
    pedido = db().um(
        """SELECT s.id, s.aluno_id, s.materia_id, s.nivel_dificuldade, s.status, u.instituicao_id
           FROM solicitacoes_ajuda s JOIN usuarios u ON u.id = s.aluno_id
           WHERE s.id = %s""",
        (solicitacao_id,),
    )
    if not pedido or pedido['instituicao_id'] != g.usuario['instituicao_id']:
        raise ErroApi(404, 'Pedido não encontrado.')
    if pedido['status'] != 'pendente':
        raise ErroApi(409, 'Este pedido não está mais disponível (outro monitor pode ter aceitado).')
    if pedido['aluno_id'] == g.usuario['id']:
        raise ErroApi(400, 'Esse pedido é seu: outra pessoa precisa aceitar.')
    minha_materia = db().um(
        """SELECT nivel_conhecimento FROM monitor_materias
           WHERE usuario_id = %s AND materia_id = %s AND ativo = TRUE""",
        (g.usuario['id'], pedido['materia_id']),
    )
    if not minha_materia:
        raise ErroApi(403, 'Adicione essa matéria em "Matérias que eu ensino" antes de aceitar.')

    # UPDATE condicional: se dois monitores clicarem juntos, só o primeiro leva.
    if not db().executar("UPDATE solicitacoes_ajuda SET status = 'em_match' WHERE id = %s AND status = 'pendente'",
                         (solicitacao_id,)):
        raise ErroApi(409, 'Outro monitor acabou de aceitar este pedido.')

    score = calcular_score(minha_materia['nivel_conhecimento'], pedido['nivel_dificuldade'])
    match_id = db().inserir(
        """INSERT INTO matches (solicitacao_id, monitor_id, aluno_id, materia_id, score_compatibilidade, status)
           VALUES (%s, %s, %s, %s, %s, 'aceito')""",
        (solicitacao_id, g.usuario['id'], pedido['aluno_id'], pedido['materia_id'], score),
    )
    conversa_id = db().inserir('INSERT INTO conversas (match_id) VALUES (%s)', (match_id,))
    notificar(pedido['aluno_id'], 'match',
              f'{primeiro_nome(g.usuario["nome_completo"])} aceitou seu pedido de ajuda. O chat já está aberto.',
              f'dashboard.html#conversa-{conversa_id}', g.usuario['id'])
    db().commit()
    return jsonify({'match_id': match_id, 'conversa_id': conversa_id, 'score': score}), 201


@app.get('/api/matches')
@login_obrigatorio(*ESTUDANTES)
def meus_matches():
    eu_id = g.usuario['id']
    linhas = db().todos(
        """SELECT mt.id, mt.status, mt.score_compatibilidade, mt.data_match, mt.data_conclusao,
                  mt.aluno_id, mt.monitor_id, m.nome AS materia_nome, mt.link_meet,
                  s.nivel_dificuldade, s.descricao_duvida,
                  ua.nome_completo AS aluno_nome, umo.nome_completo AS monitor_nome,
                  c.id AS conversa_id, c.encerrada,
                  (SELECT MAX(msg.id) FROM mensagens msg WHERE msg.conversa_id = c.id) AS ultima_mensagem_id,
                  (SELECT msg.remetente_id FROM mensagens msg WHERE msg.conversa_id = c.id
                    ORDER BY msg.id DESC LIMIT 1) AS ultima_remetente_id,
                  (SELECT COUNT(*) FROM avaliacoes a
                    WHERE a.match_id = mt.id AND a.avaliador_id = %s) AS ja_avaliei
           FROM matches mt
           JOIN materias m ON m.id = mt.materia_id
           JOIN solicitacoes_ajuda s ON s.id = mt.solicitacao_id
           JOIN usuarios ua ON ua.id = mt.aluno_id
           JOIN usuarios umo ON umo.id = mt.monitor_id
           JOIN conversas c ON c.match_id = mt.id
           WHERE mt.aluno_id = %s OR mt.monitor_id = %s
           ORDER BY (mt.status = 'aceito') DESC, mt.data_match DESC, mt.id DESC
           LIMIT 100""",
        (eu_id, eu_id, eu_id),
    )
    for linha in linhas:
        sou_aluno = linha['aluno_id'] == eu_id
        linha['meu_papel'] = 'aluno' if sou_aluno else 'monitor'
        linha['com_quem'] = linha['monitor_nome'] if sou_aluno else linha['aluno_nome']
        linha['encerrada'] = bool(linha['encerrada'])
        linha['ja_avaliei'] = bool(linha['ja_avaliei'])
        linha['tipo'] = 'monitoria'
    linhas.extend(minhas_aulas_como_conversa(eu_id))
    linhas.sort(key=lambda linha: linha['status'] != 'aceito')  # em andamento primeiro
    return jsonify(linhas)


@app.post('/api/matches/<int:match_id>/concluir')
@login_obrigatorio(*ESTUDANTES)
def concluir_match(match_id):
    """Encerra a monitoria (qualquer um dos dois pode encerrar). Depois dá para avaliar."""
    match = db().um('SELECT id, solicitacao_id, aluno_id, monitor_id, status FROM matches WHERE id = %s',
                    (match_id,))
    if not match or g.usuario['id'] not in (match['aluno_id'], match['monitor_id']):
        raise ErroApi(404, 'Monitoria não encontrada.')
    if not db().executar(
            "UPDATE matches SET status = 'concluido', data_conclusao = NOW() WHERE id = %s AND status = 'aceito'",
            (match_id,)):
        raise ErroApi(409, 'Essa monitoria já foi encerrada.')
    db().executar('UPDATE conversas SET encerrada = TRUE WHERE match_id = %s', (match_id,))
    db().executar("UPDATE solicitacoes_ajuda SET status = 'atendida' WHERE id = %s", (match['solicitacao_id'],))
    outro = match['monitor_id'] if g.usuario['id'] == match['aluno_id'] else match['aluno_id']
    notificar(outro, 'monitoria', f'{primeiro_nome(g.usuario["nome_completo"])} encerrou a monitoria. Que tal avaliar?',
              'dashboard.html#mensagens', g.usuario['id'])
    db().commit()
    return jsonify({'mensagem': 'Monitoria encerrada. Que tal avaliar?'})


# ============================================================================
# ROTAS — CHAT (mensagens moderadas)
# ============================================================================
def carregar_conversa(conversa_id, permitir_coordenacao=False):
    """Conversa de uma monitoria (2 pessoas) ou de uma aula em grupo (monitor + inscritos).
    Só devolve se quem pede participa dela (ou coordena a escola)."""
    base = db().um('SELECT id, aula_id FROM conversas WHERE id = %s', (conversa_id,))
    if not base:
        raise ErroApi(404, 'Conversa não encontrada.')
    if base['aula_id']:
        conversa = db().um(
            """SELECT c.id, c.encerrada, c.match_id, c.aula_id, ag.status AS aula_status,
                      ag.titulo AS aula_titulo, ag.monitor_id, umo.instituicao_id,
                      m.nome AS materia_nome, umo.nome_completo AS monitor_nome
               FROM conversas c
               JOIN aulas_grupo ag ON ag.id = c.aula_id
               JOIN materias m ON m.id = ag.materia_id
               JOIN usuarios umo ON umo.id = ag.monitor_id
               WHERE c.id = %s""", (conversa_id,))
        inscritos = [linha['aluno_id'] for linha in db().todos(
            'SELECT aluno_id FROM inscricoes_aula WHERE aula_id = %s', (conversa['aula_id'],))]
        conversa.update({
            'grupo': True, 'aluno_id': None, 'participantes': [conversa['monitor_id'], *inscritos],
            'aluno_nome': f'{len(inscritos)} inscrito(s)',
            'match_status': {'aberta': 'aceito', 'concluida': 'concluido'}.get(conversa['aula_status'], 'cancelado'),
        })
    else:
        conversa = db().um(
            """SELECT c.id, c.encerrada, c.match_id, c.aula_id, mt.status AS match_status,
                      mt.aluno_id, mt.monitor_id, ua.instituicao_id, m.nome AS materia_nome,
                      ua.nome_completo AS aluno_nome, umo.nome_completo AS monitor_nome
               FROM conversas c
               JOIN matches mt ON mt.id = c.match_id
               JOIN materias m ON m.id = mt.materia_id
               JOIN usuarios ua ON ua.id = mt.aluno_id
               JOIN usuarios umo ON umo.id = mt.monitor_id
               WHERE c.id = %s""", (conversa_id,))
        conversa.update({'grupo': False, 'participantes': [conversa['aluno_id'], conversa['monitor_id']]})
    usuario = g.usuario
    participante = usuario['id'] in conversa['participantes']
    coordenacao = (permitir_coordenacao and usuario['tipo_usuario'] in TIPOS_COORDENACAO
                   and usuario['instituicao_id'] == conversa['instituicao_id'])
    if not (participante or coordenacao):
        raise ErroApi(404, 'Conversa não encontrada.')
    conversa['participante'] = participante
    return conversa


@app.get('/api/mensagens')
@login_obrigatorio()
def listar_mensagens():
    """?conversa_id=N&depois=ID  (depois = só mensagens novas, usado pela atualização automática)."""
    conversa_id = inteiro(request.args.get('conversa_id'), 'Conversa')
    depois = request.args.get('depois', '0')
    depois = int(depois) if str(depois).isdigit() else 0
    conversa = carregar_conversa(conversa_id, permitir_coordenacao=True)

    # A coordenação também vê o texto original (antes do filtro), para moderar.
    coluna_original = '' if conversa['participante'] else ', msg.conteudo_original'
    mensagens = db().todos(
        f"""SELECT msg.id, msg.remetente_id, msg.conteudo_filtrado, msg.foi_filtrada,
                   msg.data_envio, u.nome_completo AS remetente_nome{coluna_original},
                   msg.anexo_categoria
            FROM mensagens msg
            JOIN usuarios u ON u.id = msg.remetente_id
            WHERE msg.conversa_id = %s AND msg.id > %s
            ORDER BY msg.id DESC
            LIMIT 300""",
        (conversa_id, depois),
    )
    mensagens.reverse()
    for mensagem in mensagens:
        preparar_mensagem(mensagem)
    return jsonify({
        'mensagens': mensagens,
        'encerrada': bool(conversa['encerrada']) or conversa['match_status'] != 'aceito',
        'match_status': conversa['match_status'],
        'materia_nome': conversa['materia_nome'],
        'aluno_nome': conversa['aluno_nome'],
        'monitor_nome': conversa['monitor_nome'],
        'grupo': conversa['grupo'],
        'aula_titulo': conversa.get('aula_titulo'),
    })


@app.post('/api/mensagens')
@login_obrigatorio(*ESTUDANTES)
def enviar_mensagem():
    dados = corpo()
    conversa_id = inteiro(dados.get('conversa_id'), 'Conversa')
    original = texto(dados, 'conteudo', 'Mensagem', 1, filtro.TAMANHO_MAXIMO)
    conversa = carregar_conversa(conversa_id)
    if conversa['encerrada'] or conversa['match_status'] != 'aceito':
        raise ErroApi(409, 'Esta monitoria foi encerrada; o chat está fechado.')

    filtrado, motivos = filtrar(original)
    if not filtrado.strip():
        raise ErroApi(400, 'A mensagem ficou vazia depois do filtro.')
    novo_id = db().inserir(
        """INSERT INTO mensagens (conversa_id, remetente_id, conteudo_original, conteudo_filtrado, foi_filtrada)
           VALUES (%s, %s, %s, %s, %s)""",
        (conversa_id, g.usuario['id'], original, filtrado, bool(motivos)),
    )
    avisar_nova_mensagem(conversa)
    db().commit()
    mensagem = buscar_mensagem(novo_id)
    return jsonify({'id': novo_id, 'foi_filtrada': bool(motivos), 'mensagem': mensagem,
                    'aviso': descrever_filtro(motivos)}), 201


# ============================================================================
# ROTAS — AVALIAÇÕES (reputação) — só depois de encerrar a monitoria
# ============================================================================
@app.post('/api/avaliacoes')
@login_obrigatorio(*ESTUDANTES)
def avaliar():
    dados = corpo()
    match_id = inteiro(dados.get('match_id'), 'Monitoria')
    try:
        nota = int(dados.get('nota'))
    except (TypeError, ValueError):
        nota = 0
    if not 1 <= nota <= 5:
        raise ErroApi(400, 'Escolha uma nota de 1 a 5 estrelas.')
    comentario = texto(dados, 'comentario', 'Comentário', 0, 500)
    comentario = filtrar(comentario)[0] if comentario else ''

    match = db().um('SELECT id, aluno_id, monitor_id, status FROM matches WHERE id = %s', (match_id,))
    if not match or g.usuario['id'] not in (match['aluno_id'], match['monitor_id']):
        raise ErroApi(404, 'Monitoria não encontrada.')
    if match['status'] != 'concluido':
        raise ErroApi(409, 'Encerre a monitoria antes de avaliar.')
    if db().um('SELECT id FROM avaliacoes WHERE match_id = %s AND avaliador_id = %s',
               (match_id, g.usuario['id'])):
        raise ErroApi(409, 'Você já avaliou esta monitoria.')

    # Quem é avaliado é decidido aqui no servidor (antes vinha do navegador).
    avaliado_id = match['monitor_id'] if g.usuario['id'] == match['aluno_id'] else match['aluno_id']
    db().inserir(
        """INSERT INTO avaliacoes (match_id, avaliador_id, avaliado_id, nota, comentario)
           VALUES (%s, %s, %s, %s, %s)""",
        (match_id, g.usuario['id'], avaliado_id, nota, comentario),
    )
    db().executar(
        """UPDATE usuarios SET reputacao_media = (
               SELECT AVG(nota) FROM avaliacoes WHERE avaliado_id = %s
           ) WHERE id = %s""",
        (avaliado_id, avaliado_id),
    )
    notificar(avaliado_id, 'avaliacao', f'Você recebeu uma avaliação de {nota} estrela{"s" if nota > 1 else ""}.',
              'dashboard.html#perfil')
    db().commit()
    return jsonify({'mensagem': 'Avaliação registrada. Obrigado!'}), 201


# ============================================================================
# ROTAS — DENÚNCIAS E MODERAÇÃO
# ============================================================================
@app.post('/api/denuncias')
@login_obrigatorio(*ESTUDANTES)
def denunciar():
    """Denuncia a outra pessoa da conversa; a última mensagem dela vai junto como evidência."""
    dados = corpo()
    conversa_id = inteiro(dados.get('conversa_id'), 'Conversa')
    motivo = texto(dados, 'motivo', 'Motivo da denúncia', 5, 500)
    conversa = carregar_conversa(conversa_id)
    if conversa['grupo']:  # na aula em grupo, a pessoa escolhe quem está denunciando
        denunciado_id = inteiro(dados.get('denunciado_id'), 'Pessoa denunciada')
        if denunciado_id == g.usuario['id'] or denunciado_id not in conversa['participantes']:
            raise ErroApi(400, 'Escolha alguém que participa desta aula.')
    else:
        denunciado_id = conversa['monitor_id'] if g.usuario['id'] == conversa['aluno_id'] else conversa['aluno_id']

    if db().um("""SELECT id FROM denuncias
                  WHERE denunciante_id = %s AND conversa_id = %s AND denunciado_id = %s
                    AND status IN ('pendente', 'em_analise')""",
               (g.usuario['id'], conversa_id, denunciado_id)):
        raise ErroApi(409, 'Você já denunciou esta conversa. A coordenação vai analisar.')
    ultima = db().um(
        'SELECT id FROM mensagens WHERE conversa_id = %s AND remetente_id = %s ORDER BY id DESC LIMIT 1',
        (conversa_id, denunciado_id),
    )
    db().inserir(
        """INSERT INTO denuncias (denunciante_id, denunciado_id, conversa_id, mensagem_id, motivo)
           VALUES (%s, %s, %s, %s, %s)""",
        (g.usuario['id'], denunciado_id, conversa_id, ultima['id'] if ultima else None, motivo),
    )
    db().executar("""INSERT INTO notificacoes (usuario_id, tipo, texto, link)
                     SELECT id, 'denuncia', 'Nova denúncia para analisar.', 'dashboard.html'
                     FROM usuarios WHERE instituicao_id = %s AND tipo_usuario IN ('coordenador', 'admin')
                       AND status_conta <> 'banido'""", (g.usuario['instituicao_id'],))
    db().commit()
    return jsonify({'mensagem': 'Denúncia enviada para a coordenação da escola.'}), 201


def banir_usuario(usuario_id):
    """Suspende a conta e desfaz o que ela tinha em andamento."""
    db().executar("UPDATE usuarios SET status_conta = 'banido' WHERE id = %s", (usuario_id,))
    desfazer_pendencias(usuario_id)


def desfazer_pendencias(usuario_id):
    """Cancela pedidos, monitorias e aulas em andamento (usado ao suspender e ao excluir a conta)."""
    db().executar("""UPDATE solicitacoes_ajuda SET status = 'cancelada'
                     WHERE aluno_id = %s AND status = 'pendente'""", (usuario_id,))
    ativos = db().todos("""SELECT id, solicitacao_id, monitor_id FROM matches
                           WHERE (aluno_id = %s OR monitor_id = %s) AND status = 'aceito'""",
                        (usuario_id, usuario_id))
    for match in ativos:
        db().executar("UPDATE matches SET status = 'cancelado', data_conclusao = NOW() WHERE id = %s",
                      (match['id'],))
        db().executar('UPDATE conversas SET encerrada = TRUE WHERE match_id = %s', (match['id'],))
        # Se o suspenso era o monitor, o pedido volta para a fila; se era o aluno, é cancelado.
        novo_status = 'pendente' if match['monitor_id'] == usuario_id else 'cancelada'
        db().executar('UPDATE solicitacoes_ajuda SET status = %s WHERE id = %s',
                      (novo_status, match['solicitacao_id']))
    # Aulas em grupo: as que ele dava são canceladas; das que participava, ele sai.
    for aula in db().todos("SELECT id FROM aulas_grupo WHERE monitor_id = %s AND status = 'aberta'", (usuario_id,)):
        db().executar("UPDATE aulas_grupo SET status = 'cancelada' WHERE id = %s", (aula['id'],))
        db().executar('UPDATE conversas SET encerrada = TRUE WHERE aula_id = %s', (aula['id'],))
    db().executar('DELETE FROM inscricoes_aula WHERE aluno_id = %s', (usuario_id,))


@app.post('/api/denuncias/<int:denuncia_id>/moderar')
@login_obrigatorio(*TIPOS_COORDENACAO)
def moderar_denuncia(denuncia_id):
    """{"acao": "advertencia" | "banimento" | "arquivar", "motivo": "..."}"""
    dados = corpo()
    acao = str(dados.get('acao') or '').strip().lower()
    if acao not in ('advertencia', 'banimento', 'arquivar'):
        raise ErroApi(400, 'Ação inválida. Use advertencia, banimento ou arquivar.')
    motivo = texto(dados, 'motivo', 'Motivo', 0, 500)

    denuncia = db().um(
        """SELECT d.id, d.status, d.motivo, d.denunciado_id, u.instituicao_id, u.tipo_usuario
           FROM denuncias d JOIN usuarios u ON u.id = d.denunciado_id
           WHERE d.id = %s""",
        (denuncia_id,),
    )
    if not denuncia or denuncia['instituicao_id'] != g.usuario['instituicao_id']:
        raise ErroApi(404, 'Denúncia não encontrada.')
    if denuncia['status'] not in ('pendente', 'em_analise'):
        raise ErroApi(409, 'Essa denúncia já foi tratada.')

    if acao == 'arquivar':
        db().executar("UPDATE denuncias SET status = 'arquivada' WHERE id = %s", (denuncia_id,))
        db().commit()
        return jsonify({'mensagem': 'Denúncia arquivada.'})

    alvo = denuncia['denunciado_id']
    if denuncia['tipo_usuario'] in TIPOS_COORDENACAO:
        raise ErroApi(400, 'Contas da coordenação não podem ser advertidas ou suspensas por aqui.')
    db().inserir(
        """INSERT INTO acoes_moderacao (usuario_alvo_id, moderador_id, denuncia_id, tipo_acao, motivo)
           VALUES (%s, %s, %s, %s, %s)""",
        (alvo, g.usuario['id'], denuncia_id, acao, motivo or denuncia['motivo']),
    )
    if acao == 'advertencia':
        db().executar("UPDATE usuarios SET status_conta = 'advertido' WHERE id = %s AND status_conta = 'ativo'",
                      (alvo,))
        db().executar("UPDATE denuncias SET status = 'resolvida' WHERE id = %s", (denuncia_id,))
        mensagem = 'Advertência registrada. A pessoa verá um aviso ao entrar.'
    else:
        banir_usuario(alvo)
        # Outras denúncias abertas contra a mesma pessoa também ficam resolvidas.
        db().executar("""UPDATE denuncias SET status = 'resolvida'
                         WHERE denunciado_id = %s AND status IN ('pendente', 'em_analise')""", (alvo,))
        mensagem = 'Conta suspensa. As monitorias em andamento dela foram encerradas.'
    db().commit()
    return jsonify({'mensagem': mensagem})


@app.post('/api/usuarios/<int:usuario_id>/desbanir')
@login_obrigatorio(*TIPOS_COORDENACAO)
def desbanir(usuario_id):
    afetadas = db().executar(
        """UPDATE usuarios SET status_conta = 'ativo'
           WHERE id = %s AND instituicao_id = %s AND status_conta = 'banido'""",
        (usuario_id, g.usuario['instituicao_id']),
    )
    if not afetadas:
        raise ErroApi(404, 'Conta suspensa não encontrada.')
    db().inserir(
        """INSERT INTO acoes_moderacao (usuario_alvo_id, moderador_id, tipo_acao, motivo)
           VALUES (%s, %s, 'desbanimento', %s)""",
        (usuario_id, g.usuario['id'], 'Conta reativada pela coordenação.'),
    )
    db().commit()
    return jsonify({'mensagem': 'Conta reativada.'})


# ============================================================================
# ROTAS — PAINEL DA COORDENAÇÃO (usa a instituição de quem está logado)
# ============================================================================
@app.get('/api/painel')
@login_obrigatorio(*TIPOS_COORDENACAO)
def painel_coordenacao():
    inst = g.usuario['instituicao_id']
    resumo = db().um(
        """SELECT
             (SELECT COUNT(*) FROM usuarios WHERE instituicao_id = %s AND tipo_usuario IN ('aluno', 'monitor')) AS alunos,
             (SELECT COUNT(DISTINCT mm.usuario_id) FROM monitor_materias mm JOIN usuarios u ON u.id = mm.usuario_id
               WHERE u.instituicao_id = %s AND mm.ativo = TRUE) AS monitores,
             (SELECT COUNT(*) FROM solicitacoes_ajuda s JOIN usuarios u ON u.id = s.aluno_id
               WHERE u.instituicao_id = %s) AS solicitacoes,
             (SELECT COUNT(*) FROM solicitacoes_ajuda s JOIN usuarios u ON u.id = s.aluno_id
               WHERE u.instituicao_id = %s AND s.status = 'pendente') AS pendentes,
             (SELECT COUNT(*) FROM matches mt JOIN usuarios u ON u.id = mt.aluno_id
               WHERE u.instituicao_id = %s AND mt.status IN ('aceito', 'concluido')) AS monitorias,
             (SELECT COUNT(*) FROM mensagens msg JOIN usuarios u ON u.id = msg.remetente_id
               WHERE u.instituicao_id = %s AND msg.foi_filtrada = TRUE) AS mensagens_filtradas,
             (SELECT COUNT(*) FROM aulas_grupo ag JOIN usuarios u ON u.id = ag.monitor_id
               WHERE u.instituicao_id = %s AND ag.status <> 'cancelada') AS aulas_grupo,
             (SELECT COUNT(*) FROM denuncias d JOIN usuarios u ON u.id = d.denunciado_id
               WHERE u.instituicao_id = %s AND d.status IN ('pendente', 'em_analise')) AS denuncias_abertas""",
        (inst,) * 8,
    )
    materias = db().todos(
        """SELECT materia, total_solicitacoes, total_atendidas, taxa_defasagem_pct
           FROM vw_painel_coordenacao
           WHERE instituicao_id = %s
           ORDER BY total_solicitacoes DESC, materia""",
        (inst,),
    )
    monitores = db().todos(
        """SELECT u.id, u.nome_completo, u.reputacao_media, u.status_conta,
                  (SELECT COUNT(*) FROM matches mt
                    WHERE mt.monitor_id = u.id AND mt.status IN ('aceito', 'concluido')) AS monitorias,
                  (SELECT COUNT(*) FROM matches mt
                    WHERE mt.monitor_id = u.id AND mt.status = 'concluido') AS concluidas,
                  (SELECT COUNT(*) FROM avaliacoes a WHERE a.avaliado_id = u.id) AS avaliacoes
           FROM usuarios u
           WHERE u.instituicao_id = %s AND u.tipo_usuario IN ('aluno', 'monitor')
             AND (EXISTS (SELECT 1 FROM monitor_materias mm WHERE mm.usuario_id = u.id)
                  OR EXISTS (SELECT 1 FROM matches mt WHERE mt.monitor_id = u.id))
           ORDER BY monitorias DESC, u.nome_completo
           LIMIT 30""",
        (inst,),
    )
    denuncias = db().todos(
        """SELECT d.id, d.motivo, d.status, d.data_denuncia, d.conversa_id, d.denunciado_id,
                  ud.nome_completo AS denunciado_nome, ud.tipo_usuario AS denunciado_tipo,
                  ud.status_conta AS denunciado_status, ue.nome_completo AS denunciante_nome,
                  msg.conteudo_original AS mensagem_original,
                  (SELECT COUNT(*) FROM acoes_moderacao am
                    WHERE am.usuario_alvo_id = d.denunciado_id AND am.tipo_acao = 'advertencia') AS advertencias
           FROM denuncias d
           JOIN usuarios ud ON ud.id = d.denunciado_id
           JOIN usuarios ue ON ue.id = d.denunciante_id
           LEFT JOIN mensagens msg ON msg.id = d.mensagem_id
           WHERE ud.instituicao_id = %s
           ORDER BY (d.status IN ('pendente', 'em_analise')) DESC, d.data_denuncia DESC, d.id DESC
           LIMIT 50""",
        (inst,),
    )
    suspensos = db().todos(
        """SELECT id, nome_completo, tipo_usuario, email_institucional FROM usuarios
           WHERE instituicao_id = %s AND status_conta = 'banido' ORDER BY nome_completo""",
        (inst,),
    )
    return jsonify({
        'instituicao': g.usuario['instituicao_nome'],
        'resumo': resumo,
        'materias': materias,
        'monitores': monitores,
        'denuncias': denuncias,
        'suspensos': suspensos,
    })


# ============================================================================
# INICIALIZAÇÃO
# ============================================================================
# ============================================================================
# NOTIFICAÇÕES (sino do cabeçalho) — criadas nos eventos reais acima
# ============================================================================
def primeiro_nome(nome):
    return nome.split()[0] if nome and nome.split() else 'Alguém'


def notificar(usuario_id, tipo, texto_aviso, link='dashboard.html', ator_id=None):
    """ator_id = quem causou o aviso: o primeiro nome dele no texto vira um link para o perfil."""
    db().inserir('INSERT INTO notificacoes (usuario_id, tipo, texto, link, ator_id) VALUES (%s, %s, %s, %s, %s)',
                 (usuario_id, tipo, texto_aviso[:250], link, ator_id))


def avisar_nova_mensagem(conversa):
    """Uma notificação por conversa até a pessoa abrir (não vira spam a cada mensagem)."""
    link = f'dashboard.html#conversa-{conversa["id"]}'
    nome = primeiro_nome(g.usuario['nome_completo'])
    onde = f'na aula "{conversa["aula_titulo"]}"' if conversa['grupo'] else f'em {conversa["materia_nome"]}'
    for pessoa in conversa['participantes']:
        if pessoa == g.usuario['id']:
            continue
        if not db().um("SELECT id FROM notificacoes WHERE usuario_id = %s AND link = %s AND tipo = 'mensagem' AND lida = FALSE",
                       (pessoa, link)):
            notificar(pessoa, 'mensagem', f'Nova mensagem de {nome} {onde}.', link, g.usuario['id'])


@app.get('/api/notificacoes')
@login_obrigatorio()
def listar_notificacoes():
    itens = db().todos(
        """SELECT n.id, n.tipo, n.texto, n.link, n.lida, n.data_criacao, n.ator_id, a.nome_completo AS ator_nome
           FROM notificacoes n LEFT JOIN usuarios a ON a.id = n.ator_id
           WHERE n.usuario_id = %s ORDER BY n.id DESC LIMIT 20""", (g.usuario['id'],))
    for item in itens:
        item['lida'] = bool(item['lida'])
        # O navegador procura este primeiro nome no texto e transforma em link para o perfil.
        item['ator_nome'] = primeiro_nome(item['ator_nome']) if item['ator_id'] else None
    total = db().um('SELECT COUNT(*) AS total FROM notificacoes WHERE usuario_id = %s AND lida = FALSE',
                    (g.usuario['id'],))['total']
    return jsonify({'itens': itens, 'nao_lidas': total})


@app.post('/api/notificacoes/lidas')
@login_obrigatorio()
def marcar_notificacoes_lidas():
    """Sem corpo: marca todas. Com {"ids": [...]}: só essas."""
    dados = request.get_json(silent=True) or {}
    ids = [i for i in (dados.get('ids') or []) if isinstance(i, int)][:100]
    if ids:
        marcadores = ', '.join(['%s'] * len(ids))
        db().executar(f'UPDATE notificacoes SET lida = TRUE WHERE usuario_id = %s AND id IN ({marcadores})',
                      (g.usuario['id'], *ids))
    else:
        db().executar('UPDATE notificacoes SET lida = TRUE WHERE usuario_id = %s AND lida = FALSE',
                      (g.usuario['id'],))
    db().commit()
    return jsonify({'mensagem': 'Notificações marcadas como lidas.'})


# ============================================================================
# PERFIL — dados reais (avaliações, monitorias, matérias)
# ============================================================================
def montar_perfil(usuario_id):
    perfil = db().um(
        """SELECT u.id, u.nome_completo, u.tipo_usuario, u.bio, u.reputacao_media, u.status_conta,
                  u.data_cadastro, u.email_verificado, u.instituicao_id, i.nome AS instituicao_nome,
                  (SELECT COUNT(*) FROM avaliacoes a WHERE a.avaliado_id = u.id) AS total_avaliacoes,
                  (SELECT COUNT(*) FROM matches mt WHERE (mt.monitor_id = u.id OR mt.aluno_id = u.id)
                      AND mt.status IN ('aceito', 'concluido')) AS total_monitorias,
                  (SELECT COUNT(*) FROM matches mt WHERE mt.monitor_id = u.id
                      AND mt.status = 'concluido') AS monitorias_dadas
           FROM usuarios u JOIN instituicoes i ON i.id = u.instituicao_id
           WHERE u.id = %s""", (usuario_id,))
    if not perfil or perfil['instituicao_id'] != g.usuario['instituicao_id']:
        raise ErroApi(404, 'Perfil não encontrado.')  # só vê perfis da própria escola
    perfil['ensina'] = db().todos(
        """SELECT m.nome, mm.nivel_conhecimento AS nivel FROM monitor_materias mm
           JOIN materias m ON m.id = mm.materia_id
           WHERE mm.usuario_id = %s AND mm.ativo = TRUE ORDER BY m.nome""", (usuario_id,))
    perfil['quer_aprender'] = [linha['nome'] for linha in db().todos(
        """SELECT DISTINCT m.nome FROM solicitacoes_ajuda s JOIN materias m ON m.id = s.materia_id
           WHERE s.aluno_id = %s AND s.status <> 'cancelada' ORDER BY m.nome""", (usuario_id,))]
    perfil['avaliacoes'] = db().todos(
        """SELECT a.nota, a.comentario, a.data_avaliacao, m.nome AS materia
           FROM avaliacoes a JOIN matches mt ON mt.id = a.match_id JOIN materias m ON m.id = mt.materia_id
           WHERE a.avaliado_id = %s ORDER BY a.id DESC LIMIT 5""", (usuario_id,))
    perfil['email_verificado'] = bool(perfil['email_verificado'])
    perfil['eu'] = usuario_id == g.usuario['id']
    if not perfil['total_avaliacoes']:
        perfil['reputacao_media'] = None  # sem avaliação ainda: não mostra "5,0" falso
    return perfil


@app.get('/api/perfil')
@login_obrigatorio()
def meu_perfil():
    return jsonify(montar_perfil(g.usuario['id']))


@app.get('/api/perfil/<int:usuario_id>')
@login_obrigatorio()
def ver_perfil(usuario_id):
    return jsonify(montar_perfil(usuario_id))


@app.get('/api/usuarios/busca')
@login_obrigatorio()
def buscar_usuarios():
    """Lupa do cabeçalho: pessoas da MESMA escola pelo nome (sem ligar para acento ou maiúscula)."""
    termos = filtro.normalizar(' '.join(str(request.args.get('q') or '').split())[:60]).split()
    if not termos or len(''.join(termos)) < 2:
        return jsonify([])
    coordenacao = g.usuario['tipo_usuario'] in TIPOS_COORDENACAO
    pessoas = db().todos(
        """SELECT u.id, u.nome_completo, u.tipo_usuario, u.reputacao_media, u.status_conta,
                  (SELECT COUNT(*) FROM avaliacoes a WHERE a.avaliado_id = u.id) AS total_avaliacoes
           FROM usuarios u WHERE u.instituicao_id = %s""", (g.usuario['instituicao_id'],))
    achados = []
    for pessoa in pessoas:
        if pessoa['status_conta'] == 'banido' and not coordenacao:
            continue  # conta suspensa só aparece para a coordenação
        nome = filtro.normalizar(pessoa['nome_completo'])
        palavras = nome.split()
        if all(termo in nome for termo in termos):
            # Quem tem uma palavra do nome começando pelo que foi digitado aparece primeiro.
            comeca = any(p.startswith(termos[0]) for p in palavras)
            achados.append((not comeca, nome, pessoa))
    achados.sort(key=lambda item: item[:2])
    return jsonify([{
        'id': p['id'], 'nome_completo': p['nome_completo'], 'tipo_usuario': p['tipo_usuario'],
        'status_conta': p['status_conta'], 'eu': p['id'] == g.usuario['id'],
        'reputacao_media': p['reputacao_media'] if p['total_avaliacoes'] else None,
    } for _, _, p in achados[:10]])


@app.put('/api/perfil')
@login_obrigatorio()
def editar_perfil():
    dados = corpo()
    nome = ' '.join(texto(dados, 'nome_completo', 'Nome', 3, 150).split())
    bio = texto(dados, 'bio', 'Sobre você', 0, 300)
    bio, motivos = filtrar(bio) if bio else ('', [])
    db().executar('UPDATE usuarios SET nome_completo = %s, bio = %s WHERE id = %s',
                  (nome, bio or None, g.usuario['id']))
    db().commit()
    return jsonify({'mensagem': 'Perfil atualizado.', 'aviso': descrever_filtro(motivos, 'texto do perfil'),
                    'perfil': montar_perfil(g.usuario['id'])})


# ============================================================================
# CHAT SÓ COM TEXTO (v6.4): o envio de arquivos e áudios foi retirado.
# As colunas anexo_* continuam no banco (nada é apagado), mas não são mais usadas.
# Mensagens antigas que eram só um arquivo aparecem com um aviso no lugar.
# ============================================================================
PASTA_UPLOADS = os.path.join(config.PASTA_BACKEND, 'uploads')  # arquivos de versões antigas
SQL_MENSAGEM = """SELECT msg.id, msg.remetente_id, msg.conteudo_filtrado, msg.foi_filtrada, msg.data_envio,
                         msg.anexo_categoria, u.nome_completo AS remetente_nome
                  FROM mensagens msg JOIN usuarios u ON u.id = msg.remetente_id WHERE msg.id = %s"""


def preparar_mensagem(mensagem):
    mensagem['foi_filtrada'] = bool(mensagem['foi_filtrada'])
    mensagem['anexo_removido'] = bool(mensagem.pop('anexo_categoria', None))
    for coluna in ('anexo_nome', 'anexo_tipo', 'anexo_tamanho', 'anexo_arquivo'):
        mensagem.pop(coluna, None)
    return mensagem


def buscar_mensagem(mensagem_id):
    return preparar_mensagem(db().um(SQL_MENSAGEM, (mensagem_id,)))


# ============================================================================
# SENHAS: esqueci minha senha (código por e-mail), trocar senha e
# redefinição pela coordenação (senha temporária)
# ============================================================================
CODIGO_VALIDADE = timedelta(minutes=15)
CODIGO_TENTATIVAS = 5
CODIGOS_POR_HORA = 3
LETRAS_TEMPORARIA = 'abcdefghjkmnpqrstuvwxyz23456789'  # sem l/1/o/0, que confundem


def validar_senha_nova(senha):
    senha = str(senha or '')
    if len(senha) < 6:
        raise ErroApi(400, 'A senha precisa ter pelo menos 6 caracteres.')
    if len(senha) > 128:
        raise ErroApi(400, 'A senha pode ter no máximo 128 caracteres.')
    return senha


def agora():
    return datetime.now().replace(microsecond=0)


def como_data(valor):
    return datetime.fromisoformat(str(valor)) if isinstance(valor, str) else valor


def enviar_email(destino, assunto, texto_email, html_email=None):
    """Envia pelo Gmail (ou outro SMTP) configurado no .env. Sempre com conexão criptografada."""
    mensagem = EmailMessage()
    mensagem['Subject'] = assunto
    mensagem['From'] = f'ClassMatch <{cfg.EMAIL_USUARIO}>'
    mensagem['To'] = destino
    mensagem.set_content(texto_email)
    if html_email:
        mensagem.add_alternative(html_email, subtype='html')
    contexto = ssl.create_default_context()
    local = cfg.EMAIL_SERVIDOR in ('127.0.0.1', 'localhost')  # só para testes no próprio computador
    try:
        if cfg.EMAIL_PORTA == 465:
            with smtplib.SMTP_SSL(cfg.EMAIL_SERVIDOR, 465, context=contexto, timeout=20) as smtp:
                smtp.login(cfg.EMAIL_USUARIO, cfg.EMAIL_SENHA_APP)
                smtp.send_message(mensagem)
            return
        with smtplib.SMTP(cfg.EMAIL_SERVIDOR, cfg.EMAIL_PORTA, timeout=20) as smtp:
            smtp.ehlo()
            if smtp.has_extn('starttls'):
                smtp.starttls(context=contexto)
                smtp.ehlo()
            elif not local:
                raise smtplib.SMTPException('o servidor de e-mail não oferece conexão segura')
            smtp.login(cfg.EMAIL_USUARIO, cfg.EMAIL_SENHA_APP)
            smtp.send_message(mensagem)
    except smtplib.SMTPAuthenticationError as erro:
        print(f'  [e-mail] O Gmail recusou o login: confira EMAIL_USUARIO e EMAIL_SENHA_APP no .env ({erro})')
        raise ErroApi(503, 'O envio de e-mail do ClassMatch está com problema. Procure a coordenação.') from None
    except (smtplib.SMTPException, OSError) as erro:
        print(f'  [e-mail] Não consegui enviar: {erro}')
        raise ErroApi(503, 'Não foi possível enviar o e-mail agora. Tente de novo em alguns minutos.') from None


def recarregar_email():
    """Relê o e-mail do .env (quem configurou com o servidor ligado não precisa reiniciar)."""
    valores = config.ler_env(config.ARQUIVO_ENV)
    cfg.EMAIL_USUARIO = (valores.get('EMAIL_USUARIO') or '').strip()
    cfg.EMAIL_SENHA_APP = (valores.get('EMAIL_SENHA_APP') or '').replace(' ', '')
    cfg.EMAIL_SERVIDOR = (valores.get('EMAIL_SERVIDOR') or 'smtp.gmail.com').strip()
    try:
        cfg.EMAIL_PORTA = int(valores.get('EMAIL_PORTA') or 587)
    except ValueError:
        cfg.EMAIL_PORTA = 587
    cfg.EMAIL_ATIVO = bool(cfg.EMAIL_USUARIO and cfg.EMAIL_SENHA_APP)


@app.post('/api/senha/esqueci')
def esqueci_senha():
    """Envia o link + código. A resposta no site é igual exista ou não o e-mail;
    o motivo de cada pedido aparece só na janela do servidor."""
    if not cfg.EMAIL_ATIVO:
        recarregar_email()
    if not cfg.EMAIL_ATIVO:
        print('  [senha] Pedido de nova senha, mas o e-mail não está configurado no .env (mostrei "procure a coordenação").')
        return jsonify({'modo': 'coordenacao',
                        'mensagem': 'Procure a coordenação da sua escola: ela gera uma senha temporária '
                                    'para você entrar e criar uma nova.'})
    email = str(corpo().get('email') or '').strip().lower()[:150]
    if '@' not in email:
        raise ErroApi(400, 'Digite o e-mail da sua conta.')
    usuario = db().um('SELECT id, nome_completo, status_conta FROM usuarios WHERE LOWER(email_institucional) = %s',
                      (email,))
    if not usuario:
        print(f'  [senha] Pedido para {email}: NÃO existe conta com esse e-mail (nada foi enviado).')
    elif usuario['status_conta'] == 'banido':
        print(f'  [senha] Pedido para {email}: conta suspensa (nada foi enviado).')
    if usuario and usuario['status_conta'] != 'banido':
        recentes = db().um('SELECT COUNT(*) AS total FROM codigos_senha WHERE usuario_id = %s AND data_criacao >= %s',
                           (usuario['id'], agora() - timedelta(hours=1)))['total']
        if recentes < CODIGOS_POR_HORA:  # evita encher a caixa de alguém de e-mails
            codigo = f'{secrets.randbelow(1_000_000):06d}'
            db().executar('UPDATE codigos_senha SET usado = TRUE WHERE usuario_id = %s AND usado = FALSE',
                          (usuario['id'],))
            codigo_id = db().inserir('INSERT INTO codigos_senha (usuario_id, codigo_hash, expira_em, data_criacao) '
                                     'VALUES (%s, %s, %s, %s)',
                                     (usuario['id'], gerar_hash_senha(codigo), agora() + CODIGO_VALIDADE, agora()))
            link = f'{cfg.SITE_URL}/redefinir-senha.html?token={assinador_senha.dumps({"u": usuario["id"], "c": codigo_id})}'
            nome = primeiro_nome(usuario['nome_completo'])
            enviar_email(email, 'Crie sua nova senha do ClassMatch',
                         f'Olá, {nome}!\n\nRecebemos um pedido para trocar a senha da sua conta no ClassMatch.\n\n'
                         f'1) Abra este link: {link}\n2) Digite o código: {codigo}\n\n'
                         f'O link e o código valem por 15 minutos e só funcionam uma vez.\n'
                         f'Se não foi você que pediu, ignore este e-mail: sua senha continua a mesma.\n\nEquipe ClassMatch',
                         email_html_senha(nome, codigo, link))
            db().commit()
            print(f'  [senha] Pedido para {email}: link enviado por e-mail.')
        else:
            print(f'  [senha] Pedido para {email}: já foram {CODIGOS_POR_HORA} e-mails na última hora (nada enviado; tente mais tarde).')
    return jsonify({'modo': 'email',
                    'mensagem': 'Se esse e-mail tiver uma conta, enviamos um link para criar a nova senha. '
                                'Ele vale por 15 minutos (olhe também a caixa de spam).'})


def email_html_senha(nome, codigo, link):
    nome, link = html.escape(nome), html.escape(link, quote=True)
    return f"""<!DOCTYPE html><html><body style="margin:0;padding:24px;background:#F3F5FB;font-family:Arial,Helvetica,sans-serif;color:#0B1020">
<div style="max-width:480px;margin:0 auto;background:#FFFFFF;border:1px solid #DDE3EF;border-radius:14px;padding:28px">
<p style="margin:0 0 6px;font-weight:bold;letter-spacing:2px;color:#1F4FD8;font-size:13px">CLASS MATCH</p>
<h1 style="font-size:21px;margin:0 0 14px">Criar uma nova senha</h1>
<p style="margin:0 0 18px">Olá, {nome}! Recebemos um pedido para trocar a senha da sua conta.</p>
<p style="margin:0 0 22px"><a href="{link}" style="display:inline-block;background:#1F4FD8;color:#FFFFFF;text-decoration:none;padding:12px 24px;border-radius:999px;font-weight:bold">Redefinir minha senha</a></p>
<p style="margin:0 0 6px">Na página que abrir, digite este código:</p>
<p style="margin:0 0 22px;font-size:30px;font-weight:bold;letter-spacing:8px;font-family:'Courier New',monospace">{codigo}</p>
<p style="margin:0;color:#56607A;font-size:13px">O link e o código valem por 15 minutos e só funcionam uma vez. Se não foi você que pediu, ignore este e-mail: sua senha continua a mesma.</p>
</div></body></html>"""


def mascarar_email(email):
    usuario, _, dominio = email.partition('@')
    return f'{usuario[:2]}•••@{dominio}'


def ler_link_senha(token):
    """Confere o link do e-mail: assinatura, validade (15 min) e se o código ainda não foi usado."""
    try:
        dados = assinador_senha.loads(str(token or ''), max_age=int(CODIGO_VALIDADE.total_seconds()))
    except SignatureExpired:
        raise ErroApi(400, 'Este link venceu (vale 15 minutos). Peça um novo.') from None
    except BadSignature:
        raise ErroApi(400, 'Link inválido. Peça um novo.') from None
    if not isinstance(dados, dict) or not isinstance(dados.get('u'), int) or not isinstance(dados.get('c'), int):
        raise ErroApi(400, 'Link inválido. Peça um novo.')
    usuario = db().um('SELECT id, email_institucional, status_conta FROM usuarios WHERE id = %s', (dados['u'],))
    registro = db().um('SELECT id, codigo_hash, tentativas, expira_em FROM codigos_senha '
                       'WHERE id = %s AND usuario_id = %s AND usado = FALSE', (dados['c'], dados['u']))
    if not usuario or not registro or usuario['status_conta'] == 'banido' or como_data(registro['expira_em']) < agora():
        raise ErroApi(400, 'Este link já foi usado ou venceu. Peça um novo.')
    return usuario, registro


@app.get('/api/senha/link')
def conferir_link_senha():
    usuario, _ = ler_link_senha(request.args.get('token'))
    return jsonify({'email': mascarar_email(usuario['email_institucional'])})


@app.post('/api/senha/redefinir')
def redefinir_senha():
    """Com o token do link do e-mail (ou o e-mail digitado) + código de 6 números + senha nova."""
    dados = corpo()
    codigo = re.sub(r'\D', '', str(dados.get('codigo') or ''))[:6]
    nova = validar_senha_nova(dados.get('nova_senha'))
    if dados.get('token'):
        usuario, registro = ler_link_senha(dados.get('token'))
    else:
        email = str(dados.get('email') or '').strip().lower()[:150]
        usuario = db().um('SELECT id, status_conta FROM usuarios WHERE LOWER(email_institucional) = %s', (email,))
        registro = usuario and db().um(
            'SELECT id, codigo_hash, tentativas, expira_em FROM codigos_senha '
            'WHERE usuario_id = %s AND usado = FALSE ORDER BY id DESC LIMIT 1', (usuario['id'],))
        if not registro or usuario['status_conta'] == 'banido' or como_data(registro['expira_em']) < agora():
            raise ErroApi(400, 'Código inválido ou vencido. Peça um novo.')
    if len(codigo) != 6 or not conferir_senha(registro['codigo_hash'], codigo):
        tentativas = registro['tentativas'] + 1
        db().executar('UPDATE codigos_senha SET tentativas = %s, usado = %s WHERE id = %s',
                      (tentativas, tentativas >= CODIGO_TENTATIVAS, registro['id']))
        db().commit()
        restantes = CODIGO_TENTATIVAS - tentativas
        raise ErroApi(400, f'Código incorreto. Você ainda tem {restantes} tentativa(s).' if restantes > 0
                      else 'Código incorreto muitas vezes. Peça um novo.')
    db().executar('UPDATE usuarios SET senha_hash = %s, trocar_senha = FALSE WHERE id = %s',
                  (gerar_hash_senha(nova), usuario['id']))
    db().executar('UPDATE codigos_senha SET usado = TRUE WHERE usuario_id = %s', (usuario['id'],))
    db().commit()
    # Já entra na conta com a senha nova
    return jsonify({'mensagem': 'Senha alterada! Entrando...', 'token': criar_token(usuario['id']),
                    'usuario': publico(buscar_usuario(usuario['id']))})


@app.put('/api/senha')
@login_obrigatorio()
def trocar_senha():
    dados = corpo()
    atual = str(dados.get('senha_atual') or '')
    nova = validar_senha_nova(dados.get('nova_senha'))
    if not conferir_senha(g.usuario['senha_hash'], atual):
        raise ErroApi(400, 'A senha atual está incorreta.')
    if atual == nova:
        raise ErroApi(400, 'A nova senha precisa ser diferente da atual.')
    db().executar('UPDATE usuarios SET senha_hash = %s, trocar_senha = FALSE WHERE id = %s',
                  (gerar_hash_senha(nova), g.usuario['id']))
    db().commit()
    return jsonify({'mensagem': 'Senha alterada com sucesso!', 'usuario': publico(buscar_usuario(g.usuario['id']))})


@app.post('/api/coordenacao/redefinir-senha')
@login_obrigatorio('coordenador', 'admin')
def coordenacao_redefinir_senha():
    """Gera uma senha temporária; no próximo login a pessoa é obrigada a criar outra."""
    identificacao = str(corpo().get('identificacao') or '').strip().lower()[:150]
    if not identificacao:
        raise ErroApi(400, 'Digite o e-mail da pessoa.')
    alvo = db().um(
        """SELECT id, nome_completo, tipo_usuario FROM usuarios
           WHERE instituicao_id = %s AND LOWER(email_institucional) = %s""",
        (g.usuario['instituicao_id'], identificacao))
    if not alvo:
        raise ErroApi(404, 'Não encontrei ninguém com esse e-mail na sua escola.')
    if alvo['tipo_usuario'] in ('coordenador', 'admin'):
        raise ErroApi(403, 'Senhas da coordenação não podem ser redefinidas por aqui.')
    temporaria = ''.join(secrets.choice(LETRAS_TEMPORARIA) for _ in range(8))
    db().executar('UPDATE usuarios SET senha_hash = %s, trocar_senha = TRUE WHERE id = %s',
                  (gerar_hash_senha(temporaria), alvo['id']))
    db().executar('UPDATE codigos_senha SET usado = TRUE WHERE usuario_id = %s', (alvo['id'],))
    db().commit()
    return jsonify({'nome': alvo['nome_completo'], 'senha_temporaria': temporaria})


# ============================================================================
# CÓDIGOS POR E-MAIL: confirmar o e-mail no cadastro e confirmar a exclusão da conta
# Mesmas regras do "esqueci minha senha": 6 números, 15 minutos, uso único,
# no máximo 5 tentativas e 3 e-mails por hora para o mesmo endereço.
# ============================================================================
FINALIDADES_CODIGO = {
    'cadastro': ('Confirme seu e-mail no ClassMatch', 'Confirmar seu e-mail',
                 'Use o código abaixo para terminar de criar sua conta no ClassMatch.',
                 'Se não foi você que tentou criar uma conta, ignore este e-mail.'),
    'excluir': ('Confirme a exclusão da sua conta do ClassMatch', 'Excluir sua conta',
                'Recebemos um pedido para EXCLUIR DEFINITIVAMENTE a sua conta do ClassMatch. '
                'Para confirmar, digite o código abaixo no site.',
                'Se não foi você, NÃO passe este código para ninguém e troque a sua senha: '
                'sem o código a conta não é excluída.'),
}


def email_configurado():
    if not cfg.EMAIL_ATIVO:
        recarregar_email()
    return cfg.EMAIL_ATIVO


def enviar_codigo_email(email, finalidade, nome):
    recentes = db().um('SELECT COUNT(*) AS total FROM codigos_email '
                       'WHERE email = %s AND finalidade = %s AND data_criacao >= %s',
                       (email, finalidade, agora() - timedelta(hours=1)))['total']
    if recentes >= CODIGOS_POR_HORA:  # evita encher a caixa de alguém de e-mails
        raise ErroApi(429, 'Já mandamos vários códigos para esse e-mail na última hora. '
                           'Use o último que chegou ou tente de novo mais tarde.')
    codigo = f'{secrets.randbelow(1_000_000):06d}'
    db().executar('UPDATE codigos_email SET usado = TRUE WHERE email = %s AND finalidade = %s AND usado = FALSE',
                  (email, finalidade))
    db().inserir('INSERT INTO codigos_email (email, finalidade, codigo_hash, expira_em, data_criacao) '
                 'VALUES (%s, %s, %s, %s, %s)',
                 (email, finalidade, gerar_hash_senha(codigo), agora() + CODIGO_VALIDADE, agora()))
    assunto, titulo, explicacao, rodape = FINALIDADES_CODIGO[finalidade]
    nome = primeiro_nome(nome)
    enviar_email(email, assunto,
                 f'Olá, {nome}!\n\n{explicacao}\n\nCódigo: {codigo}\n\n'
                 f'O código vale por 15 minutos e só funciona uma vez.\n{rodape}\n\nEquipe ClassMatch',
                 email_html_codigo(nome, titulo, explicacao, codigo, rodape))
    db().commit()  # só grava o código se o e-mail saiu
    print(f'  [{finalidade}] Código enviado para {email}.')


def email_html_codigo(nome, titulo, explicacao, codigo, rodape):
    nome, titulo, explicacao, rodape = (html.escape(t) for t in (nome, titulo, explicacao, rodape))
    return f"""<!DOCTYPE html><html><body style="margin:0;padding:24px;background:#F3F5FB;font-family:Arial,Helvetica,sans-serif;color:#0B1020">
<div style="max-width:480px;margin:0 auto;background:#FFFFFF;border:1px solid #DDE3EF;border-radius:14px;padding:28px">
<p style="margin:0 0 6px;font-weight:bold;letter-spacing:2px;color:#1F4FD8;font-size:13px">CLASS MATCH</p>
<h1 style="font-size:21px;margin:0 0 14px">{titulo}</h1>
<p style="margin:0 0 18px">Olá, {nome}! {explicacao}</p>
<p style="margin:0 0 22px;font-size:30px;font-weight:bold;letter-spacing:8px;font-family:'Courier New',monospace">{codigo}</p>
<p style="margin:0;color:#56607A;font-size:13px">O código vale por 15 minutos e só funciona uma vez. {rodape}</p>
</div></body></html>"""


def conferir_codigo_email(email, finalidade, codigo_digitado):
    """Confere o último código enviado. Errou: conta a tentativa (e grava, mesmo com o erro)."""
    codigo = re.sub(r'\D', '', str(codigo_digitado or ''))[:6]
    if not codigo:
        raise ErroApi(400, 'Digite o código de 6 números que chegou no seu e-mail.')
    registro = db().um('SELECT id, codigo_hash, tentativas, expira_em FROM codigos_email '
                       'WHERE email = %s AND finalidade = %s AND usado = FALSE ORDER BY id DESC LIMIT 1',
                       (email, finalidade))
    if not registro or como_data(registro['expira_em']) < agora():
        raise ErroApi(400, 'Este código venceu ou já foi usado. Peça um novo.')
    if len(codigo) != 6 or not conferir_senha(registro['codigo_hash'], codigo):
        tentativas = registro['tentativas'] + 1
        db().executar('UPDATE codigos_email SET tentativas = %s, usado = %s WHERE id = %s',
                      (tentativas, tentativas >= CODIGO_TENTATIVAS, registro['id']))
        db().commit()
        restantes = CODIGO_TENTATIVAS - tentativas
        raise ErroApi(400, f'Código incorreto. Você ainda tem {restantes} tentativa(s).' if restantes > 0
                      else 'Código incorreto muitas vezes. Peça um novo.')
    db().executar('UPDATE codigos_email SET usado = TRUE WHERE email = %s AND finalidade = %s',
                  (email, finalidade))


# ----------------------------------------------------------------------------
# EXCLUIR A CONTA (aba Perfil): senha + código do e-mail. Apaga a conta e tudo
# que é dela: pedidos, monitorias (com o chat), aulas que dava, mensagens,
# avaliações e denúncias. Não tem volta.
# ----------------------------------------------------------------------------
def conferir_pedido_exclusao(dados):
    if g.usuario['tipo_usuario'] in TIPOS_COORDENACAO:
        raise ErroApi(403, 'Contas da coordenação não podem ser excluídas por aqui. Fale com o administrador do ClassMatch.')
    if not conferir_senha(g.usuario['senha_hash'], str(dados.get('senha') or '')):
        raise ErroApi(400, 'Senha incorreta.')


@app.post('/api/conta/excluir/codigo')
@login_obrigatorio()
def excluir_conta_codigo():
    """1º passo: confere a senha e manda o código para o e-mail da conta."""
    conferir_pedido_exclusao(corpo())
    if not email_configurado():
        print(f'  [excluir] {g.usuario["email_institucional"]}: e-mail não configurado no .env, exclusão confirmada só pela senha.')
        return jsonify({'modo': 'senha'})
    email = g.usuario['email_institucional'].lower()
    enviar_codigo_email(email, 'excluir', g.usuario['nome_completo'])
    return jsonify({'modo': 'email', 'email': mascarar_email(email),
                    'mensagem': f'Enviamos um código de 6 números para {mascarar_email(email)}.'})


@app.post('/api/conta/excluir')
@login_obrigatorio()
def excluir_conta():
    """2º passo: senha + código do e-mail -> apaga a conta para sempre."""
    dados = corpo()
    conferir_pedido_exclusao(dados)
    email = g.usuario['email_institucional'].lower()
    if email_configurado():
        conferir_codigo_email(email, 'excluir', dados.get('codigo'))
    arquivos = apagar_dados_do_usuario(g.usuario['id'])
    db().executar('DELETE FROM codigos_email WHERE email = %s', (email,))
    db().commit()
    for salvo in arquivos:  # depois do commit: se falhar, o arquivo só fica órfão
        apagar_arquivo(salvo)
    print(f'  [excluir] Conta {g.usuario["id"]} ({email}) excluída pelo próprio usuário.')
    return jsonify({'mensagem': 'Sua conta foi excluída. Sentiremos sua falta!'})


def apagar_dados_do_usuario(usuario_id):
    """Apaga a conta respeitando as chaves estrangeiras. Devolve os anexos para apagar do disco/Storage."""
    desfazer_pendencias(usuario_id)  # pedido de quem ele monitorava volta para a fila
    eu = (usuario_id, usuario_id)
    filtro_conversas = """conversa_id IN (
        SELECT c.id FROM conversas c LEFT JOIN matches mt ON mt.id = c.match_id
        LEFT JOIN aulas_grupo ag ON ag.id = c.aula_id
        WHERE mt.monitor_id = %s OR mt.aluno_id = %s OR ag.monitor_id = %s)"""
    arquivos = [linha['anexo_arquivo'] for linha in db().todos(
        f'SELECT anexo_arquivo FROM mensagens WHERE anexo_arquivo IS NOT NULL AND (remetente_id = %s OR {filtro_conversas})',
        (usuario_id, usuario_id, usuario_id, usuario_id))]
    # Quem perde avaliações (dadas por ele ou feitas nas monitorias com ele) tem a média recalculada.
    afetados = {linha['avaliado_id'] for linha in db().todos(
        """SELECT a.avaliado_id FROM avaliacoes a JOIN matches mt ON mt.id = a.match_id
           WHERE a.avaliador_id = %s OR mt.monitor_id = %s OR mt.aluno_id = %s""", (usuario_id, *eu))}
    afetados.discard(usuario_id)

    db().executar('DELETE FROM acoes_moderacao WHERE usuario_alvo_id = %s OR moderador_id = %s', eu)
    db().executar('DELETE FROM denuncias WHERE denunciante_id = %s OR denunciado_id = %s', eu)
    db().executar('DELETE FROM avaliacoes WHERE avaliador_id = %s OR avaliado_id = %s', eu)
    db().executar('DELETE FROM mensagens WHERE remetente_id = %s', (usuario_id,))
    db().executar('DELETE FROM matches WHERE monitor_id = %s OR aluno_id = %s', eu)  # leva conversas e mensagens
    db().executar('DELETE FROM aulas_grupo WHERE monitor_id = %s', (usuario_id,))  # leva inscrições e chat
    db().executar('DELETE FROM solicitacoes_ajuda WHERE aluno_id = %s', (usuario_id,))
    db().executar('DELETE FROM usuarios WHERE id = %s', (usuario_id,))  # o resto sai em cascata
    for avaliado_id in afetados:
        db().executar(
            """UPDATE usuarios SET reputacao_media = COALESCE((
                   SELECT AVG(nota) FROM avaliacoes WHERE avaliado_id = %s), 5.00)
               WHERE id = %s""", (avaliado_id, avaliado_id))
    return arquivos


# ----------------------------------------------------------------------------
# Arquivos de versões antigas (antes da v6.4): só são apagados, junto com a conta.
# "sb:conversa-12/abc.webm" = Supabase Storage; "abc.webm" = pasta backend/uploads.
# ----------------------------------------------------------------------------
def apagar_arquivo(salvo):
    if salvo.startswith('sb:'):
        if armazenamento.ativo(cfg):
            armazenamento.apagar(cfg, salvo[3:])
        return
    try:
        os.remove(os.path.join(PASTA_UPLOADS, os.path.basename(salvo)))
    except OSError:
        pass


# ============================================================================
# GOOGLE MEET (monitoria e aula em grupo)
# Só links do meet.google.com: os outros links continuam bloqueados no chat.
# ============================================================================
REGEX_MEET = re.compile(r'(?:https?://)?meet\.google\.com/([a-z]{3}-[a-z]{4}-[a-z]{3})(?:[/?#].*)?', re.IGNORECASE)


def validar_meet(valor):
    valor = str(valor or '').strip()
    if not valor:
        return None
    achou = REGEX_MEET.fullmatch(valor)
    if not achou:
        raise ErroApi(400, 'Cole um link do Google Meet, como https://meet.google.com/abc-defg-hij')
    return f'https://meet.google.com/{achou.group(1).lower()}'


@app.put('/api/matches/<int:match_id>/meet')
@login_obrigatorio(*ESTUDANTES)
def definir_meet_monitoria(match_id):
    link = validar_meet(corpo().get('link'))
    match = db().um('SELECT id, aluno_id, monitor_id, status FROM matches WHERE id = %s', (match_id,))
    if not match or g.usuario['id'] not in (match['aluno_id'], match['monitor_id']):
        raise ErroApi(404, 'Monitoria não encontrada.')
    if match['status'] != 'aceito':
        raise ErroApi(409, 'Esta monitoria já foi encerrada.')
    db().executar('UPDATE matches SET link_meet = %s WHERE id = %s', (link, match_id))
    if link:
        conversa = db().um('SELECT id FROM conversas WHERE match_id = %s', (match_id,))
        outro = match['monitor_id'] if g.usuario['id'] == match['aluno_id'] else match['aluno_id']
        notificar(outro, 'mensagem', f'{primeiro_nome(g.usuario["nome_completo"])} colocou o link do Google Meet na monitoria.',
                  f'dashboard.html#conversa-{conversa["id"]}', g.usuario['id'])
    db().commit()
    return jsonify({'link_meet': link, 'mensagem': 'Link do Meet salvo!' if link else 'Link do Meet removido.'})


# ============================================================================
# AULAS EM GRUPO: 1 monitor para vários alunos (vagas, data/hora, Meet e chat da turma)
# ============================================================================
SQL_AULA = """SELECT ag.id, ag.titulo, ag.descricao, ag.data_hora, ag.duracao_min, ag.vagas, ag.status,
                     ag.link_meet, ag.monitor_id, ag.materia_id, u.instituicao_id,
                     u.nome_completo AS monitor_nome, m.nome AS materia_nome, c.id AS conversa_id,
                     (SELECT COUNT(*) FROM inscricoes_aula i WHERE i.aula_id = ag.id) AS inscritos
              FROM aulas_grupo ag
              JOIN usuarios u ON u.id = ag.monitor_id
              JOIN materias m ON m.id = ag.materia_id
              LEFT JOIN conversas c ON c.aula_id = ag.id"""


def ler_data_hora(valor):
    try:
        return datetime.strptime(str(valor or '').strip()[:16], '%Y-%m-%dT%H:%M')
    except ValueError:
        raise ErroApi(400, 'Escolha a data e a hora da aula.') from None


def fim_da_aula(aula):
    return como_data(aula['data_hora']) + timedelta(minutes=aula['duracao_min'])


def carregar_aula(aula_id, so_monitor=False):
    aula = db().um(SQL_AULA + ' WHERE ag.id = %s', (aula_id,))
    if not aula or aula['instituicao_id'] != g.usuario['instituicao_id']:
        raise ErroApi(404, 'Aula não encontrada.')
    if so_monitor and aula['monitor_id'] != g.usuario['id']:
        raise ErroApi(403, 'Só quem dá a aula pode fazer isso.')
    return aula


def notificar_inscritos(aula_id, tipo, texto_aviso, link):
    """Aviso para toda a turma, vindo de quem dá a aula (o nome dele vira link no aviso)."""
    db().executar("""INSERT INTO notificacoes (usuario_id, tipo, texto, link, ator_id)
                     SELECT aluno_id, %s, %s, %s, %s FROM inscricoes_aula WHERE aula_id = %s""",
                  (tipo, texto_aviso[:250], link, g.usuario['id'], aula_id))


def minhas_aulas_como_conversa(eu_id):
    """Aulas que dou ou em que estou inscrito, no mesmo formato da lista de monitorias (chat)."""
    aulas = db().todos(
        SQL_AULA + """
           WHERE (ag.monitor_id = %s OR EXISTS (SELECT 1 FROM inscricoes_aula i
                                                 WHERE i.aula_id = ag.id AND i.aluno_id = %s))
             AND ag.data_hora >= %s
           ORDER BY ag.data_hora DESC LIMIT 50""",
        (eu_id, eu_id, agora() - timedelta(days=30)))
    itens = []
    for aula in aulas:
        sou_monitor = aula['monitor_id'] == eu_id
        ultima = db().um('SELECT id, remetente_id FROM mensagens WHERE conversa_id = %s ORDER BY id DESC LIMIT 1',
                         (aula['conversa_id'],))
        participantes = db().todos(
            """SELECT u.id, u.nome_completo AS nome FROM usuarios u WHERE u.id = %s
               UNION ALL
               SELECT u.id, u.nome_completo AS nome FROM inscricoes_aula i JOIN usuarios u ON u.id = i.aluno_id
               WHERE i.aula_id = %s""", (aula['monitor_id'], aula['id']))
        itens.append({
            'tipo': 'aula', 'id': None, 'aula_id': aula['id'], 'titulo': aula['titulo'],
            'materia_nome': aula['materia_nome'], 'data_hora': aula['data_hora'], 'duracao_min': aula['duracao_min'],
            'vagas': aula['vagas'], 'inscritos': aula['inscritos'], 'link_meet': aula['link_meet'],
            'status': {'aberta': 'aceito', 'concluida': 'concluido'}.get(aula['status'], 'cancelado'),
            'aula_status': aula['status'], 'monitor_id': aula['monitor_id'], 'aluno_id': None,
            'meu_papel': 'monitor' if sou_monitor else 'aluno',
            'com_quem': f'{aula["inscritos"]} inscrito(s)' if sou_monitor else f'monitor(a) {aula["monitor_nome"]}',
            'conversa_id': aula['conversa_id'], 'encerrada': aula['status'] != 'aberta', 'ja_avaliei': True,
            'nivel_dificuldade': None, 'participantes': participantes,
            'ultima_mensagem_id': ultima['id'] if ultima else None,
            'ultima_remetente_id': ultima['remetente_id'] if ultima else None,
        })
    return itens


@app.get('/api/aulas')
@login_obrigatorio(*ESTUDANTES)
def listar_aulas():
    """Aulas da escola (próximas e da última semana), com vagas e se eu participo."""
    eu_id = g.usuario['id']
    aulas = db().todos(
        SQL_AULA + """
           WHERE u.instituicao_id = %s AND ag.status <> 'cancelada' AND ag.data_hora >= %s
           ORDER BY ag.data_hora, ag.id LIMIT 100""",
        (g.usuario['instituicao_id'], agora() - timedelta(days=7)))
    minhas = {linha['aula_id'] for linha in db().todos('SELECT aula_id FROM inscricoes_aula WHERE aluno_id = %s', (eu_id,))}
    for aula in aulas:
        aula['sou_monitor'] = aula['monitor_id'] == eu_id
        aula['inscrito'] = aula['id'] in minhas
        if not (aula['sou_monitor'] or aula['inscrito']):
            aula['link_meet'] = None  # o link só aparece para quem participa
            aula['conversa_id'] = None
        aula['ja_passou'] = fim_da_aula(aula) < agora()
        aula['vagas_restantes'] = max(0, aula['vagas'] - aula['inscritos'])
        del aula['instituicao_id']
    return jsonify(aulas)


@app.post('/api/aulas')
@login_obrigatorio(*ESTUDANTES)
def criar_aula():
    dados = corpo()
    materia_id = inteiro(dados.get('materia_id'), 'Matéria')
    if not db().um('SELECT id FROM monitor_materias WHERE usuario_id = %s AND materia_id = %s AND ativo = TRUE',
                   (g.usuario['id'], materia_id)):
        raise ErroApi(400, 'Você só pode criar aulas das matérias que ensina (adicione em "Matérias que eu ensino").')
    titulo, motivos = filtrar(' '.join(texto(dados, 'titulo', 'Título', 3, 120).split()))
    descricao = texto(dados, 'descricao', 'Descrição', 0, 500)
    descricao, motivos2 = filtrar(descricao) if descricao else ('', [])
    data_hora = ler_data_hora(dados.get('data_hora'))
    if data_hora < agora() + timedelta(minutes=5):
        raise ErroApi(400, 'Escolha uma data e hora no futuro.')
    if data_hora > agora() + timedelta(days=90):
        raise ErroApi(400, 'Marque a aula para daqui a no máximo 90 dias.')
    duracao = inteiro(dados.get('duracao_min'), 'Duração')
    if not 15 <= duracao <= 240:
        raise ErroApi(400, 'A duração precisa ser de 15 minutos a 4 horas.')
    vagas = inteiro(dados.get('vagas'), 'Vagas')
    if not 2 <= vagas <= 50:
        raise ErroApi(400, 'As vagas precisam ser de 2 a 50.')
    link = validar_meet(dados.get('link_meet'))
    materia = db().um('SELECT nome FROM materias WHERE id = %s', (materia_id,))
    aula_id = db().inserir(
        """INSERT INTO aulas_grupo (monitor_id, materia_id, titulo, descricao, data_hora, duracao_min, vagas, link_meet)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (g.usuario['id'], materia_id, titulo, descricao or None, data_hora, duracao, vagas, link))
    db().inserir('INSERT INTO conversas (aula_id) VALUES (%s)', (aula_id,))
    db().executar(  # avisa quem está esperando ajuda nessa matéria
        """INSERT INTO notificacoes (usuario_id, tipo, texto, link)
           SELECT DISTINCT s.aluno_id, 'monitoria', %s, 'dashboard.html#sec-aulas'
           FROM solicitacoes_ajuda s JOIN usuarios u ON u.id = s.aluno_id
           WHERE s.materia_id = %s AND s.status = 'pendente' AND u.instituicao_id = %s AND s.aluno_id <> %s""",
        (f'Nova aula em grupo de {materia["nome"]}: "{titulo}".'[:250], materia_id,
         g.usuario['instituicao_id'], g.usuario['id']))
    db().commit()
    return jsonify({'id': aula_id, 'mensagem': 'Aula criada! Ela já aparece para os colegas.',
                    'aviso': descrever_filtro(motivos + motivos2, 'texto da aula')}), 201


@app.post('/api/aulas/<int:aula_id>/inscricao')
@login_obrigatorio(*ESTUDANTES)
def inscrever_na_aula(aula_id):
    aula = carregar_aula(aula_id)
    if aula['monitor_id'] == g.usuario['id']:
        raise ErroApi(400, 'Você é quem dá esta aula.')
    if aula['status'] != 'aberta' or fim_da_aula(aula) < agora():
        raise ErroApi(409, 'Esta aula não aceita mais inscrições.')
    if db().um('SELECT id FROM inscricoes_aula WHERE aula_id = %s AND aluno_id = %s', (aula_id, g.usuario['id'])):
        raise ErroApi(409, 'Você já está inscrito(a) nesta aula.')
    if aula['inscritos'] >= aula['vagas']:
        raise ErroApi(409, 'Esta aula já está lotada.')
    db().inserir('INSERT INTO inscricoes_aula (aula_id, aluno_id) VALUES (%s, %s)', (aula_id, g.usuario['id']))
    notificar(aula['monitor_id'], 'match',
              f'{primeiro_nome(g.usuario["nome_completo"])} entrou na sua aula "{aula["titulo"]}" '
              f'({aula["inscritos"] + 1}/{aula["vagas"]}).', f'dashboard.html#conversa-{aula["conversa_id"]}', g.usuario['id'])
    db().commit()
    return jsonify({'mensagem': 'Inscrição feita! O chat da turma está em "Minhas monitorias".',
                    'conversa_id': aula['conversa_id']}), 201


@app.delete('/api/aulas/<int:aula_id>/inscricao')
@login_obrigatorio(*ESTUDANTES)
def sair_da_aula(aula_id):
    aula = carregar_aula(aula_id)
    if aula['status'] != 'aberta':
        raise ErroApi(409, 'Esta aula já foi encerrada.')
    if not db().executar('DELETE FROM inscricoes_aula WHERE aula_id = %s AND aluno_id = %s', (aula_id, g.usuario['id'])):
        raise ErroApi(404, 'Você não está inscrito(a) nesta aula.')
    db().commit()
    return jsonify({'mensagem': 'Você saiu da aula.'})


@app.put('/api/aulas/<int:aula_id>/meet')
@login_obrigatorio(*ESTUDANTES)
def definir_meet_aula(aula_id):
    aula = carregar_aula(aula_id, so_monitor=True)
    if aula['status'] != 'aberta':
        raise ErroApi(409, 'Esta aula já foi encerrada.')
    link = validar_meet(corpo().get('link'))
    db().executar('UPDATE aulas_grupo SET link_meet = %s WHERE id = %s', (link, aula_id))
    if link:
        notificar_inscritos(aula_id, 'mensagem', f'{primeiro_nome(g.usuario["nome_completo"])} colocou o link do Google Meet da aula "{aula["titulo"]}".',
                            f'dashboard.html#conversa-{aula["conversa_id"]}')
    db().commit()
    return jsonify({'link_meet': link, 'mensagem': 'Link do Meet salvo!' if link else 'Link do Meet removido.'})


@app.post('/api/aulas/<int:aula_id>/status')
@login_obrigatorio(*ESTUDANTES)
def mudar_status_aula(aula_id):
    """Quem dá a aula pode encerrar (concluida) ou cancelar. O chat da turma fecha."""
    aula = carregar_aula(aula_id, so_monitor=True)
    novo = str(corpo().get('status') or '')
    if novo not in ('concluida', 'cancelada'):
        raise ErroApi(400, 'Status inválido.')
    if aula['status'] != 'aberta':
        raise ErroApi(409, 'Esta aula já foi encerrada.')
    db().executar('UPDATE aulas_grupo SET status = %s WHERE id = %s', (novo, aula_id))
    db().executar('UPDATE conversas SET encerrada = TRUE WHERE aula_id = %s', (aula_id,))
    nome = primeiro_nome(g.usuario['nome_completo'])
    texto_aviso = (f'{nome} cancelou a aula "{aula["titulo"]}".' if novo == 'cancelada'
                   else f'{nome} encerrou a aula "{aula["titulo"]}". Obrigado por participar!')
    notificar_inscritos(aula_id, 'monitoria', texto_aviso, 'dashboard.html#sec-aulas')
    db().commit()
    return jsonify({'mensagem': 'Aula cancelada.' if novo == 'cancelada' else 'Aula encerrada.'})


class _SemLogDePolling(logging.Filter):
    """Esconde do terminal os GETs repetitivos (atualização automática do chat)."""

    def filter(self, registro):
        linha = registro.getMessage()
        if 'OPTIONS /' in linha:
            return False
        return not ('GET /' in linha and (' 200 ' in linha or ' 304 ' in linha))


def _porta_ocupada(porta):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as teste:
        teste.settimeout(0.5)
        return teste.connect_ex(('127.0.0.1', porta)) == 0


def _classmatch_ja_rodando(porta):
    """None = não é o ClassMatch; senão devolve a versão que está rodando ('' = versão antiga)."""
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{porta}/api/saude', timeout=2) as resposta:
            dados = json.loads(resposta.read().decode('utf-8'))
            return str(dados.get('versao') or '') if dados.get('app') == 'classmatch' else None
    except Exception:
        return None


ARQUIVO_SQL = arquivo_do_script(cfg, os.path.join(config.PASTA_PROJETO, 'database'))


def _interativo():
    return bool(sys.stdin) and sys.stdin.isatty()


def _perguntar_sim(pergunta, padrao_sim=True):
    opcoes = '[S/n]' if padrao_sim else '[s/N]'
    resposta = input(f'  {pergunta} {opcoes} ').strip().lower()
    if not resposta:
        return padrao_sim
    return resposta in ('s', 'sim', 'y', 'yes')


def rodar_banco_sql():
    """Cria (ou recria) o banco rodando o database/banco.sql, sem precisar do Workbench."""
    print(f'  [banco] Rodando o database/{os.path.basename(ARQUIVO_SQL)}...')
    ok, mensagem = criar_banco(cfg, ARQUIVO_SQL)
    print(f'  [banco] {"OK: " if ok else "PROBLEMA: "}{mensagem}')
    if ok:
        print('  [banco] Contas de teste criadas (senha de todas: senha123).')
    return ok


def verificar_banco_no_inicio():
    """Testa o MySQL antes de ligar o servidor e explica (ou resolve) o que estiver errado."""
    tentativas_senha = 0
    ja_criou = False
    while True:
        try:
            conexao = conectar(cfg)
        except ErroBanco as erro:
            causa = erro.__cause__
            codigo = codigo_erro(causa) if causa is not None else None
            if codigo == 1049 and _interativo() and not ja_criou:
                print(f'  [banco] O banco "{cfg.DB_NAME}" ainda não existe neste MySQL.')
            else:
                print(f'  [banco] PROBLEMA: {erro.mensagem}')
            if codigo == 1045 and _interativo() and tentativas_senha < 3:
                tentativas_senha += 1
                nova = input('  Digite a senha correta do MySQL (ou só Enter para seguir sem banco): ')
                if nova:
                    cfg.DB_PASSWORD = nova
                    config.salvar_no_env({'DB_PASSWORD': nova})
                    print('  Senha salva no backend/.env. Testando de novo...')
                    continue
            if codigo == 1049 and _interativo() and not ja_criou:
                print()
                if _perguntar_sim(f'Quer que eu crie o banco "{cfg.DB_NAME}" agora, com o database/banco.sql?'):
                    ja_criou = True
                    if rodar_banco_sql():
                        continue
            print('  O site vai abrir, mas vai mostrar esse aviso até o banco ser corrigido.')
            return False

        atualizar_banco(conexao, cfg)  # acrescenta colunas/tabelas novas sem apagar dados
        try:
            with conexao.cursor() as cursor:
                cursor.execute('SELECT anexo_categoria FROM mensagens LIMIT 1')  # colunas novas desta versão
                cursor.execute('SELECT trocar_senha FROM usuarios LIMIT 1')
                cursor.execute('SELECT id FROM codigos_senha LIMIT 1')
                cursor.execute('SELECT bio FROM usuarios LIMIT 1')
                cursor.execute('SELECT id FROM notificacoes LIMIT 1')
                cursor.execute('SELECT COUNT(*) AS total FROM instituicoes')
                escolas = cursor.fetchone()['total']
                cursor.execute('SELECT COUNT(*) AS total FROM usuarios')
                usuarios = cursor.fetchone()['total']
        except ERROS_BANCO as erro:
            codigo = codigo_erro(erro)
            conexao.close()
            if (codigo in TABELA_FALTANDO or codigo in COLUNA_FALTANDO) and _interativo() and not ja_criou:
                vazio = cfg.DB_TIPO == 'postgres' and codigo in TABELA_FALTANDO
                if vazio:
                    print(f'  [banco] O banco "{cfg.DB_NAME}" ainda não tem as tabelas do ClassMatch.')
                    pergunta = 'Quer que eu crie as tabelas agora (com os dados de teste)?'
                else:
                    print(f'  [banco] O banco "{cfg.DB_NAME}" é de uma versão antiga do ClassMatch.')
                    pergunta = 'Recriar o banco agora? ISSO APAGA os dados que estão nele.'
                if _perguntar_sim(pergunta, padrao_sim=vazio):
                    ja_criou = True
                    if rodar_banco_sql():
                        continue
            else:
                print(f'  [banco] PROBLEMA: {traduzir_erro(erro, cfg) or erro}')
            print('  O site vai abrir, mas vai mostrar esse aviso até o banco ser corrigido.')
            return False
        conexao.close()

        print(f'  [banco] OK: {cfg.DB_NAME} ({"Supabase/PostgreSQL" if cfg.DB_TIPO == "postgres" else "MySQL"}) '
              f'em {cfg.DB_HOST}:{cfg.DB_PORT} '
              f'({escolas} escola(s), {usuarios} usuário(s))')
        if not escolas:
            print('  [banco] AVISO: nenhuma escola na tabela instituicoes; ninguém consegue se cadastrar.')
        return True


def testar_email():
    """python app.py --testar-email  (é o que o testar_email.bat faz)."""
    print()
    print('  ClassMatch — teste de envio de e-mail')
    print('  ' + '-' * 46)
    if not cfg.EMAIL_ATIVO:
        print('  O envio de e-mail ainda não está configurado.')
        print('  Preencha EMAIL_USUARIO e EMAIL_SENHA_APP no backend/.env (veja o README).')
        return
    destino = input('  Mandar um e-mail de teste para qual endereço? ').strip()
    try:
        enviar_email(destino, 'Teste do ClassMatch', 'Se você recebeu este e-mail, o envio do ClassMatch está funcionando!')
    except ErroApi as erro:
        print(f'  PROBLEMA: {erro.mensagem}')
        return
    print('  Enviado! Confira a caixa de entrada (e o spam).')


def modo_criar_banco():
    """python app.py --criar-banco  (é o que o criar_banco.bat faz)."""
    print()
    print('  ClassMatch — criar o banco de dados')
    print('  ' + '-' * 46)
    print(f'  MySQL: {cfg.DB_USER}@{cfg.DB_HOST}:{cfg.DB_PORT}   banco: {cfg.DB_NAME}')
    print(f'  Isso APAGA o banco "{cfg.DB_NAME}" (se existir) e cria de novo com os dados de teste.')
    if _interativo() and not _perguntar_sim('Continuar?'):
        print('  Nada foi feito.')
        return 1
    while True:
        print('  [banco] Rodando o database/banco.sql...')
        ok, mensagem = criar_banco(cfg, ARQUIVO_SQL)
        print(f'  [banco] {"OK: " if ok else "PROBLEMA: "}{mensagem}')
        if ok:
            print('  Contas de teste criadas (senha de todas: senha123).')
            print('  Pronto! Agora é só abrir o iniciar.bat.')
            return 0
        if 'recusou o usuário' in mensagem and _interativo():
            nova = input('  Digite a senha correta do MySQL (ou só Enter para sair): ')
            if nova:
                cfg.DB_PASSWORD = nova
                config.salvar_no_env({'DB_PASSWORD': nova})
                continue
        return 1


def main():
    if '--testar-email' in sys.argv:
        testar_email()
        return
    if '--criar-banco' in sys.argv:
        sys.exit(modo_criar_banco())

    abrir_navegador = '--abrir' in sys.argv
    endereco = f'http://127.0.0.1:{cfg.PORTA}'

    print()
    print(f'  ClassMatch v{VERSAO} — backend Flask')
    print('  ' + '-' * 46)

    if _porta_ocupada(cfg.PORTA):
        rodando = _classmatch_ja_rodando(cfg.PORTA)
        if rodando == VERSAO:
            print(f'  O ClassMatch JÁ está rodando em outra janela ({endereco}).')
            if abrir_navegador:
                webbrowser.open(endereco)
            return
        if rodando is not None:  # outra janela com uma versão ANTIGA ocupando a porta
            print('  ATENÇÃO: tem uma versão ANTIGA do ClassMatch aberta em outra janela preta.')
            print('  Por isso o site não muda. Feche TODAS as janelas pretas do ClassMatch')
            print('  (olhe a barra de tarefas) e abra este INICIAR.bat de novo.')
            sys.exit(1)
        print(f'  ERRO: a porta {cfg.PORTA} está ocupada por outro programa.')
        print('  Feche esse programa ou coloque PORTA=5001 no backend/.env.')
        if sys.platform == 'darwin':
            print('  (No Mac, a porta 5000 costuma ser do "Receptor AirPlay".)')
        sys.exit(1)

    verificar_banco_no_inicio()
    print('  ' + '-' * 46)
    print(f'  Site no ar:  {endereco}')
    print('  Deixe esta janela aberta. Para desligar: Ctrl+C (ou feche a janela).')
    print()

    logging.getLogger('werkzeug').addFilter(_SemLogDePolling())
    if abrir_navegador:
        threading.Timer(1.2, lambda: webbrowser.open(endereco)).start()
    print('  [chat] Só mensagens de texto (envio de arquivos e áudios desativado).')
    os.environ['FLASK_SKIP_DOTENV'] = '1'  # o .env já é lido pelo config.py (evita o aviso do python-dotenv)
    import flask.cli
    flask.cli.show_server_banner = lambda *args, **kwargs: None  # tira o aviso em inglês; o nosso já aparece acima
    app.run(host=cfg.HOST, port=cfg.PORTA, debug=False, use_reloader=False, threaded=True)


if __name__ == '__main__':
    main()
