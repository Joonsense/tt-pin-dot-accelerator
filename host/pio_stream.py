# SPDX-License-Identifier: Apache-2.0
# chip-lab 병렬 핀 INT8/INT4 내적 가속기 고속 호스트 (RP2040/RP2350 PIO, TT 데모보드 v3 핀).
#
# 수동 클록 드라이버(pin_client.py)는 파이썬이 클록을 한 번씩 치므로 느리다. 여기서는 PIO 상태 기계 두 개가
# 칩 클록을 직접 만들고 클록마다 한 바이트를 넣는다:
#   SM0 feeder : FIFO 의 32bit 단어 하나 = 칩 클록 한 번. 클록 Low 동안 ui_in[7:0] + uio[3:0] (IN_VALID·ABORT·OUT_READY·CHAIN)
#                을 한 번에 내고, SM1 이 출력을 읽을 때까지 기다린 뒤 IN_READY(uio[4]) 를 보고 클록을 올린다.
#                IN_READY 가 0 이면 클록만 한 번 치고 같은 단어를 다시 낸다.
#   SM1 capture: 클록 Low 마다 OUT_VALID(uio[5]) 가 1 이면 uo_out 한 바이트를 RX FIFO 로. 다 읽으면 SM0 에 알린다.
# LOAD(uio[6], 가중치 고정판) 는 바이트마다 바뀌지 않으므로 CPU 가 핀으로 직접 든다.
#
# 데모보드 v3 GPIO (tt-micropython-firmware gpio_map_dbv3.py, 2026-10-22 확인): 클록 16, ui_in 17~24, uio 25~32, uo_out 33~40.
# 이 파일의 PIO 프로그램은 chip-lab 의 PIO 에뮬레이터(backend/pio_emu.py)가 같은 소스를 RTL 과 함께 돌려 검증했다.
# 실제 보드·DMA 경로는 하드웨어에서 확인되지 않았다.
import rp2
from rp2 import PIO

CLK_PIN, UI_BASE, UIO_BASE, UO_BASE = 16, 17, 25, 33
IN_READY_PIN, OUT_VALID_PIN, LOAD_PIN = UIO_BASE + 4, UIO_BASE + 5, UIO_BASE + 6
IN_VALID, ABORT, OUT_READY, CHAIN, LOAD = 1, 2, 4, 8, 64   # uio 비트 (pin_client.py 와 같다)


@rp2.asm_pio(out_init=(PIO.OUT_LOW,) * 12, sideset_init=PIO.OUT_LOW, out_shiftdir=PIO.SHIFT_RIGHT)
def feeder():
    wrap_target()
    pull(block)            .side(0)      # 클록 Low (떨어지는 에지)
    out(pins, 12)          .side(0)      # ui_in[7:0] + uio[3:0]
    label("retry")
    irq(0)                 .side(0)      # SM1: 출력 읽어라
    wait(1, irq, 1)        .side(0)      # SM1 이 다 읽을 때까지
    jmp(pin, "take")       .side(0)      # IN_READY
    nop()                  .side(1)      # 못 받음: 클록만 한 번 (출력·파이프라인은 진행)
    jmp("retry")           .side(0)
    label("take")
    nop()                  .side(1)      # 올라가는 에지: 바이트 전달
    wrap()


@rp2.asm_pio(in_shiftdir=PIO.SHIFT_LEFT)
def capture():
    wrap_target()
    wait(1, irq, 0)
    jmp(pin, "grab")                      # OUT_VALID
    jmp("done")
    label("grab")
    in_(pins, 8)                          # uo_out
    push(block)                           # RX 가 차면 멈춘다 → SM0 도 멈춰 클록이 선다 (결과를 잃지 않음)
    label("done")
    irq(1)                                # SM0: 다 읽었다
    wrap()


def words(data, flags):
    """바이트·플래그 → SM0 단어. 단어 비트 0~7 = ui_in, 8~11 = uio[3:0]. LOAD 는 단어에 없다 (CPU 핀)."""
    return [(d & 255) | (((f & 15) | IN_VALID | OUT_READY) << 8) for d, f in zip(data, flags)]


def idle(count):
    return [OUT_READY << 8] * count


class PioDot:
    """pin_client.PinDot 과 같은 함수 (stream·long_dot·load·batch·batch_dot) 를 PIO 로. run 만 다르다."""

    def __init__(self, n, width, int4=False, stationary=False, freq=150_000_000, backend=None):
        from pin_client import PinDot
        self.base = PinDot(None, n, width, int4, stationary)
        self.base.run = self.run
        self.nbytes = (width + 7) // 8
        self.backend = backend or BoardBackend(freq)
        for name in ('stream', 'long_dot', 'load', 'batch', 'batch_dot', 'dot'):
            setattr(self, name, getattr(self.base, name))

    def signed(self, raw):
        return self.base.signed(raw)

    def run(self, data, flags, wanted, limit=None):
        loads = {bool(f & LOAD) for f in flags}
        if len(loads) > 1:
            raise ValueError('LOAD 는 한 호출 안에서 바뀌지 않는다 (load 와 batch 를 나눠 부른다)')
        self.backend.set_load(bool(loads and loads.pop()))
        raw = self.backend.run(words(data, flags) + idle(16 + 2 * self.nbytes), wanted * self.nbytes)
        self.backend.set_load(False)
        return [self.signed(sum(raw[k * self.nbytes + i] << (8 * i) for i in range(self.nbytes))) for k in range(wanted)]


class BoardBackend:
    """데모보드: SM0·SM1 을 띄우고 단어를 넣어 결과 바이트를 받는다. (하드웨어 미검증. 대량 전송은 DMA 로 바꿀 자리)"""

    def __init__(self, freq):
        from machine import Pin
        self.load_pin = Pin(LOAD_PIN, Pin.OUT, value=0)
        self.sm0 = rp2.StateMachine(0, feeder, freq=freq, sideset_base=Pin(CLK_PIN), out_base=Pin(UI_BASE), jmp_pin=Pin(IN_READY_PIN))
        self.sm1 = rp2.StateMachine(1, capture, freq=freq, in_base=Pin(UO_BASE), jmp_pin=Pin(OUT_VALID_PIN))
        self.sm1.active(1)
        self.sm0.active(1)

    def set_load(self, value):
        self.load_pin.value(1 if value else 0)

    def run(self, stream, count):
        got, index = [], 0
        while index < len(stream) or len(got) < count:
            while index < len(stream) and self.sm0.tx_fifo() < 4:
                self.sm0.put(stream[index])
                index += 1
            while self.sm1.rx_fifo():
                got.append(self.sm1.get() & 255)
        return got[:count]
