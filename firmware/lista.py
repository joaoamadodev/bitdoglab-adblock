# Consulta à lista de bloqueio guardada na flash da placa.
#
# A placa tem só 264 KB de RAM, então a lista não cabe na memória. O arquivo
# "bloqueio.bin" (gerado no PC por ferramentas/gerar_lista.py) guarda, para cada
# domínio, os 5 primeiros bytes do SHA-256, ORDENADOS. A busca é binária direto
# no arquivo (~17 leituras para 100 mil domínios).
#
#   "=dominio"  -> bloqueia só aquele nome exato (listas no formato hosts)
#   "*dominio"  -> bloqueia o domínio e todos os subdomínios (formato ||dominio^)
#
# 5 bytes = 40 bits: chance de falso positivo ~1 em 10 milhões por consulta.

import hashlib

TAM_REGISTRO = 5


def chave(prefixo, nome):
    return hashlib.sha256((prefixo + nome).encode()).digest()[:TAM_REGISTRO]


def sufixos(nome):
    """'a.b.exemplo.com' -> ['a.b.exemplo.com', 'b.exemplo.com', 'exemplo.com'] (sem o TLD sozinho)."""
    partes = nome.split(".")
    return [".".join(partes[i:]) for i in range(len(partes) - 1)] or [nome]


def ler_txt(caminho):
    """Lê um .txt de domínios (um por linha, # = comentário). Ausente -> conjunto vazio."""
    conj = set()
    try:
        with open(caminho) as f:
            for linha in f:
                d = linha.split("#")[0].strip().lower().rstrip(".")
                if d:
                    conj.add(d)
    except OSError:
        pass
    return conj


class ListaBloqueio:
    def __init__(self, caminho_bin, caminho_liberar=None, caminho_bloquear=None,
                 caminho_foco=None):
        self.f = None
        self.total = 0
        try:
            self.f = open(caminho_bin, "rb")
            self.f.seek(0, 2)
            self.total = self.f.tell() // TAM_REGISTRO
        except OSError:
            self.f = None
        # Listas pequenas editáveis direto na placa (valem para subdomínios também).
        self.caminho_liberar = caminho_liberar
        self.caminho_bloquear = caminho_bloquear
        self.liberar = ler_txt(caminho_liberar) if caminho_liberar else set()
        self.bloquear = ler_txt(caminho_bloquear) if caminho_bloquear else set()
        # "foco": distrações bloqueadas só quando foco_ativo (modo foco/estudo).
        self.foco = ler_txt(caminho_foco) if caminho_foco else set()
        self.foco_ativo = False
        self._cache = {}

    def _anexar(self, caminho, dom):
        if not caminho:
            return
        try:
            with open(caminho, "a") as f:
                f.write(dom + "\n")
        except OSError as e:
            print("nao salvou", dom, "em", caminho, ":", e)

    def adicionar_liberar(self, dom):
        novo = dom not in self.liberar
        self.liberar.add(dom)
        self.bloquear.discard(dom)   # liberar vence; tira de bloquear se estava lá
        self._cache = {}
        if novo:
            self._anexar(self.caminho_liberar, dom)
        return True

    def adicionar_bloquear(self, dom):
        novo = dom not in self.bloquear
        self.bloquear.add(dom)
        self._cache = {}
        if novo:
            self._anexar(self.caminho_bloquear, dom)
        return True

    def _tem(self, h):
        f = self.f
        lo, hi = 0, self.total - 1
        while lo <= hi:
            meio = (lo + hi) // 2
            f.seek(meio * TAM_REGISTRO)
            v = f.read(TAM_REGISTRO)
            if v == h:
                return True
            if v < h:
                lo = meio + 1
            else:
                hi = meio - 1
        return False

    def _decidir(self, nome):
        suf = sufixos(nome)
        for s in suf:
            if s in self.liberar:
                return False          # liberar sempre vence
        if self.foco_ativo:
            for s in suf:
                if s in self.foco:
                    return True       # modo foco: bloqueia as distrações
        for s in suf:
            if s in self.bloquear:
                return True
        if not self.f or not self.total:
            return False
        if self._tem(chave("=", nome)):
            return True
        for s in suf:
            if self._tem(chave("*", s)):
                return True
        return False

    def bloqueado(self, nome):
        r = self._cache.get(nome)
        if r is None:
            r = self._decidir(nome)
            if len(self._cache) >= 256:   # cache pequeno, para não estourar a RAM
                self._cache = {}
            self._cache[nome] = r
        return r
