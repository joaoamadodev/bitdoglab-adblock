# Pinagem da BitDogLab

Baseada na Raspberry Pi Pico H/W — tudo são GPIOs dela. A maioria dos pinos é igual
em todas as versões; **só o barramento do OLED muda** entre as variantes.

Fontes: os **conectores** (I2C0/1, IDC, headers de garra) e o microfone (GP28) vêm do
README e do **datasheet oficial da V6**; os pinos dos **componentes on-board** (OLED, LED RGB,
botões, matriz, joystick) vêm dos **exemplos de código oficiais** (repo `BitDogLab-C` /
firmware EmbarcaTech), pois os docs de produto da V6 não os enumeram. Pinos da V7: BIH V7.

> ⚠️ **O OLED fica em pinos diferentes conforme a placa:**
> - **EmbarcaTech (TIC-37) / BitDogLab V6:** OLED em **GPIO14 (SDA) / GPIO15 (SCL)**, I2C1.
> - **BitDogLab Unicamp V7:** OLED em **GPIO2 (SDA) / GPIO3 (SCL)**, I2C1.
>
> Este projeto **detecta sozinho** qual é (procura o display 0x3C em 14/15 e depois 2/3),
> então funciona nas duas sem você configurar nada.

## Periféricos on-board

| Periférico | GPIO | Observações |
|---|---|---|
| LED RGB — vermelho | 13 | cátodo comum, resistor 220 Ω, PWM |
| LED RGB — verde | 11 | resistor 220 Ω, PWM |
| LED RGB — azul | 12 | resistor 150 Ω, PWM |
| Matriz 5x5 WS2812B (NeoPixel) | 7 | 25 LEDs; conector Dout/5V/GND no fim; jumper "Ext. RGB Neopixel" no verso |
| Botão A | 5 | outro terminal no GND → usar pull-up; apertado = LOW |
| Botão B | 6 | idem |
| **Botão C** | **10** | idem (na V7 existe o 3º botão) |
| Buzzer A | 21 | passivo, via transistor, PWM |
| **Display OLED (I2C1)** | **14/15** (EmbarcaTech/V6) ou **2/3** (V7) | SDA/SCL; endereço 0x3C; SSD1306 128x64 0.96" |
| Joystick KY023 — VRy | 26 | ADC0 |
| Joystick KY023 — VRx | 27 | ADC1 |
| Joystick KY023 — botão SW | 22 | pull-up; apertado = LOW |
| Microfone (eletreto, analógico) | 28 | ADC2; nível médio ~1,65 V, faixa 0–3,3 V |

Orientação lógica validada do joystick: `JOY_SWAP_XY=False`, `JOY_INVERT_X=True`, `JOY_INVERT_Y=True`.

## Conectores externos

| Conector | Pinos |
|---|---|
| I2C0 (canto superior direito) | SDA GPIO0, SCL GPIO1, 3V3, GND (também serve de UART TX/RX) |
| I2C1 (lateral esquerda) | SDA GPIO2, SCL GPIO3, 3V3, GND — **mesmos pinos do OLED** |
| Barra de garras (jacaré) | DIG0=GPIO0, DIG1=GPIO1, DIG2=GPIO2, DIG3=GPIO3, + GND analógico, GPIO28, GND, 3V3, 5V |

> Como GPIO2/3 são compartilhados entre OLED, conector I2C1 e DIG2/DIG3, **não** ligue
> periféricos externos nesses pinos enquanto usar o display.

### Conector IDC de expansão (14 pinos)

```
1 GND      2 5V       3 3V3      4 GPIO8
5 GPIO28   6 GPIO9    7 GND-ana  8 GPIO4
9 GPIO17  10 GND     11 GPIO16  12 GPIO19
13 GND    14 GPIO18
```
SPI no IDC: GPIO16 = MISO/RX, GPIO17 = CSn, GPIO18 = SCK, GPIO19 = MOSI/TX.

## Display OLED — observações

- A placa EmbarcaTech / V6 usa o **SSD1306 128x64 0.96"** (retangular). É o que o driver
  embutido deste projeto (`painel.py`) usa — funciona direto.
- Só a BitDogLab Unicamp V7 pode trazer, em vez dele, o **SH1107 128x128** (quadrado). Esse
  precisa do driver oficial `sh1107_bitdoglab.py` (em `libs_software/` no repo
  https://github.com/BitDogLab/BitDogLab) — drivers genéricos dão imagem deslocada/espelhada.
- Se o display não acender: desconecte periféricos externos do barramento do OLED e confira
  no REPL qual bus responde: `I2C(1, sda=Pin(14), scl=Pin(15)).scan()` deve devolver `[60]`
  (0x3C). Se não, teste com `Pin(2)/Pin(3)`.

## Pinos usados pelo projeto AdBlock
LED RGB (13/11/12), matriz (7), botões A e B (5/6) e OLED (autodetecta 14/15 ou 2/3, I2C1).
Livres para uso futuro: Botão C (10), buzzer (21), joystick (26/27/22), microfone (28).
