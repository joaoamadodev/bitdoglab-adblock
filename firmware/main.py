# BitDogLab AdBlock — servidor DNS que bloqueia anúncios na rede inteira.
#
# Fluxo: celular/PC pergunta "ads.exemplo.com?" -> a placa consulta a lista:
#   - é anúncio  -> responde 0.0.0.0 na hora (o anúncio não carrega)
#   - não é      -> repassa para o DNS superior (1.1.1.1) e devolve a resposta
#
# Botão A: pausa/retoma o bloqueio.   Botão B: troca a tela do display.

import gc
import os
import time
import socket
import select
import network
import machine
import rp2

import config as cfg
import dns
from lista import ListaBloqueio
from painel import Painel
from web import ServidorWeb

MAX_PENDENTES = 64      # consultas aguardando o DNS superior
TEMPO_RESERVA = 1500    # ms sem resposta -> tenta o DNS reserva
TEMPO_DESISTIR = 4000   # ms sem resposta -> devolve SERVFAIL

wdt = machine.WDT(timeout=8000)   # se travar, a placa reinicia sozinha
painel = Painel(getattr(cfg, "BRILHO_MATRIZ", 6), getattr(cfg, "OLED_CANDIDATOS", None),
                getattr(cfg, "BUZZER_PINO", 21))


def ip_int(ip):
    a, b, c, d = (int(x) for x in ip.split("."))
    return (a << 24) | (b << 16) | (c << 8) | d


def esperar(ms):
    fim = time.ticks_add(time.ticks_ms(), ms)
    while time.ticks_diff(fim, time.ticks_ms()) > 0:
        wdt.feed()
        time.sleep_ms(100)


def conectar_wifi():
    rp2.country(cfg.PAIS_WIFI)
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.config(pm=0xA11140)   # desliga economia de energia: respostas mais rápidas
    if cfg.IP_FIXO:
        wlan.ifconfig((cfg.IP_FIXO, cfg.MASCARA, cfg.GATEWAY, cfg.DNS_SUPERIOR))
    for tentativa in range(1, 6):
        painel.texto(["BitDogLab", "AdBlock", "", "Conectando...", cfg.WIFI_SSID, "", "tentativa %d" % tentativa])
        painel.icone("erro")
        wlan.connect(cfg.WIFI_SSID, cfg.WIFI_SENHA)
        for _ in range(150):           # até 15 s
            wdt.feed()
            if wlan.isconnected():
                return wlan
            time.sleep_ms(100)
        wlan.disconnect()
    painel.texto(["Sem Wi-Fi!", "", "Confira SSID e", "senha no", "config.py", "", "Reiniciando..."])
    esperar(5000)
    machine.reset()


# ------------------------------------------------------------------ início
painel.cor(0, 0, 3000)
painel.texto(["BitDogLab", "AdBlock", "", "Carregando", "lista..."])
lista = ListaBloqueio("bloqueio.bin", "liberar.txt", "bloquear.txt", "foco.txt")
print("Lista: %d dominios (+%d extras, %d liberados, %d foco)"
      % (lista.total, len(lista.bloquear), len(lista.liberar), len(lista.foco)))

wlan = conectar_wifi()
meu_ip, mascara = wlan.ifconfig()[0], wlan.ifconfig()[1]
rede = ip_int(meu_ip) & ip_int(mascara)
masc = ip_int(mascara)
superiores = (cfg.DNS_SUPERIOR, cfg.DNS_SUPERIOR_RESERVA)
print("Conectado. DNS da rede -> %s" % meu_ip)

srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
srv.bind(("0.0.0.0", 53))
up = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# porta de origem aleatória: dificulta resposta forjada (envenenamento de cache)
up.bind(("0.0.0.0", 20000 + int.from_bytes(os.urandom(2), "big") % 40000))

poll = select.poll()
poll.register(srv, select.POLLIN)
poll.register(up, select.POLLIN)

# novo_id -> [endereco_cliente, id_original(bytes), pergunta(bytes), t0, tentativas, pacote, fim]
pendentes = {}
st = {"consultas": 0, "bloqueadas": 0, "erros": 0}
ultimos = []            # últimos domínios bloqueados (para a tela 2)
rank = {}               # domínio -> quantas vezes foi bloqueado (p/ ranking)
hist_c = []             # consultas por minuto (últimos 60 min, p/ gráfico)
hist_b = []             # bloqueadas por minuto (últimos 60 min)
base_c = 0
base_b = 0
pausado_ate = 0
foco_ate = 0            # modo foco: timestamp de término (0 = desligado)
sem_wifi_desde = 0
tela = 0
inicio = time.ticks_ms()


def estado():
    if sem_wifi_desde:
        return "erro"
    if pausado_ate:
        return "pausa"
    if foco_ate:
        return "foco"
    return "ativo"


def foco_restante():
    if not foco_ate:
        return 0
    ms = time.ticks_diff(foco_ate, time.ticks_ms())
    return ((ms + 59999) // 60000) if ms > 0 else 0   # arredonda p/ cima (30:00 -> 30)


def lan_ok(ip):
    try:
        return (ip_int(ip) & masc) == rede
    except Exception:
        return False


# ---- funções que o site chama (web.py) ----
def top_rank(n):
    itens = sorted(rank.items(), key=lambda kv: kv[1], reverse=True)[:n]
    return ["%s (%d)" % (d, c) for d, c in itens]


def web_status():
    c, b = st["consultas"], st["bloqueadas"]
    return {
        "estado": estado(), "ip": meu_ip,
        "consultas": c, "bloqueadas": b,
        "taxa": (b * 100 // c) if c else 0,
        "lista": lista.total, "extras": len(lista.bloquear), "liberados": len(lista.liberar),
        "uptime_min": time.ticks_diff(time.ticks_ms(), inicio) // 60000,
        "pausado": 1 if pausado_ate else 0,
        "foco": 1 if foco_ate else 0,
        "foco_min": foco_restante(),
        "erros": st["erros"],
        "ultimos": list(ultimos),
        "rank": top_rank(5),
        "hist_c": hist_c,
        "hist_b": hist_b,
    }


def web_pausar():
    global pausado_ate
    if pausado_ate:
        pausado_ate = 0
    else:
        pausado_ate = time.ticks_add(time.ticks_ms(), cfg.PAUSA_MINUTOS * 60000) or 1
    lista._cache = {}
    return pausado_ate


def _foco_on():
    global foco_ate
    foco_ate = time.ticks_add(time.ticks_ms(), cfg.FOCO_MINUTOS * 60000) or 1
    lista.foco_ativo = True
    lista._cache = {}


def _foco_off():
    global foco_ate
    foco_ate = 0
    lista.foco_ativo = False
    lista._cache = {}


def web_foco():
    if foco_ate:
        _foco_off()
    else:
        _foco_on()
    return foco_restante()


web = None
try:
    web = ServidorWeb(getattr(cfg, "PORTA_WEB", 80), getattr(cfg, "PAINEL_SENHA", ""),
                      web_status, web_pausar, lista.adicionar_liberar, lista.adicionar_bloquear,
                      web_foco, lan_ok)
    poll.register(web.sock, select.POLLIN)
    print("Site do painel -> http://%s/" % meu_ip)
except Exception as e:
    print("Site indisponivel:", e)


def do_cliente():
    pkt, addr = srv.recvfrom(512)
    try:
        if (ip_int(addr[0]) & masc) != rede:
            return                      # só atende a própria rede (nunca vira DNS aberto)
    except Exception:
        return
    p = dns.ler_pergunta(pkt)
    if p is None:
        return
    nome, qtype, qclass, fim = p
    st["consultas"] += 1
    if not pausado_ate and qclass == dns.CLASSE_IN and lista.bloqueado(nome):
        srv.sendto(dns.resposta_bloqueio(pkt, fim, qtype), addr)
        st["bloqueadas"] += 1
        ultimos.insert(0, nome)
        del ultimos[4:]
        rank[nome] = rank.get(nome, 0) + 1
        painel.piscar_bloqueio()
        return
    if len(pendentes) >= MAX_PENDENTES:
        srv.sendto(dns.resposta_erro(pkt, fim, dns.RCODE_SERVFAIL), addr)
        return
    while True:
        nid = int.from_bytes(os.urandom(2), "big")
        if nid not in pendentes:
            break
    q = bytearray(pkt)
    q[0], q[1] = nid >> 8, nid & 0xFF
    pendentes[nid] = [addr, bytes(pkt[0:2]), bytes(pkt[12:fim]), time.ticks_ms(), 1, q, fim]
    up.sendto(q, (superiores[0], 53))


def do_superior():
    pkt, addr = up.recvfrom(1500)
    if addr[0] not in superiores or len(pkt) < 12 or not (pkt[2] & 0x80):
        return
    nid = (pkt[0] << 8) | pkt[1]
    p = pendentes.get(nid)
    if p is None:
        return
    perg = p[2]
    if bytes(pkt[12:12 + len(perg)]) != perg:
        return                          # pergunta não confere: resposta forjada, ignora
    del pendentes[nid]
    r = bytearray(pkt)
    r[0], r[1] = p[1][0], p[1][1]
    srv.sendto(r, p[0])


def manutencao():
    agora = time.ticks_ms()
    for nid in list(pendentes):
        p = pendentes[nid]
        idade = time.ticks_diff(agora, p[3])
        if idade > TEMPO_DESISTIR:
            del pendentes[nid]
            st["erros"] += 1
            try:
                q = p[5]
                q[0], q[1] = p[1][0], p[1][1]
                srv.sendto(dns.resposta_erro(q, p[6], dns.RCODE_SERVFAIL), p[0])
            except Exception:
                pass
        elif idade > TEMPO_RESERVA and p[4] == 1:
            p[4] = 2
            try:
                up.sendto(p[5], (superiores[1], 53))
            except Exception:
                pass


def desenhar():
    c, b = st["consultas"], st["bloqueadas"]
    pct = (b * 100 // c) if c else 0
    if tela == 0:
        up_min = time.ticks_diff(time.ticks_ms(), inicio) // 60000
        if foco_ate:
            titulo = "FOCO %d min" % foco_restante()
        elif pausado_ate:
            titulo = "AdBlock PAUSADO"
        else:
            titulo = "AdBlock ATIVO"
        painel.texto([
            titulo,
            meu_ip,
            "",
            "Consultas %d" % c,
            "Bloqueio  %d" % b,
            "Taxa      %d%%" % pct,
            "Lista %dk" % (lista.total // 1000),
            "Ligado %dh%02dm" % (up_min // 60, up_min % 60),
        ])
    else:
        painel.texto(["Ult. bloqueados:", ""] + ([u[-16:] for u in ultimos] or ["(nenhum ainda)"]))


ult_tela = ult_manut = ult_wifi = ult_hist = ult_med = ult_bip = time.ticks_ms()
base_med = 0            # consultas no início da janela do medidor

while True:
    wdt.feed()
    try:
        for obj, ev in poll.poll(30):
            try:
                if obj is srv:
                    do_cliente()
                elif web is not None and web.e_meu(obj):
                    web.atender(wdt)
                else:
                    do_superior()
            except Exception as e:
                st["erros"] += 1
                print("erro pacote:", e)
    except Exception as e:
        print("erro poll:", e)

    agora = time.ticks_ms()

    if painel.apertou_a():
        _foco_on()                      # botão A: liga o modo foco por FOCO_MINUTOS
        desenhar()
    if painel.apertou_b():
        if foco_ate:
            _foco_off()                 # botão B: cancela o foco...
        else:
            tela = 1 - tela             # ...ou troca a tela, se não houver foco
        desenhar()
    if pausado_ate and time.ticks_diff(agora, pausado_ate) > 0:
        pausado_ate = 0                 # fim da pausa: volta a bloquear sozinho
    if foco_ate and time.ticks_diff(agora, foco_ate) > 0:
        _foco_off()                     # fim do foco: volta ao normal sozinho

    painel.atualizar_led(estado())
    painel.tick()                       # serviço do buzzer (não bloqueia)

    if time.ticks_diff(agora, ult_med) > 150:
        ult_med = agora
        if getattr(cfg, "MATRIZ_MEDIDOR", True) and estado() == "ativo":
            delta = st["consultas"] - base_med
            base_med = st["consultas"]
            painel.medidor(max(1, min(25, delta * 3)), "ativo")  # tráfego -> luz
        else:
            base_med = st["consultas"]
            painel.icone(estado())      # pausa/foco/erro: ícone de status

    if time.ticks_diff(agora, ult_manut) > 250:
        ult_manut = agora
        manutencao()
    if time.ticks_diff(agora, ult_tela) > 1000:
        ult_tela = agora
        desenhar()
        gc.collect()
    if time.ticks_diff(agora, ult_hist) > 60000:
        ult_hist = agora
        hist_c.append(st["consultas"] - base_c)
        hist_b.append(st["bloqueadas"] - base_b)
        base_c = st["consultas"]
        base_b = st["bloqueadas"]
        del hist_c[:-60]        # mantém só os últimos 60 minutos
        del hist_b[:-60]
        if len(rank) > 200:     # poda: guarda só os 60 mais bloqueados
            manter = dict(sorted(rank.items(), key=lambda kv: kv[1], reverse=True)[:60])
            rank.clear()
            rank.update(manter)

    if time.ticks_diff(agora, ult_wifi) > 5000:
        ult_wifi = agora
        if wlan.isconnected():
            sem_wifi_desde = 0
        else:
            alerta = getattr(cfg, "ALERTA_SONORO", True)
            if not sem_wifi_desde:
                sem_wifi_desde = agora
                ult_bip = agora
                if alerta:
                    painel.apitar()     # bipe no instante em que o Wi-Fi cai
            else:
                if alerta and time.ticks_diff(agora, ult_bip) > 15000:
                    ult_bip = agora
                    painel.apitar()     # re-bipa a cada 15 s enquanto estiver sem Wi-Fi
                if time.ticks_diff(agora, sem_wifi_desde) > 30000:
                    machine.reset()     # caiu o Wi-Fi por 30 s: reinicia e reconecta
