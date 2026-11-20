# Leitura e montagem de pacotes DNS (RFC 1035) — só o necessário.
# Roda tanto no MicroPython da placa quanto no Python do PC (para testes).

TIPO_A = 1
TIPO_AAAA = 28
CLASSE_IN = 1

RCODE_SERVFAIL = 2


def ler_pergunta(pkt):
    """Lê a pergunta de uma CONSULTA.

    Retorna (nome, qtype, qclass, fim_da_pergunta) ou None se o pacote for
    malformado, for uma resposta, ou não for uma consulta padrão com 1 pergunta.
    Tudo é validado contra o tamanho do pacote: pacote ruim nunca derruba a placa.
    """
    n = len(pkt)
    if n < 12:
        return None
    if pkt[2] & 0x80:            # bit QR = 1 -> é resposta, não pergunta
        return None
    if (pkt[2] >> 3) & 0x0F:     # opcode diferente de QUERY
        return None
    if ((pkt[4] << 8) | pkt[5]) != 1:   # exatamente 1 pergunta
        return None
    i = 12
    partes = []
    total = 0
    while True:
        if i >= n:
            return None
        tam = pkt[i]
        i += 1
        if tam == 0:
            break
        if tam & 0xC0:           # compressão não é válida dentro da pergunta
            return None
        if i + tam > n:
            return None
        partes.append(bytes(pkt[i:i + tam]))
        i += tam
        total += tam + 1
        if total > 255:
            return None
    if i + 4 > n:
        return None
    qtype = (pkt[i] << 8) | pkt[i + 1]
    qclass = (pkt[i + 2] << 8) | pkt[i + 3]
    try:
        nome = b".".join(partes).decode().lower()
    except Exception:
        return None
    return nome, qtype, qclass, i + 4


def resposta_bloqueio(pkt, fim, qtype, ttl=60):
    """Resposta 'nulo' (estilo Pi-hole): A -> 0.0.0.0, AAAA -> ::, demais -> vazio."""
    rd = pkt[2] & 0x01
    tem_resp = qtype in (TIPO_A, TIPO_AAAA)
    cab = bytes((pkt[0], pkt[1], 0x80 | rd, 0x80, 0, 1, 0, 1 if tem_resp else 0, 0, 0, 0, 0))
    pergunta = bytes(pkt[12:fim])
    if not tem_resp:
        return cab + pergunta
    dados = b"\x00" * (4 if qtype == TIPO_A else 16)
    rr = bytes((0xC0, 0x0C, qtype >> 8, qtype & 0xFF, 0, CLASSE_IN,
                (ttl >> 24) & 0xFF, (ttl >> 16) & 0xFF, (ttl >> 8) & 0xFF, ttl & 0xFF,
                0, len(dados)))
    return cab + pergunta + rr + dados


def resposta_erro(pkt, fim, rcode):
    """Resposta de erro (ex.: SERVFAIL) para o cliente não ficar esperando."""
    rd = pkt[2] & 0x01
    cab = bytes((pkt[0], pkt[1], 0x80 | rd, 0x80 | (rcode & 0x0F), 0, 1, 0, 0, 0, 0, 0, 0))
    return cab + bytes(pkt[12:fim])
