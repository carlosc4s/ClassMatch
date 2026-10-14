/* ============================================================================
   dashboard.js — painel do ClassMatch
   Um arquivo para os três tipos de conta:
   - aluno:        pede ajuda, acompanha os pedidos, conversa com o monitor
   - monitor:      escolhe as matérias que ensina, aceita pedidos, conversa
   - coordenação:  números da escola, defasagem por matéria, denúncias
   Tudo que aparece na tela vem do backend Flask (api.js).
   ============================================================================ */

const usuario = sessao.obter();
if (!usuario) window.location.replace('entrar.html');

const $ = (id) => document.getElementById(id);
const tipo = usuario ? usuario.tipo_usuario : '';
// Todo estudante aprende E ensina (o papel é escolhido em cada monitoria).
const ehEstudante = tipo === 'aluno' || tipo === 'monitor';
const ehAluno = ehEstudante;
const ehMonitor = ehEstudante;
const CHAVE_MODO = 'classmatch_modo';
const ehCoordenacao = tipo === 'coordenador' || tipo === 'admin';
const movimentoReduzido = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const STATUS = {
    // pedidos
    pendente: 'Esperando monitor', em_match: 'Em monitoria', atendida: 'Atendida', cancelada: 'Cancelada',
    // monitorias
    aceito: 'Em andamento', concluido: 'Concluída', cancelado: 'Cancelada', recusado: 'Recusada', proposto: 'Proposta',
    // denúncias
    em_analise: 'Em análise', resolvida: 'Resolvida', arquivada: 'Arquivada',
    // contas
    ativo: 'Ativa', advertido: 'Advertida', banido: 'Suspensa',
};

// Denúncias usam "pendente" com outro sentido: para analisar, não esperando monitor.
const STATUS_DENUNCIA = { pendente: 'Para analisar', em_analise: 'Em análise', resolvida: 'Resolvida', arquivada: 'Arquivada' };

function selo(status, rotulos = STATUS) {
    return h('span', { class: `badge ${status}` }, rotulos[status] || STATUS[status] || status);
}

const PAPEL = { aluno: 'aluno', monitor: 'monitor', coordenador: 'coordenação', admin: 'administração' };

function plural(n, singular, pluralTexto) {
    return `${n} ${n === 1 ? singular : pluralTexto}`;
}

/* ---------------- Avisos na tela ---------------- */
let temporizadorToast = null;
function avisar(texto, tipoAviso = 'ok') {
    const toast = $('toast');
    toast.textContent = texto;
    toast.className = `msg toast show ${tipoAviso}`;
    clearTimeout(temporizadorToast);
    temporizadorToast = setTimeout(() => { toast.className = 'msg toast'; }, tipoAviso === 'ok' ? 3500 : 7000);
}

// Executa uma carga de dados; se o servidor/banco cair, mostra a faixa no topo.
async function executar(tarefa, { silencioso = false } = {}) {
    try {
        await tarefa();
        $('faixa-servidor').hidden = true;
        return true;
    } catch (err) {
        if (err.status === 0 || err.status === 503) {
            $('faixa-servidor').textContent = err.message;
            $('faixa-servidor').hidden = false;
        } else if (err.status !== 401 && !silencioso) {
            avisar(err.message, 'error');
        }
        if (!(err instanceof ErroApi)) console.error(err);
        return false;
    }
}

// Evita duas cargas iguais ao mesmo tempo (atualização automática + clique).
function semSobreposicao(funcao) {
    let rodando = null;
    return (...args) => {
        if (!rodando) rodando = funcao(...args).finally(() => { rodando = null; });
        return rodando;
    };
}

function repetir(funcao, milissegundos) {
    setInterval(() => { if (!document.hidden) funcao(); }, milissegundos);
}

// Botão desativado enquanto a ação roda (evita clique duplo).
async function comBotao(botao, tarefa) {
    if (botao) botao.disabled = true;
    try { return await tarefa(); } finally { if (botao) botao.disabled = false; }
}

/* ---------------- Janela de confirmação (reaproveitada) ---------------- */
function perguntar({ titulo, texto = '', campo = null, minimo = 0, botao = 'Confirmar', perigo = false, opcoes = null, rotuloOpcoes = '' }) {
    const dialogo = $('dialogo');
    if (typeof dialogo.showModal !== 'function') {
        if (opcoes) return Promise.resolve(null);
        // Navegador muito antigo: usa as caixas padrão.
        if (campo) {
            const valor = window.prompt(`${titulo}\n\n${texto}\n\n${campo}`);
            return Promise.resolve(valor === null ? null : valor.trim());
        }
        return Promise.resolve(window.confirm(`${titulo}\n\n${texto}`) ? '' : null);
    }

    $('dialogo-titulo').textContent = titulo;
    $('dialogo-texto').textContent = texto;
    $('dialogo-texto').hidden = !texto;
    const entrada = $('dialogo-entrada');
    $('dialogo-campo').hidden = !campo;
    $('dialogo-rotulo').textContent = campo || '';
    entrada.value = '';
    $('dialogo-campo-opcoes').hidden = !opcoes;
    if (opcoes) {
        $('dialogo-rotulo-opcoes').textContent = rotuloOpcoes;
        $('dialogo-opcoes').replaceChildren(...opcoes.map(o => h('option', { value: o.valor }, o.texto)));
    }
    entrada.required = Boolean(campo) && minimo > 0;
    entrada.minLength = campo && minimo > 0 ? minimo : 0;
    const confirmar = $('dialogo-confirmar');
    confirmar.textContent = botao;
    confirmar.className = `btn ${perigo ? 'btn-perigo-cheio' : 'btn-primary'}`;

    return new Promise((resolver) => {
        dialogo.returnValue = '';
        dialogo.addEventListener('close', () => {
            if (dialogo.returnValue !== 'ok') resolver(null);
            else resolver(opcoes ? { texto: entrada.value.trim(), opcao: $('dialogo-opcoes').value } : entrada.value.trim());
        }, { once: true });
        dialogo.showModal();
        (campo ? entrada : confirmar).focus();
    });
}
$('dialogo-cancelar').addEventListener('click', () => $('dialogo').close(''));

/* ---------------- Cabeçalho, sair e advertência ---------------- */
const SUBTITULOS = {
    aluno: 'Escolha abaixo: aprender, ensinar ou os dois.',
    monitor: 'Escolha abaixo: aprender, ensinar ou os dois.',
    coordenador: 'Acompanhe a escola, as denúncias e os monitores.',
    admin: 'Acompanhe a escola, as denúncias e os monitores.',
};

function preencherCabecalho(dados) {
    $('ola-nome').textContent = (dados.nome_completo || '').split(' ')[0];
    $('ola-sub').textContent = SUBTITULOS[dados.tipo_usuario] || '';
    $('user-tipo').textContent = TIPOS[dados.tipo_usuario] || dados.tipo_usuario;
}

function mostrarAdvertencia(dados) {
    const adv = dados.ultima_advertencia;
    const faixa = $('faixa-advertencia');
    if (dados.status_conta !== 'advertido' || !adv) { faixa.hidden = true; return; }
    const chave = `classmatch_adv_${dados.id}`;
    if (localStorage.getItem(chave) === String(adv.data_acao)) return; // já foi lida
    $('faixa-advertencia-texto').textContent =
        `A coordenação registrou uma advertência na sua conta em ${formatarData(adv.data_acao, false)}: ` +
        `"${adv.motivo || 'comportamento inadequado no chat'}". Novas denúncias podem suspender a conta.`;
    faixa.hidden = false;
    $('faixa-advertencia-fechar').onclick = () => {
        localStorage.setItem(chave, String(adv.data_acao));
        faixa.hidden = true;
    };
}

/* ---------------- Matérias (dropdowns) ---------------- */
let materias = [];

async function carregarMaterias() {
    materias = await api.listarMaterias();
}

// Monta o <select> agrupado por área. O aluno vê quantos monitores cada matéria tem.
function preencherSelectMaterias(selectId, mostrarMonitores) {
    const select = $(selectId);
    const selecionada = select.value;
    const grupos = new Map();
    for (const m of materias) {
        const area = m.area || 'Outras';
        if (!grupos.has(area)) grupos.set(area, []);
        let rotulo = m.nome;
        if (mostrarMonitores) {
            rotulo += m.total_monitores ? ` (${plural(m.total_monitores, 'monitor', 'monitores')})` : ' (sem monitor ainda)';
        }
        grupos.get(area).push(h('option', { value: m.id }, rotulo));
    }
    select.replaceChildren(...[...grupos].map(([area, opcoes]) => h('optgroup', { label: area }, opcoes)));
    if (selecionada) select.value = selecionada;
}

/* ============================================================================
   ALUNO
   ============================================================================ */
let solicitacoesConhecidas = null; // id -> status (para avisar quando um monitor aceitar)

function atualizarDicaMateria() {
    const materia = materias.find(m => String(m.id) === $('sol-materia').value);
    const dica = $('sol-dica');
    if (!materia) { dica.textContent = ''; return; }
    dica.textContent = materia.total_monitores
        ? `${plural(materia.total_monitores, 'monitor(a) da sua escola ensina', 'monitores da sua escola ensinam')} esta matéria.`
        : 'Ninguém ensina esta matéria ainda. O pedido fica esperando até um monitor se cadastrar nela.';
}

function atualizarContador() {
    $('sol-contador').textContent = `${$('sol-desc').value.length}/500`;
}

async function enviarSolicitacao(e) {
    e.preventDefault();
    const form = e.target;
    const dados = {
        materia_id: Number($('sol-materia').value),
        nivel_dificuldade: $('sol-nivel').value,
        descricao_duvida: $('sol-desc').value.trim(),
    };
    await comBotao(form.querySelector('button[type="submit"]'), () => executar(async () => {
        const resposta = await api.criarSolicitacao(dados);
        $('sol-desc').value = '';
        atualizarContador();
        if (resposta.aviso) avisar(resposta.aviso, 'aviso');
        else avisar('Pedido enviado! Ele aparece para os monitores dessa matéria.');
        await carregarMinhasSolicitacoes();
    }));
}

const carregarMinhasSolicitacoes = semSobreposicao(async () => {
    const lista = await api.minhasSolicitacoes();
    const box = $('lista-solicitacoes');
    const abertas = lista.filter(s => s.status === 'pendente').length;
    $('count-solicitacoes').textContent = plural(lista.length, 'pedido', 'pedidos') +
        (abertas ? `, ${abertas} esperando` : '');

    // Aviso quando um pedido que estava esperando foi aceito.
    if (solicitacoesConhecidas) {
        for (const s of lista) {
            if (solicitacoesConhecidas.get(s.id) === 'pendente' && s.status === 'em_match') {
                avisar(`${s.monitor_nome} aceitou seu pedido de ${s.materia_nome}. O chat já está aberto.`);
                carregarMeusMatches().catch(() => {});
            }
        }
    }
    solicitacoesConhecidas = new Map(lista.map(s => [s.id, s.status]));

    if (lista.length === 0) {
        box.replaceChildren(h('div', { class: 'empty-state' },
            'Você ainda não pediu ajuda em nenhuma matéria. Use o formulário acima.'));
        return;
    }

    box.replaceChildren(...lista.map(s => h('div', { class: 'item' },
        h('div', { class: 'item-top' },
            h('span', { class: 'item-title' }, s.materia_nome),
            selo(s.status)),
        h('div', { class: 'item-meta' },
            `Nível ${NIVEIS[s.nivel_dificuldade].toLowerCase()} · ${formatarData(s.data_criacao)}`,
            s.monitor_nome ? ` · monitor(a): ${s.monitor_nome}` : ''),
        s.descricao_duvida ? h('p', { class: 'item-texto' }, s.descricao_duvida) : null,
        (s.status === 'pendente' || s.conversa_id) ? h('div', { class: 'item-actions' },
            s.conversa_id ? h('button', {
                type: 'button', class: 'btn btn-accent btn-sm',
                onclick: () => abrirChat(s.conversa_id, true),
            }, s.status === 'em_match' ? 'Abrir conversa' : 'Ver conversa') : null,
            s.status === 'pendente' ? h('button', {
                type: 'button', class: 'btn btn-ghost btn-sm',
                onclick: (ev) => cancelarSolicitacao(s, ev.currentTarget),
            }, 'Cancelar pedido') : null,
        ) : null,
    )));
});

async function cancelarSolicitacao(s, botao) {
    const ok = await perguntar({
        titulo: 'Cancelar este pedido?',
        texto: `O pedido de ${s.materia_nome} some da lista dos monitores.`,
        botao: 'Cancelar pedido',
    });
    if (ok === null) return;
    await comBotao(botao, () => executar(async () => {
        const resposta = await api.cancelarSolicitacao(s.id);
        avisar(resposta.mensagem);
        await carregarMinhasSolicitacoes();
    }));
}

/* ============================================================================
   MONITOR
   ============================================================================ */
let pendentesConhecidos = null;

async function adicionarMinhaMateria(e) {
    e.preventDefault();
    const dados = {
        materia_id: Number($('mm-materia').value),
        nivel_conhecimento: $('mm-nivel').value,
    };
    await comBotao(e.target.querySelector('button[type="submit"]'), () => executar(async () => {
        const resposta = await api.adicionarMateriaMonitor(dados);
        avisar(resposta.mensagem);
        await carregarMinhasMaterias();
        await carregarPendentes();
    }));
}

async function carregarMinhasMaterias() {
    const lista = await api.minhasMaterias();
    preencherMateriasAula(lista);
    const box = $('lista-minhas-materias');
    if (lista.length === 0) {
        box.replaceChildren(h('div', { class: 'empty-state' },
            'Adicione as matérias em que você pode ajudar outros alunos. Os pedidos delas aparecem logo abaixo.'));
        return;
    }
    box.replaceChildren(...lista.map(m => h('span', { class: 'chip' },
        h('span', null, m.materia_nome, h('span', { class: 'chip-nivel' }, NIVEIS[m.nivel_conhecimento])),
        h('button', {
            type: 'button', class: 'chip-remover', title: `Parar de ensinar ${m.materia_nome}`,
            'aria-label': `Parar de ensinar ${m.materia_nome}`,
            onclick: (ev) => removerMinhaMateria(m, ev.currentTarget),
        }, '×'),
    )));
}

async function removerMinhaMateria(m, botao) {
    const ok = await perguntar({
        titulo: `Parar de ensinar ${m.materia_nome}?`,
        texto: 'Os pedidos dessa matéria deixam de aparecer para você. As conversas que já existem continuam.',
        botao: 'Remover matéria',
    });
    if (ok === null) return;
    await comBotao(botao, () => executar(async () => {
        const resposta = await api.removerMateriaMonitor(m.id);
        avisar(resposta.mensagem);
        await carregarMinhasMaterias();
        await carregarPendentes();
    }));
}

const carregarPendentes = semSobreposicao(async () => {
    const lista = await api.solicitacoesPendentes();
    const box = $('lista-pendentes');
    $('count-pendentes').textContent = `${lista.length} ${lista.length === 1 ? 'disponível' : 'disponíveis'}`;

    if (pendentesConhecidos) {
        const novos = lista.filter(s => !pendentesConhecidos.has(s.id));
        if (novos.length === 1) avisar(`Novo pedido de ajuda em ${novos[0].materia_nome}.`);
        else if (novos.length > 1) avisar(`${novos.length} novos pedidos de ajuda nas suas matérias.`);
    }
    pendentesConhecidos = new Set(lista.map(s => s.id));

    if (lista.length === 0) {
        box.replaceChildren(h('div', { class: 'empty-state' },
            'Nenhum pedido esperando nas suas matérias agora. Esta lista se atualiza sozinha.'));
        return;
    }

    box.replaceChildren(...lista.map(s => h('div', { class: 'item card-match' },
        h('div', { class: 'item-top' },
            h('div', null,
                h('div', { class: 'rotulo-match' }, icone('alvo'), ' POSSÍVEL MATCH'),
                h('div', { class: 'item-title' }, s.aluno_nome)),
            h('span', { class: 'badge' }, formatarData(s.data_criacao))),
        h('div', { class: 'info-match' },
            h('span', null, `Quer aprender: ${s.materia_nome}`),
            h('span', null, `Dúvida: ${NIVEIS[s.nivel_dificuldade]}`),
            h('span', null, `Seu nível: ${NIVEIS[s.meu_nivel]}`)),
        s.descricao_duvida ? h('p', { class: 'item-texto' }, s.descricao_duvida) : null,
        h('div', { class: 'item-actions' },
            h('button', { type: 'button', class: 'btn btn-ghost btn-sm', onclick: () => verPerfil(s.aluno_id) }, 'Ver perfil'),
            h('button', {
                type: 'button', class: 'btn btn-primary btn-sm',
                onclick: (ev) => aceitarPedido(s, ev.currentTarget),
            }, 'Aceitar e conversar'),
            h('span', { class: `compat${s.score >= 85 ? ' compat-alta' : ''}` },
                h('span', { class: 'barra', 'aria-hidden': 'true' },
                    h('span', { class: 'barra-cheia', style: `width:${s.score}%` })),
                `${s.score}% compatível`),
        ),
    )));
});

async function aceitarPedido(s, botao) {
    let conversaNova = null;
    await comBotao(botao, () => executar(async () => {
        const resposta = await api.aceitarSolicitacao(s.id);
        conversaNova = resposta.conversa_id;
        avisar(`Pedido aceito! O chat com ${s.aluno_nome} está aberto.`);
    }));
    // Atualiza as listas de qualquer jeito (se outro monitor aceitou antes, o pedido some).
    await executar(carregarPendentes, { silencioso: true });
    await executar(carregarMeusMatches, { silencioso: true });
    if (conversaNova) abrirChat(conversaNova, true);
}

/* ============================================================================
   MONITORIAS + CHAT (aluno e monitor)
   ============================================================================ */
let matches = [];
// ultimoId: maior id que o SERVIDOR já mandou (base do "depois="); ids: o que já está na tela.
const chat = { conversaId: null, matchId: null, ultimoId: 0, ids: new Set(), versao: 0, encerrada: false };
const CHAVE_LIDAS = `classmatch_lidas_${usuario ? usuario.id : 0}`;

function lidas() {
    try { return JSON.parse(localStorage.getItem(CHAVE_LIDAS)) || {}; } catch (_) { return {}; }
}
function marcarLida(conversaId, mensagemId) {
    const mapa = lidas();
    if ((mapa[conversaId] || 0) >= mensagemId) return;
    mapa[conversaId] = mensagemId;
    localStorage.setItem(CHAVE_LIDAS, JSON.stringify(mapa));
}

const carregarMeusMatches = semSobreposicao(async () => {
    matches = await api.meusMatches();
    const box = $('lista-matches');
    const ativas = matches.filter(m => m.status === 'aceito').length;
    $('count-matches').textContent = plural(matches.length, 'monitoria', 'monitorias') +
        (ativas ? `, ${ativas} em andamento` : '');

    if (matches.length === 0) {
        box.replaceChildren(h('div', { class: 'empty-state' },
            'Quando alguém aceitar um pedido seu, você aceitar um pedido ou entrar numa aula em grupo, a conversa aparece aqui.'));
    } else {
        const mapaLidas = lidas();
        box.replaceChildren(...matches.map(m => {
            const naoLida = m.ultima_mensagem_id && m.ultima_remetente_id !== usuario.id &&
                m.ultima_mensagem_id > (mapaLidas[m.conversa_id] || 0) && m.conversa_id !== chat.conversaId;
            const faltaAvaliar = m.status === 'concluido' && !m.ja_avaliei;
            return h('div', {
                class: `item item-clicavel${m.conversa_id === chat.conversaId ? ' ativo' : ''}`,
                role: 'button', tabindex: '0', 'data-conversa': m.conversa_id,
                'aria-label': `Abrir conversa de ${m.materia_nome} com ${m.com_quem}`,
                onclick: () => abrirChat(m.conversa_id),
                onkeydown: (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); abrirChat(m.conversa_id); } },
            },
                h('div', { class: 'item-top' },
                    h('span', { class: 'item-title' }, m.tipo === 'aula' ? `Aula em grupo: ${m.titulo}` : m.materia_nome),
                    selo(m.status)),
                h('div', { class: 'item-meta' },
                    h('span', { class: 'badge azul' }, m.meu_papel === 'monitor' ? 'Você ensina' : 'Você aprende'), ' ',
                    m.tipo === 'aula' ? `${m.materia_nome} · ${formatarData(m.data_hora)} · ${m.com_quem}` : `com ${m.com_quem}`),
                (naoLida || faltaAvaliar) ? h('div', { class: 'item-sinais' },
                    naoLida ? h('span', { class: 'sinal sinal-novo' }, 'Mensagem nova') : null,
                    faltaAvaliar ? h('span', { class: 'sinal' }, 'Falta avaliar') : null,
                ) : null,
            );
        }));
    }
    if (chat.conversaId) atualizarEstadoChat();
});

async function abrirChat(conversaId, rolarAte = false) {
    let m = matches.find(x => x.conversa_id === conversaId);
    if (!m) {
        await executar(carregarMeusMatches);
        m = matches.find(x => x.conversa_id === conversaId);
        if (!m) return;
    }
    chat.conversaId = conversaId;
    chat.matchId = m.id;
    chat.ultimoId = 0;
    chat.ids = new Set();
    chat.versao += 1;
    chat.encerrada = m.status !== 'aceito';
    $('btn-perfil-conversa').onclick = () => verPerfil(m.meu_papel === 'aluno' ? m.monitor_id : m.aluno_id);
    $('btn-perfil-conversa').hidden = m.tipo === 'aula' && m.meu_papel === 'monitor';
    marcarNotificacoesDaConversa(conversaId);

    $('chat-box').hidden = false;
    $('chat-vazio').hidden = true;
    $('chat-titulo').textContent = m.tipo === 'aula' ? `Aula em grupo: ${m.titulo}` : m.materia_nome;
    $('chat-subtitulo').textContent = m.tipo === 'aula'
        ? `${m.materia_nome} · ${formatarData(m.data_hora)} · ${m.inscritos} de ${m.vagas} vagas`
        : `com ${m.com_quem} · dúvida de nível ${NIVEIS[m.nivel_dificuldade].toLowerCase()}`;
    $('chat-messages').replaceChildren();
    document.querySelectorAll('#lista-matches .item-clicavel').forEach(item => {
        const esta = Number(item.dataset.conversa) === conversaId;
        item.classList.toggle('ativo', esta);
        if (esta) item.querySelector('.sinal-novo')?.remove();
    });
    atualizarEstadoChat();
    await executar(carregarMensagens);

    if (rolarAte || window.innerWidth < 760) {
        $('chat-box').scrollIntoView({ behavior: movimentoReduzido ? 'auto' : 'smooth', block: 'nearest' });
    }
    if (!chat.encerrada) $('chat-texto').focus({ preventScroll: true });
}

function horaDaMensagem(iso) {
    const data = new Date(iso);
    const hora = data.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    return data.toDateString() === new Date().toDateString()
        ? hora
        : `${data.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })} ${hora}`;
}

function blocoMensagem(msg, { mostrarOriginal = false, destacarId = null } = {}) {
    const minha = msg.remetente_id === usuario.id;
    const classes = ['chat-msg'];
    if (minha) classes.push('mine');
    if (destacarId && msg.remetente_id === destacarId) classes.push('destacada');
    return h('div', { class: classes.join(' '), 'data-id': msg.id },
        h('div', { class: 'who' }, `${minha ? 'Você' : msg.remetente_nome} · ${horaDaMensagem(msg.data_envio)}`),
        msg.conteudo_filtrado ? h('div', { class: 'texto' }, msg.conteudo_filtrado) : null,
        // Versões antigas permitiam arquivos/áudios; agora o chat é só texto.
        msg.anexo_removido ? h('div', { class: 'flag' }, 'Arquivo ou áudio antigo (o chat agora é só texto)') : null,
        msg.foi_filtrada ? h('div', { class: 'flag' }, 'Parte da mensagem foi filtrada') : null,
        mostrarOriginal && msg.foi_filtrada && msg.conteudo_original
            ? h('div', { class: 'original' }, `Texto original: ${msg.conteudo_original}`) : null,
    );
}

function adicionarMensagens(lista, { doServidor = true } = {}) {
    const box = $('chat-messages');
    if (doServidor && lista.length) chat.ultimoId = Math.max(chat.ultimoId, ...lista.map(msg => msg.id));
    const novas = lista.filter(msg => !chat.ids.has(msg.id));
    if (novas.length === 0) {
        if (!chat.ids.size && !box.children.length) {
            box.replaceChildren(h('div', { class: 'chat-vazio-msg' },
                ehAluno ? 'Nenhuma mensagem ainda. Diga oi e explique em que parte você travou.'
                        : 'Nenhuma mensagem ainda. Apresente-se e pergunte o que o aluno já tentou.'));
        }
        return;
    }
    const estavaNoFim = !chat.ids.size || box.scrollHeight - box.scrollTop - box.clientHeight < 60;
    box.querySelector('.chat-vazio-msg')?.remove();
    for (const msg of novas) {
        chat.ids.add(msg.id);
        // Mantém a ordem certa mesmo se uma mensagem chegar "atrasada".
        const seguinte = [...box.children].find(el => Number(el.dataset.id) > msg.id);
        box.insertBefore(blocoMensagem(msg), seguinte || null);
    }
    marcarLida(chat.conversaId, Math.max(...chat.ids));
    if (estavaNoFim) box.scrollTop = box.scrollHeight;
}

const carregarMensagens = semSobreposicao(async () => {
    if (!chat.conversaId) return;
    const versao = chat.versao;
    const resposta = await api.mensagens(chat.conversaId, chat.ultimoId);
    if (versao !== chat.versao) return; // trocou de conversa enquanto carregava
    adicionarMensagens(resposta.mensagens);
    if (resposta.encerrada !== chat.encerrada) {
        chat.encerrada = resposta.encerrada;
        await carregarMeusMatches(); // traz o status novo (concluída / cancelada)
        if (ehAluno) carregarMinhasSolicitacoes().catch(() => {});
    }
    atualizarEstadoChat();
});

function atualizarEstadoChat() {
    const m = matches.find(x => x.conversa_id === chat.conversaId);
    if (!m) return;
    const encerrada = chat.encerrada || m.status !== 'aceito';
    $('form-chat').hidden = encerrada;
    $('btn-encerrar').hidden = encerrada;
    $('btn-encerrar').textContent = m.tipo !== 'aula' ? 'Encerrar' : m.meu_papel === 'monitor' ? 'Encerrar aula' : 'Sair da aula';
    $('btn-meet').hidden = !m.link_meet || encerrada;
    if (m.link_meet) $('btn-meet').href = m.link_meet;
    $('btn-definir-meet').hidden = encerrada || (m.tipo === 'aula' && m.meu_papel !== 'monitor');

    const rodape = $('chat-rodape');
    if (!encerrada) { rodape.hidden = true; return; }
    rodape.hidden = false;

    if (m.tipo === 'aula') {
        rodape.dataset.match = '';
        rodape.replaceChildren(h('p', null, m.status === 'cancelado'
            ? 'Esta aula em grupo foi cancelada.' : 'Esta aula em grupo foi encerrada. Obrigado por participar!'));
        return;
    }
    if (m.status === 'cancelado') {
        rodape.dataset.match = '';
        rodape.replaceChildren(h('p', null, 'Esta monitoria foi encerrada pela coordenação da escola.'));
        return;
    }
    if (m.ja_avaliei) {
        rodape.dataset.match = '';
        rodape.replaceChildren(h('p', null, 'Monitoria encerrada. Você já avaliou, obrigado!'));
        return;
    }
    if (rodape.dataset.match === String(m.id) && rodape.querySelector('form')) return; // formulário já aberto
    rodape.dataset.match = String(m.id);
    rodape.replaceChildren(formularioAvaliacao(m));
}

function formularioAvaliacao(m) {
    let nota = 0;
    const estrelas = [1, 2, 3, 4, 5].map(n => h('button', {
        type: 'button', class: 'estrela', 'aria-label': plural(n, 'estrela', 'estrelas'), 'aria-pressed': 'false',
        onclick: () => {
            nota = n;
            estrelas.forEach((botao, i) => {
                botao.classList.toggle('acesa', i < n);
                botao.setAttribute('aria-pressed', String(i < n));
            });
        },
    }, '★'));
    const comentario = h('input', {
        type: 'text', class: 'entrada', maxlength: '500',
        placeholder: 'Comentário (opcional)', 'aria-label': 'Comentário da avaliação',
    });
    const pergunta = m.meu_papel === 'aluno'
        ? `Monitoria encerrada. Como foi a ajuda de ${m.com_quem}?`
        : `Monitoria encerrada. Como foi a monitoria com ${m.com_quem}?`;

    return h('form', {
        class: 'avaliacao',
        onsubmit: async (ev) => {
            ev.preventDefault();
            if (!nota) { avisar('Escolha de 1 a 5 estrelas.', 'error'); return; }
            await comBotao(ev.target.querySelector('button[type="submit"]'), () => executar(async () => {
                const resposta = await api.avaliar(m.id, nota, comentario.value.trim());
                avisar(resposta.mensagem);
                await carregarMeusMatches();
            }));
        },
    },
        h('p', null, pergunta),
        h('div', { class: 'estrelas', role: 'group', 'aria-label': 'Nota' }, estrelas),
        h('div', { class: 'avaliacao-linha' },
            comentario,
            h('button', { type: 'submit', class: 'btn btn-accent btn-sm' }, 'Enviar avaliação')),
    );
}

async function enviarMensagemChat(e) {
    e.preventDefault();
    const input = $('chat-texto');
    const texto = input.value.trim();
    const botao = e.target.querySelector('button[type="submit"]');
    if (!chat.conversaId) return;
    if (!texto) return;
    const versao = chat.versao;
    await comBotao(botao, () => executar(async () => {
        try {
            const resposta = await api.enviarMensagem(chat.conversaId, texto);
            input.value = '';
            if (versao === chat.versao) {
                adicionarMensagens([resposta.mensagem], { doServidor: false });
                carregarMensagens().catch(() => {}); // traz o que a outra pessoa mandou nesse meio-tempo
            }
            if (resposta.aviso) avisar(resposta.aviso, 'aviso');
        } catch (err) {
            if (err.status === 409) { // a outra pessoa encerrou a monitoria
                chat.encerrada = true;
                await carregarMeusMatches();
            }
            throw err;
        }
    }));
    if (!chat.encerrada) input.focus();
}

async function encerrarMonitoria() {
    const m = matches.find(x => x.conversa_id === chat.conversaId);
    if (!m) return;
    if (m.tipo === 'aula') return encerrarOuSairDaAula(m);
    const ok = await perguntar({
        titulo: 'Encerrar esta monitoria?',
        texto: `O chat com ${m.com_quem} fecha para os dois e o pedido fica como atendido. Depois vocês podem se avaliar.`,
        botao: 'Encerrar monitoria',
    });
    if (ok === null) return;
    await executar(async () => {
        const resposta = await api.concluirMatch(m.id);
        avisar(resposta.mensagem);
        chat.encerrada = true;
        await carregarMeusMatches();
        if (ehAluno) await carregarMinhasSolicitacoes();
    });
}

async function denunciarConversa() {
    const m = matches.find(x => x.conversa_id === chat.conversaId);
    if (!m) return;
    if (m.tipo === 'aula') return denunciarNaAula(m);
    const motivo = await perguntar({
        titulo: `Denunciar ${m.com_quem}`,
        texto: 'A coordenação da escola lê a conversa e decide o que fazer. A outra pessoa não é avisada da denúncia.',
        campo: 'O que aconteceu?',
        minimo: 5,
        botao: 'Enviar denúncia',
        perigo: true,
    });
    if (motivo === null) return;
    await executar(async () => {
        const resposta = await api.denunciar(m.conversa_id, motivo);
        avisar(resposta.mensagem);
    });
}

/* ============================================================================
   COORDENAÇÃO
   ============================================================================ */
function numeroBR(valor, casas = 1) {
    return Number(valor || 0).toLocaleString('pt-BR', { maximumFractionDigits: casas });
}

const carregarPainel = semSobreposicao(async () => {
    const p = await api.painelCoordenacao();
    const r = p.resumo;
    $('painel-titulo').textContent = p.instituicao;
    $('painel-atualizado').textContent =
        `atualizado às ${new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`;

    const numeros = [
        ['Estudantes', r.alunos], ['Ensinam', r.monitores], ['Aulas em grupo', r.aulas_grupo], ['Pedidos de ajuda', r.solicitacoes],
        ['Esperando monitor', r.pendentes], ['Monitorias feitas', r.monitorias],
        ['Mensagens filtradas', r.mensagens_filtradas], ['Denúncias abertas', r.denuncias_abertas],
    ];
    $('painel-resumo').replaceChildren(...numeros.map(([rotulo, valor]) => h('div', {
        class: `stat${rotulo === 'Denúncias abertas' && valor > 0 ? ' alerta' : ''}`,
    }, h('dt', null, rotulo), h('dd', null, numeroBR(valor, 0)))));

    // Defasagem por matéria (view vw_painel_coordenacao)
    const corpoMaterias = document.querySelector('#tabela-painel tbody');
    corpoMaterias.replaceChildren(...(p.materias.length ? p.materias.map(l => {
        const taxa = Number(l.taxa_defasagem_pct || 0);
        return h('tr', null,
            h('td', null, l.materia),
            h('td', null, l.total_solicitacoes),
            h('td', null, l.total_atendidas),
            h('td', null, h('span', { class: 'taxa' },
                h('span', { class: 'barra', 'aria-hidden': 'true' },
                    h('span', { class: `barra-cheia${taxa >= 50 ? ' alta' : ''}`, style: `width:${Math.min(100, taxa)}%` })),
                `${numeroBR(taxa)}%`)),
        );
    }) : [h('tr', null, h('td', { colspan: '4', class: 'vazio' }, 'Nenhum pedido de ajuda registrado ainda.'))]));

    // Monitores
    const corpoMonitores = document.querySelector('#tabela-monitores tbody');
    corpoMonitores.replaceChildren(...(p.monitores.length ? p.monitores.map(m => h('tr', null,
        h('td', null, h('button', { type: 'button', class: 'link-perfil', onclick: () => verPerfil(m.id) }, m.nome_completo)),
        h('td', null, m.monitorias),
        h('td', null, m.concluidas),
        h('td', null, m.avaliacoes
            ? `★ ${numeroBR(m.reputacao_media)} (${plural(m.avaliacoes, 'avaliação', 'avaliações')})`
            : 'sem avaliações'),
        h('td', null, selo(m.status_conta)),
    )) : [h('tr', null, h('td', { colspan: '5', class: 'vazio' }, 'Nenhum monitor cadastrado ainda.'))]));

    // Denúncias
    const abertas = p.denuncias.filter(d => d.status === 'pendente' || d.status === 'em_analise');
    $('count-denuncias').textContent = abertas.length ? `${abertas.length} para analisar` : 'nenhuma aberta';
    $('lista-denuncias').replaceChildren(...(p.denuncias.length ? p.denuncias.map(itemDenuncia)
        : [h('div', { class: 'empty-state' }, 'Nenhuma denúncia até agora.')]));

    // Contas suspensas
    $('lista-suspensos').replaceChildren(...(p.suspensos.length ? p.suspensos.map(u => h('div', { class: 'item' },
        h('div', { class: 'item-top' },
            h('span', { class: 'item-title' }, u.nome_completo),
            selo('banido')),
        h('div', { class: 'item-meta' }, `${TIPOS[u.tipo_usuario] || u.tipo_usuario} · ${u.email_institucional}`),
        h('div', { class: 'item-actions' },
            h('button', {
                type: 'button', class: 'btn btn-ghost btn-sm',
                onclick: (ev) => reativarConta(u, ev.currentTarget),
            }, 'Reativar conta')),
    )) : [h('div', { class: 'empty-state' }, 'Nenhuma conta suspensa.')]));
});

function itemDenuncia(d) {
    const aberta = d.status === 'pendente' || d.status === 'em_analise';
    const jaSuspenso = d.denunciado_status === 'banido';
    const papel = PAPEL[d.denunciado_tipo] || d.denunciado_tipo;
    return h('div', { class: `item${aberta ? ' item-alerta' : ''}` },
        h('div', { class: 'item-top' },
            h('span', { class: 'item-title' }, `Contra ${d.denunciado_nome}, ${papel}`),
            selo(d.status, STATUS_DENUNCIA)),
        h('div', { class: 'item-meta' },
            `Denunciado por ${d.denunciante_nome} · ${formatarData(d.data_denuncia)}`,
            d.advertencias ? ` · ${plural(d.advertencias, 'advertência', 'advertências')} na conta` : '',
            jaSuspenso ? ' · conta suspensa' : ''),
        h('p', { class: 'item-texto' }, d.motivo),
        d.mensagem_original ? h('blockquote', { class: 'citacao' },
            h('span', { class: 'citacao-rotulo' }, `Última mensagem de ${d.denunciado_nome}, como foi digitada:`),
            d.mensagem_original) : null,
        h('div', { class: 'item-actions' },
            h('button', { type: 'button', class: 'btn btn-ghost btn-sm', onclick: () => verPerfil(d.denunciado_id) }, 'Ver perfil'),
            d.conversa_id ? h('button', {
                type: 'button', class: 'btn btn-ghost btn-sm',
                onclick: (ev) => lerConversa(d, ev.currentTarget),
            }, 'Ler conversa') : null,
            aberta && !jaSuspenso ? h('button', {
                type: 'button', class: 'btn btn-ghost btn-sm',
                onclick: (ev) => moderar(d, 'advertencia', ev.currentTarget),
            }, 'Advertir') : null,
            aberta && !jaSuspenso ? h('button', {
                type: 'button', class: 'btn btn-ghost btn-sm btn-perigo',
                onclick: (ev) => moderar(d, 'banimento', ev.currentTarget),
            }, 'Suspender conta') : null,
            aberta ? h('button', {
                type: 'button', class: 'btn btn-ghost btn-sm',
                onclick: (ev) => moderar(d, 'arquivar', ev.currentTarget),
            }, 'Arquivar') : null,
        ),
    );
}

async function moderar(d, acao, botao) {
    const textos = {
        advertencia: {
            titulo: `Advertir ${d.denunciado_nome}?`,
            texto: 'A pessoa vê este recado na próxima vez que abrir o ClassMatch. Se ficar em branco, vai o motivo da denúncia.',
            campo: 'Recado para a pessoa', botao: 'Registrar advertência',
        },
        banimento: {
            titulo: `Suspender a conta de ${d.denunciado_nome}?`,
            texto: 'A pessoa sai do sistema na hora e não consegue entrar de novo. As monitorias em andamento dela ' +
                   'são encerradas. Dá para reativar depois em "Contas suspensas".',
            campo: 'Motivo (fica no registro da coordenação)', botao: 'Suspender conta', perigo: true,
        },
        arquivar: {
            titulo: 'Arquivar esta denúncia?',
            texto: 'Use quando não houve problema de verdade. Nada muda na conta da pessoa.',
            botao: 'Arquivar denúncia',
        },
    }[acao];
    const motivo = await perguntar(textos);
    if (motivo === null) return;
    await comBotao(botao, () => executar(async () => {
        const resposta = await api.moderarDenuncia(d.id, acao, motivo);
        avisar(resposta.mensagem);
        await carregarPainel();
    }));
}

async function reativarConta(u, botao) {
    const ok = await perguntar({
        titulo: `Reativar a conta de ${u.nome_completo}?`,
        texto: 'A pessoa volta a conseguir entrar no ClassMatch.',
        botao: 'Reativar conta',
    });
    if (ok === null) return;
    await comBotao(botao, () => executar(async () => {
        const resposta = await api.reativarUsuario(u.id);
        avisar(resposta.mensagem);
        await carregarPainel();
    }));
}

async function lerConversa(d, botao) {
    await comBotao(botao, () => executar(async () => {
        const resposta = await api.mensagens(d.conversa_id);
        $('conversa-titulo').textContent = `${resposta.materia_nome}: ${resposta.aluno_nome} e ${resposta.monitor_nome}`;
        $('conversa-subtitulo').textContent =
            `${plural(resposta.mensagens.length, 'mensagem', 'mensagens')} · em destaque, as de ${d.denunciado_nome}` +
            (resposta.encerrada ? ' · monitoria encerrada' : ' · monitoria em andamento');
        const box = $('conversa-mensagens');
        box.replaceChildren(...(resposta.mensagens.length
            ? resposta.mensagens.map(msg => blocoMensagem(msg, { mostrarOriginal: true, destacarId: d.denunciado_id }))
            : [h('div', { class: 'chat-vazio-msg' }, 'Esta conversa não tem mensagens.')]));
        $('dialogo-conversa').showModal();
        box.scrollTop = box.scrollHeight;
    }));
}
$('conversa-fechar').addEventListener('click', () => $('dialogo-conversa').close());

/* ============================================================================
   INÍCIO
   ============================================================================ */
async function init() {
    preencherCabecalho(usuario);
    montarAtalhos();
    iniciarPerfil();
    iniciarSenha();
    iniciarExclusao();

    // Entrou com senha temporária (dada pela coordenação): primeiro cria uma senha nova.
    let atual = usuario;
    try { atual = await api.eu(); sessao.atualizarUsuario(atual); } catch (_) { /* segue com a sessão salva */ }
    if (atual.trocar_senha) {
        abrirDialogoSenha(true);
        return;
    }

    // Dados atualizados de quem está logado (e aviso de advertência, se houver).
    executar(async () => {
        const eu = await api.eu();
        sessao.atualizarUsuario(eu);
        preencherCabecalho(eu);
        mostrarAdvertencia(eu);
    }, { silencioso: true });

    if (ehAluno) {
        $('view-aluno').hidden = false;
        $('section-matches').hidden = false;
        $('form-solicitacao').addEventListener('submit', enviarSolicitacao);
        $('sol-materia').addEventListener('change', atualizarDicaMateria);
        $('sol-desc').addEventListener('input', atualizarContador);
        await executar(async () => {
            await carregarMaterias();
            preencherSelectMaterias('sol-materia', true);
            atualizarDicaMateria();
        });
        await executar(carregarMinhasSolicitacoes);
        await executar(carregarMeusMatches);
        repetir(() => executar(async () => {
            await carregarMinhasSolicitacoes();
            await carregarMeusMatches();
        }, { silencioso: true }), 10000);
    }

    if (ehMonitor) {
        $('view-monitor').hidden = false;
        $('section-matches').hidden = false;
        $('form-minha-materia').addEventListener('submit', adicionarMinhaMateria);
        await executar(async () => {
            await carregarMaterias();
            preencherSelectMaterias('mm-materia', false);
        });
        await executar(carregarMinhasMaterias);
        await executar(carregarPendentes);
        await executar(carregarMeusMatches);
        repetir(() => executar(async () => {
            await carregarPendentes();
            await carregarMeusMatches();
        }, { silencioso: true }), 10000);
    }

    if (ehEstudante) {
        $('form-aula').addEventListener('submit', criarAula);
        document.querySelectorAll('.modo-btn').forEach(b => b.addEventListener('click', () => mostrarModo(b.dataset.modo)));
        $('modo-escolha').hidden = false;
        let modoSalvo = 'aprender';
        try { modoSalvo = localStorage.getItem(CHAVE_MODO) || 'aprender'; } catch (_) { /* sem armazenamento */ }
        mostrarModo(modoSalvo);
        await executar(carregarAulas);
        repetir(() => executar(carregarAulas, { silencioso: true }), 20000);
    }

    if (ehAluno || ehMonitor) {
        $('btn-definir-meet').addEventListener('click', definirMeet);
        $('form-chat').addEventListener('submit', enviarMensagemChat);
        $('btn-encerrar').addEventListener('click', encerrarMonitoria);
        $('btn-denunciar').addEventListener('click', denunciarConversa);
        repetir(() => { if (chat.conversaId) executar(carregarMensagens, { silencioso: true }); }, 3000);
    }

    if (ehCoordenacao) {
        $('view-coordenador').hidden = false;
        await executar(carregarPainel);
        repetir(() => executar(carregarPainel, { silencioso: true }), 20000);
    }

    rotear();
    window.addEventListener('hashchange', rotear);

    // Voltou para a aba: atualiza na hora em vez de esperar o próximo ciclo.
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) return;
        if (ehAluno) executar(carregarMinhasSolicitacoes, { silencioso: true });
        if (ehMonitor) executar(carregarPendentes, { silencioso: true });
        if (ehAluno || ehMonitor) executar(carregarMeusMatches, { silencioso: true });
        if (ehEstudante) executar(carregarAulas, { silencioso: true });
        if (chat.conversaId) executar(carregarMensagens, { silencioso: true });
        if (ehCoordenacao) executar(carregarPainel, { silencioso: true });
    });
}


/* ============================================================================
   ATALHOS E ROTAS (#perfil, #mensagens, #matches, #conversa-12, #usuario-5)
   ============================================================================ */
function montarAtalhos() {
    const lista = ehAluno
        ? [['ajuda', 'Pedir ajuda', '#sec-pedir'], ['alvo', 'Possíveis matches', '#matches'], ['usuarios', 'Aulas em grupo', '#sec-aulas'], ['mensagem', 'Mensagens', '#mensagens']]
        : ehMonitor
            ? [['alvo', 'Possíveis matches', '#matches'], ['livro', 'Minhas matérias', '#sec-materias'], ['mensagem', 'Mensagens', '#mensagens'], ['usuario', 'Meu perfil', '#perfil']]
            : [['bandeira', 'Denúncias', '#sec-denuncias'], ['grafico', 'Defasagem', '#sec-defasagem'], ['usuarios', 'Monitores', '#sec-monitores'], ['usuario', 'Meu perfil', '#perfil']];
    $('atalhos').replaceChildren(...lista.map(([nomeIcone, texto, href]) =>
        h('a', { href, class: 'card atalho' }, h('span', { class: 'atalho-icone' }, icone(nomeIcone)), texto)));
}

function rolarPara(elemento) {
    if (elemento) elemento.scrollIntoView({ behavior: movimentoReduzido ? 'auto' : 'smooth', block: 'start' });
}

async function rotear() {
    const hash = location.hash;
    const perfil = hash === '#perfil';
    $('view-painel').hidden = perfil;
    $('view-perfil').hidden = !perfil;
    montarCabecalho(); // destaca o item certo do menu
    if (perfil) {
        window.scrollTo(0, 0);
        await executar(carregarMeuPerfil);
        return;
    }
    // Veio da busca ou de uma notificação em outra página: abre o perfil da pessoa por cima do painel.
    const pessoa = hash.match(/^#usuario-(\d+)$/);
    if (pessoa) {
        history.replaceState(null, '', 'dashboard.html');
        return verPerfil(Number(pessoa[1]));
    }
    const conversa = hash.match(/^#conversa-(\d+)$/);
    if (conversa && (ehAluno || ehMonitor)) return abrirChat(Number(conversa[1]), true);
    if (hash === '#mensagens') return rolarPara($('section-matches'));
    if (hash === '#matches') { mostrarModo('ensinar'); return rolarPara($('sec-pendentes')); }
    if (hash.startsWith('#sec-')) {
        const alvo = document.querySelector(hash);
        if (alvo && alvo.closest('#view-aluno')) mostrarModo('aprender');
        if (alvo && alvo.closest('#view-monitor')) mostrarModo('ensinar');
        rolarPara(alvo);
    }
}

// Abriu a conversa: as notificações de mensagem dela ficam como lidas.
function marcarNotificacoesDaConversa(conversaId) {
    const ids = notificacoes.filter(n => !n.lida && n.link === `dashboard.html#conversa-${conversaId}`).map(n => n.id);
    if (ids.length) api.marcarNotificacoes(ids).then(carregarNotificacoes).catch(() => {});
}

/* ============================================================================
   PERFIL
   ============================================================================ */
let meuPerfil = null;

function estrelasTexto(media) {
    const cheias = Math.round(Number(media || 0));
    return '★'.repeat(cheias) + '☆'.repeat(5 - cheias);
}

function chips(itens, vazio) {
    return itens.length ? h('div', { class: 'lista-materias' }, itens) : h('p', { class: 'muted' }, vazio);
}

function desenharPerfil(p, editavel) {
    const media = p.reputacao_media;
    return [
        h('div', { class: 'perfil-topo' },
            h('span', { class: 'avatar grande', 'aria-hidden': 'true' }, iniciais(p.nome_completo)),
            h('div', null,
                h('h1', null, p.nome_completo),
                h('div', { class: 'badges' },
                    h('span', { class: 'badge azul' }, TIPOS[p.tipo_usuario] || p.tipo_usuario),
                    h('span', { class: 'badge' }, p.instituicao_nome),
                    p.email_verificado ? h('span', { class: 'badge ativo' }, icone('check'), 'E-mail verificado') : null,
                    p.status_conta !== 'ativo' ? selo(p.status_conta) : null)),
            editavel ? h('div', { class: 'item-actions', style: 'margin:0 0 0 auto' },
                h('button', { type: 'button', class: 'btn btn-ghost btn-sm', onclick: abrirEdicaoPerfil }, icone('lapis'), ' Editar perfil'),
                h('button', { type: 'button', class: 'btn btn-ghost btn-sm', onclick: () => abrirDialogoSenha(false) }, icone('cadeado'), ' Trocar senha')) : null),
        p.bio ? h('p', { class: 'perfil-bio' }, p.bio)
            : editavel ? h('p', { class: 'perfil-bio' }, 'Conte um pouco sobre você em "Editar perfil".') : null,
        h('dl', { class: 'perfil-numeros' },
            h('div', { class: 'stat' }, h('dt', null, 'Avaliação média'),
                h('dd', null, media != null ? numeroBR(media) : '—'),
                media != null ? h('div', { class: 'nota-estrelas', 'aria-hidden': 'true' }, estrelasTexto(media)) : null),
            h('div', { class: 'stat' }, h('dt', null, 'Avaliações recebidas'), h('dd', null, p.total_avaliacoes)),
            h('div', { class: 'stat' }, h('dt', null, 'Monitorias'), h('dd', null, p.total_monitorias))),
        ['aluno', 'monitor'].includes(p.tipo_usuario) || p.ensina.length ? h('div', { class: 'perfil-bloco' }, h('h3', null, 'Ensina'),
            chips(p.ensina.map(e => h('span', { class: 'chip simples' }, e.nome, h('span', { class: 'chip-nivel' }, NIVEIS[e.nivel]))),
                'Nenhuma matéria cadastrada ainda.')) : null,
        ['aluno', 'monitor'].includes(p.tipo_usuario) || p.quer_aprender.length ? h('div', { class: 'perfil-bloco' }, h('h3', null, 'Quer aprender'),
            chips(p.quer_aprender.map(nome => h('span', { class: 'chip simples' }, nome)), 'Nenhum pedido de ajuda ainda.')) : null,
        h('div', { class: 'perfil-bloco' }, h('h3', null, 'Últimas avaliações'),
            p.avaliacoes.length ? p.avaliacoes.map(a => h('div', { class: 'avaliacao-item' },
                h('span', { class: 'nota-estrelas', title: `${a.nota} de 5` }, estrelasTexto(a.nota)),
                ` · ${a.materia} · ${formatarData(a.data_avaliacao, false)}`,
                a.comentario ? h('div', null, `"${a.comentario}"`) : null))
                : h('p', { class: 'muted' }, 'Nenhuma avaliação ainda.')),
        // Só no MEU perfil e só para estudantes (conta da coordenação não se exclui por aqui).
        editavel && ['aluno', 'monitor'].includes(p.tipo_usuario) ? h('div', { class: 'perfil-bloco zona-perigo' },
            h('h3', null, 'Excluir conta'),
            h('p', { class: 'muted' }, 'Apaga para sempre a sua conta, seus pedidos, monitorias, conversas e avaliações. Não tem como desfazer.'),
            h('button', { type: 'button', class: 'btn btn-ghost btn-sm btn-perigo', onclick: abrirDialogoExclusao },
                icone('lixeira'), ' Excluir minha conta')) : null,
    ].filter(Boolean); // replaceChildren(null) escreveria "null" na tela
}

async function carregarMeuPerfil() {
    meuPerfil = await api.perfil();
    $('perfil-conteudo').replaceChildren(...desenharPerfil(meuPerfil, true));
}

function abrirEdicaoPerfil() {
    $('perfil-nome').value = meuPerfil.nome_completo;
    $('perfil-bio').value = meuPerfil.bio || '';
    $('perfil-contador').textContent = `${$('perfil-bio').value.length}/300`;
    $('form-perfil').hidden = false;
    $('form-perfil').scrollIntoView({ behavior: movimentoReduzido ? 'auto' : 'smooth' });
    $('perfil-nome').focus({ preventScroll: true });
}

function iniciarPerfil() {
    $('perfil-bio').addEventListener('input', () => { $('perfil-contador').textContent = `${$('perfil-bio').value.length}/300`; });
    $('perfil-cancelar').addEventListener('click', () => { $('form-perfil').hidden = true; });
    $('perfil-modal-fechar').addEventListener('click', () => $('dialogo-perfil').close());
    $('form-perfil').addEventListener('submit', async (e) => {
        e.preventDefault();
        await comBotao(e.target.querySelector('button[type="submit"]'), () => executar(async () => {
            const resposta = await api.editarPerfil({ nome_completo: $('perfil-nome').value.trim(), bio: $('perfil-bio').value.trim() });
            meuPerfil = resposta.perfil;
            $('perfil-conteudo').replaceChildren(...desenharPerfil(meuPerfil, true));
            $('form-perfil').hidden = true;
            sessao.atualizarUsuario({ ...sessao.obter(), nome_completo: meuPerfil.nome_completo });
            preencherCabecalho(sessao.obter());
            montarCabecalho();
            avisar(resposta.aviso || 'Perfil atualizado com sucesso!', resposta.aviso ? 'aviso' : 'ok');
        }));
    });
}

async function verPerfil(usuarioId) {
    if (!usuarioId) return;
    await executar(async () => {
        const perfil = await api.verPerfil(usuarioId);
        $('perfil-modal-conteudo').replaceChildren(...desenharPerfil(perfil, false));
        $('dialogo-perfil').showModal();
    });
}

/* ============================================================================
   EXCLUIR A CONTA (aba Perfil): 1) senha  2) código que chega no e-mail
   ============================================================================ */
function abrirDialogoExclusao() {
    $('form-excluir').reset();
    $('excluir-erro').className = 'msg';
    $('excluir-passo-senha').hidden = false;
    $('excluir-passo-codigo').hidden = true;
    $('excluir-enviar').hidden = false;
    $('excluir-confirmar').hidden = true;
    $('excluir-codigo').required = false;
    $('dialogo-excluir').showModal();
    $('excluir-senha').focus();
}

function erroExclusao(texto) {
    $('excluir-erro').textContent = texto;
    $('excluir-erro').className = 'msg show error';
}

async function pedirCodigoExclusao(botao) {
    $('excluir-erro').className = 'msg';
    await comBotao(botao, async () => {
        try {
            const resposta = await api.pedirCodigoExclusao($('excluir-senha').value);
            const comEmail = resposta.modo === 'email';
            $('excluir-passo-senha').hidden = true;
            $('excluir-passo-codigo').hidden = false;
            $('excluir-campo-codigo').hidden = !comEmail;
            $('excluir-codigo').required = comEmail;
            $('excluir-reenviar').hidden = !comEmail;
            $('excluir-texto-codigo').textContent = comEmail
                ? `${resposta.mensagem} Digite o código abaixo para confirmar. Ele vale por 15 minutos (olhe também o spam).`
                : 'Última confirmação: depois de clicar no botão vermelho, a sua conta deixa de existir.';
            $('excluir-enviar').hidden = true;
            $('excluir-confirmar').hidden = false;
            (comEmail ? $('excluir-codigo') : $('excluir-confirmar')).focus();
        } catch (err) {
            erroExclusao(err.message);
        }
    });
}

function iniciarExclusao() {
    $('excluir-cancelar').addEventListener('click', () => $('dialogo-excluir').close());
    $('excluir-reenviar').addEventListener('click', (e) => pedirCodigoExclusao(e.currentTarget));
    $('excluir-codigo').addEventListener('input', (e) => { e.target.value = e.target.value.replace(/\D/g, '').slice(0, 6); });
    $('form-excluir').addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!$('excluir-passo-senha').hidden) {
            if (!$('excluir-ciente').checked) return erroExclusao('Marque a caixa dizendo que você entende que não tem volta.');
            return pedirCodigoExclusao($('excluir-enviar'));
        }
        $('excluir-erro').className = 'msg';
        await comBotao($('excluir-confirmar'), async () => {
            try {
                const resposta = await api.excluirConta($('excluir-senha').value, $('excluir-codigo').value);
                sessao.limpar();
                sessionStorage.setItem('classmatch_recado_ok', resposta.mensagem); // aparece na página inicial
                window.location.replace('index.html');
            } catch (err) {
                erroExclusao(err.message);
            }
        });
    });
}

/* ============================================================================
   SENHA: trocar (perfil), troca obrigatória (senha temporária) e coordenação
   ============================================================================ */
let senhaObrigatoria = false;

function abrirDialogoSenha(obrigatoria) {
    senhaObrigatoria = obrigatoria;
    $('form-senha').reset();
    $('senha-erro').className = 'msg';
    $('senha-titulo').textContent = obrigatoria ? 'Crie uma senha nova' : 'Trocar senha';
    $('senha-texto').textContent = obrigatoria
        ? 'A coordenação redefiniu sua senha. Para continuar, digite a senha temporária que você recebeu e crie uma senha só sua.'
        : '';
    $('senha-atual-rotulo').textContent = obrigatoria ? 'Senha temporária' : 'Senha atual';
    $('senha-cancelar').hidden = obrigatoria;
    $('dialogo-senha').showModal();
    $('senha-atual').focus();
}

function iniciarSenha() {
    $('senha-cancelar').addEventListener('click', () => $('dialogo-senha').close());
    // Troca obrigatória: não fecha com Esc
    $('dialogo-senha').addEventListener('cancel', (e) => { if (senhaObrigatoria) e.preventDefault(); });
    $('form-senha').addEventListener('submit', async (e) => {
        e.preventDefault();
        const erro = $('senha-erro');
        erro.className = 'msg';
        if ($('senha-nova').value !== $('senha-nova2').value) {
            erro.textContent = 'As duas senhas novas não são iguais.';
            erro.className = 'msg show error';
            return;
        }
        await comBotao(e.target.querySelector('button[type="submit"]'), async () => {
            try {
                const resposta = await api.trocarSenha($('senha-atual').value, $('senha-nova').value);
                sessao.atualizarUsuario(resposta.usuario);
                if (senhaObrigatoria) {
                    location.reload(); // agora o painel carrega normalmente
                    return;
                }
                $('dialogo-senha').close();
                avisar(resposta.mensagem, 'ok');
            } catch (err) {
                erro.textContent = err.message;
                erro.className = 'msg show error';
            }
        });
    });
    if (!ehAluno && !ehMonitor) {
        $('form-redefinir').addEventListener('submit', redefinirSenhaDeUsuario);
    }
}

async function redefinirSenhaDeUsuario(e) {
    e.preventDefault();
    const identificacao = $('redef-id').value.trim();
    const confirmou = await perguntar({
        titulo: 'Gerar senha temporária?',
        texto: `A senha atual de "${identificacao}" deixa de funcionar. No próximo login, a pessoa vai criar uma senha nova.`,
        botao: 'Gerar senha',
    });
    if (confirmou === null) return; // '' = confirmou, null = cancelou
    await comBotao(e.target.querySelector('button[type="submit"]'), () => executar(async () => {
        const resposta = await api.redefinirSenhaUsuario(identificacao);
        const caixa = $('redef-resultado');
        caixa.replaceChildren(
            h('span', { class: 'citacao-rotulo' }, `Senha temporária de ${resposta.nome}:`),
            h('strong', { style: 'font-size:1.4rem;letter-spacing:.12em;font-family:monospace' }, resposta.senha_temporaria),
            ' ',
            h('button', { type: 'button', class: 'btn btn-ghost btn-sm', onclick: async (ev) => {
                try { await navigator.clipboard.writeText(resposta.senha_temporaria); ev.currentTarget.textContent = 'Copiada!'; }
                catch (_) { avisar('Não consegui copiar; anote a senha.', 'aviso'); }
            } }, 'Copiar'),
            h('span', { class: 'citacao-rotulo', style: 'margin-top:6px' }, 'Passe essa senha só para a própria pessoa. Ela não aparece de novo.'));
        caixa.hidden = false;
        e.target.reset(); // limpa o campo sem deixar a borda vermelha
    }));
}


/* ============================================================================
   QUERO APRENDER / QUERO ENSINAR (o estudante escolhe o que fazer agora)
   ============================================================================ */
function mostrarModo(modo) {
    if (!ehEstudante) return;
    const ensinar = modo === 'ensinar';
    $('view-aluno').hidden = ensinar;
    $('view-monitor').hidden = !ensinar;
    document.querySelectorAll('.modo-btn').forEach(botao => {
        const ativo = botao.dataset.modo === (ensinar ? 'ensinar' : 'aprender');
        botao.classList.toggle('ativo', ativo);
        botao.setAttribute('aria-selected', String(ativo));
    });
    try { localStorage.setItem(CHAVE_MODO, ensinar ? 'ensinar' : 'aprender'); } catch (_) { /* sem armazenamento */ }
}

/* ============================================================================
   AULAS EM GRUPO (1 monitor para vários alunos)
   ============================================================================ */
function preencherMateriasAula(minhas) {
    const select = $('aula-materia');
    const atual = select.value;
    select.replaceChildren(...(minhas.length
        ? minhas.map(m => h('option', { value: m.materia_id }, m.materia_nome))
        : [h('option', { value: '' }, 'Adicione antes uma matéria que você ensina')]));
    if (atual) select.value = atual;
    $('form-aula').querySelector('button[type="submit"]').disabled = minhas.length === 0;
}

function quandoAula(a) {
    const inicio = new Date(a.data_hora);
    const dia = inicio.toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: '2-digit' });
    const hora = inicio.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    return `${dia} às ${hora} · ${a.duracao_min} min`;
}

function cartaoAula(a) {
    const lotada = a.vagas_restantes === 0;
    const acoes = [];
    if (a.sou_monitor) {
        if (a.conversa_id) acoes.push(h('button', { type: 'button', class: 'btn btn-primary btn-sm', onclick: () => abrirChatDaAula(a.conversa_id) }, 'Abrir chat da turma'));
        if (a.status === 'aberta') acoes.push(h('button', { type: 'button', class: 'btn btn-ghost btn-sm btn-perigo', onclick: (ev) => cancelarAula(a, ev.currentTarget) }, 'Cancelar aula'));
    } else if (a.inscrito) {
        acoes.push(h('button', { type: 'button', class: 'btn btn-primary btn-sm', onclick: () => abrirChatDaAula(a.conversa_id) }, 'Abrir chat da turma'));
        if (a.link_meet && a.status === 'aberta') acoes.push(h('a', { class: 'btn btn-sm btn-meet', href: a.link_meet, target: '_blank', rel: 'noopener' }, icone('video'), ' Entrar no Meet'));
        if (a.status === 'aberta' && !a.ja_passou) acoes.push(h('button', { type: 'button', class: 'btn btn-ghost btn-sm', onclick: (ev) => sairDaAula(a, ev.currentTarget) }, 'Sair da aula'));
    } else if (a.status === 'aberta' && !a.ja_passou) {
        acoes.push(h('button', {
            type: 'button', class: 'btn btn-primary btn-sm', disabled: lotada,
            onclick: (ev) => inscreverNaAula(a, ev.currentTarget),
        }, lotada ? 'Lotada' : 'Quero participar'));
    }
    if (!a.sou_monitor) acoes.push(h('button', { type: 'button', class: 'btn btn-ghost btn-sm', onclick: () => verPerfil(a.monitor_id) }, 'Ver perfil do monitor'));
    const situacao = a.status === 'concluida' ? selo('concluido') : a.ja_passou ? h('span', { class: 'badge' }, 'Já aconteceu')
        : a.inscrito ? h('span', { class: 'badge ativo' }, 'Inscrito(a)') : lotada ? h('span', { class: 'badge cancelada' }, 'Lotada')
            : h('span', { class: 'badge azul' }, `${a.vagas_restantes} vaga(s)`);
    return h('div', { class: 'item' },
        h('div', { class: 'item-top' },
            h('div', null,
                h('div', { class: 'rotulo-match' }, icone('usuarios'), ' AULA EM GRUPO'),
                h('div', { class: 'item-title' }, a.titulo)),
            situacao),
        h('div', { class: 'aula-info' },
            h('span', null, a.materia_nome),
            h('span', null, quandoAula(a)),
            h('span', null, a.sou_monitor ? 'Você ensina' : `com ${a.monitor_nome}`),
            h('span', null, `${a.inscritos} de ${a.vagas} vagas preenchidas`)),
        a.descricao ? h('p', { class: 'item-texto' }, a.descricao) : null,
        acoes.length ? h('div', { class: 'item-actions' }, acoes) : null);
}

const carregarAulas = semSobreposicao(async () => {
    const aulas = await api.aulas();
    const outras = aulas.filter(a => !a.sou_monitor && (a.status === 'aberta' || a.inscrito));
    $('count-aulas').textContent = plural(outras.filter(a => !a.ja_passou).length, 'aula', 'aulas');
    $('lista-aulas').replaceChildren(...(outras.length ? outras.map(cartaoAula)
        : [h('div', { class: 'empty-state' }, 'Nenhuma aula em grupo marcada na sua escola por enquanto.')]));
    const minhas = aulas.filter(a => a.sou_monitor);
    $('lista-minhas-aulas').replaceChildren(...(minhas.length ? minhas.map(cartaoAula)
        : [h('div', { class: 'empty-state' }, 'Você ainda não criou nenhuma aula em grupo.')]));
});

async function criarAula(e) {
    e.preventDefault();
    const dados = {
        materia_id: Number($('aula-materia').value),
        titulo: $('aula-titulo').value.trim(),
        descricao: $('aula-descricao').value.trim(),
        data_hora: $('aula-data').value,
        duracao_min: Number($('aula-duracao').value),
        vagas: Number($('aula-vagas').value),
        link_meet: $('aula-meet').value.trim(),
    };
    await comBotao(e.target.querySelector('button[type="submit"]'), () => executar(async () => {
        const resposta = await api.criarAula(dados);
        e.target.reset();
        $('aula-vagas').value = 10;
        avisar(resposta.aviso || resposta.mensagem, resposta.aviso ? 'aviso' : 'ok');
        await carregarAulas();
        await carregarMeusMatches();
    }));
}

async function inscreverNaAula(a, botao) {
    await comBotao(botao, () => executar(async () => {
        const resposta = await api.inscreverAula(a.id);
        avisar(resposta.mensagem);
        await carregarAulas();
        await carregarMeusMatches();
    }));
}

async function sairDaAula(a, botao) {
    const ok = await perguntar({ titulo: 'Sair desta aula?', texto: `Sua vaga em "${a.titulo}" fica livre para outro colega.`, botao: 'Sair da aula' });
    if (ok === null) return;
    await comBotao(botao, () => executar(async () => {
        const resposta = await api.sairAula(a.id);
        avisar(resposta.mensagem);
        if (chat.conversaId === a.conversa_id) { chat.conversaId = null; $('chat-box').hidden = true; $('chat-vazio').hidden = false; }
        await carregarAulas();
        await carregarMeusMatches();
    }));
}

async function cancelarAula(a, botao) {
    const ok = await perguntar({ titulo: 'Cancelar esta aula?', texto: `Os inscritos em "${a.titulo}" são avisados e o chat da turma fecha.`, botao: 'Cancelar aula', perigo: true });
    if (ok === null) return;
    await comBotao(botao, () => executar(async () => {
        const resposta = await api.statusAula(a.id, 'cancelada');
        avisar(resposta.mensagem);
        await carregarAulas();
        await carregarMeusMatches();
    }));
}

function abrirChatDaAula(conversaId) {
    abrirChat(conversaId, true);
}

// Botão "Encerrar" no chat de uma aula: quem ensina encerra, quem participa sai.
async function encerrarOuSairDaAula(m) {
    if (m.meu_papel !== 'monitor') return sairDaAula({ id: m.aula_id, titulo: m.titulo, conversa_id: m.conversa_id }, $('btn-encerrar'));
    const ok = await perguntar({ titulo: 'Encerrar esta aula?', texto: 'O chat da turma fecha para todos. Os inscritos recebem um aviso.', botao: 'Encerrar aula' });
    if (ok === null) return;
    await executar(async () => {
        const resposta = await api.statusAula(m.aula_id, 'concluida');
        avisar(resposta.mensagem);
        await carregarAulas();
        await carregarMeusMatches();
    });
}

// Denúncia no chat da turma: escolhe quem.
async function denunciarNaAula(m) {
    const outros = (m.participantes || []).filter(p => p.id !== usuario.id);
    if (!outros.length) { avisar('Ainda não há outras pessoas nesta aula.', 'aviso'); return; }
    const resposta = await perguntar({
        titulo: 'Denunciar alguém desta aula',
        texto: 'A coordenação da escola lê a conversa e decide o que fazer. A pessoa não é avisada.',
        opcoes: outros.map(p => ({ valor: p.id, texto: p.nome })), rotuloOpcoes: 'Quem você quer denunciar?',
        campo: 'O que aconteceu?', minimo: 5, botao: 'Enviar denúncia', perigo: true,
    });
    if (resposta === null) return;
    await executar(async () => {
        const r = await api.denunciar(m.conversa_id, resposta.texto, Number(resposta.opcao));
        avisar(r.mensagem);
    });
}

/* ---------------- Google Meet (monitoria e aula) ---------------- */
async function definirMeet() {
    const m = matches.find(x => x.conversa_id === chat.conversaId);
    if (!m) return;
    const link = await perguntar({
        titulo: 'Link do Google Meet',
        texto: 'Entre em meet.google.com, clique em "Nova reunião", copie o link e cole aqui. Para tirar o link, deixe em branco.',
        campo: 'Link da reunião', botao: 'Salvar link',
    });
    if (link === null) return;
    await executar(async () => {
        const resposta = m.tipo === 'aula' ? await api.meetAula(m.aula_id, link) : await api.meetMonitoria(m.id, link);
        avisar(resposta.mensagem);
        await carregarMeusMatches();
        if (m.tipo === 'aula') await carregarAulas();
    });
}

if (usuario) init();
