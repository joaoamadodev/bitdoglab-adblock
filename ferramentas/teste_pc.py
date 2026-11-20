"""Testa no PC a lógica que roda na placa (DNS + lista), sem precisar da BitDogLab.

    python ferramentas\\teste_pc.py
"""
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "firmware"))
sys.path.insert(0, str(RAIZ / "ferramentas"))

import dns                      # noqa: E402
from lista import ListaBloqueio  # noqa: E402
import gerar_lista              # noqa: E402
import web                      # noqa: E402
import binascii                 # noqa: E402


def consulta(nome, qtype=dns.TIPO_A, ident=0x1234):
    q = bytes((ident >> 8, ident & 0xFF, 0x01, 0x00, 0, 1, 0, 0, 0, 0, 0, 0))
    for parte in nome.split("."):
        q += bytes((len(parte),)) + parte.encode()
    return q + b"\x00" + bytes((qtype >> 8, qtype & 0xFF, 0, 1))


def main():
    hosts = """
# comentário
0.0.0.0 ads.exemplo.com
127.0.0.1 rastreador.net
0.0.0.0 localhost
||doubleclick-teste.com^
0.0.0.0 liberado.exemplo.org
"""
    dados, ne, ns = gerar_lista.gerar([hosts], {"exemplo.org"})
    assert (ne, ns) == (2, 1), (ne, ns)
    d = Path(tempfile.mkdtemp())
    (d / "b.bin").write_bytes(dados)
    (d / "lib.txt").write_text("site-bom.com\n")
    (d / "blq.txt").write_text("extra.com\n")
    (d / "foco.txt").write_text("youtube.com\nsite-bom.com\n")
    L = ListaBloqueio(str(d / "b.bin"), str(d / "lib.txt"), str(d / "blq.txt"), str(d / "foco.txt"))

    casos = {
        "ads.exemplo.com": True,        # exato
        "x.ads.exemplo.com": False,     # hosts = só exato
        "exemplo.com": False,
        "doubleclick-teste.com": True,  # ||dominio^ = com subdomínios
        "a.b.doubleclick-teste.com": True,
        "rastreador.net": True,
        "liberado.exemplo.org": False,  # removido pelo liberar no gerador
        "extra.com": True,              # bloquear.txt da placa
        "sub.extra.com": True,
        "google.com": False,
    }
    for nome, esperado in casos.items():
        assert L.bloqueado(nome) == esperado, nome

    # modo foco: distrações só bloqueiam quando foco_ativo
    assert not L.bloqueado("youtube.com")          # foco desligado
    L.foco_ativo = True
    L._cache = {}
    assert L.bloqueado("youtube.com") and L.bloqueado("m.youtube.com")
    assert not L.bloqueado("site-bom.com")         # liberar vence até no foco
    L.foco_ativo = False
    L._cache = {}
    assert not L.bloqueado("youtube.com")          # foco acabou

    # pacote de consulta -> pergunta
    q = consulta("Ads.Exemplo.COM")
    nome, qt, qc, fim = dns.ler_pergunta(q)
    assert (nome, qt, qc, fim) == ("ads.exemplo.com", 1, 1, len(q))

    # resposta de bloqueio A e AAAA
    r = dns.resposta_bloqueio(q, fim, dns.TIPO_A)
    assert r[:2] == q[:2] and r[2] & 0x80 and r[7] == 1 and r.endswith(b"\x00\x04\x00\x00\x00\x00")
    q6 = consulta("ads.exemplo.com", dns.TIPO_AAAA)
    r6 = dns.resposta_bloqueio(q6, dns.ler_pergunta(q6)[3], dns.TIPO_AAAA)
    assert r6.endswith(b"\x00\x10" + b"\x00" * 16)
    qh = consulta("ads.exemplo.com", 65)   # tipo HTTPS: resposta vazia
    rh = dns.resposta_bloqueio(qh, dns.ler_pergunta(qh)[3], 65)
    assert rh[7] == 0 and len(rh) == len(qh)

    # pacotes malformados não podem quebrar nada
    ruins = [b"", b"\x00" * 11, q[:-1], q[:14], bytes(q[:2]) + b"\x81\x80" + q[4:],
             q[:12] + b"\xc0\x0c" + q[-4:], q[:12] + b"\x3f" + b"a" * 10]
    for p in ruins:
        assert dns.ler_pergunta(p) is None, p
    import os
    for _ in range(20000):                 # fuzz aleatório
        dns.ler_pergunta(os.urandom(os.urandom(1)[0] % 80))

    testar_lista_persistencia()
    testar_web()
    print("OK — todos os testes passaram (%d casos de lista)." % len(casos))


def testar_lista_persistencia():
    d = Path(tempfile.mkdtemp())
    (d / "b.bin").write_bytes(b"")
    lib, blo = d / "lib.txt", d / "blo.txt"
    lib.write_text("")
    blo.write_text("")
    L = ListaBloqueio(str(d / "b.bin"), str(lib), str(blo))
    L.adicionar_bloquear("ruim.com")
    L.adicionar_bloquear("ruim.com")         # 2x não duplica no arquivo
    L.adicionar_liberar("bom.com")
    assert L.bloqueado("ruim.com") and L.bloqueado("x.ruim.com")
    assert not L.bloqueado("bom.com")
    # recarrega do disco: tem que persistir
    L2 = ListaBloqueio(str(d / "b.bin"), str(lib), str(blo))
    assert "ruim.com" in L2.bloquear and "bom.com" in L2.liberar
    assert lib.read_text().count("bom.com") == 1
    assert blo.read_text().count("ruim.com") == 1
    # liberar vence bloquear
    L2.adicionar_bloquear("conflito.com")
    L2.adicionar_liberar("conflito.com")
    assert not L2.bloqueado("conflito.com")


class _FakeConn:
    def __init__(self, req):
        self._req = req
        self.enviado = b""
    def settimeout(self, t): pass
    def recv(self, n):
        if not self._req:
            return b""
        ch, self._req = self._req[:n], self._req[n:]
        return ch
    def sendall(self, d): self.enviado += d
    def close(self): pass


class _FakeListen:
    def __init__(self, conn): self._conn = conn
    def accept(self):
        if self._conn is None:
            raise OSError("vazio")
        c, self._conn = self._conn, None
        return c, ("127.0.0.1", 50000)


class _FakeWdt:
    def feed(self): pass


def _servidor():
    estado = {"pausado": 0, "liberados": [], "bloqueados": []}
    sw = web.ServidorWeb.__new__(web.ServidorWeb)   # sem bind de socket real
    sw.cb_status = lambda: {"estado": "ativo", "ip": "192.168.0.53", "consultas": 10,
                            "bloqueadas": 4, "taxa": 40, "lista": 76000, "extras": 1,
                            "liberados": 0, "uptime_min": 5, "pausado": estado["pausado"],
                            "erros": 0, "ultimos": ["ads.x.com", "track.y.net"],
                            "rank": ["ads.x.com (3)", "track.y.net (1)"],
                            "hist_c": [0, 5, 12], "hist_b": [0, 2, 4]}
    def pausar():
        estado["pausado"] ^= 1
        return estado["pausado"]
    sw.cb_pausar = pausar
    sw.cb_liberar = lambda d: estado["liberados"].append(d)
    sw.cb_bloquear = lambda d: estado["bloqueados"].append(d)
    def foco():
        estado["foco"] = 0 if estado.get("foco") else 30
        return estado["foco"]
    sw.cb_foco = foco
    sw.lan_ok = lambda ip: True
    tok = binascii.b2a_base64(b"admin:segredo").strip()
    sw._auth = b"Basic " + tok
    return sw, estado, b"Basic " + tok


def _req(sw, texto):
    conn = _FakeConn(texto if isinstance(texto, bytes) else texto.encode())
    sw.sock = _FakeListen(conn)
    sw.atender(_FakeWdt())
    return conn.enviado


def testar_web():
    # validador de domínio e decode de url
    assert web._dom_valido("Ads.Exemplo.COM") == "ads.exemplo.com"
    assert web._dom_valido("ruim/path") is None
    assert web._dom_valido("semponto") is None
    assert web._desurl("site%2Ecom") == "site.com"

    sw, estado, auth = _servidor()

    # sem auth -> 401
    r = _req(sw, "GET / HTTP/1.1\r\nHost: x\r\n\r\n")
    assert b"401" in r and b"WWW-Authenticate" in r

    # com auth -> página
    r = _req(sw, b"GET / HTTP/1.1\r\nHost: x\r\nAuthorization: " + auth + b"\r\n\r\n")
    assert b"200 OK" in r and b"BitDogLab AdBlock" in r

    # /api -> json com os campos
    r = _req(sw, b"GET /api HTTP/1.1\r\nAuthorization: " + auth + b"\r\n\r\n")
    assert b"200 OK" in r and b'"consultas":10' in r and b'"ip":"192.168.0.53"' in r
    assert b'"ultimos":["ads.x.com","track.y.net"]' in r
    assert b'"hist_c":[0,5,12]' in r and b'"hist_b":[0,2,4]' in r   # listas de números
    assert b'"rank":["ads.x.com (3)","track.y.net (1)"]' in r

    # pausar alterna
    r = _req(sw, b"POST /pausar HTTP/1.1\r\nAuthorization: " + auth + b"\r\n\r\n")
    assert b'"pausado":1' in r and estado["pausado"] == 1

    # modo foco alterna (liga 30 min, desliga)
    r = _req(sw, b"POST /foco HTTP/1.1\r\nAuthorization: " + auth + b"\r\n\r\n")
    assert b'"foco":1' in r and b'"foco_min":30' in r and estado["foco"] == 30
    r = _req(sw, b"POST /foco HTTP/1.1\r\nAuthorization: " + auth + b"\r\n\r\n")
    assert b'"foco":0' in r and estado["foco"] == 0

    # liberar com corpo urlencoded
    corpo = b"d=meusite.com"
    r = _req(sw, b"POST /liberar HTTP/1.1\r\nAuthorization: " + auth +
             b"\r\nContent-Length: " + str(len(corpo)).encode() + b"\r\n\r\n" + corpo)
    assert b'"ok":true' in r and estado["liberados"] == ["meusite.com"]

    # bloquear com domínio inválido -> ok:false
    corpo = b"d=invalido"
    r = _req(sw, b"POST /bloquear HTTP/1.1\r\nAuthorization: " + auth +
             b"\r\nContent-Length: " + str(len(corpo)).encode() + b"\r\n\r\n" + corpo)
    assert b'"ok":false' in r and estado["bloqueados"] == []

    # rota desconhecida -> 404
    r = _req(sw, b"GET /xpto HTTP/1.1\r\nAuthorization: " + auth + b"\r\n\r\n")
    assert b"404" in r


if __name__ == "__main__":
    main()
