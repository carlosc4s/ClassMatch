/* ============================================================================
   layout.js — cabeçalho, rodapé, tema claro/escuro, busca de usuários e notificações.
   Usado em todas as páginas: basta ter <header id="topo"> e <footer id="rodape">.
   ============================================================================ */
const CHAVE_TEMA = 'classmatch_tema';
const CONTATO = { email: 'classmatch0@gmail.com', telefone: '+55 11 91324-5005', whats: '5511913245005' };

function temaAtual() {
    return document.documentElement.dataset.tema === 'escuro' ? 'escuro' : 'claro';
}

function trocarTema() {
    const novo = temaAtual() === 'escuro' ? 'claro' : 'escuro';
    document.documentElement.dataset.tema = novo;
    try { localStorage.setItem(CHAVE_TEMA, novo); } catch (_) { /* navegador sem armazenamento */ }
    atualizarBotaoTema();
}

function atualizarBotaoTema() {
    const botao = document.getElementById('btn-tema');
    if (!botao) return;
    const escuro = temaAtual() === 'escuro';
    botao.replaceChildren(icone(escuro ? 'sol' : 'lua'));
    botao.title = escuro ? 'Mudar para o tema claro' : 'Mudar para o tema escuro';
    botao.setAttribute('aria-label', botao.title);
}

// As duas versões da logo ficam na página; o CSS mostra a do tema atual.
function logo(tipo, classe) {
    return [
        h('img', { src: `img/${tipo}-claro.png`, alt: 'ClassMatch', class: `${classe} so-claro` }),
        h('img', { src: `img/${tipo}-escuro.png`, alt: 'ClassMatch', class: `${classe} so-escuro` }),
    ];
}

function linkMenu(texto, href) {
    const aqui = location.pathname.split('/').pop() || 'index.html';
    const [pagina, ancora] = href.split('#');
    const atual = pagina === aqui && (!ancora ? !location.hash || location.hash === '#painel' : location.hash === `#${ancora}`);
    return h('a', { href, class: `link${atual ? ' atual' : ''}` }, texto);
}

function montarCabecalho() {
    const topo = document.getElementById('topo');
    if (!topo) return;
    const usuario = sessao.obter();
    const conversa = usuario && (usuario.tipo_usuario === 'aluno' || usuario.tipo_usuario === 'monitor');

    const menu = h('nav', { class: 'menu', id: 'menu', 'aria-label': 'Navegação principal' },
        linkMenu('Início', 'index.html'),
        usuario ? linkMenu('Dashboard', 'dashboard.html') : linkMenu('Como funciona', 'index.html#como-funciona'),
        conversa ? linkMenu('Matches', 'dashboard.html#matches') : null,
        conversa ? linkMenu('Mensagens', 'dashboard.html#mensagens') : null,
        linkMenu('Ajuda', 'ajuda.html'),
        usuario ? linkMenu('Perfil', 'dashboard.html#perfil') : linkMenu('Entrar', 'entrar.html'),
        usuario ? caixaBusca() : null,
        usuario ? h('a', { href: '#', class: 'link', onclick: (e) => { e.preventDefault(); sair(); } }, 'Sair') : null,
    );

    const acoes = h('div', { class: 'acoes-topo' },
        usuario ? h('div', { class: 'notif-caixa' },
            h('button', { type: 'button', class: 'icone-btn', id: 'btn-notif', 'aria-label': 'Notificações',
                'aria-expanded': 'false', onclick: alternarNotificacoes }, icone('sino'),
                h('span', { class: 'contador-notif', id: 'contador-notif', hidden: true })),
            h('div', { class: 'painel-notif', id: 'painel-notif', hidden: true })) : null,
        h('button', { type: 'button', class: 'icone-btn', id: 'btn-tema', onclick: trocarTema }),
        usuario ? h('a', { href: 'dashboard.html#perfil', class: 'avatar', title: 'Meu perfil' }, iniciais(usuario.nome_completo))
            : h('a', { href: 'entrar.html#cadastro', class: 'btn btn-primary btn-sm' }, 'Criar conta'),
        h('button', { type: 'button', class: 'icone-btn menu-btn', 'aria-label': 'Abrir menu', 'aria-controls': 'menu',
            onclick: (e) => {
                const aberto = document.getElementById('menu').classList.toggle('aberto');
                e.currentTarget.setAttribute('aria-expanded', String(aberto));
                e.currentTarget.replaceChildren(icone(aberto ? 'fechar' : 'menu'));
            } }, icone('menu')),
    );

    // O painel redesenha o cabeçalho ao trocar de aba: a busca aberta continua aberta com o que foi digitado.
    const buscaAntes = document.getElementById('painel-busca');
    const termoAntes = buscaAntes && !buscaAntes.hidden ? document.getElementById('busca-termo').value : null;
    const focoNaBusca = buscaAntes && buscaAntes.contains(document.activeElement);

    topo.className = 'topo';
    topo.replaceChildren(h('div', { class: 'topo-interno' },
        h('a', { href: 'index.html', class: 'marca', 'aria-label': 'ClassMatch — página inicial' },
            logo('simbolo', 'simbolo'), logo('texto', 'nome')),
        menu, acoes));
    // Fecha o menu do celular ao escolher um link
    menu.querySelectorAll('a').forEach(a => a.addEventListener('click', () => menu.classList.remove('aberto')));
    atualizarBotaoTema();
    if (usuario && termoAntes !== null) {
        document.getElementById('painel-busca').hidden = false;
        document.getElementById('btn-busca').setAttribute('aria-expanded', 'true');
        document.getElementById('busca-termo').value = termoAntes;
        if (focoNaBusca) document.getElementById('busca-termo').focus();
        procurarUsuarios(termoAntes);
    }
    if (usuario) iniciarNotificacoes();
}

function montarRodape() {
    const rodape = document.getElementById('rodape');
    if (!rodape) return;
    rodape.className = 'rodape';
    rodape.replaceChildren(
        h('div', { class: 'rodape-interno' },
            h('div', null,
                h('img', { src: 'img/texto-escuro.png', alt: 'CLASS MATCH' }),
                h('p', { class: 'rodape-lema' }, 'Aprenda • Ensine • Conecte-se')),
            h('div', null,
                h('h3', null, 'Links'),
                h('a', { href: 'index.html' }, 'Início'),
                h('a', { href: 'ajuda.html' }, 'Ajuda'),
                h('a', { href: 'ajuda.html#contato' }, 'Contato')),
            h('div', null,
                h('h3', null, 'Contato'),
                h('a', { href: `mailto:${CONTATO.email}` }, icone('email'), ` ${CONTATO.email}`),
                h('a', { href: `https://wa.me/${CONTATO.whats}`, target: '_blank', rel: 'noopener' }, icone('telefone'), ` ${CONTATO.telefone}`))),
        h('div', { class: 'rodape-base' },
            h('span', null, `© ${new Date().getFullYear()} ClassMatch · versão 6.4`),
            h('span', null, 'Equipe Ceap')));
}

function sair() {
    sessao.limpar();
    window.location.href = 'index.html';
}

/* ---------------- Notificações (dados reais do backend) ---------------- */
const ICONES_NOTIF = { pedido: 'ajuda', match: 'alvo', mensagem: 'mensagem', monitoria: 'check', avaliacao: 'estrela', denuncia: 'bandeira', moderacao: 'alerta' };
let notificacoes = [];

async function carregarNotificacoes() {
    try {
        const dados = await api.notificacoes();
        notificacoes = dados.itens;
        const contador = document.getElementById('contador-notif');
        if (contador) {
            contador.textContent = dados.nao_lidas > 9 ? '9+' : String(dados.nao_lidas);
            contador.hidden = dados.nao_lidas === 0;
        }
        if (!document.getElementById('painel-notif').hidden) desenharNotificacoes();
    } catch (err) {
        if (err.status === 401) montarCabecalho(); // sessão acabou: volta a mostrar "Entrar"
    }
}

function desenharNotificacoes() {
    const painel = document.getElementById('painel-notif');
    const algumaNaoLida = notificacoes.some(n => !n.lida);
    painel.replaceChildren(
        h('div', { class: 'painel-notif-topo' },
            h('strong', null, 'Notificações'),
            algumaNaoLida ? h('button', { type: 'button', onclick: async () => {
                await api.marcarNotificacoes().catch(() => {});
                carregarNotificacoes();
            } }, 'Marcar todas como lidas') : null),
        h('div', { class: 'lista-notif' }, notificacoes.length ? notificacoes.map(n => {
            const abrir = async () => {
                if (!n.lida) await api.marcarNotificacoes([n.id]).catch(() => {});
                window.location.href = n.link || 'dashboard.html';
                if (location.pathname.endsWith('dashboard.html')) { fecharNotificacoes(); carregarNotificacoes(); }
            };
            return h('div', {
                class: `notif${n.lida ? '' : ' nao-lida'}`, role: 'button', tabindex: '0',
                onclick: abrir,
                onkeydown: (e) => { if ((e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget) { e.preventDefault(); abrir(); } },
            },
                h('span', { class: 'notif-icone' }, icone(ICONES_NOTIF[n.tipo] || 'sino')),
                h('span', { class: 'notif-texto' }, ...textoNotificacao(n), h('span', { class: 'notif-tempo' }, tempoAtras(n.data_criacao))),
            );
        }) : [h('div', { class: 'notif-vazia' }, 'Nada por aqui ainda. Avisamos quando algo acontecer.')]));
}

// O nome de quem causou o aviso ("Marina aceitou seu pedido...") vira um botão para o perfil dela.
function textoNotificacao(n) {
    const posicao = n.ator_id && n.ator_nome ? n.texto.indexOf(n.ator_nome) : -1;
    if (posicao < 0) return [n.texto];
    return [
        n.texto.slice(0, posicao),
        h('button', {
            type: 'button', class: 'notif-nome', title: `Ver o perfil de ${n.ator_nome}`,
            onclick: async (e) => {
                e.stopPropagation(); // não abre o link do aviso, só o perfil
                if (!n.lida) api.marcarNotificacoes([n.id]).then(carregarNotificacoes).catch(() => {});
                fecharNotificacoes();
                abrirPerfilUsuario(n.ator_id);
            },
        }, n.ator_nome),
        n.texto.slice(posicao + n.ator_nome.length),
    ];
}

// No painel abre a janela do perfil na hora; nas outras páginas vai para o painel e abre lá.
function abrirPerfilUsuario(usuarioId) {
    if (typeof verPerfil === 'function' && document.getElementById('dialogo-perfil')) {
        verPerfil(usuarioId);
    } else {
        window.location.href = `dashboard.html#usuario-${usuarioId}`;
    }
}

/* ---------------- Busca de usuários (lupa ao lado do "Sair") ---------------- */
let temporizadorBusca = null;
let buscaAtual = 0;

function caixaBusca() {
    return h('div', { class: 'busca-caixa' },
        h('button', { type: 'button', class: 'icone-btn', id: 'btn-busca', title: 'Procurar pessoas',
            'aria-label': 'Procurar pessoas', 'aria-expanded': 'false', 'aria-controls': 'painel-busca',
            onclick: alternarBusca }, icone('lupa')),
        h('div', { class: 'painel-busca', id: 'painel-busca', hidden: true },
            h('input', { type: 'search', id: 'busca-termo', placeholder: 'Procurar pelo nome…', maxlength: '60',
                autocomplete: 'off', spellcheck: 'false', 'aria-label': 'Nome da pessoa',
                oninput: (e) => {
                    clearTimeout(temporizadorBusca);
                    temporizadorBusca = setTimeout(() => procurarUsuarios(e.target.value), 250);
                },
                onkeydown: (e) => {
                    if (e.key === 'ArrowDown') { e.preventDefault(); const primeiro = document.querySelector('.busca-item'); if (primeiro) primeiro.focus(); }
                } }),
            h('div', { class: 'lista-busca', id: 'lista-busca', role: 'list' },
                h('div', { class: 'busca-dica' }, 'Digite pelo menos 2 letras do nome.'))));
}

function alternarBusca(e) {
    e.stopPropagation();
    const painel = document.getElementById('painel-busca');
    const abrir = painel.hidden;
    painel.hidden = !abrir;
    document.getElementById('btn-busca').setAttribute('aria-expanded', String(abrir));
    if (abrir) { fecharNotificacoes(); document.getElementById('busca-termo').focus(); }
}

function fecharBusca() {
    const painel = document.getElementById('painel-busca');
    if (!painel || painel.hidden) return;
    painel.hidden = true;
    document.getElementById('btn-busca').setAttribute('aria-expanded', 'false');
}

async function procurarUsuarios(termo) {
    const lista = document.getElementById('lista-busca');
    termo = termo.trim();
    if (termo.replace(/\s/g, '').length < 2) {
        lista.replaceChildren(h('div', { class: 'busca-dica' }, 'Digite pelo menos 2 letras do nome.'));
        return;
    }
    const minhaBusca = ++buscaAtual; // ignora respostas de buscas antigas (digitação rápida)
    lista.replaceChildren(h('div', { class: 'busca-dica' }, 'Procurando…'));
    try {
        const pessoas = await api.buscarUsuarios(termo);
        if (minhaBusca !== buscaAtual) return;
        lista.replaceChildren(...(pessoas.length ? pessoas.map(p => h('button', {
            type: 'button', class: 'busca-item', role: 'listitem',
            onclick: () => {
                fecharBusca();
                const menu = document.getElementById('menu');
                if (menu) menu.classList.remove('aberto'); // celular: fecha o menu aberto
                abrirPerfilUsuario(p.id);
            },
            onkeydown: (e) => {
                const alvo = e.key === 'ArrowDown' ? e.currentTarget.nextElementSibling : e.key === 'ArrowUp' ? e.currentTarget.previousElementSibling : null;
                if (alvo) { e.preventDefault(); alvo.focus(); }
                else if (e.key === 'ArrowUp') { e.preventDefault(); document.getElementById('busca-termo').focus(); }
            },
        },
            h('span', { class: 'avatar pequeno', 'aria-hidden': 'true' }, iniciais(p.nome_completo)),
            h('span', { class: 'busca-info' },
                h('strong', null, p.nome_completo, p.eu ? ' (você)' : ''),
                h('span', { class: 'busca-detalhe' }, TIPOS[p.tipo_usuario] || p.tipo_usuario,
                    p.reputacao_media != null ? ` · ★ ${Number(p.reputacao_media).toFixed(1).replace('.', ',')}` : '',
                    p.status_conta === 'banido' ? ' · conta suspensa' : '')),
        )) : [h('div', { class: 'busca-dica' }, 'Ninguém da sua escola com esse nome.')]));
    } catch (err) {
        if (minhaBusca === buscaAtual) lista.replaceChildren(h('div', { class: 'busca-dica' }, err.message));
    }
}

function alternarNotificacoes() {
    const painel = document.getElementById('painel-notif');
    const abrir = painel.hidden;
    painel.hidden = !abrir;
    document.getElementById('btn-notif').setAttribute('aria-expanded', String(abrir));
    if (abrir) { fecharBusca(); desenharNotificacoes(); }
}

function fecharNotificacoes() {
    const painel = document.getElementById('painel-notif');
    if (painel) painel.hidden = true;
}

let notificacoesIniciadas = false;
function iniciarNotificacoes() {
    carregarNotificacoes();
    if (notificacoesIniciadas) return;
    notificacoesIniciadas = true;
    setInterval(() => { if (!document.hidden && sessao.obter()) carregarNotificacoes(); }, 15000);
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.notif-caixa')) fecharNotificacoes();
        if (!e.target.closest('.busca-caixa')) fecharBusca();
    });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { fecharNotificacoes(); fecharBusca(); } });
}

montarCabecalho();
montarRodape();
colocarIcones();
