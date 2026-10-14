/* ============================================================================
   api.js — A PONTE entre este front-end (HTML/CSS/JS) e o banco de dados.
   ============================================================================
   O navegador NUNCA fala diretamente com o MySQL. Ele fala com o servidor
   Flask (backend/app.py) por HTTP, usando fetch(). O Flask é quem tem o
   usuário/senha do banco e quem executa o SQL. Este arquivo só empacota
   essas chamadas HTTP para o resto do front-end usar de forma simples.

   Endereço da API (automático):
   - Site aberto pelo próprio Flask (http://127.0.0.1:5000) -> usa o mesmo endereço.
   - Site aberto pelo Live Server (porta 5500) ou por duplo clique no HTML
     -> usa http://127.0.0.1:5000. Se mudar a PORTA no backend/.env, mude
        API_ENDERECO_PADRAO abaixo também.

   Login: o backend devolve um "token" no login. Ele fica salvo no navegador e
   vai em toda chamada (cabeçalho Authorization). O servidor descobre quem é
   você pelo token — por isso ninguém consegue se passar por outra pessoa
   trocando um id na URL.
   ============================================================================ */

const API_ENDERECO_PADRAO = 'http://127.0.0.1:5000';

const CHAVE_TOKEN = 'classmatch_token';
const CHAVE_USUARIO = 'classmatch_user';
const CHAVE_RECADO = 'classmatch_recado';

class ErroApi extends Error {
    constructor(mensagem, status) {
        super(mensagem);
        this.status = status; // 0 = servidor fora do ar
    }
}

/* ---------- Descobre onde o Flask está (só na primeira chamada) ---------- */
let _baseApi = null;

function descobrirBase() {
    if (_baseApi) return _baseApi;
    _baseApi = (async () => {
        const liveServer = /^55\d\d$/.test(location.port); // Live Server usa 5500, 5501...
        if ((location.protocol === 'http:' || location.protocol === 'https:') && !liveServer) {
            try {
                const resposta = await fetch('/api/saude', { cache: 'no-store' });
                const dados = await resposta.json();
                if (dados && dados.app === 'classmatch') return ''; // o próprio Flask entregou o site
            } catch (_) { /* Live Server ou outra origem: usa o endereço padrão */ }
        }
        return API_ENDERECO_PADRAO;
    })();
    return _baseApi;
}

async function apiRequest(caminho, { method = 'GET', body = null } = {}) {
    const base = await descobrirBase();
    const opcoes = { method, headers: {}, cache: 'no-store' };
    const token = sessao.token();
    if (token) opcoes.headers.Authorization = `Bearer ${token}`;
    if (body instanceof FormData) {
        opcoes.body = body; // arquivo: o navegador monta o multipart sozinho
    } else if (body !== null) {
        opcoes.headers['Content-Type'] = 'application/json';
        opcoes.body = JSON.stringify(body);
    }

    let resposta;
    try {
        resposta = await fetch(`${base}/api${caminho}`, opcoes);
    } catch (_) {
        throw new ErroApi(
            'Não foi possível falar com o servidor. Confira se a janela do backend está aberta ' +
            '(duplo clique em backend/iniciar.bat) e recarregue a página.', 0);
    }

    let dados = null;
    try { dados = await resposta.json(); } catch (_) { /* corpo vazio ou não-JSON */ }

    if (!resposta.ok) {
        const mensagem = (dados && dados.erro) || `Erro ${resposta.status} na requisição.`;
        // Token vencido/inválido ou conta suspensa: volta para a tela de login.
        if (resposta.status === 401 && token && !caminho.startsWith('/login')) {
            sessao.limpar();
            sessionStorage.setItem(CHAVE_RECADO, mensagem);
            // Páginas públicas (início, ajuda, entrar) continuam abertas; o painel volta para o login.
            if (!/(index|ajuda|entrar|redefinir-senha)\.html$|\/$/.test(location.pathname)) location.replace('entrar.html');
        }
        throw new ErroApi(mensagem, resposta.status);
    }
    return dados;
}

const api = {
    saude: () => apiRequest('/saude'),
    escolas: () => apiRequest('/escolas'),

    pedirCodigoCadastro: (dados) => apiRequest('/cadastro/codigo', { method: 'POST', body: dados }),
    cadastrar: (dados) => apiRequest('/cadastro', { method: 'POST', body: dados }), // dados + codigo do e-mail
    login: (emailOuRa, senha) => apiRequest('/login', { method: 'POST', body: { email_institucional: emailOuRa, senha } }),
    eu: () => apiRequest('/eu'),

    listarMaterias: () => apiRequest('/materias'),

    // Aluno
    minhasSolicitacoes: () => apiRequest('/solicitacoes'),
    criarSolicitacao: (dados) => apiRequest('/solicitacoes', { method: 'POST', body: dados }),
    cancelarSolicitacao: (id) => apiRequest(`/solicitacoes/${id}/cancelar`, { method: 'POST' }),

    // Monitor
    solicitacoesPendentes: () => apiRequest('/solicitacoes/pendentes'),
    aceitarSolicitacao: (solicitacaoId) => apiRequest('/matches', { method: 'POST', body: { solicitacao_id: solicitacaoId } }),
    minhasMaterias: () => apiRequest('/monitor-materias'),
    adicionarMateriaMonitor: (dados) => apiRequest('/monitor-materias', { method: 'POST', body: dados }),
    removerMateriaMonitor: (id) => apiRequest(`/monitor-materias/${id}`, { method: 'DELETE' }),

    // Monitorias e chat (aluno e monitor)
    meusMatches: () => apiRequest('/matches'),
    concluirMatch: (matchId) => apiRequest(`/matches/${matchId}/concluir`, { method: 'POST' }),
    mensagens: (conversaId, depois = 0) => apiRequest(`/mensagens?conversa_id=${conversaId}&depois=${depois}`),
    enviarMensagem: (conversaId, conteudo) => apiRequest('/mensagens', { method: 'POST', body: { conversa_id: conversaId, conteudo } }),
    avaliar: (matchId, nota, comentario) => apiRequest('/avaliacoes', { method: 'POST', body: { match_id: matchId, nota, comentario } }),
    denunciar: (conversaId, motivo, denunciadoId = null) => apiRequest('/denuncias', {
        method: 'POST', body: denunciadoId ? { conversa_id: conversaId, motivo, denunciado_id: denunciadoId } : { conversa_id: conversaId, motivo } }),
    meetMonitoria: (matchId, link) => apiRequest(`/matches/${matchId}/meet`, { method: 'PUT', body: { link } }),

    // Aulas em grupo
    aulas: () => apiRequest('/aulas'),
    criarAula: (dados) => apiRequest('/aulas', { method: 'POST', body: dados }),
    inscreverAula: (id) => apiRequest(`/aulas/${id}/inscricao`, { method: 'POST' }),
    sairAula: (id) => apiRequest(`/aulas/${id}/inscricao`, { method: 'DELETE' }),
    meetAula: (id, link) => apiRequest(`/aulas/${id}/meet`, { method: 'PUT', body: { link } }),
    statusAula: (id, status) => apiRequest(`/aulas/${id}/status`, { method: 'POST', body: { status } }),

    // Senhas
    esqueciSenha: (email) => apiRequest('/senha/esqueci', { method: 'POST', body: { email } }),
    linkSenha: (token) => apiRequest(`/senha/link?token=${encodeURIComponent(token)}`),
    redefinirSenha: (dados) => apiRequest('/senha/redefinir', { method: 'POST', body: dados }),
    trocarSenha: (senhaAtual, novaSenha) => apiRequest('/senha', { method: 'PUT', body: { senha_atual: senhaAtual, nova_senha: novaSenha } }),
    redefinirSenhaUsuario: (identificacao) => apiRequest('/coordenacao/redefinir-senha', { method: 'POST', body: { identificacao } }),

    // Perfil e notificações
    perfil: () => apiRequest('/perfil'),
    verPerfil: (usuarioId) => apiRequest(`/perfil/${usuarioId}`),
    editarPerfil: (dados) => apiRequest('/perfil', { method: 'PUT', body: dados }),
    buscarUsuarios: (termo) => apiRequest(`/usuarios/busca?q=${encodeURIComponent(termo)}`),
    pedirCodigoExclusao: (senha) => apiRequest('/conta/excluir/codigo', { method: 'POST', body: { senha } }),
    excluirConta: (senha, codigo) => apiRequest('/conta/excluir', { method: 'POST', body: { senha, codigo } }),
    notificacoes: () => apiRequest('/notificacoes'),
    marcarNotificacoes: (ids = null) => apiRequest('/notificacoes/lidas', { method: 'POST', body: ids ? { ids } : {} }),

    // Coordenação
    painelCoordenacao: () => apiRequest('/painel'),
    moderarDenuncia: (denunciaId, acao, motivo) => apiRequest(`/denuncias/${denunciaId}/moderar`, { method: 'POST', body: { acao, motivo } }),
    reativarUsuario: (usuarioId) => apiRequest(`/usuarios/${usuarioId}/desbanir`, { method: 'POST' }),
};

/* ---------- Sessão no navegador (token + dados de quem está logado) ---------- */
const sessao = {
    salvar(token, usuario) {
        localStorage.setItem(CHAVE_TOKEN, token);
        localStorage.setItem(CHAVE_USUARIO, JSON.stringify(usuario));
    },
    atualizarUsuario(usuario) {
        localStorage.setItem(CHAVE_USUARIO, JSON.stringify(usuario));
    },
    token() {
        return localStorage.getItem(CHAVE_TOKEN);
    },
    obter() {
        if (!this.token()) return null; // sessão da versão antiga (sem token) não vale mais
        try { return JSON.parse(localStorage.getItem(CHAVE_USUARIO)); } catch (_) { return null; }
    },
    limpar() {
        localStorage.removeItem(CHAVE_TOKEN);
        localStorage.removeItem(CHAVE_USUARIO);
    },
};

/* ---------- Utilidades de tela usadas pelo login e pelo painel ---------- */

// Cria elementos sem innerHTML: o texto digitado pelos usuários nunca vira HTML.
function h(tag, atributos, ...filhos) {
    const el = document.createElement(tag);
    for (const [nome, valor] of Object.entries(atributos || {})) {
        if (valor === null || valor === undefined || valor === false) continue;
        if (nome === 'class') el.className = valor;
        else if (nome.startsWith('on') && typeof valor === 'function') el.addEventListener(nome.slice(2), valor);
        else if (valor === true) el.setAttribute(nome, '');
        else el.setAttribute(nome, valor);
    }
    for (const filho of filhos.flat()) {
        if (filho === null || filho === undefined || filho === false) continue;
        el.append(filho instanceof Node ? filho : document.createTextNode(String(filho)));
    }
    return el;
}

/* Ícones em SVG (traço, herdam a cor do texto). No JS: icone('sino').
   No HTML: <i data-icone="sino"></i> (o layout.js troca pelo desenho). */
const ICONES = {
    sino: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    sol: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
    lua: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
    lupa: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    lixeira: '<path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M10 11v6M14 11v6"/>',
    fechar: '<path d="M18 6 6 18M6 6l12 12"/>',
    clipe: '<path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/>',
    microfone: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M19 10v1a7 7 0 0 1-14 0v-1M12 18v4"/>',
    enviar: '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
    parar: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    alvo: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    mensagem: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    estrela: '<path d="m12 2 3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/>',
    bandeira: '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><path d="M4 22v-7"/>',
    alerta: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4M12 17h.01"/>',
    livro: '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    usuario: '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    usuarios: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    novoUsuario: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M19 8v6M22 11h-6"/>',
    grafico: '<path d="M3 3v18h18"/><path d="M18 17V9M13 17V5M8 17v-3"/>',
    ajuda: '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3M12 17h.01"/>',
    lampada: '<path d="M9 18h6M10 22h4"/><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14"/>',
    lapis: '<path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>',
    lista: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    arquivo: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>',
    imagem: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.09-3.09a2 2 0 0 0-2.82 0L6 21"/>',
    audio: '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
    cadeado: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    video: '<path d="m16 13 5.22 3.48a.5.5 0 0 0 .78-.42V7.94a.5.5 0 0 0-.78-.42L16 11"/><rect x="2" y="6" width="14" height="12" rx="2"/>',
    escudo: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    casa: '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/>',
    email: '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/>',
    telefone: '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/>',
};

function icone(nome) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('class', 'icone');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    svg.innerHTML = ICONES[nome] || '';
    return svg;
}

function colocarIcones(raiz = document) {
    raiz.querySelectorAll('i[data-icone]').forEach(marca => marca.replaceWith(icone(marca.dataset.icone)));
}

const NIVEIS = { basico: 'Básico', intermediario: 'Intermediário', avancado: 'Avançado' };
const TIPOS = { aluno: 'Estudante', monitor: 'Estudante', coordenador: 'Coordenação', admin: 'Administração' };

function iniciais(nome) {
    const partes = String(nome || '?').trim().split(/\s+/);
    return ((partes[0] || '?')[0] + (partes.length > 1 ? partes[partes.length - 1][0] : '')).toUpperCase();
}

function tamanhoArquivo(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1).replace('.', ',')} MB`;
}

function tempoAtras(iso) {
    const segundos = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (segundos < 60) return 'agora';
    if (segundos < 3600) return `há ${Math.floor(segundos / 60)} min`;
    if (segundos < 86400) return `há ${Math.floor(segundos / 3600)} h`;
    return formatarData(iso, false);
}

function formatarData(iso, comHora = true) {
    if (!iso) return '';
    const data = new Date(iso);
    if (Number.isNaN(data.getTime())) return '';
    const dia = data.toLocaleDateString('pt-BR');
    return comHora ? `${dia} ${data.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}` : dia;
}
