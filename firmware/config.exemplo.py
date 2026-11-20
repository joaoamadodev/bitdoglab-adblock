# Copie este arquivo para "config.py" e preencha com os dados da SUA rede.
# O config.py contém a senha do Wi-Fi: não compartilhe nem suba para o Git.

WIFI_SSID = "NOME_DA_SUA_REDE"
WIFI_SENHA = "SENHA_DA_SUA_REDE"
PAIS_WIFI = "BR"

# IP fixo da placa na rede. É ESTE IP que você vai colocar como DNS no roteador.
# Escolha um IP fora da faixa do DHCP do roteador (ou faça uma "reserva DHCP"
# no roteador e coloque IP_FIXO = None).
IP_FIXO = "192.168.0.53"
MASCARA = "255.255.255.0"
GATEWAY = "192.168.0.1"

# Para onde vão as consultas que NÃO são de anúncio.
DNS_SUPERIOR = "1.1.1.1"          # Cloudflare
DNS_SUPERIOR_RESERVA = "8.8.8.8"  # Google (usado se o primeiro não responder)

# Pausa do bloqueio (pelo painel web) dura este tempo, depois volta sozinho.
PAUSA_MINUTOS = 10

# Modo foco: botão A da placa (ou o site) liga por este tempo; botão B cancela.
# Bloqueia as distrações listadas em foco.txt além dos anúncios.
FOCO_MINUTOS = 30

# --- Site de controle (painel no navegador) ---
# Acesse em http://IP_DA_PLACA/ por qualquer aparelho DA SUA REDE.
# Usuário do login é sempre "admin"; a senha é a de baixo. TROQUE por uma sua.
# Deixe PAINEL_SENHA = "" para desligar o login (NÃO recomendado).
# NUNCA encaminhe esta porta no roteador para a internet (veja o README).
PAINEL_SENHA = "troque-esta-senha"
PORTA_WEB = 80

# Brilho da matriz 5x5 de LEDs (0 = desligada, máx. 255; acima de 20 ofusca).
BRILHO_MATRIZ = 6

# Matriz 5x5 como medidor de tráfego (True) ou só ícone de status (False).
MATRIZ_MEDIDOR = True
# Buzzer apita quando o Wi-Fi cai. BUZZER_PINO = 21 na BitDogLab.
ALERTA_SONORO = True
BUZZER_PINO = 21

# Display OLED: por padrão o projeto DETECTA o barramento sozinho, testando
# GP14/15 (EmbarcaTech / BitDogLab V6) e depois GP2/3 (BitDogLab Unicamp V7).
# Normalmente você NÃO precisa mexer aqui. Para forçar um barramento específico,
# descomente e deixe só o seu, no formato (bus_i2c, SDA, SCL):
# OLED_CANDIDATOS = [(1, 14, 15)]   # EmbarcaTech / V6
# OLED_CANDIDATOS = [(1, 2, 3)]     # Unicamp V7
