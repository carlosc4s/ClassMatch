-- ============================================================================
-- CLASSMATCH — Schema de Banco de Dados (versão MySQL)
-- Plataforma SaaS B2B de monitoria entre pares (ambiente institucional fechado)
-- ============================================================================
-- Testado para rodar no MySQL Workbench / MySQL Shell / MySQL 8+ (usa CHECK
-- constraint, que só é aplicado de fato a partir do MySQL 8.0.16 — em versões
-- anteriores a cláusula é aceita mas ignorada).
--
-- Como rodar: no Workbench, abra este arquivo e clique no raio (Execute) SEM
-- selecionar nada, para executar o script inteiro.
-- ============================================================================

-- Garante que os acentos dos dados iniciais sejam gravados certo.
SET NAMES utf8mb4;

-- ATENÇÃO: isso apaga o banco inteiro se ele já existir, para permitir
-- rodar o script do zero sempre que precisar (útil durante o desenvolvimento).
-- Comente/remova essa linha quando for usar em produção com dados reais.
DROP DATABASE IF EXISTS classmatch_db;

CREATE DATABASE IF NOT EXISTS classmatch_db
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE classmatch_db;

-- ============================================================================
-- 1. INSTITUIÇÕES (cliente B2B)
-- ============================================================================
CREATE TABLE instituicoes (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    nome                    VARCHAR(150) NOT NULL,
    dominio_email           VARCHAR(100) NOT NULL UNIQUE,   -- ex: escola.sp.gov.br (valida cadastro)
    cidade                  VARCHAR(100),
    estado                  CHAR(2),
    plano_contratado        VARCHAR(30) NOT NULL DEFAULT 'basico'
                                CHECK (plano_contratado IN ('basico','intermediario','premium')),
    custo_mensal            DECIMAL(8,2) DEFAULT 130.00,     -- R$130 a R$200/mês
    data_contratacao        DATE NOT NULL DEFAULT (CURRENT_DATE),
    ativo                   BOOLEAN NOT NULL DEFAULT TRUE
) ENGINE=InnoDB;

-- ============================================================================
-- 2. USUÁRIOS (alunos, monitores, coordenadores, admins da plataforma)
-- ============================================================================
CREATE TABLE usuarios (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    instituicao_id          INT NOT NULL,
    nome_completo           VARCHAR(150) NOT NULL,
    email_institucional     VARCHAR(150) NOT NULL UNIQUE,   -- validado contra dominio_email
    senha_hash              VARCHAR(255) NOT NULL,
    -- 'aluno' e 'monitor' são a mesma conta de estudante: o papel é escolhido em cada monitoria
    -- (quem pede ajuda é o aluno daquela monitoria, quem aceita é o monitor).
    tipo_usuario            VARCHAR(20) NOT NULL
                                CHECK (tipo_usuario IN ('aluno','monitor','coordenador','admin')),
    data_nascimento         DATE,
    faixa_etaria            VARCHAR(20)                     -- calculada a partir da data_nasc.
                                CHECK (faixa_etaria IN ('fundamental','medio','superior')),
    reputacao_media         DECIMAL(3,2) DEFAULT 5.00,       -- média das avaliações recebidas
    status_conta            VARCHAR(20) NOT NULL DEFAULT 'ativo'
                                CHECK (status_conta IN ('ativo','advertido','banido')),
    email_verificado        BOOLEAN NOT NULL DEFAULT FALSE,
    data_cadastro           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ultimo_login            TIMESTAMP NULL,
    bio                     VARCHAR(300) NULL,              -- "sobre mim" do perfil
    trocar_senha            BOOLEAN NOT NULL DEFAULT FALSE, -- senha temporária: obriga a criar outra no login
    CONSTRAINT fk_usuarios_instituicao FOREIGN KEY (instituicao_id)
        REFERENCES instituicoes(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE INDEX idx_usuarios_instituicao ON usuarios(instituicao_id);
CREATE INDEX idx_usuarios_tipo ON usuarios(tipo_usuario);

-- ============================================================================
-- 3. MATÉRIAS
-- ============================================================================
CREATE TABLE materias (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    nome                    VARCHAR(100) NOT NULL,
    area                    VARCHAR(60),                     -- ex: TI, Exatas, Linguagens
    descricao               TEXT
) ENGINE=InnoDB;

-- ============================================================================
-- 4. MONITOR x MATÉRIA (o que cada monitor pode ensinar e em que nível)
-- ============================================================================
CREATE TABLE monitor_materias (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id              INT NOT NULL,
    materia_id              INT NOT NULL,
    nivel_conhecimento      VARCHAR(20) NOT NULL
                                CHECK (nivel_conhecimento IN ('basico','intermediario','avancado')),
    ativo                   BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE KEY uk_usuario_materia (usuario_id, materia_id),
    CONSTRAINT fk_mm_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    CONSTRAINT fk_mm_materia FOREIGN KEY (materia_id) REFERENCES materias(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ============================================================================
-- 5. DISPONIBILIDADE DE HORÁRIOS (usada pelo algoritmo de match)
-- ============================================================================
CREATE TABLE disponibilidade_horarios (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id              INT NOT NULL,
    dia_semana              TINYINT NOT NULL CHECK (dia_semana BETWEEN 0 AND 6), -- 0=domingo
    horario_inicio          TIME NOT NULL,
    horario_fim             TIME NOT NULL,
    CHECK (horario_fim > horario_inicio),
    CONSTRAINT fk_disp_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE INDEX idx_disponibilidade_usuario ON disponibilidade_horarios(usuario_id);

-- ============================================================================
-- 6. SOLICITAÇÕES DE AJUDA (aluno pede monitoria)
-- ============================================================================
CREATE TABLE solicitacoes_ajuda (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    aluno_id                INT NOT NULL,
    materia_id              INT NOT NULL,
    nivel_dificuldade       VARCHAR(20) NOT NULL
                                CHECK (nivel_dificuldade IN ('basico','intermediario','avancado')),
    descricao_duvida        TEXT,
    -- pendente -> em_match (monitor aceitou, chat aberto) -> atendida (monitoria encerrada)
    -- pendente -> cancelada (o aluno desistiu)
    status                  VARCHAR(20) NOT NULL DEFAULT 'pendente'
                                CHECK (status IN ('pendente','em_match','atendida','cancelada')),
    data_criacao            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_solic_aluno FOREIGN KEY (aluno_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    CONSTRAINT fk_solic_materia FOREIGN KEY (materia_id) REFERENCES materias(id)
) ENGINE=InnoDB;

CREATE INDEX idx_solicitacoes_status ON solicitacoes_ajuda(status);

-- ============================================================================
-- 7. MATCHES (resultado do algoritmo de 3 variáveis: matéria + horário + nível)
-- ============================================================================
CREATE TABLE matches (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    solicitacao_id          INT NOT NULL,
    monitor_id              INT NOT NULL,
    aluno_id                INT NOT NULL,
    materia_id              INT NOT NULL,
    score_compatibilidade   DECIMAL(5,2),                    -- saída do algoritmo (0-100)
    status                  VARCHAR(20) NOT NULL DEFAULT 'proposto'
                                CHECK (status IN ('proposto','aceito','recusado','concluido','cancelado')),
    data_match              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    data_conclusao          TIMESTAMP NULL,
    link_meet               VARCHAR(120) NULL,               -- reunião do Google Meet (opcional)
    CONSTRAINT fk_match_solic FOREIGN KEY (solicitacao_id) REFERENCES solicitacoes_ajuda(id) ON DELETE CASCADE,
    CONSTRAINT fk_match_monitor FOREIGN KEY (monitor_id) REFERENCES usuarios(id),
    CONSTRAINT fk_match_aluno FOREIGN KEY (aluno_id) REFERENCES usuarios(id),
    CONSTRAINT fk_match_materia FOREIGN KEY (materia_id) REFERENCES materias(id)
) ENGINE=InnoDB;

CREATE INDEX idx_matches_monitor ON matches(monitor_id);
CREATE INDEX idx_matches_aluno ON matches(aluno_id);

-- ============================================================================
-- 8. CONVERSAS (uma sala de chat por match, sem migração externa)
-- ============================================================================
-- ------------------------------------------------------------
-- Aulas em grupo: 1 monitor para vários alunos (com vagas, data/hora e Meet)
-- ------------------------------------------------------------
CREATE TABLE aulas_grupo (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    monitor_id              INT NOT NULL,
    materia_id              INT NOT NULL,
    titulo                  VARCHAR(120) NOT NULL,
    descricao               VARCHAR(500) NULL,
    data_hora               TIMESTAMP NOT NULL,
    duracao_min             SMALLINT NOT NULL DEFAULT 60,
    vagas                   SMALLINT NOT NULL CHECK (vagas BETWEEN 2 AND 50),
    link_meet               VARCHAR(120) NULL,
    status                  VARCHAR(20) NOT NULL DEFAULT 'aberta'
                                CHECK (status IN ('aberta','concluida','cancelada')),
    data_criacao            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_aula_monitor FOREIGN KEY (monitor_id) REFERENCES usuarios(id),
    CONSTRAINT fk_aula_materia FOREIGN KEY (materia_id) REFERENCES materias(id)
) ENGINE=InnoDB;
CREATE INDEX idx_aulas_data ON aulas_grupo(data_hora);

CREATE TABLE inscricoes_aula (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    aula_id                 INT NOT NULL,
    aluno_id                INT NOT NULL,
    data_inscricao          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_inscricao UNIQUE (aula_id, aluno_id),
    CONSTRAINT fk_inscricao_aula FOREIGN KEY (aula_id) REFERENCES aulas_grupo(id) ON DELETE CASCADE,
    CONSTRAINT fk_inscricao_aluno FOREIGN KEY (aluno_id) REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- A conversa é de UMA monitoria (match_id) OU de UMA aula em grupo (aula_id).
CREATE TABLE conversas (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    match_id                INT NULL UNIQUE,
    aula_id                 INT NULL UNIQUE,
    data_criacao            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    encerrada               BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT fk_conversa_match FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
    CONSTRAINT fk_conversa_aula FOREIGN KEY (aula_id) REFERENCES aulas_grupo(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ============================================================================
-- 9. MENSAGENS (chat interno moderado)
-- ============================================================================
CREATE TABLE mensagens (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    conversa_id             INT NOT NULL,
    remetente_id            INT NOT NULL,
    conteudo_original       TEXT NOT NULL,                   -- guardado apenas p/ auditoria/moderação
    conteudo_filtrado       TEXT NOT NULL,                   -- versão exibida (após filtro automático)
    foi_filtrada            BOOLEAN NOT NULL DEFAULT FALSE,   -- indica se algo foi bloqueado/mascarado
    data_envio              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- Anexo (arquivo ou áudio). O arquivo fica em backend/uploads com nome aleatório;
    -- só participantes da conversa (ou a coordenação) conseguem baixar.
    anexo_arquivo           VARCHAR(100) NULL,
    anexo_nome              VARCHAR(150) NULL,
    anexo_tipo              VARCHAR(100) NULL,
    anexo_tamanho           INT NULL,
    anexo_categoria         VARCHAR(20) NULL
                                CHECK (anexo_categoria IN ('imagem','audio','documento')),
    CONSTRAINT fk_msg_conversa FOREIGN KEY (conversa_id) REFERENCES conversas(id) ON DELETE CASCADE,
    CONSTRAINT fk_msg_remetente FOREIGN KEY (remetente_id) REFERENCES usuarios(id)
) ENGINE=InnoDB;

CREATE INDEX idx_mensagens_conversa ON mensagens(conversa_id, id);

-- ============================================================================
-- 10. PALAVRAS FILTRADAS (dicionário do filtro automático: palavrões,
--     tentativas de contato externo, padrões de dados pessoais como telefone)
-- ============================================================================
CREATE TABLE palavras_filtradas (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    padrao                  VARCHAR(150) NOT NULL,            -- palavra ou regex
    tipo                    VARCHAR(30) NOT NULL
                                CHECK (tipo IN ('palavrao','dado_pessoal','contato_externo')),
    ativo                   BOOLEAN NOT NULL DEFAULT TRUE
) ENGINE=InnoDB;

-- ============================================================================
-- 11. AVALIAÇÕES (sistema de reputação)
-- ============================================================================
CREATE TABLE avaliacoes (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    match_id                INT NOT NULL,
    avaliador_id            INT NOT NULL,
    avaliado_id             INT NOT NULL,
    nota                    TINYINT NOT NULL CHECK (nota BETWEEN 1 AND 5),
    comentario              TEXT,
    data_avaliacao          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_match_avaliador (match_id, avaliador_id),
    CONSTRAINT fk_aval_match FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
    CONSTRAINT fk_aval_avaliador FOREIGN KEY (avaliador_id) REFERENCES usuarios(id),
    CONSTRAINT fk_aval_avaliado FOREIGN KEY (avaliado_id) REFERENCES usuarios(id)
) ENGINE=InnoDB;

CREATE INDEX idx_avaliacoes_avaliado ON avaliacoes(avaliado_id);

-- ============================================================================
-- 12. DENÚNCIAS (usuário reporta comportamento indevido)
-- ============================================================================
CREATE TABLE denuncias (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    denunciante_id          INT NOT NULL,
    denunciado_id           INT NOT NULL,
    conversa_id             INT NULL,                         -- conversa em que o problema aconteceu
    mensagem_id             INT NULL,                         -- última mensagem do denunciado (evidência)
    motivo                  TEXT NOT NULL,
    status                  VARCHAR(20) NOT NULL DEFAULT 'pendente'
                                CHECK (status IN ('pendente','em_analise','resolvida','arquivada')),
    data_denuncia           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_den_denunciante FOREIGN KEY (denunciante_id) REFERENCES usuarios(id),
    CONSTRAINT fk_den_denunciado FOREIGN KEY (denunciado_id) REFERENCES usuarios(id),
    CONSTRAINT fk_den_conversa FOREIGN KEY (conversa_id) REFERENCES conversas(id) ON DELETE SET NULL,
    CONSTRAINT fk_den_mensagem FOREIGN KEY (mensagem_id) REFERENCES mensagens(id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE INDEX idx_denuncias_status ON denuncias(status);

-- ============================================================================
-- 13. AÇÕES DE MODERAÇÃO (log de advertir/banir pela coordenação)
-- ============================================================================
CREATE TABLE acoes_moderacao (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    usuario_alvo_id         INT NOT NULL,
    moderador_id            INT NOT NULL,                     -- coordenador/admin
    denuncia_id             INT NULL,
    tipo_acao               VARCHAR(20) NOT NULL
                                CHECK (tipo_acao IN ('advertencia','banimento','desbanimento','remocao_mensagem')),
    motivo                  TEXT,
    data_acao               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_mod_alvo FOREIGN KEY (usuario_alvo_id) REFERENCES usuarios(id),
    CONSTRAINT fk_mod_moderador FOREIGN KEY (moderador_id) REFERENCES usuarios(id),
    CONSTRAINT fk_mod_denuncia FOREIGN KEY (denuncia_id) REFERENCES denuncias(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- ============================================================================
-- 14. MÉTRICAS DE DEFASAGEM (snapshot histórico p/ painel B2B da coordenação)
-- ============================================================================
CREATE TABLE metricas_defasagem (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    instituicao_id          INT NOT NULL,
    materia_id              INT NOT NULL,
    periodo_referencia      DATE NOT NULL,                    -- ex: primeiro dia do mês de referência
    total_solicitacoes      INT NOT NULL DEFAULT 0,
    total_atendidas         INT NOT NULL DEFAULT 0,
    taxa_defasagem          DECIMAL(5,2),                     -- % de solicitações não atendidas
    data_geracao            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_inst_materia_periodo (instituicao_id, materia_id, periodo_referencia),
    CONSTRAINT fk_metr_instituicao FOREIGN KEY (instituicao_id) REFERENCES instituicoes(id) ON DELETE CASCADE,
    CONSTRAINT fk_metr_materia FOREIGN KEY (materia_id) REFERENCES materias(id)
) ENGINE=InnoDB;

-- ============================================================================
-- 15. LOG DE ACESSO (auditoria LGPD — login/tentativas, IP, dispositivo)
-- ============================================================================
CREATE TABLE log_acesso (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id              INT NULL,
    email_tentativa         VARCHAR(150),                     -- registrado mesmo se falhar
    sucesso                 BOOLEAN NOT NULL,
    ip_origem               VARCHAR(45),
    user_agent              VARCHAR(255),
    data_evento             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_log_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE INDEX idx_log_acesso_usuario ON log_acesso(usuario_id);

-- ------------------------------------------------------------
-- Notificações (sino do cabeçalho): criadas pelo backend quando algo acontece
-- ------------------------------------------------------------
CREATE TABLE notificacoes (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id              INT NOT NULL,
    tipo                    VARCHAR(20) NOT NULL
                                CHECK (tipo IN ('pedido','match','mensagem','monitoria','avaliacao','denuncia','moderacao')),
    texto                   VARCHAR(255) NOT NULL,
    link                    VARCHAR(150) NOT NULL DEFAULT 'dashboard.html',
    lida                    BOOLEAN NOT NULL DEFAULT FALSE,
    data_criacao            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ator_id                 INT NULL,                       -- quem causou o aviso (nome vira link para o perfil)
    CONSTRAINT fk_notif_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    CONSTRAINT fk_notif_ator FOREIGN KEY (ator_id) REFERENCES usuarios(id) ON DELETE SET NULL
) ENGINE=InnoDB;
CREATE INDEX idx_notificacoes_usuario ON notificacoes(usuario_id, lida);

-- ------------------------------------------------------------
-- "Esqueci minha senha": códigos de 6 números enviados por e-mail.
-- Guarda só o hash do código; vale 15 minutos, uso único, máx. 5 tentativas.
-- ------------------------------------------------------------
CREATE TABLE codigos_senha (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id              INT NOT NULL,
    codigo_hash             VARCHAR(255) NOT NULL,
    tentativas              SMALLINT NOT NULL DEFAULT 0,
    usado                   BOOLEAN NOT NULL DEFAULT FALSE,
    expira_em               TIMESTAMP NOT NULL,
    data_criacao            TIMESTAMP NOT NULL,
    CONSTRAINT fk_codigo_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB;
CREATE INDEX idx_codigos_usuario ON codigos_senha(usuario_id, usado);

-- ------------------------------------------------------------
-- Códigos de 6 números por e-mail para CONFIRMAR o e-mail no cadastro
-- e para EXCLUIR a conta. Ligados ao e-mail (no cadastro a conta ainda não existe).
-- Guarda só o hash do código; vale 15 minutos, uso único, máx. 5 tentativas.
-- ------------------------------------------------------------
CREATE TABLE codigos_email (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    email                   VARCHAR(150) NOT NULL,
    finalidade              VARCHAR(20) NOT NULL CHECK (finalidade IN ('cadastro','excluir')),
    codigo_hash             VARCHAR(255) NOT NULL,
    tentativas              SMALLINT NOT NULL DEFAULT 0,
    usado                   BOOLEAN NOT NULL DEFAULT FALSE,
    expira_em               TIMESTAMP NOT NULL,
    data_criacao            TIMESTAMP NOT NULL
) ENGINE=InnoDB;
CREATE INDEX idx_codigos_email ON codigos_email(email, finalidade);

-- ============================================================================
-- VIEW: Painel de matérias mais solicitadas x atendidas por instituição
-- (base para o Dashboard B2B da coordenação). "Atendida" = um monitor aceitou
-- (em_match) ou a monitoria já terminou (atendida).
-- ============================================================================
CREATE VIEW vw_painel_coordenacao AS
SELECT
    i.id            AS instituicao_id,
    i.nome          AS instituicao,
    m.nome          AS materia,
    COUNT(s.id)                                                        AS total_solicitacoes,
    SUM(CASE WHEN s.status IN ('em_match','atendida') THEN 1 ELSE 0 END)   AS total_atendidas,
    ROUND(
        100.0 * SUM(CASE WHEN s.status IN ('em_match','atendida') THEN 0 ELSE 1 END)
        / NULLIF(COUNT(s.id), 0), 2
    )                                                                   AS taxa_defasagem_pct
FROM solicitacoes_ajuda s
JOIN usuarios u     ON u.id = s.aluno_id
JOIN instituicoes i ON i.id = u.instituicao_id
JOIN materias m     ON m.id = s.materia_id
GROUP BY i.id, i.nome, m.nome;

-- ============================================================================
-- DADOS INICIAIS (seed de exemplo — dá para apresentar o sistema na hora)
-- ============================================================================
INSERT INTO instituicoes (nome, dominio_email, cidade, estado) VALUES
('Escola Técnica Exemplo', 'escola.sp.gov.br', 'São Paulo', 'SP');

INSERT INTO materias (nome, area) VALUES
('Lógica de Programação', 'TI'),         -- id 1
('Banco de Dados', 'TI'),                -- id 2
('Redes de Computadores', 'TI'),         -- id 3
('Matemática', 'Exatas'),                -- id 4
('Programação Web', 'TI'),               -- id 5
('Física', 'Exatas'),                    -- id 6
('Química', 'Exatas'),                   -- id 7
('Língua Portuguesa', 'Linguagens'),     -- id 8
('Inglês', 'Linguagens'),                -- id 9
('História', 'Humanas'),                 -- id 10
('Geografia', 'Humanas');                -- id 11

-- Contas de teste. SENHA DE TODAS: senha123
-- (o hash é do Werkzeug/Flask)
INSERT INTO usuarios (instituicao_id, nome_completo, email_institucional,
                      senha_hash, tipo_usuario, data_nascimento, faixa_etaria, email_verificado) VALUES
(1, 'Coordenação Exemplo', 'coordenacao@escola.sp.gov.br',
 'scrypt:32768:8:1$EvVDOWlFfXogD5hn$42cdf991386b9c5ba04e4c5ea54efa1390f96d75102115b3a745f797fe380f57555a88a6d5623684b909527330ad57b447de5ab7dd2eeb3794e744fec8a52e35',
 'coordenador', '1985-03-10', 'superior', TRUE),                                      -- id 1
(1, 'Marina Souza', 'monitor.demo@escola.sp.gov.br',
 'scrypt:32768:8:1$GX2En1Ccz1HpTTe3$736c977ea914a4cf5d8f38f22a7181dfa5210fde451d036992d14e0e015e3445cb12634f6fc942cd834a44aea82b7086cc434ab3fbcca1ab3e71b51af04733c7',
 'monitor', '2009-05-20', 'medio', TRUE),                                             -- id 2
(1, 'Lucas Almeida', 'aluno.demo@escola.sp.gov.br',
 'scrypt:32768:8:1$OJgYNEv5NTMwIfkF$a2d5857a5590448cc985f24c3e3ab08b7bfbf3dd359a5f27594ca39b32584b884a9644d0964c0e0b62afb2fd4f69dd52d6b01beef6aec80a28fe8ed37ae1d92d',
 'aluno', '2010-08-15', 'medio', TRUE);                                               -- id 3

-- O que a monitora de teste ensina
INSERT INTO monitor_materias (usuario_id, materia_id, nivel_conhecimento) VALUES
(2, 1, 'avancado'),        -- Lógica de Programação
(2, 4, 'intermediario'),   -- Matemática
(2, 2, 'basico');          -- Banco de Dados

-- Uma monitoria que já aconteceu (para o painel e a reputação não começarem vazios)
INSERT INTO solicitacoes_ajuda (aluno_id, materia_id, nivel_dificuldade, descricao_duvida, status) VALUES
(3, 1, 'basico', 'Não entendi a diferença entre o laço while e o laço for.', 'atendida');   -- id 1
INSERT INTO matches (solicitacao_id, monitor_id, aluno_id, materia_id, score_compatibilidade, status, data_conclusao) VALUES
(1, 2, 3, 1, 85, 'concluido', CURRENT_TIMESTAMP);                                              -- id 1
INSERT INTO conversas (match_id, encerrada) VALUES (1, TRUE);                                    -- id 1
INSERT INTO mensagens (conversa_id, remetente_id, conteudo_original, conteudo_filtrado, foi_filtrada) VALUES
(1, 2, 'Oi, Lucas! O for é para quando você sabe quantas vezes vai repetir; o while repete enquanto a condição for verdadeira.',
       'Oi, Lucas! O for é para quando você sabe quantas vezes vai repetir; o while repete enquanto a condição for verdadeira.', FALSE),
(1, 3, 'Ahh, entendi! Me chama no zap 11 98888-7777 se eu travar de novo',
       'Ahh, entendi! Me chama no [removido pela moderação] [removido pela moderação] se eu travar de novo', TRUE),
(1, 2, 'Melhor falarmos por aqui mesmo. Qualquer dúvida é só abrir outro pedido!',
       'Melhor falarmos por aqui mesmo. Qualquer dúvida é só abrir outro pedido!', FALSE);
INSERT INTO avaliacoes (match_id, avaliador_id, avaliado_id, nota, comentario) VALUES
(1, 3, 2, 5, 'Explicou super bem!');
UPDATE usuarios SET reputacao_media = 5.00,
       bio = 'Curto ajudar em lógica e matemática. Chama que a gente resolve junto!' WHERE id = 2;

-- Um pedido esperando monitor (aparece para a monitora de teste aceitar)
INSERT INTO solicitacoes_ajuda (aluno_id, materia_id, nivel_dificuldade, descricao_duvida) VALUES
(3, 4, 'basico', 'Não sei quando usar a fórmula de Bhaskara na equação do 2º grau.');          -- id 2

-- Palavras extras do filtro do chat (o backend já tem uma lista própria;
-- a coordenação pode acrescentar linhas aqui sem mexer no código).
INSERT INTO palavras_filtradas (padrao, tipo) VALUES
('kwai', 'contato_externo'),
('twitch', 'contato_externo'),
('chave pix', 'dado_pessoal'),
('meu endereço', 'dado_pessoal'),
('trouxa', 'palavrao');

SELECT 'Banco classmatch_db criado com sucesso! Contas de teste: senha123' AS resultado;
