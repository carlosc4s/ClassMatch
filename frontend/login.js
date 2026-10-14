// Alterna entre as abas Entrar / Cadastrar
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById(`panel-${btn.dataset.tab}`).classList.add('active');
        esconderMensagem();
    });
});

const msgBox = document.getElementById('msg-box');
function mostrarMensagem(texto, tipo) {
    msgBox.textContent = texto;
    msgBox.className = `msg show ${tipo}`;
}
function esconderMensagem() {
    msgBox.className = 'msg';
}

// Botão fica "ocupado" enquanto espera o servidor (evita cadastro em dobro).
async function comBotaoOcupado(form, textoOcupado, tarefa) {
    const botao = form.querySelector('button[type="submit"]');
    const textoOriginal = botao.textContent;
    botao.disabled = true;
    botao.textContent = textoOcupado;
    try {
        await tarefa();
    } finally {
        botao.disabled = false;
        botao.textContent = textoOriginal;
    }
}

// Recado deixado por outra página (ex.: "Sua sessão expirou").
const recado = sessionStorage.getItem(CHAVE_RECADO);
if (recado) {
    sessionStorage.removeItem(CHAVE_RECADO);
    mostrarMensagem(recado, 'error');
}

// Se já existe uma sessão salva, vai direto pro painel
if (sessao.obter()) {
    window.location.href = 'dashboard.html';
} else {
    verificarServidor();
}

// Avisa logo na entrada se o backend ou o banco estiverem com problema.
async function verificarServidor() {
    try {
        const saude = await api.saude();
        if (saude.banco !== 'ok') {
            mostrarMensagem(saude.mensagem || 'O servidor está no ar, mas o banco de dados não respondeu.', 'error');
            return;
        }
        await carregarEscolas();
    } catch (err) {
        mostrarMensagem(err.message, 'error');
    }
}

// O campo "Escola" só aparece quando o sistema tem mais de uma escola.
async function carregarEscolas() {
    const escolas = await api.escolas();
    const campo = document.getElementById('campo-escola');
    const select = document.getElementById('cad-escola');
    if (escolas.length <= 1) {
        campo.hidden = true;
        select.required = false;
        return;
    }
    select.replaceChildren(
        h('option', { value: '' }, 'Escolha a sua escola'),
        ...escolas.map(e => h('option', { value: e.id },
            e.cidade ? `${e.nome} (${e.cidade}${e.estado ? '/' + e.estado : ''})` : e.nome)),
    );
    select.required = true;
    campo.hidden = false;
}

// Data de nascimento não pode ser no futuro
document.getElementById('cad-nasc').max = new Date().toISOString().slice(0, 10);

// Contas de teste: preenchem o login
document.querySelectorAll('.contas-teste [data-email]').forEach(botao => {
    botao.addEventListener('click', () => {
        document.getElementById('login-email').value = botao.dataset.email;
        document.getElementById('login-senha').value = 'senha123';
        document.getElementById('login-senha').focus();
    });
});

// ---------- LOGIN ----------
document.getElementById('form-login').addEventListener('submit', async (e) => {
    e.preventDefault();
    esconderMensagem();
    const email = document.getElementById('login-email').value.trim();
    const senha = document.getElementById('login-senha').value;

    await comBotaoOcupado(e.target, 'Entrando…', async () => {
        try {
            const resposta = await api.login(email, senha);
            sessao.salvar(resposta.token, resposta.usuario);
            window.location.href = 'dashboard.html';
        } catch (err) {
            mostrarMensagem(err.message, 'error');
        }
    });
});

// ---------- CADASTRO ----------
// 1º passo: confere os dados e manda um código para o e-mail.
// 2º passo: com o código, cria a conta (o e-mail fica confirmado).
// Se o servidor não tiver e-mail configurado, cria a conta direto (como antes).
const formCadastro = document.getElementById('form-cadastro');
const formCodigo = document.getElementById('form-codigo-cadastro');
let cadastroPendente = null;

async function criarConta(dados) {
    const resposta = await api.cadastrar(dados);
    // O backend já devolve o token: a pessoa entra direto, sem digitar a senha de novo.
    sessao.salvar(resposta.token, resposta.usuario);
    mostrarMensagem('Conta criada! Abrindo o seu painel…', 'ok');
    setTimeout(() => { window.location.href = 'dashboard.html'; }, 600);
}

function mostrarPassoCodigo(resposta) {
    formCadastro.hidden = true;
    formCodigo.hidden = false;
    document.getElementById('cad-codigo-texto').textContent = resposta.mensagem;
    document.getElementById('cad-codigo').value = '';
    document.getElementById('cad-codigo').focus();
}

document.getElementById('cad-codigo').addEventListener('input', (e) => {
    e.target.value = e.target.value.replace(/\D/g, '').slice(0, 6);
});

document.getElementById('cad-voltar').addEventListener('click', () => {
    formCodigo.hidden = true;
    formCadastro.hidden = false;
    esconderMensagem();
});

document.getElementById('cad-reenviar').addEventListener('click', async (e) => {
    if (!cadastroPendente) return;
    esconderMensagem();
    const botao = e.currentTarget;
    botao.disabled = true;
    try {
        const resposta = await api.pedirCodigoCadastro(cadastroPendente);
        mostrarPassoCodigo(resposta);
        mostrarMensagem('Mandamos um código novo. Use só o último que chegar.', 'ok');
    } catch (err) {
        mostrarMensagem(err.message, 'error');
    } finally {
        botao.disabled = false;
    }
});

formCodigo.addEventListener('submit', async (e) => {
    e.preventDefault();
    esconderMensagem();
    await comBotaoOcupado(e.target, 'Confirmando…', async () => {
        try {
            await criarConta({ ...cadastroPendente, codigo: document.getElementById('cad-codigo').value });
        } catch (err) {
            mostrarMensagem(err.message, 'error');
        }
    });
});

formCadastro.addEventListener('submit', async (e) => {
    e.preventDefault();
    esconderMensagem();

    const dados = {
        nome_completo: document.getElementById('cad-nome').value.trim(),
        email_institucional: document.getElementById('cad-email').value.trim(),
        data_nascimento: document.getElementById('cad-nasc').value,
        senha: document.getElementById('cad-senha').value,
    };
    const escola = document.getElementById('cad-escola');
    if (!document.getElementById('campo-escola').hidden && escola.value) dados.instituicao_id = Number(escola.value);

    await comBotaoOcupado(e.target, 'Enviando código…', async () => {
        try {
            const resposta = await api.pedirCodigoCadastro(dados);
            cadastroPendente = dados;
            if (resposta.modo === 'email') mostrarPassoCodigo(resposta);
            else await criarConta(dados);
        } catch (err) {
            mostrarMensagem(err.message, 'error');
        }
    });
});


// Abre a aba certa pelo endereço (entrar.html#cadastro) e pelos links "Crie agora" / "Entrar".
function abrirAba(nome) {
    if (nome === 'esqueci') { // painel sem botão de aba
        document.querySelectorAll('.tab-btn, .tab-panel').forEach(el => el.classList.remove('active'));
        document.getElementById('panel-esqueci').classList.add('active');
        esconderMensagem();
        const email = document.getElementById('login-email').value.trim();
        if (email.includes('@')) document.getElementById('esq-email').value = email;
        document.getElementById('esq-email').focus();
        return;
    }
    const botao = document.querySelector(`.tab-btn[data-tab="${nome}"]`);
    if (botao) botao.click();
}
document.querySelectorAll('[data-ir-para]').forEach(link => link.addEventListener('click', (e) => {
    e.preventDefault();
    abrirAba(link.dataset.irPara);
    history.replaceState(null, '', `#${link.dataset.irPara}`);
}));
window.addEventListener('hashchange', () => abrirAba(
    location.hash === '#cadastro' ? 'cadastro' : location.hash === '#esqueci' ? 'esqueci' : 'login'));
if (location.hash === '#cadastro' || location.hash === '#esqueci') abrirAba(location.hash.slice(1));

// ---------- ESQUECI MINHA SENHA ----------
// Manda o e-mail com o link; a senha nova é criada na página redefinir-senha.html.
document.getElementById('form-esqueci').addEventListener('submit', async (e) => {
    e.preventDefault();
    esconderMensagem();
    const email = document.getElementById('esq-email').value.trim();
    await comBotaoOcupado(e.target, 'Enviando…', async () => {
        try {
            const resposta = await api.esqueciSenha(email);
            mostrarMensagem(resposta.mensagem, resposta.modo === 'coordenacao' ? 'aviso' : 'ok');
            document.getElementById('esq-enviado').hidden = resposta.modo !== 'email';
        } catch (err) {
            mostrarMensagem(err.message, 'error');
        }
    });
});

// As contas de teste (senha conhecida) só aparecem rodando no próprio computador.
// Se o site for publicado num endereço de verdade, o quadro some.
if (!['127.0.0.1', 'localhost', ''].includes(location.hostname)) {
    const contasTeste = document.querySelector('.contas-teste');
    if (contasTeste) contasTeste.remove();
}
