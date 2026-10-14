# ClassMatch — front-end + back-end Flask + banco (MySQL ou Supabase)

Monitoria entre alunos da mesma escola: o aluno pede ajuda numa matéria, um monitor aceita, os dois conversam num chat moderado (só texto) e a coordenação acompanha tudo. Equipe Ceap.

```
class/
├── frontend/
│   ├── index.html      página inicial (visitantes)
│   ├── entrar.html     login e cadastro (entrar.html#cadastro abre direto o cadastro)
│   ├── dashboard.html  painel do aluno / monitor / coordenação + perfil (#perfil) + chat
│   ├── ajuda.html      perguntas frequentes e contato
│   ├── layout.js       cabeçalho, rodapé, tema claro/escuro, busca de pessoas e notificações (todas as páginas)
│   ├── api.js          conversa com o backend
│   ├── style.css       visual (preto, azul e branco; tema claro e escuro)
│   └── img/            logo oficial: versão clara e escura (símbolo, nome e completa)
├── backend/
│   ├── app.py          rotas da API
│   ├── banco.py        conexão com MySQL ou PostgreSQL + erros explicados em português
│   ├── filtro.py       filtro do chat (telefone, @perfil, links, palavrões...)
│   ├── config.py       lê o backend/.env (nenhuma senha fica no código)
│   ├── uploads/        arquivos de versões antigas (antes da v6.4), se existir
│   └── *.bat           instalar / iniciar / criar_banco
├── database/
│   ├── banco.sql           MySQL (Workbench)
│   └── banco_postgres.sql  PostgreSQL / Supabase (mesma estrutura e mesmos dados de teste)
└── .vscode/            F5 para rodar/depurar o backend
```

O navegador nunca fala com o banco diretamente. Só o backend tem a senha e executa SQL.

---

## Primeira vez depois de baixar do GitHub

O repositório **não traz** nenhuma senha nem as bibliotecas. Antes de ligar:

1. Copie `backend/.env.example` para `backend/.env` e preencha com os dados do **seu** banco (MySQL local ou Supabase) e, se quiser, do e-mail. Se pular este passo, o `iniciar.bat` pergunta os dados do banco e cria o `.env` sozinho.
2. As bibliotecas (`backend/bibliotecas`) são baixadas na primeira vez que você rodar o `INICIAR.bat` (ou o `backend/instalar.bat`). Precisa de internet.
3. Crie as tabelas (veja "Qual banco usar" abaixo).

A `backend/.chave_secreta` (assina os logins) é criada sozinha na primeira vez que o servidor liga.

Para ligar: dois cliques no **`INICIAR.bat`** (pasta principal). Ele abre o site sozinho em http://127.0.0.1:5000.

## Qual banco usar

O `backend/.env` decide. Com `DB_TIPO=postgres` (ou porta 5432/6543, ou endereço do Supabase) o backend usa **Supabase/PostgreSQL**; senão usa **MySQL**. O código SQL é o mesmo para os dois.

**Supabase (primeira vez):** no site do Supabase, abra o projeto > botão **Connect** > **Session pooler** e copie host, porta e usuário para o `.env` (veja o `.env.example`). Depois crie as tabelas de um destes jeitos:

- rode o `backend\criar_banco.bat`, ou
- no Supabase: **SQL Editor** > New query > cole o `database/banco_postgres.sql` > **Run**.

O script liga o *Row Level Security* em todas as tabelas: o backend continua funcionando normalmente, mas a API pública do Supabase (chave "anon/publishable") fica sem acesso aos dados.

> Rede da escola bloqueando a porta 5432? O Supabase não conecta. Teste no roteador do celular ou use o MySQL local.

## Segurança (antes de publicar)

- **Nenhuma senha fica no código.** A senha do banco fica só no `backend/.env`, que **não vai para o GitHub** (está no `.gitignore`). Para rodar, copie o `backend/.env.example` para `backend/.env` e preencha com os dados do seu banco.
- **Upload pelo site do GitHub (arrastar arquivos) ignora o `.gitignore`.** Nunca arraste a pasta que tem o `.env`.
- Se uma senha do banco já foi parar em algum arquivo compartilhado, troque no Supabase: *Project Settings > Database > Reset database password*.
- As senhas dos usuários ficam no banco só como *hash* (embaralhadas); ninguém consegue ler.
- `backend/.chave_secreta` (assina os logins) é gerada sozinha em cada computador e também não vai para o GitHub.
- As **contas de teste** (senha `senha123`) servem para demonstração. O quadro delas na tela de entrar só aparece rodando no próprio computador. Se o site for colocado online de verdade, apague essas contas ou troque as senhas.

## Esqueci minha senha

1. Na tela de entrar, **Esqueci minha senha** → a pessoa digita o e-mail → **Enviar link**.
2. Chega um e-mail do ClassMatch com o botão **Redefinir minha senha** e um **código de 6 números**.
3. O botão abre a página `redefinir-senha.html`, que mostra a conta (e-mail mascarado) e pede o código e a senha nova. Ao salvar, já entra no painel.

Segurança: o link é assinado e vence em 15 minutos; o código só funciona uma vez e com até 5 tentativas; no máximo 3 e-mails por hora para a mesma conta; a resposta é igual exista ou não o e-mail (ninguém descobre quais contas existem). Se o link não abrir, a página `redefinir-senha.html` também aceita e-mail + código.

**Para o e-mail sair de verdade** (sem isso, o site manda procurar a coordenação, que gera uma senha temporária no painel dela):

1. Entre na conta Gmail que vai enviar os e-mails do ClassMatch > Conta Google > **Segurança** > ative a **Verificação em duas etapas**.
2. Abra https://myaccount.google.com/apppasswords, crie uma senha de app chamada "ClassMatch" e copie as 16 letras.
3. No `backend/.env`, apague o `#` das linhas `EMAIL_USUARIO` e `EMAIL_SENHA_APP`, cole as 16 letras e salve.
4. Dois cliques no **`backend/testar_email.bat`**: ele manda um e-mail de teste e diz se deu certo (ou o motivo do erro).
5. Reinicie o `INICIAR.bat`.

> O link do e-mail aponta para `http://127.0.0.1:5000`, então abre no computador onde o servidor está ligado. Se o site estiver em outro endereço, coloque `SITE_URL=` no `.env`. Algumas redes de escola bloqueiam envio de e-mail; se o teste falhar na escola, teste em casa.

## Novidades da v6.4

- **Chat só com texto:** saiu o envio de arquivos e de áudios (botões de clipe e de microfone) em todos os chats: monitorias, chat da turma das aulas em grupo e a leitura de conversas pela coordenação. As rotas `/api/mensagens/anexo` e `/api/anexos/<id>` não existem mais.
- **Nada foi apagado do banco:** as colunas `anexo_*` da tabela `mensagens` continuam lá. Mensagens antigas que eram um arquivo ou áudio aparecem com o aviso "Arquivo ou áudio antigo (o chat agora é só texto)". Os arquivos antigos (em `backend/uploads` ou no Supabase Storage) só são apagados quando a conta de quem enviou é excluída.
- `UPLOAD_MAX_MB` no `.env` não é mais usado.

## Novidades da v6.3

- **Busca de pessoas (lupa ao lado do "Sair"):** procura colegas **da mesma escola** pelo nome, sem ligar para acento ou maiúscula ("joao" acha "João"). Clicou no resultado, abre o perfil. Contas suspensas só aparecem para a coordenação. No celular, a busca fica dentro do menu.
- **Nome clicável nas notificações:** em avisos como "**Marina** aceitou seu pedido de ajuda", o nome é um link para o perfil da pessoa (clicar no resto do aviso continua abrindo a conversa). Fora do painel, o clique leva para `dashboard.html#usuario-ID`, que abre o perfil.
- **Confirmação do e-mail no cadastro:** depois de preencher o formulário, chega um **código de 6 números** no e-mail e a conta só é criada com ele (a conta fica com o selo "E-mail verificado").
- **Excluir minha conta (aba Perfil, só estudantes):** pede a senha, manda um **código para o e-mail** e só então apaga a conta **para sempre**, junto com pedidos, monitorias (e o chat delas), aulas em grupo que a pessoa dava, mensagens, avaliações e denúncias. Se a pessoa estava monitorando alguém, o pedido do colega volta para a fila. A média de quem perdeu uma avaliação é recalculada. Contas da coordenação não se excluem por aqui.

Os códigos seguem as mesmas regras do "esqueci minha senha": valem 15 minutos, funcionam uma vez, até 5 tentativas e no máximo 3 e-mails por hora para o mesmo endereço. **Precisa do e-mail configurado** no `backend/.env` (`EMAIL_USUARIO` e `EMAIL_SENHA_APP`, veja "Esqueci minha senha" acima). Sem isso o site continua funcionando: o cadastro é criado sem código e a exclusão é confirmada só pela senha (a janela do servidor avisa).

O banco é atualizado sozinho quando o servidor liga (tabela nova `codigos_email` e coluna `notificacoes.ator_id`), sem apagar nada.

## Novidades da v6

- **Sem RA:** o cadastro e o login usam só o e-mail. O ID de cada usuário é sequencial (1, 2, 3...).
- **Todo estudante aprende e ensina:** o cadastro não pergunta mais "aluno ou monitor". No painel há **Quero aprender** (pedir ajuda, aulas em grupo) e **Quero ensinar** (matérias, possíveis matches, criar aulas). O papel vale por monitoria: quem pediu é o aluno dela, quem aceitou é o monitor. Ninguém aceita o próprio pedido.
- **Google Meet:** no chat, **Link do Meet** guarda o link da reunião e aparece **Entrar na reunião (Meet)** para os participantes. Só links `meet.google.com` são aceitos (os outros links continuam bloqueados no chat).
- **Aulas em grupo (1 monitor para vários alunos):** quem ensina cria a aula (matéria, título, data/hora, duração, 2 a 50 vagas e Meet). Os colegas se inscrevem até lotar e todos entram no **chat da turma** (com filtro e denúncia escolhendo a pessoa). Quem pediu ajuda naquela matéria é avisado da aula nova. O link do Meet só aparece para quem está inscrito.
- **Atualização automática do banco:** ao ligar, o servidor acrescenta as colunas/tabelas novas e tira o RA, **sem apagar os dados**.

## Novidades desta versão (v5)

- Página inicial, página de ajuda (FAQ + WhatsApp e e-mail) e rodapé da Equipe Ceap.
- Nova identidade preto/azul/branco, tema claro/escuro (botão de lua/sol, fica salvo) e logo oficial que troca com o tema.
- Menu único em todas as páginas (hambúrguer no celular) e botões de voltar.
- Perfil com avaliação média, número de avaliações e monitorias, matérias, últimas avaliações e **Editar perfil**.
- Cards de "Possível match" com **Ver perfil** e **Aceitar e conversar**.
- **Notificações reais**: novo pedido (monitores da matéria), pedido aceito, nova mensagem, monitoria encerrada, avaliação recebida e denúncia (coordenação).
- Backend funciona com MySQL **ou** Supabase; a senha que estava escrita no `config.py` foi removida.

---

## Modo fácil (Windows)

1. **Confira a senha:** copie `backend/.env.example` para `backend/.env` e coloque a senha do seu MySQL em `DB_PASSWORD` (ou deixe o `iniciar.bat` perguntar). Se estiver errada, o servidor avisa e pergunta a senha certa na hora.
2. **Dê dois cliques em `backend/iniciar.bat`.** Na primeira vez ele baixa as bibliotecas (precisa de internet) e, se o banco `classmatch_db` ainda não existir, pergunta *"Quer que eu crie o banco agora?"* — aperte **Enter**. Depois liga o servidor e abre o site no navegador. Deixe a janela preta aberta enquanto usa.

**Para zerar o banco** (voltar só com os dados de teste): feche a janela do servidor e dê dois cliques em `backend/criar_banco.bat`. Quem preferir pode continuar usando o Workbench: abra `database/banco.sql` e clique no primeiro raio sem selecionar nada.

Se aparecer que o Python não foi encontrado: instale em https://www.python.org/downloads/ marcando **"Add python.exe to PATH"** (em computador da escola, peça ao técnico).

### Contas de teste (senha de todas: `senha123`)

| Conta | E-mail |
|---|---|
| Aluno | `aluno.demo@escola.sp.gov.br` |
| Monitora | `monitor.demo@escola.sp.gov.br` |
| Coordenação | `coordenacao@escola.sp.gov.br` |

Na tela de entrada, "Contas de teste" preenche o login com um clique. (Para apresentar sem elas, apague o bloco `<details class="contas-teste">` do `entrar.html`.)

### Testando o fluxo completo

1. Entre como **aluno** e peça ajuda numa matéria (a monitora de teste ensina Lógica de Programação, Matemática e Banco de Dados).
2. Em outra janela anônima, entre como **monitora**: o pedido aparece em "Pedidos de ajuda disponíveis". Clique em **Aceitar**.
3. Conversem pelo chat (ele se atualiza sozinho). Teste mandar um telefone, um `@instagram` ou um palavrão: o backend filtra antes de salvar.
4. Use **Denunciar** e depois entre como **coordenação** para ler a conversa (com o texto original, antes do filtro) e advertir/suspender.
5. **Encerre** a monitoria e avalie com estrelas.

### Cadastro

Aceita **qualquer e-mail**. Cada conta pertence a uma escola (o match e o painel da coordenação são por escola), escolhida assim:

- Se o sistema tem **uma escola só**, todo mundo entra nela (o campo "Escola" nem aparece).
- Com **mais de uma escola**, o cadastro mostra o campo "Escola" para a pessoa escolher.
- Se o e-mail for do domínio da escola (coluna `dominio_email`, ex.: `escola.sp.gov.br`, subdomínios valem), a escola é escolhida sozinha e a conta fica com `email_verificado = TRUE`.

Para cadastrar outra escola:

```sql
INSERT INTO instituicoes (nome, dominio_email, cidade, estado)
VALUES ('Etec Exemplo', 'etec.sp.gov.br', 'São Paulo', 'SP');
```

Para ter outra conta de coordenação: cadastre-se normalmente e depois rode
`UPDATE usuarios SET tipo_usuario = 'coordenador' WHERE email_institucional = 'seu.email@escola.sp.gov.br';`

---

## Modo manual (terminal, Mac/Linux ou quem preferir)

```bash
cd backend
python -m pip install -r requirements.txt --target bibliotecas
python app.py            # ou: python app.py --abrir  (abre o navegador)
```

(No Windows, se `python` não for reconhecido, use `py` no lugar.)

Site em **http://127.0.0.1:5000**. No Mac, a porta 5000 costuma estar ocupada pelo "Receptor AirPlay": coloque `PORTA=5001` no `backend/.env`.

### VS Code

- **F5** roda o backend com a configuração **"ClassMatch: Flask backend"** (dá para colocar breakpoints no Python). Rode o `instalar.bat` uma vez antes. Se o VS Code perguntar qual Python usar (`Ctrl+Shift+P` → "Python: Select Interpreter"), escolha o Python instalado no computador, não um `venv`.
- **Live Server** é opcional: se abrir o `frontend/index.html` por ele, o site continua falando com o Flask em `127.0.0.1:5000` (o servidor Flask precisa estar ligado). Se mudar a `PORTA`, mude `API_ENDERECO_PADRAO` no `frontend/api.js` também.

---

## Rotas da API

Todas respondem JSON. As que pedem login exigem o cabeçalho `Authorization: Bearer <token>` (o `api.js` já manda sozinho).

| Método | Rota | Quem | Para quê |
|---|---|---|---|
| GET | `/api/saude` | todos | servidor e banco estão ok? |
| GET | `/api/escolas` | todos | escolas ativas (para o campo "Escola" do cadastro) |
| POST | `/api/cadastro/codigo` | todos | confere os dados do cadastro e manda o código para o e-mail (`modo: "direto"` se o e-mail não estiver configurado) |
| POST | `/api/cadastro` | todos | cria conta (aluno/monitor) com qualquer e-mail + `codigo` do e-mail e devolve o token |
| POST | `/api/login` | todos | e-mail + senha → token |
| GET | `/api/eu` | logado | dados atualizados de quem está logado |
| GET | `/api/materias` | logado | matérias + quantos monitores ensinam cada uma |
| GET · POST | `/api/monitor-materias` | monitor | matérias que eu ensino (POST também atualiza o nível) |
| DELETE | `/api/monitor-materias/<id>` | monitor | parar de ensinar uma matéria |
| GET · POST | `/api/solicitacoes` | aluno | meus pedidos / pedir ajuda |
| POST | `/api/solicitacoes/<id>/cancelar` | aluno | cancelar pedido que ainda espera monitor |
| GET | `/api/solicitacoes/pendentes` | monitor | pedidos das minhas matérias, com compatibilidade |
| POST | `/api/matches` | monitor | aceitar pedido (cria match + conversa) |
| GET | `/api/matches` | aluno/monitor | minhas monitorias |
| POST | `/api/matches/<id>/concluir` | aluno/monitor | encerrar monitoria |
| GET | `/api/mensagens?conversa_id=N&depois=ID` | participante ou coordenação | mensagens (só as novas, com `depois`) |
| POST | `/api/mensagens` | aluno/monitor | enviar mensagem (passa pelo filtro) |
| POST | `/api/avaliacoes` | aluno/monitor | nota de 1 a 5 depois de encerrar |
| POST | `/api/denuncias` | aluno/monitor | denunciar a outra pessoa da conversa |
| GET | `/api/painel` | coordenação | números, defasagem, monitores, denúncias |
| POST | `/api/denuncias/<id>/moderar` | coordenação | `advertencia`, `banimento` ou `arquivar` |
| POST | `/api/usuarios/<id>/desbanir` | coordenação | reativar conta suspensa |

---

### Rotas novas (v5)

| Método | Rota | Quem | O que faz |
|---|---|---|---|
| GET | `/api/perfil` | logado | meu perfil (média, avaliações, monitorias, matérias) |
| GET | `/api/perfil/<id>` | logado | perfil de outra pessoa **da mesma escola** |
| PUT | `/api/perfil` | logado | edita nome e "sobre você" (passa pelo filtro) |
| GET | `/api/notificacoes` | logado | últimas 20 + quantas não lidas |
| POST | `/api/notificacoes/lidas` | logado | marca todas (ou `{"ids": [...]}`) como lidas |
| POST | `/api/senha/esqueci` | qualquer um | envia o código por e-mail (ou avisa para procurar a coordenação) |
| GET | `/api/senha/link?token=` | qualquer um | confere o link do e-mail (mostra o e-mail mascarado) |
| POST | `/api/senha/redefinir` | qualquer um | token do link (ou e-mail) + código + nova senha → já entra |
| PUT | `/api/senha` | logado | trocar senha (pede a atual) |
| POST | `/api/coordenacao/redefinir-senha` | coordenação | gera senha temporária para aluno/monitor da escola |
| GET | `/api/usuarios/busca?q=` | logado | até 10 pessoas da mesma escola cujo nome bate com a busca (v6.3) |
| POST | `/api/conta/excluir/codigo` | estudante | `{"senha"}` → manda o código de exclusão para o e-mail da conta (v6.3) |
| POST | `/api/conta/excluir` | estudante | `{"senha", "codigo"}` → exclui a conta para sempre (v6.3) |
| PUT | `/api/matches/<id>/meet` | participantes | salva/remove o link do Meet da monitoria |
| GET | `/api/aulas` | estudante | aulas em grupo da escola (vagas, se estou inscrito) |
| POST | `/api/aulas` | estudante que ensina a matéria | cria aula em grupo |
| POST / DELETE | `/api/aulas/<id>/inscricao` | estudante | entra / sai da aula |
| PUT | `/api/aulas/<id>/meet` | quem dá a aula | link do Meet da aula (inscritos são avisados) |
| POST | `/api/aulas/<id>/status` | quem dá a aula | `{"status": "concluida"}` ou `"cancelada"` |

## Se algo der errado

A janela do servidor (e o site) mostram a causa em português. As mais comuns:

| Mensagem / sintoma | O que fazer |
|---|---|
| "não encontrei o Python" / janela fecha na hora | Instale o Python marcando "Add python.exe to PATH" e rode o `iniciar.bat` de novo. |
| `WinError 1260 ... política de grupo` | Era da versão antiga, que usava `venv`. Use o `instalar.bat` desta versão (ele apaga o `venv` e não precisa dele). Veja "Computador da escola" abaixo. |
| "A instalação das bibliotecas falhou" | Sem internet ou a rede da escola bloqueia o `pip`. Tente em outra rede (ex.: celular). |
| "O MySQL recusou o usuário root" | Senha errada em `backend/.env`. O servidor pergunta a senha certa e salva. |
| "O banco classmatch_db ainda não foi criado" | Feche a janela do servidor e abra o `iniciar.bat` de novo: ele pergunta se pode criar (aperte Enter). |
| "O banco está com a estrutura antiga" / "Falta uma tabela" | Feche a janela do servidor e rode o `criar_banco.bat`. |
| "Não consegui conectar ao MySQL" | O MySQL está desligado: Windows → `services.msc` → serviço **MySQL80** → Iniciar (XAMPP: botão Start). |
| "A porta 5000 está ocupada" | O ClassMatch já está aberto em outra janela, ou outro programa usa a porta: coloque `PORTA=5001` no `backend/.env`. |
| "Escolha a sua escola na lista" | Há mais de uma escola cadastrada: escolha a sua no campo "Escola". |
| "Não foi possível falar com o servidor" no site | A janela do `iniciar.bat` foi fechada. Abra de novo e recarregue a página. |
| Mudei um arquivo e o site não mudou | Recarregue com **Ctrl + F5**. |

## Computador da escola

Computadores de laboratório costumam ter regras do Windows ("política de grupo") que bloqueiam programas fora de Arquivos de Programas. Esta versão foi feita para funcionar assim mesmo: ela só roda o Python oficial e deixa as bibliotecas como arquivos comuns na pasta `backend/bibliotecas`. Se ainda assim algo for barrado:

- **O `pip` não consegue baixar (rede da escola bloqueia):** rode o `instalar.bat` em casa, com a **mesma versão do Python** da escola (a do laboratório é a 3.13), e leve a pasta `backend/bibliotecas` junto no pendrive.
- **Aviso sobre "cryptography" bloqueada:** o MySQL 8 só precisa dela na primeira conexão depois que o MySQL liga. Contorno simples: abra o **MySQL Workbench e conecte no banco uma vez** antes de rodar o `iniciar.bat`. Outro jeito (MySQL 8.0): rode no Workbench
  `ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'sua_senha';`
- **O próprio Python está bloqueado:** aí só o técnico da escola resolve (liberando o Python ou instalando em Arquivos de Programas).

## Próximos passos sugeridos

- Cruzar `disponibilidade_horarios` no match (hoje o match usa matéria + nível).
- Tela para a coordenação editar a tabela `palavras_filtradas` e cadastrar escolas.

## Publicar na Vercel

O repositório já vem pronto (`vercel.json`, `api/index.py` e `requirements.txt` na raiz). A Vercel entrega a pasta `frontend/` como site e roda o Flask só nas rotas `/api/...`. No computador nada muda: continue usando o `INICIAR.bat`.

1. Na Vercel: **Settings > Build and Deployment**: *Framework Preset* = **Other** e *Root Directory* **vazio** (a raiz do repositório, não `backend`).
2. **Settings > Environment Variables**: cadastre as mesmas chaves do `backend/.env` (o banco tem que ser o **Supabase**; o MySQL do seu computador não é acessível pela internet):
   `DB_TIPO`, `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_FUSO` e **`SECRET_KEY`** (obrigatória: um texto longo e aleatório, senão os logins caem sozinhos). Opcionais: `EMAIL_USUARIO`, `EMAIL_SENHA_APP`, `SITE_URL`, `SUPABASE_URL`, `SUPABASE_CHAVE_SECRETA`.
3. Faça um novo deploy (**Deployments > ... > Redeploy**).

As tabelas não são criadas pela Vercel: crie antes no Supabase (SQL Editor com o `database/banco_postgres.sql`, ou rodando o ClassMatch uma vez no computador apontando para o Supabase).
