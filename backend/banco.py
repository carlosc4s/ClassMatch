"""
banco.py — acesso ao banco de dados do ClassMatch.

Funciona com os dois bancos, escolhido pelo backend/.env (config.DB_TIPO):
  - MySQL      (no computador, com o Workbench)  -> biblioteca PyMySQL
  - PostgreSQL (Supabase, na nuvem)              -> biblioteca psycopg2
As duas usam %s nos parâmetros, então o SQL do app.py é o mesmo para as duas.
"""
import os

try:
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError:  # só é obrigatório quando DB_TIPO=mysql
    pymysql = None
try:
    import psycopg2
    import psycopg2.extras
except ImportError:  # só é obrigatório quando DB_TIPO=postgres
    psycopg2 = None


class ErroApi(Exception):
    """Erro "esperado": o app.py transforma em resposta JSON {"erro": "..."}."""

    def __init__(self, status, mensagem):
        super().__init__(mensagem)
        self.status = status
        self.mensagem = mensagem


class ErroBanco(ErroApi):
    """Problema de conexão/estrutura do banco (responde 503)."""

    def __init__(self, mensagem):
        super().__init__(503, mensagem)


# Exceções dos dois drivers (para "except ERROS_BANCO")
ERROS_BANCO = tuple(t for t in (
    RuntimeError,
    pymysql.err.MySQLError if pymysql else None,
    psycopg2.Error if psycopg2 else None,
) if t)

# Códigos equivalentes: MySQL (número) e PostgreSQL (SQLSTATE)
DUPLICADO = {1062, '23505'}
CHAVE_ESTRANGEIRA = {1452, '23503'}
VALOR_INVALIDO = {3819, 1406, '23514', '22001'}
TABELA_FALTANDO = {1146, '42P01'}
COLUNA_FALTANDO = {1054, '42703'}


def codigo_erro(erro):
    if psycopg2 is not None and isinstance(erro, psycopg2.Error):
        return erro.pgcode
    args = getattr(erro, 'args', None)
    return args[0] if args else None


def traduzir_erro(erro, cfg):
    """Mensagem amigável para os erros de configuração mais comuns (ou None)."""
    if isinstance(erro, RuntimeError) and 'cryptography' in str(erro):
        return ('O MySQL 8 pediu a biblioteca "cryptography" para o login e ela não carregou. '
                'Rode o backend/instalar.bat de novo; se o computador bloquear essa biblioteca, '
                'veja "Computador da escola" no README.md.')
    codigo = codigo_erro(erro)
    if codigo in TABELA_FALTANDO or codigo in COLUNA_FALTANDO:
        return ('O banco está sem as tabelas desta versão do ClassMatch. Feche a janela do servidor e '
                'rode o backend/criar_banco.bat (apaga os dados de teste antigos).')

    if psycopg2 is not None and isinstance(erro, psycopg2.Error):
        texto = str(erro).lower()
        if 'tenant identifier' in texto or 'enoidentifier' in texto:
            return (f'O Supabase não reconheceu o usuário "{cfg.DB_USER}". No pooler ele precisa ser '
                    '"postgres.ID_DO_PROJETO" (no site do Supabase: Connect > Session pooler, campo user). '
                    'Corrija o DB_USER no backend/.env ou nas variáveis da Vercel (e faça Redeploy).')
        if 'password authentication failed' in texto or 'tenant or user not found' in texto:
            return ('O Supabase recusou o usuário/senha do backend/.env. Confira DB_USER e DB_PASSWORD '
                    '(no site do Supabase: Connect > Session pooler).')
        if 'could not translate host name' in texto or 'name or service not known' in texto:
            return ('Não encontrei o servidor do banco (DB_HOST). Confira o endereço no backend/.env '
                    'e se o computador está com internet.')
        if 'timeout' in texto or 'could not connect' in texto or 'connection refused' in texto:
            return ('Não consegui conectar ao Supabase. Confira a internet: redes de escola às vezes '
                    'bloqueiam a porta 5432 (teste no roteador do celular).')
        return None

    mensagens = {
        1044: f'O usuário "{cfg.DB_USER}" não tem permissão no banco "{cfg.DB_NAME}".',
        1045: (f'O MySQL recusou o usuário "{cfg.DB_USER}" com a senha do backend/.env. '
               'Confira DB_USER e DB_PASSWORD nesse arquivo e reinicie o servidor.'),
        1049: (f'O banco "{cfg.DB_NAME}" ainda não foi criado. Feche a janela do servidor e abra o '
               'backend/iniciar.bat de novo: ele pergunta se pode criar o banco sozinho.'),
        2003: (f'Não consegui conectar ao MySQL em {cfg.DB_HOST}:{cfg.DB_PORT}. '
               'O MySQL está ligado? (serviço MySQL80 no Windows, ou Start no XAMPP)'),
        2005: f'Endereço do MySQL inválido: "{cfg.DB_HOST}". Confira DB_HOST no backend/.env.',
        2006: 'A conexão com o MySQL caiu. Tente de novo.',
        2013: 'A conexão com o MySQL caiu no meio da consulta. Tente de novo.',
    }
    return mensagens.get(codigo)


def conectar(cfg):
    """Abre uma conexão nova. Erros de configuração viram ErroBanco com a explicação."""
    try:
        if cfg.DB_TIPO == 'postgres':
            if psycopg2 is None:
                raise ErroBanco('Falta a biblioteca psycopg2 (usada com o Supabase). Rode o backend/instalar.bat.')
            conexao = psycopg2.connect(
                host=cfg.DB_HOST, port=cfg.DB_PORT, user=cfg.DB_USER, password=cfg.DB_PASSWORD,
                dbname=cfg.DB_NAME, connect_timeout=8, application_name='classmatch',
                cursor_factory=psycopg2.extras.RealDictCursor,
            )
            if cfg.DB_FUSO:  # o servidor do Supabase fica em UTC; mostramos o horário do Brasil
                with conexao.cursor() as cursor:
                    cursor.execute('SET TIME ZONE %s', (cfg.DB_FUSO,))
                conexao.commit()
            return conexao
        if pymysql is None:
            raise ErroBanco('Falta a biblioteca PyMySQL. Rode o backend/instalar.bat.')
        return pymysql.connect(
            host=cfg.DB_HOST, port=cfg.DB_PORT, user=cfg.DB_USER, password=cfg.DB_PASSWORD,
            database=cfg.DB_NAME, charset='utf8mb4', cursorclass=DictCursor,
            autocommit=False, connect_timeout=5,
        )
    except ERROS_BANCO as erro:
        raise ErroBanco(traduzir_erro(erro, cfg) or f'Erro ao conectar no banco: {erro}') from erro


class Banco:
    """Uma conexão por requisição. Tudo que não recebeu commit() é desfeito no final."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.postgres = cfg.DB_TIPO == 'postgres'
        self.conexao = conectar(cfg)

    def _rodar(self, sql, parametros=()):
        cursor = self.conexao.cursor()
        try:
            cursor.execute(sql, parametros or None)
        except ERROS_BANCO as erro:
            if self.postgres:  # no PostgreSQL um erro "trava" a transação até o rollback
                self.conexao.rollback()
            codigo = codigo_erro(erro)
            if codigo in DUPLICADO:
                raise ErroApi(409, 'Esse registro já existe.') from erro
            if codigo in CHAVE_ESTRANGEIRA:
                raise ErroApi(400, 'Referência inválida: o registro relacionado não existe.') from erro
            if codigo in VALOR_INVALIDO:
                raise ErroApi(400, 'Algum valor está fora do permitido.') from erro
            mensagem = traduzir_erro(erro, self.cfg)
            if mensagem:
                raise ErroBanco(mensagem) from erro
            raise
        return cursor

    def todos(self, sql, parametros=()):
        return [dict(linha) for linha in self._rodar(sql, parametros).fetchall()]

    def um(self, sql, parametros=()):
        linha = self._rodar(sql, parametros).fetchone()
        return dict(linha) if linha else None

    def inserir(self, sql, parametros=()):
        """INSERT que devolve o id novo (lastrowid no MySQL, RETURNING id no PostgreSQL)."""
        if self.postgres:
            if 'RETURNING' not in sql.upper():
                sql = sql.rstrip().rstrip(';') + ' RETURNING id'
            linha = self._rodar(sql, parametros).fetchone()
            return linha['id'] if linha else None
        return self._rodar(sql, parametros).lastrowid

    def executar(self, sql, parametros=()):
        return self._rodar(sql, parametros).rowcount

    def commit(self):
        self.conexao.commit()

    def rollback(self):
        try:
            self.conexao.rollback()
        except ERROS_BANCO:
            pass

    def fechar(self):
        try:
            self.conexao.close()
        except ERROS_BANCO:
            pass


# ----------------------------------------------------------------------------
# CRIAR O BANCO SEM O WORKBENCH / SEM O SQL EDITOR DO SUPABASE
# ----------------------------------------------------------------------------
def dividir_script(texto):
    """Separa um arquivo .sql em comandos, ignorando comentários e ';' dentro de textos."""
    comandos, atual = [], []
    aspas = None
    i, n = 0, len(texto)
    while i < n:
        c = texto[i]
        if aspas:
            atual.append(c)
            if c == '\\' and i + 1 < n:
                atual.append(texto[i + 1])
                i += 2
                continue
            if c == aspas:
                aspas = None
        elif texto.startswith('--', i) or c == '#':
            fim = texto.find('\n', i)
            i = n if fim < 0 else fim
            continue
        elif texto.startswith('/*', i):
            fim = texto.find('*/', i + 2)
            i = n if fim < 0 else fim + 2
            continue
        elif c in ('\'', '"', '`'):
            aspas = c
            atual.append(c)
        elif c == ';':
            comando = ''.join(atual).strip()
            if comando:
                comandos.append(comando)
            atual = []
        else:
            atual.append(c)
        i += 1
    resto = ''.join(atual).strip()
    if resto:
        comandos.append(resto)
    return comandos


def arquivo_do_script(cfg, pasta_database):
    nome = 'banco_postgres.sql' if cfg.DB_TIPO == 'postgres' else 'banco.sql'
    return os.path.join(pasta_database, nome)


def criar_banco(cfg, caminho_script):
    """Apaga e recria o banco rodando o script. Devolve (ok, mensagem)."""
    try:
        with open(caminho_script, encoding='utf-8-sig') as arquivo:
            script = arquivo.read()
    except OSError:
        return False, f'Não achei o arquivo {caminho_script}.'

    if cfg.DB_TIPO == 'postgres':
        try:
            conexao = conectar(cfg)
        except ErroBanco as erro:
            return False, erro.mensagem
        try:
            with conexao.cursor() as cursor:
                cursor.execute(script)  # o PostgreSQL aceita o script inteiro de uma vez
            conexao.commit()
        except ERROS_BANCO as erro:
            conexao.rollback()
            return False, f'O PostgreSQL recusou o banco_postgres.sql: {str(erro).strip()}'
        finally:
            conexao.close()
        return True, f'Tabelas do ClassMatch criadas no banco "{cfg.DB_NAME}" (Supabase/PostgreSQL).'

    if pymysql is None:
        return False, 'Falta a biblioteca PyMySQL. Rode o backend/instalar.bat.'
    if cfg.DB_NAME != 'classmatch_db':  # respeita um DB_NAME diferente no .env
        script = script.replace('classmatch_db', cfg.DB_NAME)
    comandos = dividir_script(script)
    try:
        conexao = pymysql.connect(host=cfg.DB_HOST, port=cfg.DB_PORT, user=cfg.DB_USER,
                                  password=cfg.DB_PASSWORD, charset='utf8mb4',
                                  autocommit=True, connect_timeout=5)
    except ERROS_BANCO as erro:
        return False, traduzir_erro(erro, cfg) or f'Erro ao conectar no MySQL: {erro}'
    try:
        with conexao.cursor() as cursor:
            for numero, comando in enumerate(comandos, start=1):
                try:
                    cursor.execute(comando)
                    cursor.fetchall()
                except ERROS_BANCO as erro:
                    trecho = ' '.join(comando.split())[:90]
                    return False, (f'O MySQL recusou o comando {numero} de {len(comandos)} do banco.sql: '
                                   f'{erro.args[-1] if erro.args else erro}\n           Comando: {trecho}...')
    finally:
        conexao.close()
    return True, f'Banco "{cfg.DB_NAME}" criado ({len(comandos)} comandos do banco.sql).'


# ----------------------------------------------------------------------------
# ATUALIZAÇÃO AUTOMÁTICA: acrescenta o que as versões novas precisam, SEM apagar dados.
# Roda toda vez que o servidor liga; o que já existe é simplesmente ignorado.
# ----------------------------------------------------------------------------
ATUALIZACOES = {
    'mysql': [
        'ALTER TABLE usuarios ADD COLUMN trocar_senha BOOLEAN NOT NULL DEFAULT FALSE',
        """CREATE TABLE IF NOT EXISTS codigos_senha (
               id INT AUTO_INCREMENT PRIMARY KEY, usuario_id INT NOT NULL,
               codigo_hash VARCHAR(255) NOT NULL, tentativas SMALLINT NOT NULL DEFAULT 0,
               usado BOOLEAN NOT NULL DEFAULT FALSE, expira_em TIMESTAMP NOT NULL, data_criacao TIMESTAMP NOT NULL,
               CONSTRAINT fk_codigo_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
           ) ENGINE=InnoDB""",
        # v6: sem RA, Meet, aulas em grupo
        'ALTER TABLE usuarios DROP INDEX uk_instituicao_ra',
        'ALTER TABLE usuarios DROP COLUMN ra_matricula',
        'ALTER TABLE matches ADD COLUMN link_meet VARCHAR(120) NULL',
        """CREATE TABLE IF NOT EXISTS aulas_grupo (
               id INT AUTO_INCREMENT PRIMARY KEY, monitor_id INT NOT NULL, materia_id INT NOT NULL,
               titulo VARCHAR(120) NOT NULL, descricao VARCHAR(500) NULL, data_hora TIMESTAMP NOT NULL,
               duracao_min SMALLINT NOT NULL DEFAULT 60, vagas SMALLINT NOT NULL CHECK (vagas BETWEEN 2 AND 50),
               link_meet VARCHAR(120) NULL,
               status VARCHAR(20) NOT NULL DEFAULT 'aberta' CHECK (status IN ('aberta','concluida','cancelada')),
               data_criacao TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
               CONSTRAINT fk_aula_monitor FOREIGN KEY (monitor_id) REFERENCES usuarios(id),
               CONSTRAINT fk_aula_materia FOREIGN KEY (materia_id) REFERENCES materias(id)
           ) ENGINE=InnoDB""",
        """CREATE TABLE IF NOT EXISTS inscricoes_aula (
               id INT AUTO_INCREMENT PRIMARY KEY, aula_id INT NOT NULL, aluno_id INT NOT NULL,
               data_inscricao TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
               CONSTRAINT uq_inscricao UNIQUE (aula_id, aluno_id),
               CONSTRAINT fk_inscricao_aula FOREIGN KEY (aula_id) REFERENCES aulas_grupo(id) ON DELETE CASCADE,
               CONSTRAINT fk_inscricao_aluno FOREIGN KEY (aluno_id) REFERENCES usuarios(id) ON DELETE CASCADE
           ) ENGINE=InnoDB""",
        'ALTER TABLE conversas MODIFY match_id INT NULL',
        'ALTER TABLE conversas ADD COLUMN aula_id INT NULL UNIQUE',
        'ALTER TABLE conversas ADD CONSTRAINT fk_conversa_aula FOREIGN KEY (aula_id) REFERENCES aulas_grupo(id) ON DELETE CASCADE',
        # v6.3: busca de usuários, confirmação de e-mail, excluir conta, nome clicável nas notificações
        'ALTER TABLE notificacoes ADD COLUMN ator_id INT NULL',
        'ALTER TABLE notificacoes ADD CONSTRAINT fk_notif_ator FOREIGN KEY (ator_id) REFERENCES usuarios(id) ON DELETE SET NULL',
        """CREATE TABLE IF NOT EXISTS codigos_email (
               id INT AUTO_INCREMENT PRIMARY KEY, email VARCHAR(150) NOT NULL,
               finalidade VARCHAR(20) NOT NULL CHECK (finalidade IN ('cadastro','excluir')),
               codigo_hash VARCHAR(255) NOT NULL, tentativas SMALLINT NOT NULL DEFAULT 0,
               usado BOOLEAN NOT NULL DEFAULT FALSE, expira_em TIMESTAMP NOT NULL, data_criacao TIMESTAMP NOT NULL
           ) ENGINE=InnoDB""",
        'CREATE INDEX idx_codigos_email ON codigos_email(email, finalidade)',
    ],
    'postgres': [
        'ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS trocar_senha BOOLEAN NOT NULL DEFAULT FALSE',
        """CREATE TABLE IF NOT EXISTS codigos_senha (
               id SERIAL PRIMARY KEY, usuario_id INT NOT NULL,
               codigo_hash VARCHAR(255) NOT NULL, tentativas SMALLINT NOT NULL DEFAULT 0,
               usado BOOLEAN NOT NULL DEFAULT FALSE, expira_em TIMESTAMP NOT NULL, data_criacao TIMESTAMP NOT NULL,
               CONSTRAINT fk_codigo_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
           )""",
        'ALTER TABLE codigos_senha ENABLE ROW LEVEL SECURITY',
        # v6: sem RA, Meet, aulas em grupo
        'ALTER TABLE usuarios DROP COLUMN IF EXISTS ra_matricula',
        'ALTER TABLE matches ADD COLUMN IF NOT EXISTS link_meet VARCHAR(120) NULL',
        """CREATE TABLE IF NOT EXISTS aulas_grupo (
               id SERIAL PRIMARY KEY, monitor_id INT NOT NULL REFERENCES usuarios(id),
               materia_id INT NOT NULL REFERENCES materias(id),
               titulo VARCHAR(120) NOT NULL, descricao VARCHAR(500) NULL, data_hora TIMESTAMP NOT NULL,
               duracao_min SMALLINT NOT NULL DEFAULT 60, vagas SMALLINT NOT NULL CHECK (vagas BETWEEN 2 AND 50),
               link_meet VARCHAR(120) NULL,
               status VARCHAR(20) NOT NULL DEFAULT 'aberta' CHECK (status IN ('aberta','concluida','cancelada')),
               data_criacao TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
           )""",
        """CREATE TABLE IF NOT EXISTS inscricoes_aula (
               id SERIAL PRIMARY KEY, aula_id INT NOT NULL REFERENCES aulas_grupo(id) ON DELETE CASCADE,
               aluno_id INT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
               data_inscricao TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
               CONSTRAINT uq_inscricao UNIQUE (aula_id, aluno_id)
           )""",
        'ALTER TABLE aulas_grupo ENABLE ROW LEVEL SECURITY',
        'ALTER TABLE inscricoes_aula ENABLE ROW LEVEL SECURITY',
        'ALTER TABLE conversas ALTER COLUMN match_id DROP NOT NULL',
        'ALTER TABLE conversas ADD COLUMN IF NOT EXISTS aula_id INT NULL UNIQUE REFERENCES aulas_grupo(id) ON DELETE CASCADE',
        # v6.3: busca de usuários, confirmação de e-mail, excluir conta, nome clicável nas notificações
        'ALTER TABLE notificacoes ADD COLUMN IF NOT EXISTS ator_id INT NULL REFERENCES usuarios(id) ON DELETE SET NULL',
        """CREATE TABLE IF NOT EXISTS codigos_email (
               id SERIAL PRIMARY KEY, email VARCHAR(150) NOT NULL,
               finalidade VARCHAR(20) NOT NULL CHECK (finalidade IN ('cadastro','excluir')),
               codigo_hash VARCHAR(255) NOT NULL, tentativas SMALLINT NOT NULL DEFAULT 0,
               usado BOOLEAN NOT NULL DEFAULT FALSE, expira_em TIMESTAMP NOT NULL, data_criacao TIMESTAMP NOT NULL
           )""",
        'CREATE INDEX IF NOT EXISTS idx_codigos_email ON codigos_email(email, finalidade)',
        'ALTER TABLE codigos_email ENABLE ROW LEVEL SECURITY',
    ],
}


def atualizar_banco(conexao, cfg):
    for comando in ATUALIZACOES.get(cfg.DB_TIPO, []):
        try:
            with conexao.cursor() as cursor:
                cursor.execute(comando)
            conexao.commit()
        except ERROS_BANCO:
            conexao.rollback()  # já existia (ou o banco ainda não tem as tabelas base)
