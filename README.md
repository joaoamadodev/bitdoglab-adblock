# BitDogLab AdBlock

Bloqueador de anúncios para a **rede inteira** (celulares, TVs, PCs) rodando na placa
educacional **BitDogLab** (Raspberry Pi Pico W + MicroPython), no estilo do Pi-hole.
A placa vira o servidor DNS da casa: pedidos para domínios de anúncio recebem `0.0.0.0`,
e o resto é repassado ao 1.1.1.1.

```
celular ──"ads.x.com?"──► BitDogLab ──é anúncio──► responde 0.0.0.0 (anúncio não carrega)
                               └────não é───────► 1.1.1.1 ──► resposta volta ao celular
```

## Recursos
- 🛡️ **Bloqueio por DNS** de ~76 mil domínios de anúncios/rastreadores (lista StevenBlack).
- 🌐 **Painel web** com login: estatísticas ao vivo, gráfico por minuto, ranking dos mais
  bloqueados e liberar/bloquear domínios pelo navegador.
- 🎯 **Modo foco**: bloqueia redes sociais/distrações por 30 min (botão A ou pelo site).
- 📟 **Interface física**: display OLED, LED RGB de status, matriz 5×5 como medidor de
  tráfego e buzzer que avisa quando o Wi-Fi cai.
- 🔒 **Seguro por padrão**: responde só à LAN, protege contra respostas DNS forjadas, watchdog
  que reinicia sozinho, e detecção automática do barramento do display (V6/EmbarcaTech e V7).
- 🧪 Lógica testável no PC, sem a placa (`ferramentas/teste_pc.py`).

## Site de controle (painel no navegador)

A placa também serve um **painel web**. Abra, de qualquer aparelho DA SUA REDE:

```
http://IP_DA_PLACA/        (login: usuário "admin", senha = PAINEL_SENHA do config.py)
```

No painel você vê, em tempo real: estado (ativo/pausado), consultas, bloqueios, taxa, tempo
ligado, tamanho da lista, um **gráfico de consultas/bloqueios por minuto (última hora)**, o
**ranking dos domínios mais bloqueados** e os últimos domínios bloqueados. E você pode, pelo navegador:
**pausar/retomar** o bloqueio e **liberar** ou **bloquear** um domínio na hora (as mudanças
são salvas em `liberar.txt`/`bloquear.txt` na própria placa).

## Na placa

| Item | Função |
|---|---|
| LED RGB verde | bloqueando; **pisca vermelho** a cada anúncio barrado |
| LED roxo / matriz com "alvo" | **modo foco** ligado |
| LED azul / matriz com barras amarelas | bloqueio pausado |
| LED vermelho / matriz com X | sem Wi-Fi |
| **Botão A** | liga o **modo foco** por 30 min (bloqueia as distrações) |
| **Botão B** | cancela o foco; ou troca a tela, se não houver foco |
| Display OLED | IP, consultas, bloqueios, % e tempo ligado (ou "FOCO X min") |

### Modo foco (estudo/trabalho)
Durante o foco, além dos anúncios, a placa bloqueia os sites que distraem (redes sociais,
YouTube, etc. — a lista fica em `firmware/foco.txt`, você edita à vontade). Liga pelo **botão A**
(30 min, ajustável em `FOCO_MINUTOS`) ou pelo **botão do site**; **botão B** ou o site cancelam;
no fim do tempo volta sozinho ao normal.

Pinos: botões A/B 5 e 6, LED R 13 / G 11 / B 12, matriz WS2812 no 7, OLED I2C1.
Mapa completo em [PINAGEM.md](PINAGEM.md).

> ⚠️ O barramento do OLED muda conforme a placa: **GP14/15** na EmbarcaTech (TIC-37) e na
> BitDogLab V6, **GP2/3** na Unicamp V7. O projeto **detecta sozinho** (procura o display em
> 14/15 e depois em 2/3), então não precisa configurar. Para forçar, use `OLED_CANDIDATOS`
> no `config.py`. O display 128x64 (SSD1306) é o padrão; o 128x128 (SH1107, só em algumas V7)
> precisaria de outro driver — veja PINAGEM.md.

## Instalação (passo a passo)

### 1. MicroPython na placa
1. Baixe o firmware em https://micropython.org/download/RPI_PICO_W/
   (se a sua BitDogLab tiver **Pico 2 W**, use `RPI_PICO2_W`).
2. Segure o botão **BOOTSEL** da Pico, ligue o USB e solte. Vai aparecer um pendrive `RPI-RP2`.
3. Arraste o arquivo `.uf2` para dentro dele. A placa reinicia sozinha.

### 2. Ferramenta para copiar arquivos (PowerShell)
```
pip install mpremote
```

### 3. Gerar a lista de bloqueio (no PC)
```
cd "D:\Estudo - Tabalho\bitdoglab-adblock"
```
```
python ferramentas\gerar_lista.py
```
Isso cria `firmware\bloqueio.bin` (~400-500 KB).

### 4. Configurar
```
copy firmware\config.exemplo.py firmware\config.py
```
```
notepad firmware\config.py
```
Preencha o Wi-Fi e o **IP fixo** (ex.: `192.168.0.53`). Escolha um IP fora da faixa de DHCP
do roteador e confira se `GATEWAY` é o IP do roteador.

### 5. Copiar para a placa
```
cd firmware
```
```
mpremote cp config.py dns.py lista.py painel.py liberar.txt bloquear.txt bloqueio.bin :
```
```
mpremote cp main.py :
```
```
mpremote reset
```
Para ver o log ao vivo (Ctrl+] para sair):
```
mpremote repl
```

### 6. Testar antes de mexer no roteador
Troque o IP pelo da sua placa:
```
nslookup doubleclick.net 192.168.0.53
```
```
nslookup google.com 192.168.0.53
```
O primeiro deve responder `0.0.0.0` e o segundo, um IP normal.

### 7. Ativar para a rede toda
No painel do roteador (DHCP / LAN), coloque o **DNS primário = IP da placa**.
Reconecte o Wi-Fi dos aparelhos para que peguem o novo DNS.

## Acessar o painel de fora de casa (remoto de verdade)
Dentro de casa, o site já funciona em `http://IP_DA_PLACA/`. Para acessar **de fora**, NÃO
encaminhe a porta no roteador (vira alvo na internet). Use um dos caminhos seguros:
- **VPN do roteador** (WireGuard/OpenVPN): você entra na sua rede de casa e abre o IP da placa.
- **Tailscale** com *subnet router*: instale o Tailscale num dispositivo sempre ligado da rede
  (um PC, um Raspberry Pi) e publique a sub-rede da sua casa (ex.: `192.168.0.0/24`). Aí, de
  qualquer lugar logado na sua tailnet, você abre `http://IP_DA_PLACA/`. (O Tailscale não roda
  na própria Pico; por isso vai noutro aparelho da casa.)
Em ambos, o acesso continua protegido pela senha do painel e nada fica exposto na internet.

## Manutenção
- **Site quebrou?** Aperte o botão A (pausa), confirme, ponha o domínio em `firmware\liberar.txt` e rode
  `mpremote cp liberar.txt :` seguido de `mpremote reset`.
- **Bloquear algo a mais:** mesma coisa com `bloquear.txt`.
- **Atualizar a lista:** uma vez por mês, rode o passo 3 de novo e copie só o `bloqueio.bin`.
- **Testar a lógica no PC:** `python ferramentas\teste_pc.py`

## Limitações (é bom saber)
- **Anúncios do YouTube e Instagram não somem**: eles vêm do mesmo domínio do vídeo/conteúdo.
  Nenhum bloqueador por DNS (nem o Pi-hole) resolve isso.
- **DNS secundário no roteador:** se você colocar um secundário (ex.: 8.8.8.8), parte dos anúncios
  passa por ele. Se colocar só a placa e ela desligar, a internet "para" até ela voltar. A placa
  reinicia sozinha se travar (watchdog) ou perder o Wi-Fi, então o recomendado é **só a placa**,
  com fonte USB confiável.
- Navegadores com **DNS seguro (DoH)** ligado ignoram a placa. Desative em Chrome/Edge/Firefox
  se quiser bloquear neles.
- A placa só fala Wi-Fi 2.4 GHz e aguenta ~130 mil domínios na lista.
- Não atende DNS por TCP (raríssimo em casa).

## Segurança
- A placa **só responde a aparelhos da sua rede**; pedidos de fora são descartados.
  **Nunca** abra/encaminhe a porta 53 no roteador para a internet (vira DNS aberto e é usado em ataques).
- Respostas do DNS superior só são aceitas se vierem do IP configurado, com ID aleatório e pergunta
  idêntica (proteção contra resposta forjada).
- `config.py` contém a senha do Wi-Fi e a do painel: fica fora do Git (`.gitignore`).
- As listas são baixadas só por HTTPS e tratadas como texto: só entra o que for um domínio válido.
- **Painel web:** só responde à sua rede e exige login (senha em `PAINEL_SENHA`). Troque a senha
  padrão. É Basic Auth sobre HTTP (sem criptografia), então é seguro **só dentro da LAN** —
  para acesso externo use VPN/Tailscale (acima), nunca encaminhamento de porta.

## Estrutura do projeto
```
firmware/              Código que roda na placa (MicroPython)
  main.py              Servidor DNS + laço principal
  dns.py               Montagem/leitura de pacotes DNS
  lista.py             Busca na blocklist (binária na flash) + listas editáveis
  web.py               Painel web (servidor HTTP embutido)
  painel.py            OLED, LED RGB, matriz 5x5 e buzzer
  config.exemplo.py    Modelo de configuração (copie para config.py)
  foco.txt / liberar.txt / bloquear.txt   Listas editáveis
ferramentas/           Utilitários de PC
  gerar_lista.py       Gera a blocklist (bloqueio.bin) das fontes
  enviar.ps1           Envia os arquivos para a placa (mpremote)
  teste_pc.py          Testes da lógica, sem a placa
PINAGEM.md             Mapa de pinos da BitDogLab (V6/EmbarcaTech e V7)
```

## Licença
Distribuído sob a licença MIT. Veja [LICENSE](LICENSE).

---
Feito por **João Amado** como projeto educacional com a placa BitDogLab.
