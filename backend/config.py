"""
Configuração do backend: lê o arquivo backend/.env.

Não usamos mais o python-dotenv: este leitor próprio aceita .env salvo pelo
Bloco de Notas (com BOM), com aspas, com espaços e até o erro clássico do
Windows de salvar como ".env.txt". Se o .env não existir, o terminal pergunta
usuário e senha do MySQL e cria o arquivo sozinho.
"""
import os
import urllib.parse
import secrets
import sys

PASTA_BACKEND = os.path.dirname(os.path.abspath(__file__))
PASTA_PROJETO = os.path.dirname(PASTA_BACKEND)
PASTA_FRONTEND = os.path.join(PASTA_PROJETO, 'frontend')
ARQUIVO_ENV = os.path.join(PASTA_BACKEND, '.env')
ARQUIVO_CHAVE = os.path.join(PASTA_BACKEND, '.chave_secreta')
# Na Vercel não existe .env nem disco gravável: os dados vêm das "Environment Variables" do projeto.
NA_VERCEL = bool(os.environ.get('VERCEL'))
CHAVES_DO_AMBIENTE = (
    'DB_TIPO', 'DB_HOST', 'DB_PORT', 'DB_USER', 'DB_PASSWORD', 'DB_NAME', 'DB_FUSO', 'PORTA',
    'SECRET_KEY', 'UPLOAD_MAX_MB', 'EMAIL_USUARIO', 'EMAIL_SENHA_APP', 'EMAIL_SERVIDOR', 'EMAIL_PORTA',
    'SITE_URL', 'SUPABASE_URL', 'SUPABASE_CHAVE_SECRETA', 'SUPABASE_BUCKET',
)

SENHAS_DE_EXEMPLO = {'sua_senha_aqui', 'sua_senha_real_aqui', 'SUA_SENHA_AQUI'}


class Config:
    # Valores padrão (MySQL no próprio computador). Os dados reais ficam SÓ no backend/.env.
    DB_TIPO = 'mysql'              # 'mysql' ou 'postgres' (Supabase)
    DB_HOST = '127.0.0.1'
    DB_PORT = 3306
    DB_USER = 'root'
    DB_PASSWORD = ''
    DB_NAME = 'classmatch_db'
    DB_FUSO = 'America/Sao_Paulo'  # horário das mensagens quando o banco está na nuvem
    HOST = '127.0.0.1'
    PORTA = 5000
    SECRET_KEY = ''
    UPLOAD_MAX_MB = 10
    # E-mail que envia o código do "Esqueci minha senha" (Gmail com "senha de app").
    EMAIL_USUARIO = ''
    EMAIL_SENHA_APP = ''
    EMAIL_SERVIDOR = 'smtp.gmail.com'
    EMAIL_PORTA = 587
    EMAIL_ATIVO = False
    SITE_URL = ''
    # Supabase Storage (anexos e áudios do chat na nuvem). Vazio = salva em backend/uploads.
    SUPABASE_URL = ''
    SUPABASE_CHAVE_SECRETA = ''
    SUPABASE_BUCKET = 'anexos'


def ler_env(caminho):
    """Transforma as linhas CHAVE=valor do arquivo em um dicionário."""
    try:
        with open(caminho, encoding='utf-8-sig') as arquivo:
            linhas = arquivo.read().splitlines()
    except UnicodeDecodeError:
        with open(caminho, encoding='latin-1') as arquivo:
            linhas = arquivo.read().splitlines()

    valores = {}
    for linha in linhas:
        linha = linha.strip()
        if not linha or linha.startswith('#') or '=' not in linha:
            continue
        chave, valor = linha.split('=', 1)
        chave = chave.strip()
        if chave.lower().startswith('export '):
            chave = chave[7:].strip()
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in '"\'':
            valor = valor[1:-1]
        valores[chave] = valor
    return valores


def salvar_no_env(novos_valores):
    """Atualiza (ou cria) chaves no backend/.env sem apagar as outras linhas."""
    linhas = []
    if os.path.exists(ARQUIVO_ENV):
        with open(ARQUIVO_ENV, encoding='utf-8-sig') as arquivo:
            linhas = arquivo.read().splitlines()

    pendentes = dict(novos_valores)
    for i, linha in enumerate(linhas):
        chave = linha.split('=', 1)[0].strip() if '=' in linha else None
        if chave in pendentes:
            linhas[i] = f'{chave}={pendentes.pop(chave)}'
    if not linhas:
        linhas.append('# Dados do banco usados pelo backend do ClassMatch. NUNCA envie este arquivo para o GitHub.')
    for chave, valor in pendentes.items():
        linhas.append(f'{chave}={valor}')

    with open(ARQUIVO_ENV, 'w', encoding='utf-8', newline='\n') as arquivo:
        arquivo.write('\n'.join(linhas) + '\n')


def _perguntar_dados_do_mysql():
    """Primeira vez sem backend/.env: pergunta qual banco usar e cria o arquivo."""
    print()
    print('  Primeira vez rodando o ClassMatch nesta pasta (não achei o backend/.env).')
    print('  Dica: se você já tem um .env de outra pasta, feche esta janela e copie ele para cá.')
    print()
    print('  Qual banco você vai usar?')
    print('    1 - Supabase (na nuvem)')
    print('    2 - MySQL (instalado neste computador, com o Workbench)')
    escolha = input('  Digite 1 ou 2 [1]: ').strip() or '1'
    if escolha == '2':
        usuario = input('  Usuário do MySQL [root]: ').strip() or 'root'
        senha = input('  Senha do MySQL: ').strip()
        salvar_no_env({
            'DB_TIPO': 'mysql',
            'DB_HOST': '127.0.0.1',
            'DB_PORT': '3306',
            'DB_USER': usuario,
            'DB_PASSWORD': senha,
            'DB_NAME': 'classmatch_db',
        })
    else:
        print()
        print('  No site do Supabase: abra o projeto > botão "Connect" > "Session pooler".')
        host = input('  Host [aws-0-sa-east-1.pooler.supabase.com]: ').strip() or 'aws-0-sa-east-1.pooler.supabase.com'
        usuario = ''
        while not usuario:
            usuario = input('  Usuário (começa com "postgres."): ').strip()
        senha = input('  Senha do banco no Supabase: ').strip()
        salvar_no_env({
            'DB_TIPO': 'postgres',
            'DB_HOST': host,
            'DB_PORT': '5432',
            'DB_USER': usuario,
            'DB_PASSWORD': senha,
            'DB_NAME': 'postgres',
            'DB_FUSO': 'America/Sao_Paulo',
        })
    print('  Pronto! Salvei em backend/.env (você pode editar esse arquivo depois).')
    print()


def _chave_secreta(valores):
    """Chave que assina os tokens de login. Fica salva para o login sobreviver a reinícios."""
    if valores.get('SECRET_KEY'):
        return valores['SECRET_KEY']
    if NA_VERCEL:
        # Cada instância da Vercel geraria uma chave diferente e o login cairia sozinho.
        print('AVISO: falta a variável SECRET_KEY na Vercel. Os logins vão cair a toda hora.')
        return secrets.token_hex(32)
    try:
        if os.path.exists(ARQUIVO_CHAVE):
            with open(ARQUIVO_CHAVE, encoding='utf-8') as arquivo:
                chave = arquivo.read().strip()
            if chave:
                return chave
        chave = secrets.token_hex(32)
        with open(ARQUIVO_CHAVE, 'w', encoding='utf-8') as arquivo:
            arquivo.write(chave)
        return chave
    except OSError:
        # Pasta sem permissão de escrita: funciona, mas todos saem da conta ao reiniciar.
        return secrets.token_hex(32)


def carregar():
    """Lê o .env e devolve um objeto Config pronto para usar."""
    arquivo = ARQUIVO_ENV
    if not os.path.exists(arquivo) and os.path.exists(arquivo + '.txt'):
        print('AVISO: achei "backend/.env.txt". O Bloco de Notas colocou ".txt" no final;')
        print('       vou usar mesmo assim, mas o ideal é renomear para ".env".')
        arquivo = arquivo + '.txt'

    if not os.path.exists(arquivo) and not NA_VERCEL:
        if sys.stdin and sys.stdin.isatty():
            _perguntar_dados_do_mysql()
        else:
            print('AVISO: backend/.env não existe. Usando root sem senha.')
            print('       Copie .env.example para .env e coloque a senha do seu MySQL.')

    valores = ler_env(arquivo) if os.path.exists(arquivo) else {}
    # Variáveis de ambiente (as da Vercel) valem mais que o .env.
    valores.update({chave: os.environ[chave] for chave in CHAVES_DO_AMBIENTE if os.environ.get(chave)})

    cfg = Config()
    cfg.DB_HOST = valores.get('DB_HOST', cfg.DB_HOST) or cfg.DB_HOST
    cfg.DB_USER = valores.get('DB_USER', cfg.DB_USER) or cfg.DB_USER
    cfg.DB_PASSWORD = valores.get('DB_PASSWORD', cfg.DB_PASSWORD)
    cfg.DB_NAME = valores.get('DB_NAME', cfg.DB_NAME) or cfg.DB_NAME
    cfg.HOST = valores.get('HOST', cfg.HOST) or cfg.HOST
    try:
        cfg.DB_PORT = int(valores.get('DB_PORT', cfg.DB_PORT))
    except ValueError:
        print('AVISO: DB_PORT inválido no .env; usando 3306.')
    try:
        cfg.PORTA = int(valores.get('PORTA', cfg.PORTA))
    except ValueError:
        print('AVISO: PORTA inválida no .env; usando 5000.')

    # "localhost" às vezes tenta IPv6 no Windows e demora/falha; 127.0.0.1 é certeiro.
    if cfg.DB_HOST.lower() == 'localhost':
        cfg.DB_HOST = '127.0.0.1'

    if cfg.DB_PASSWORD in SENHAS_DE_EXEMPLO:
        print('AVISO: o backend/.env ainda está com a senha de exemplo.')
        print('       Troque DB_PASSWORD pela senha real do seu banco.')

    # Qual banco: DB_TIPO no .env, ou descobre pela porta/endereço (Supabase = PostgreSQL).
    tipo = (valores.get('DB_TIPO') or '').strip().lower()
    if tipo in ('postgresql', 'supabase'):
        tipo = 'postgres'
    if tipo not in ('mysql', 'postgres'):
        tipo = 'postgres' if (cfg.DB_PORT in (5432, 6543) or 'supabase' in cfg.DB_HOST.lower()) else 'mysql'
    cfg.DB_TIPO = tipo
    cfg.DB_FUSO = (valores.get('DB_FUSO') or cfg.DB_FUSO).strip()
    try:
        cfg.UPLOAD_MAX_MB = max(1, min(25, int(valores.get('UPLOAD_MAX_MB', cfg.UPLOAD_MAX_MB))))
    except ValueError:
        pass

    cfg.EMAIL_USUARIO = (valores.get('EMAIL_USUARIO') or '').strip()
    cfg.EMAIL_SENHA_APP = (valores.get('EMAIL_SENHA_APP') or '').replace(' ', '')  # o Google mostra com espaços
    cfg.EMAIL_SERVIDOR = (valores.get('EMAIL_SERVIDOR') or cfg.EMAIL_SERVIDOR).strip()
    try:
        cfg.EMAIL_PORTA = int(valores.get('EMAIL_PORTA', cfg.EMAIL_PORTA))
    except ValueError:
        pass
    cfg.EMAIL_ATIVO = bool(cfg.EMAIL_USUARIO and cfg.EMAIL_SENHA_APP)
    # Endereço do site usado no link do e-mail (mude se o site estiver em outro endereço)
    site_padrao = f'http://127.0.0.1:{cfg.PORTA}'
    if NA_VERCEL and os.environ.get('VERCEL_PROJECT_PRODUCTION_URL'):
        site_padrao = 'https://' + os.environ['VERCEL_PROJECT_PRODUCTION_URL']
    cfg.SITE_URL = (valores.get('SITE_URL') or site_padrao).strip().rstrip('/')

    # Aceita o endereço do projeto com ou sem /rest/v1 no final (fica só https://xxxx.supabase.co)
    url = (valores.get('SUPABASE_URL') or '').strip()
    if url:
        partes = urllib.parse.urlsplit(url if '://' in url else 'https://' + url)
        url = f'{partes.scheme}://{partes.netloc}'
    cfg.SUPABASE_URL = url
    cfg.SUPABASE_CHAVE_SECRETA = (valores.get('SUPABASE_CHAVE_SECRETA') or '').strip()
    cfg.SUPABASE_BUCKET = (valores.get('SUPABASE_BUCKET') or cfg.SUPABASE_BUCKET).strip()

    cfg.SECRET_KEY = _chave_secreta(valores)
    return cfg
