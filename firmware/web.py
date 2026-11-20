# Servidor web embutido: painel de controle do AdBlock no navegador.
#
# Roda dentro do mesmo laço de eventos do main.py (via select.poll), então NÃO
# trava o DNS. Serve uma página única que, por JavaScript, lê /api a cada 2 s e
# manda ações (pausar, liberar, bloquear) de volta.
#
# SEGURANÇA:
#  - só responde a aparelhos da própria rede (mesmo bloco do IP da placa);
#  - exige senha (HTTP Basic Auth) para QUALQUER acesso;
#  - nunca deve ser exposto à internet (não encaminhe a porta no roteador).
#    Para acessar de fora de casa, use uma VPN no roteador — veja o README.

import socket
import binascii

LIMITE_REQ = 4096       # corta requisições grandes (protege a RAM da placa)
_OK_DOM = "abcdefghijklmnopqrstuvwxyz0123456789-._"

PAGINA = b"""<!DOCTYPE html><html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BitDogLab AdBlock</title><style>
:root{color-scheme:dark light}
*{box-sizing:border-box}
body{font-family:system-ui,Arial,sans-serif;margin:0;background:#0f1115;color:#e6e6e6;
 -webkit-text-size-adjust:100%}
header{background:#161a22;padding:16px;text-align:center;border-bottom:1px solid #262b36}
h1{margin:0;font-size:18px}
main{max-width:620px;margin:0 auto;padding:16px}
.badge{display:inline-block;padding:4px 12px;border-radius:999px;font-weight:600;font-size:13px}
.ativo{background:#123d1b;color:#5bd97a}.pausa{background:#3d3312;color:#e7c14b}
.erro{background:#3d1212;color:#ee7777}.foco{background:#2a1a3d;color:#c89bf0}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:16px 0}
.card{background:#161a22;border:1px solid #262b36;border-radius:12px;padding:14px}
.card .n{font-size:26px;font-weight:700}.card .l{font-size:12px;color:#9aa4b2;margin-top:2px}
button{background:#2a6df4;color:#fff;border:0;border-radius:10px;padding:12px 16px;
 font-size:15px;font-weight:600;cursor:pointer;width:100%}
button.sec{background:#2a2f3a}
input{width:100%;padding:11px;border-radius:10px;border:1px solid #39404d;background:#0f1115;
 color:#e6e6e6;font-size:15px}
.row{display:flex;gap:8px;margin:8px 0}.row input{flex:1}.row button{width:auto;white-space:nowrap}
ul{list-style:none;padding:0;margin:8px 0}li{padding:7px 10px;background:#12151c;border-radius:8px;
 margin-bottom:5px;font-family:monospace;font-size:13px;word-break:break-all}
.msg{min-height:18px;font-size:13px;color:#5bd97a;margin-top:6px}
small{color:#9aa4b2}
</style></head><body>
<header><h1>BitDogLab AdBlock</h1><div id="ip"><small>conectando...</small></div></header>
<main>
<div style="text-align:center"><span id="estado" class="badge ativo">...</span></div>
<div class="grid">
 <div class="card"><div class="n" id="consultas">-</div><div class="l">Consultas</div></div>
 <div class="card"><div class="n" id="bloqueadas">-</div><div class="l">Bloqueadas</div></div>
 <div class="card"><div class="n" id="taxa">-</div><div class="l">Taxa de bloqueio</div></div>
 <div class="card"><div class="n" id="uptime">-</div><div class="l">Ligado</div></div>
</div>
<svg id="graf" viewBox="0 0 600 120" width="100%" preserveAspectRatio="none"
 style="background:#12151c;border-radius:12px;display:block"></svg>
<div style="text-align:center;margin:4px 0 12px">
 <small><span style="color:#7a8696">&#9632; consultas</span> &nbsp;
 <span style="color:#ee5555">&#9632; bloqueadas</span> &nbsp; por minuto (ultima hora)</small></div>
<button id="btpausa" onclick="pausar()">Pausar bloqueio</button>
<button id="btfoco" class="sec" onclick="foco()" style="margin-top:8px">Ativar modo foco (30 min)</button>
<div class="msg" id="msg"></div>
<div class="row"><input id="lib" placeholder="liberar dominio (ex: site.com)">
 <button class="sec" onclick="enviar('liberar','lib')">Liberar</button></div>
<div class="row"><input id="blo" placeholder="bloquear dominio (ex: ads.com)">
 <button class="sec" onclick="enviar('bloquear','blo')">Bloquear</button></div>
<p><small>Lista: <span id="lista">-</span> dominios &middot; <span id="extras">-</span> extras &middot;
 <span id="liberados">-</span> liberados &middot; <span id="erros">-</span> erros</small></p>
<h3 style="font-size:14px">Mais bloqueados</h3><ol id="rank" style="padding-left:18px"><li>-</li></ol>
<h3 style="font-size:14px">Ultimos bloqueados</h3><ul id="ultimos"><li>-</li></ul>
</main>
<script>
function g(id){return document.getElementById(id)}
async function atualiza(){
 try{let r=await fetch('/api');let d=await r.json();
  let e=g('estado'),cls='ativo',txt='ATIVO';
  if(d.estado=='erro'){cls='erro';txt='SEM WIFI';}
  else if(d.pausado){cls='pausa';txt='PAUSADO';}
  else if(d.foco){cls='foco';txt='FOCO '+d.foco_min+'min';}
  e.className='badge '+cls;e.textContent=txt;
  g('btfoco').textContent=d.foco?('Modo foco: '+d.foco_min+' min (cancelar)'):'Ativar modo foco (30 min)';
  g('ip').innerHTML='<small>'+d.ip+'</small>';
  g('consultas').textContent=d.consultas;g('bloqueadas').textContent=d.bloqueadas;
  g('taxa').textContent=d.taxa+'%';
  g('uptime').textContent=(d.uptime_min>=60?((d.uptime_min/60|0)+'h'+(d.uptime_min%60)+'m'):d.uptime_min+'m');
  g('lista').textContent=d.lista;g('extras').textContent=d.extras;
  g('liberados').textContent=d.liberados;g('erros').textContent=d.erros;
  g('btpausa').textContent=d.pausado?'Retomar bloqueio':'Pausar bloqueio';
  let u=g('ultimos');u.innerHTML='';
  if(!d.ultimos.length)u.innerHTML='<li>(nenhum ainda)</li>';
  else d.ultimos.forEach(x=>{let li=document.createElement('li');li.textContent=x;u.appendChild(li)});
  let rk=g('rank');rk.innerHTML='';
  if(!d.rank||!d.rank.length)rk.innerHTML='<li>(nada ainda)</li>';
  else d.rank.forEach(x=>{let li=document.createElement('li');li.textContent=x;rk.appendChild(li)});
  grafico(d.hist_c||[],d.hist_b||[]);
 }catch(e){}
}
function grafico(c,b){
 let W=600,H=120,bw=W/60,max=1;
 for(let i=0;i<c.length;i++)if(c[i]>max)max=c[i];
 let x0=W-c.length*bw,s='';
 for(let i=0;i<c.length;i++){
  let hc=Math.round(c[i]/max*(H-4)),hb=Math.round((b[i]||0)/max*(H-4)),xi=(x0+i*bw);
  s+='<rect x="'+xi.toFixed(1)+'" y="'+(H-hc)+'" width="'+(bw-1).toFixed(1)+'" height="'+hc+'" fill="#4a5568"/>';
  if(hb>0)s+='<rect x="'+xi.toFixed(1)+'" y="'+(H-hb)+'" width="'+(bw-1).toFixed(1)+'" height="'+hb+'" fill="#ee5555"/>';
 }
 g('graf').innerHTML=s;
}
async function pausar(){await fetch('/pausar',{method:'POST'});atualiza()}
async function foco(){await fetch('/foco',{method:'POST'});atualiza()}
async function enviar(acao,campo){
 let v=g(campo).value.trim();if(!v)return;
 let r=await fetch('/'+acao,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
  body:'d='+encodeURIComponent(v)});
 let d=await r.json();g('msg').textContent=d.ok?(acao+': '+d.dom+' OK'):('dominio invalido');
 g(campo).value='';atualiza();setTimeout(()=>g('msg').textContent='',3000);
}
atualiza();setInterval(atualiza,2000);
</script></body></html>"""


def _dom_valido(d):
    d = d.strip().lower().rstrip(".")
    if not d or len(d) > 253 or "." not in d:
        return None
    for c in d:
        if c not in _OK_DOM:
            return None
    return d


def _desurl(s):
    # decodifica %XX o suficiente para um domínio vindo de formulário
    out = ""
    i = 0
    while i < len(s):
        c = s[i]
        if c == "+":
            out += " "
        elif c == "%" and i + 2 < len(s):
            try:
                out += chr(int(s[i + 1:i + 3], 16))
                i += 2
            except Exception:
                out += c
        else:
            out += c
        i += 1
    return out


class ServidorWeb:
    def __init__(self, porta, senha, cb_status, cb_pausar, cb_liberar, cb_bloquear,
                 cb_foco=None, lan_ok=None):
        self.cb_status = cb_status
        self.cb_pausar = cb_pausar
        self.cb_liberar = cb_liberar
        self.cb_bloquear = cb_bloquear
        self.cb_foco = cb_foco
        self.lan_ok = lan_ok
        self._auth = None
        if senha:
            tok = binascii.b2a_base64(b"admin:" + senha.encode()).strip()
            self._auth = b"Basic " + tok
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", porta))
        self.sock.listen(2)
        self.sock.setblocking(False)

    def registrar(self, poll, flag):
        poll.register(self.sock, flag)

    def e_meu(self, obj):
        return obj is self.sock

    # ---- resposta ----
    def _resp(self, conn, status, ctype, corpo, extra=b""):
        if isinstance(corpo, str):
            corpo = corpo.encode()
        cab = b"HTTP/1.1 " + status + b"\r\nContent-Type: " + ctype + \
            b"\r\nContent-Length: " + str(len(corpo)).encode() + \
            b"\r\nConnection: close\r\n" + extra + b"\r\n"
        try:
            conn.sendall(cab + corpo)
        except Exception:
            pass

    def _json(self, conn, obj):
        # serializador mínimo (evita depender de ujson e controla o conteúdo)
        partes = []
        for k, v in obj.items():
            if isinstance(v, bool):
                v = "true" if v else "false"
            elif isinstance(v, str):
                v = '"%s"' % v.replace('"', "")
            elif isinstance(v, (list, tuple)):
                itens = []
                for x in v:
                    if isinstance(x, bool):
                        itens.append("true" if x else "false")
                    elif isinstance(x, (int, float)):
                        itens.append(str(x))
                    else:
                        itens.append('"%s"' % str(x).replace('"', ""))
                v = "[" + ",".join(itens) + "]"
            partes.append('"%s":%s' % (k, v))
        self._resp(conn, b"200 OK", b"application/json", "{" + ",".join(partes) + "}")

    def atender(self, wdt):
        try:
            conn, addr = self.sock.accept()
        except Exception:
            return
        try:
            if self.lan_ok and not self.lan_ok(addr[0]):
                self._resp(conn, b"403 Forbidden", b"text/plain", "rede nao autorizada")
                return
            conn.settimeout(1.5)
            dados = b""
            while b"\r\n\r\n" not in dados and len(dados) < LIMITE_REQ:
                try:
                    ch = conn.recv(512)
                except Exception:
                    break
                if not ch:
                    break
                dados += ch
            if not dados:
                return
            wdt.feed()
            cab, _, corpo = dados.partition(b"\r\n\r\n")
            linhas = cab.split(b"\r\n")
            try:
                metodo, caminho, _ = linhas[0].split(b" ", 2)
            except Exception:
                self._resp(conn, b"400 Bad Request", b"text/plain", "erro")
                return

            # autenticação
            if self._auth is not None:
                tem = None
                cl = 0
                for ln in linhas[1:]:
                    low = ln.lower()
                    if low.startswith(b"authorization:"):
                        tem = ln.split(b":", 1)[1].strip()
                    elif low.startswith(b"content-length:"):
                        try:
                            cl = int(ln.split(b":", 1)[1])
                        except Exception:
                            cl = 0
                if tem != self._auth:
                    self._resp(conn, b"401 Unauthorized", b"text/plain", "login necessario",
                               b'WWW-Authenticate: Basic realm="AdBlock"\r\n')
                    return
            else:
                cl = 0
                for ln in linhas[1:]:
                    if ln.lower().startswith(b"content-length:"):
                        try:
                            cl = int(ln.split(b":", 1)[1])
                        except Exception:
                            cl = 0

            # completa o corpo do POST, se faltou
            while len(corpo) < cl and len(corpo) < 1024:
                try:
                    ch = conn.recv(512)
                except Exception:
                    break
                if not ch:
                    break
                corpo += ch

            # rotas
            if caminho == b"/" or caminho == b"/index.html":
                self._resp(conn, b"200 OK", b"text/html; charset=utf-8", PAGINA)
            elif caminho == b"/api":
                self._json(conn, self.cb_status())
            elif caminho == b"/pausar" and metodo == b"POST":
                p = self.cb_pausar()
                self._json(conn, {"pausado": 1 if p else 0})
            elif caminho == b"/foco" and metodo == b"POST" and self.cb_foco:
                m = self.cb_foco()
                self._json(conn, {"foco": 1 if m else 0, "foco_min": m})
            elif caminho in (b"/liberar", b"/bloquear") and metodo == b"POST":
                dom = ""
                txt = corpo.decode("utf-8", "ignore")
                if txt.startswith("d="):
                    dom = _desurl(txt[2:].split("&")[0])
                dom = _dom_valido(dom)
                if not dom:
                    self._json(conn, {"ok": False})
                else:
                    if caminho == b"/liberar":
                        self.cb_liberar(dom)
                    else:
                        self.cb_bloquear(dom)
                    self._json(conn, {"ok": True, "dom": dom})
            else:
                self._resp(conn, b"404 Not Found", b"text/plain", "nao encontrado")
        except Exception as e:
            print("web erro:", e)
        finally:
            try:
                conn.close()
            except Exception:
                pass
