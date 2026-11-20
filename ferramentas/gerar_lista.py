"""Gera firmware/bloqueio.bin a partir de listas públicas de anúncios.

Uso (no PC):
    python ferramentas\\gerar_lista.py

Lê as URLs de ferramentas/fontes.txt, junta, remove o que estiver em
firmware/liberar.txt e grava os hashes ordenados que a placa consulta.
Só usa a biblioteca padrão do Python.
"""
import hashlib
import re
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FONTES = RAIZ / "ferramentas" / "fontes.txt"
SAIDA = RAIZ / "firmware" / "bloqueio.bin"
LIBERAR = RAIZ / "firmware" / "liberar.txt"

TAM_REGISTRO = 5           # tem que bater com firmware/lista.py
LIMITE_BYTES = 650_000     # a flash livre do MicroPython na Pico W é ~850 KB

DOMINIO = re.compile(r"^(?=.{1,253}$)([a-z0-9_]([a-z0-9_-]{0,61}[a-z0-9_])?\.)+[a-z][a-z0-9-]{0,62}$")
IGNORAR = {"localhost", "localhost.localdomain", "local", "broadcasthost", "ip6-localhost",
           "ip6-loopback", "0.0.0.0"}


def chave(prefixo, nome):
    return hashlib.sha256((prefixo + nome).encode()).digest()[:TAM_REGISTRO]


def ler_linhas_txt(caminho):
    if not caminho.exists():
        return []
    return [l.split("#")[0].strip().lower().rstrip(".") for l in caminho.read_text(encoding="utf-8").splitlines()]


def interpretar(texto):
    """Devolve (exatos, com_subdominios) de uma lista em formato hosts, domínios puros ou ||dominio^."""
    exatos, sufixos = set(), set()
    for linha in texto.splitlines():
        linha = linha.strip().lower()
        if not linha or linha[0] in "#!":
            continue
        if linha.startswith("||"):               # formato AdBlock: ||dominio^
            d = linha[2:].split("^")[0].split("$")[0]
            if "*" not in d and "/" not in d and DOMINIO.match(d):
                sufixos.add(d)
            continue
        if linha.startswith("@@") or "##" in linha:
            continue                              # regras cosméticas/exceções: não se aplicam a DNS
        partes = linha.split("#")[0].split()
        if not partes:
            continue
        if len(partes) >= 2 and partes[0] in ("0.0.0.0", "127.0.0.1", "::", "::1"):
            nomes = partes[1:]                    # formato hosts
        elif len(partes) == 1:
            nomes = partes                        # um domínio por linha
        else:
            continue
        for d in nomes:
            d = d.rstrip(".")
            if d not in IGNORAR and DOMINIO.match(d):
                exatos.add(d)
    return exatos, sufixos


def baixar(url):
    if not url.startswith("https://"):
        raise ValueError("só aceito HTTPS: " + url)
    req = urllib.request.Request(url, headers={"User-Agent": "bitdoglab-adblock/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(30_000_000).decode("utf-8", errors="ignore")


def liberado(d, liberar):
    partes = d.split(".")
    return any(".".join(partes[i:]) in liberar for i in range(len(partes)))


def gerar(textos, liberar):
    exatos, sufixos = set(), set()
    for t in textos:
        e, s = interpretar(t)
        exatos |= e
        sufixos |= s
    exatos = {d for d in exatos if not liberado(d, liberar)}
    sufixos = {d for d in sufixos if not liberado(d, liberar)}
    hashes = {chave("=", d) for d in exatos} | {chave("*", d) for d in sufixos}
    return b"".join(sorted(hashes)), len(exatos), len(sufixos)


def main():
    urls = [u for u in ler_linhas_txt(FONTES) if u]
    if not urls:
        sys.exit("Nenhuma URL em " + str(FONTES))
    textos = []
    for u in urls:
        print("Baixando", u)
        try:
            textos.append(baixar(u))
        except Exception as e:
            print("  FALHOU:", e)
    if not textos:
        sys.exit("Nenhuma lista baixada. Confira a internet.")
    liberar = {l for l in ler_linhas_txt(LIBERAR) if l}
    dados, n_exatos, n_suf = gerar(textos, liberar)
    print("Domínios exatos: %d | com subdomínios: %d | arquivo: %.0f KB"
          % (n_exatos, n_suf, len(dados) / 1024))
    if len(dados) > LIMITE_BYTES:
        sys.exit("Lista grande demais para a placa (%d KB > %d KB). Tire alguma URL de fontes.txt."
                 % (len(dados) // 1024, LIMITE_BYTES // 1024))
    SAIDA.write_bytes(dados)
    print("Gravado:", SAIDA)


if __name__ == "__main__":
    main()
