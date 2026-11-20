# Interface da BitDogLab: display OLED, LED RGB, matriz 5x5 e botões A/B.
# Pinagem comum às duas variantes: LED RGB (R 13, G 11, B 12),
# botão A = GP5, botão B = GP6, matriz WS2812 = GP7.
# OLED: o barramento MUDA conforme a placa —
#   EmbarcaTech (TIC-37): I2C1 em GP14/GP15
#   BitDogLab Unicamp V7: I2C1 em GP2/GP3
# Por isso detectamos o barramento automaticamente (procura o display em 0x3C).
# Este driver é do SSD1306 (128x64). Se a placa tiver o OLED 128x128 (SH1107),
# ele não funciona aqui — veja a nota no README/PINAGEM.
# Se algum periférico falhar, o bloqueador continua funcionando sem ele.

import time
import framebuf
from machine import Pin, PWM, I2C


class SSD1306(framebuf.FrameBuffer):
    """Driver mínimo do display OLED 128x64."""

    def __init__(self, i2c, addr=0x3C, w=128, h=64):
        self.i2c, self.addr, self.w, self.h = i2c, addr, w, h
        self.buf = bytearray(w * h // 8)
        super().__init__(self.buf, w, h, framebuf.MONO_VLSB)
        for c in (0xAE, 0x20, 0x00, 0x40, 0xA1, 0xA8, h - 1, 0xC8, 0xD3, 0x00,
                  0xDA, 0x12, 0xD5, 0x80, 0xD9, 0xF1, 0xDB, 0x30, 0x81, 0xFF,
                  0xA4, 0xA6, 0x8D, 0x14, 0xAF):
            self._cmd(c)

    def _cmd(self, c):
        self.i2c.writeto(self.addr, bytes((0x80, c)))

    def show(self):
        for c in (0x21, 0, self.w - 1, 0x22, 0, self.h // 8 - 1):
            self._cmd(c)
        self.i2c.writevto(self.addr, (b"\x40", self.buf))


# Desenhos 5x5 simétricos (ficam certos em qualquer ordem de fiação da matriz).
_ICONES = {
    "ativo": ("..#..", ".###.", "#####", ".###.", "..#.."),
    "pausa": (".#.#.", ".#.#.", ".#.#.", ".#.#.", ".#.#."),
    "erro":  ("#...#", ".#.#.", "..#..", ".#.#.", "#...#"),
    "foco":  ("#####", "#...#", "#.#.#", "#...#", "#####"),
}
_CORES = {"ativo": (0, 1, 0), "pausa": (1, 1, 0), "erro": (1, 0, 0), "foco": (1, 0, 1)}


class Painel:
    def __init__(self, brilho_matriz=6, oled_candidatos=None, buzzer_pino=21):
        # Testa cada (bus, sda, scl) e fica no 1º que tiver um display no 0x3C.
        # Default cobre EmbarcaTech (GP14/15) e BitDogLab Unicamp V7 (GP2/3).
        self.oled = None
        self.oled_pinos = None
        for bus, sda, scl in (oled_candidatos or [(1, 14, 15), (1, 2, 3)]):
            try:
                i2c = I2C(bus, sda=Pin(sda), scl=Pin(scl), freq=400000)
                if 0x3C in i2c.scan():
                    self.oled = SSD1306(i2c)
                    self.oled_pinos = (sda, scl)
                    print("OLED encontrado em GP%d/GP%d (I2C%d)" % (sda, scl, bus))
                    break
            except Exception as e:
                print("OLED GP%d/GP%d falhou:" % (sda, scl), e)
        if not self.oled:
            print("OLED indisponivel (nenhum display 0x3C encontrado)")
        self.led = {}
        for cor, pino in (("r", 13), ("g", 11), ("b", 12)):
            p = PWM(Pin(pino))
            p.freq(1000)
            p.duty_u16(0)
            self.led[cor] = p
        self.bt_a = Pin(5, Pin.IN, Pin.PULL_UP)
        self.bt_b = Pin(6, Pin.IN, Pin.PULL_UP)
        self._ult_a = self._ult_b = 1
        self.matriz = None
        self.brilho = max(0, min(255, brilho_matriz))
        if self.brilho:
            try:
                import neopixel
                self.matriz = neopixel.NeoPixel(Pin(7), 25)
            except Exception as e:
                print("Matriz indisponivel:", e)
        self._icone = None
        self._piscar_ate = 0
        # buzzer passivo (GP21) para alertas sonoros
        self.buzzer = None
        self._buzzer_ate = 0
        try:
            self.buzzer = PWM(Pin(buzzer_pino))
            self.buzzer.duty_u16(0)
        except Exception as e:
            print("Buzzer indisponivel:", e)

    # ---------- LED RGB ----------
    def cor(self, r, g, b):
        for nome, v in (("r", r), ("g", g), ("b", b)):
            self.led[nome].duty_u16(v)

    def piscar_bloqueio(self):
        """Pisca vermelho rapidamente a cada anúncio bloqueado."""
        self.cor(4000, 0, 0)
        self._piscar_ate = time.ticks_add(time.ticks_ms(), 60)

    def atualizar_led(self, estado):
        if self._piscar_ate and time.ticks_diff(time.ticks_ms(), self._piscar_ate) < 0:
            return
        self._piscar_ate = 0
        if estado == "ativo":
            self.cor(0, 1500, 0)
        elif estado == "pausa":
            self.cor(0, 0, 3000)
        elif estado == "foco":
            self.cor(2500, 0, 3500)
        else:
            self.cor(6000, 0, 0)

    # ---------- matriz 5x5 ----------
    def icone(self, estado):
        if not self.matriz or estado == self._icone:
            return
        self._icone = estado
        r, g, b = (c * self.brilho for c in _CORES[estado])
        desenho = "".join(_ICONES[estado])
        for i, ch in enumerate(desenho):
            self.matriz[i] = (r, g, b) if ch == "#" else (0, 0, 0)
        self.matriz.write()

    def medidor(self, nivel, estado):
        """Acende 'nivel' (0-25) LEDs na cor do estado: quanto mais tráfego, mais luz."""
        if not self.matriz:
            return
        self._icone = None          # invalida o ícone: ao sair do medidor, redesenha
        r, g, b = (c * self.brilho for c in _CORES.get(estado, (0, 1, 0)))
        nivel = max(0, min(25, nivel))
        for i in range(25):
            self.matriz[i] = (r, g, b) if i < nivel else (0, 0, 0)
        self.matriz.write()

    # ---------- buzzer ----------
    def apitar(self, ms=150, freq=2700):
        if not self.buzzer:
            return
        try:
            self.buzzer.freq(freq)
            self.buzzer.duty_u16(20000)
            self._buzzer_ate = time.ticks_add(time.ticks_ms(), ms)
        except Exception:
            pass

    def tick(self):
        """Chamar a cada volta do laço: desliga o buzzer na hora certa (não bloqueia)."""
        if self._buzzer_ate and time.ticks_diff(time.ticks_ms(), self._buzzer_ate) >= 0:
            self._buzzer_ate = 0
            if self.buzzer:
                try:
                    self.buzzer.duty_u16(0)
                except Exception:
                    pass

    # ---------- botões (borda de descida = apertou) ----------
    def apertou_a(self):
        v = self.bt_a.value()
        r = self._ult_a == 1 and v == 0
        self._ult_a = v
        return r

    def apertou_b(self):
        v = self.bt_b.value()
        r = self._ult_b == 1 and v == 0
        self._ult_b = v
        return r

    # ---------- display ----------
    def texto(self, linhas):
        if not self.oled:
            return
        try:
            o = self.oled
            o.fill(0)
            for i, l in enumerate(linhas[:8]):
                o.text(l[:16], 0, i * 8, 1)
            o.show()
        except Exception as e:
            print("OLED erro:", e)
