"""
Filtro automático do chat (e da descrição dos pedidos de ajuda).

Muitos usuários são menores de idade, então a conversa fica DENTRO da
plataforma. Antes de salvar, o backend troca por "[removido pela moderação]":
telefones e documentos, e-mails de fora da escola, @perfis, links de redes
sociais/apps de mensagem e nomes desses apps ("me chama no zap"). Palavrões
viram asteriscos, mesmo escritos com acento, letra repetida ou número no lugar
de letra (p0rr4, poooorra).

Além das listas abaixo, o app.py passa as linhas ativas da tabela
palavras_filtradas; assim a escola pode bloquear palavras novas direto no banco.

Uso:
    texto, motivos = filtrar_mensagem('me chama no zap 11 98888-7777')
    # texto   -> 'me chama no [removido pela moderação] [removido pela moderação]'
    # motivos -> ['rede social ou app de mensagem', 'telefone ou documento']
"""
import re
import unicodedata
from functools import lru_cache

TAMANHO_MAXIMO = 1000
REMOVIDO = '[removido pela moderação]'

PALAVROES = [
    'porra', 'caralho', 'caralha', 'merda', 'puta', 'puto', 'putaria',
    'fdp', 'pqp', 'vsf', 'vtnc', 'tnc', 'krl', 'crl', 'cacete',
    'buceta', 'boceta', 'arrombado', 'arrombada', 'desgracado', 'desgracada',
    'otario', 'otaria', 'imbecil', 'idiota', 'babaca', 'cu', 'cuzao',
    'foda', 'fodase', 'foder', 'fodido', 'fodida', 'fuder', 'fudido', 'fudida',
    'bosta', 'vagabundo', 'vagabunda', 'corno', 'retardado', 'retardada',
    'viado', 'piranha', 'escroto', 'escrota', 'burro', 'burra',
    'estupido', 'estupida',
]

# Nomes de apps/redes usados para levar a conversa para fora da plataforma.
APPS_DE_CONTATO = [
    'whatsapp', 'whats', 'wpp', 'zap', 'zapzap', 'telegram', 'instagram', 'insta',
    'discord', 'tiktok', 'snapchat', 'facebook', 'messenger', 'skype',
]

# Links para esses sites são removidos; links de conteúdo (ex.: vídeo-aula) passam.
DOMINIOS_BLOQUEADOS = [
    'whatsapp.com', 'wa.me', 'instagram.com', 'instagr.am', 'facebook.com', 'fb.com',
    'fb.me', 'm.me', 'messenger.com', 't.me', 'telegram.me', 'telegram.org',
    'discord.gg', 'discord.com', 'discordapp.com', 'tiktok.com', 'snapchat.com',
    'twitter.com', 'x.com', 'threads.net', 'kwai.com', 'linktr.ee', 'bit.ly',
    'tinyurl.com', 'cutt.ly', 'is.gd', 'encurtador.com.br', 'skype.com',
    'zoom.us', 'meet.google.com', 'onlyfans.com',
]

_EMAIL = re.compile(r'[A-Za-z0-9._%+\-]+\s*@\s*[A-Za-z0-9\-]+(?:\s*\.\s*[A-Za-z0-9\-]+)+')
_LINK = re.compile(
    r'(?:https?://|www\.)[^\s<>"]+'
    r'|\b[A-Za-z0-9][A-Za-z0-9\-]*(?:\.[A-Za-z0-9\-]+)*'
    r'\.(?:com|net|org|io|me|ly|gg|us|tv|co|app|link|site|br)\b(?:/[^\s<>"]*)?',
    re.IGNORECASE,
)
_PERFIL = re.compile(r'(?<![\w@])@[A-Za-z0-9_.]{2,}')
_NUMERO = re.compile(r'\+?\(?\d[\d\s().\-]{6,}\d')
_DATA = re.compile(r'\d{4}-\d{2}-\d{2}|\d{2}[./\-]\d{2}[./\-]\d{4}')
_ANOS = re.compile(r'(?:19|20)\d{2}\s*[-/]\s*(?:19|20)\d{2}')

_LEET = {'0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's', '7': 't', '@': 'a', '$': 's'}


def normalizar(texto):
    """Cópia do texto com o MESMO tamanho: sem acento, minúscula e sem 'leet' (p0rr4 -> porra)."""
    saida = []
    for caractere in texto:
        base = unicodedata.normalize('NFD', caractere)[0].lower()
        if len(base) != 1:
            base = caractere
        saida.append(_LEET.get(base, base))
    return ''.join(saida)


def _padrao_palavra(palavra):
    # "porra" também pega "poooorra" e "porras"; as bordas evitam falsos
    # positivos como "cumprimento" (cu) ou "computador".
    letras = ''.join(re.escape(letra) + '+' for letra in palavra)
    return r'(?<![a-z0-9])' + letras + r's*(?![a-z0-9])'


@lru_cache(maxsize=32)
def _regex_palavras(palavras):
    if not palavras:
        return None
    ordenadas = sorted(set(palavras), key=len, reverse=True)  # "putaria" antes de "puta"
    return re.compile('|'.join(_padrao_palavra(p) for p in ordenadas))


@lru_cache(maxsize=64)
def _regex_livre(padrao):
    try:
        return re.compile(padrao, re.IGNORECASE)
    except re.error:
        return re.compile(re.escape(padrao), re.IGNORECASE)


def _eh_numero_de_contato(trecho):
    limpo = trecho.strip()
    if _DATA.fullmatch(limpo) or _ANOS.fullmatch(limpo):
        return False
    digitos = re.sub(r'\D', '', trecho)
    if not 8 <= len(digitos) <= 14:
        return False
    # "1 2 3 4 5 6 7 8" (lista de exercícios) não é telefone; "98888-7777" é.
    return re.search(r'\d{4}', trecho) is not None or len(digitos) >= 10


def _dominio_permitido(dominio, permitido):
    return bool(permitido) and (dominio == permitido or dominio.endswith('.' + permitido))


def _separar_extras(extras):
    """Divide as linhas da tabela palavras_filtradas por tipo de tratamento."""
    palavroes, contato, pessoais, regex_livres = [], [], [], []
    for linha in extras or ():
        padrao = str(linha.get('padrao') or '').strip()
        if not padrao:
            continue
        tipo = linha.get('tipo')
        simples = re.fullmatch(r'[\w\s.\-]+', padrao) is not None
        if tipo == 'palavrao':
            palavroes.append(normalizar(padrao))
        elif not simples:
            regex_livres.append(padrao)
        elif tipo == 'dado_pessoal':
            pessoais.append(normalizar(padrao))
        else:
            contato.append(normalizar(padrao))
    return palavroes, contato, pessoais, regex_livres


def filtrar_mensagem(texto, dominio_permitido=None, extras=()):
    """Devolve (texto_filtrado, lista_de_motivos). A lista vem vazia se nada mudou."""
    texto = unicodedata.normalize('NFC', str(texto or '')).strip()[:TAMANHO_MAXIMO]
    dominio_permitido = (dominio_permitido or '').lower()
    motivos = []
    guardados = []  # e-mails da própria escola ficam protegidos até o final

    def marcar(motivo):
        if motivo not in motivos:
            motivos.append(motivo)

    def trocar_email(achado):
        email = re.sub(r'\s+', '', achado.group(0))
        dominio = email.rsplit('@', 1)[-1].lower()
        if _dominio_permitido(dominio, dominio_permitido):
            guardados.append(email)
            return '\uE000' + chr(0xE100 + len(guardados) - 1) + '\uE000'
        marcar('e-mail')
        return REMOVIDO

    def trocar_link(achado):
        url = achado.group(0)
        host = re.sub(r'^(?:https?://)?(?:www\.)?', '', url, flags=re.IGNORECASE)
        host = re.split(r'[/?#:]', host, maxsplit=1)[0].lower().rstrip('.')
        bloqueado = any(host == d or host.endswith('.' + d) for d in DOMINIOS_BLOQUEADOS)
        if bloqueado:
            marcar('link externo')
            return REMOVIDO
        return url

    def trocar_perfil(_achado):
        marcar('rede social ou app de mensagem')
        return REMOVIDO

    def trocar_numero(achado):
        if not _eh_numero_de_contato(achado.group(0)):
            return achado.group(0)
        marcar('telefone ou documento')
        return REMOVIDO

    palavroes_extra, contato_extra, pessoais_extra, regex_extra = _separar_extras(extras)

    # A ordem importa: o e-mail sai antes do @perfil e do link.
    texto = _EMAIL.sub(trocar_email, texto)
    texto = _LINK.sub(trocar_link, texto)
    texto = _PERFIL.sub(trocar_perfil, texto)
    texto = _NUMERO.sub(trocar_numero, texto)
    for padrao in regex_extra:
        texto, quantidade = _regex_livre(padrao).subn(REMOVIDO, texto)
        if quantidade:
            marcar('dado pessoal')

    # Nomes de apps e palavras extras: procura na cópia normalizada e troca no original.
    for lista, motivo in ((APPS_DE_CONTATO + contato_extra, 'rede social ou app de mensagem'),
                          (pessoais_extra, 'dado pessoal')):
        regex = _regex_palavras(tuple(lista))
        trechos = [(m.start(), m.end()) for m in regex.finditer(normalizar(texto))] if regex else []
        if trechos:
            marcar(motivo)
            for inicio, fim in reversed(trechos):
                texto = texto[:inicio] + REMOVIDO + texto[fim:]

    regex_palavroes = _regex_palavras(tuple(PALAVROES + palavroes_extra))
    trechos = [(m.start(), m.end()) for m in regex_palavroes.finditer(normalizar(texto))]
    if trechos:
        marcar('palavrão')
        letras = list(texto)
        for inicio, fim in trechos:
            for i in range(inicio, fim):
                if not letras[i].isspace():
                    letras[i] = '*'
        texto = ''.join(letras)

    for indice, email in enumerate(guardados):
        texto = texto.replace('\uE000' + chr(0xE100 + indice) + '\uE000', email)

    return texto, motivos
