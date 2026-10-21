# chip-lab 게이트 수준 스트레스 (병렬 핀판). 제출 저장소 기본 시험과 별도, 측정 브랜치에서만 돈다.
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, Timer

from test import N, NBYTES, WIDTH, signed

IN_VALID, ABORT, OUT_READY = 1, 2, 4
IN_READY_BIT, OUT_VALID_BIT, ERR_BIT = 4, 5, 7


def ref(a, b):
    s = sum(x * y for x, y in zip(a, b))
    lim = (1 << (WIDTH - 1)) - 1
    return max(-lim - 1, min(lim, s))


class Bench:
    def __init__(self, dut, seed):
        self.dut, self.rng = dut, random.Random(seed)
        self.ctrl, self.got, self.stall = 0, [], 0.0
        self.raw, self.count = 0, 0

    def out(self, bit):
        return (self.dut.uio_out.value.to_unsigned() >> bit) & 1

    def drive(self, data=None):
        if data is not None:
            self.dut.ui_in.value = data & 0xFF
        self.dut.uio_in.value = self.ctrl

    async def start(self):
        cocotb.start_soon(Clock(self.dut.clk, 10, unit="us").start())
        self.dut.ena.value = 1
        await self.reset()
        cocotb.start_soon(self.reader())

    async def reset(self):
        self.ctrl = 0
        self.drive(0)
        self.dut.rst_n.value = 0
        await ClockCycles(self.dut.clk, 3)
        self.dut.rst_n.value = 1
        self.raw, self.count = 0, 0
        await FallingEdge(self.dut.clk)

    async def reader(self):
        # 하강마다 OUT_READY 를 무작위로 정하고, 이번 상승에서 넘어갈 바이트(OUT_VALID && OUT_READY)를 기록
        while True:
            await FallingEdge(self.dut.clk)
            ready = self.rng.random() >= self.stall
            self.ctrl = (self.ctrl | OUT_READY) if ready else (self.ctrl & ~OUT_READY)
            self.drive()
            await Timer(1, unit="us")
            if ready and self.out(OUT_VALID_BIT) and self.dut.rst_n.value:
                self.raw |= self.dut.uo_out.value.to_unsigned() << (8 * self.count)
                self.count += 1
                if self.count == NBYTES:
                    self.got.append(signed(self.raw, WIDTH))
                    self.raw, self.count = 0, 0

    async def push(self, byte, gap=0.0):
        while self.rng.random() < gap:
            await FallingEdge(self.dut.clk)
        self.ctrl |= IN_VALID
        self.drive(byte)
        while True:
            await Timer(2, unit="us")
            ready = self.out(IN_READY_BIT)
            await FallingEdge(self.dut.clk)
            if ready:
                break
        self.ctrl &= ~IN_VALID
        self.drive()

    async def vector(self, a, b, gap=0.0):
        for x, y in zip(a, b):
            await self.push(x, gap)
            await self.push(y, gap)

    async def drain(self, want):
        for _ in range(2000):
            if len(self.got) >= want:
                return
            await FallingEdge(self.dut.clk)
        raise AssertionError(f"결과 {len(self.got)}/{want} 개만 도착")

    async def abort(self):
        self.ctrl |= ABORT
        self.drive()
        await FallingEdge(self.dut.clk)
        self.ctrl &= ~ABORT
        self.drive()
        await Timer(2, unit="us")
        return self.out(ERR_BIT)

    def rand(self):
        return [self.rng.randint(-128, 127) for _ in range(N)], [self.rng.randint(-128, 127) for _ in range(N)]


@cocotb.test()
async def random_500_gaps_backpressure(dut):
    t = Bench(dut, 2026)
    t.stall = 0.3
    await t.start()
    want = []
    for _ in range(500):
        a, b = t.rand()
        want.append(ref(a, b))
        await t.vector(a, b, gap=0.25)
    await t.drain(len(want))
    assert t.got == want, f"불일치 {sum(g != w for g, w in zip(t.got, want))}건"


@cocotb.test()
async def reset_mid_vector(dut):
    t = Bench(dut, 3)
    await t.start()
    for _ in range(20):
        a, b = t.rand()
        cut = t.rng.randint(1, 2 * N - 1)
        stream = [v for pair in zip(a, b) for v in pair][:cut]
        for v in stream:
            await t.push(v)
        await t.reset()
        t.got.clear()
        a, b = t.rand()
        await t.vector(a, b)
        await t.drain(1)
        assert t.got == [ref(a, b)], f"리셋 뒤 {t.got} != {ref(a, b)}"


@cocotb.test()
async def abort_mid_vector_then_recover(dut):
    t = Bench(dut, 11)
    await t.start()
    for _ in range(20):
        a, b = t.rand()
        cut = t.rng.randint(1, 2 * N - 1)
        for v in [v for pair in zip(a, b) for v in pair][:cut]:
            await t.push(v)
        assert await t.abort(), "ABORT 뒤 ERR 없음"
        before = len(t.got)
        a, b = t.rand()
        await t.vector(a, b)
        await t.drain(before + 1)
        assert t.got[-1] == ref(a, b) and len(t.got) == before + 1, f"ABORT 뒤 {t.got[before:]} != {ref(a, b)}"
        assert not t.out(ERR_BIT), "ERR 미해제"


@cocotb.test()
async def abort_right_after_last_byte_completes(dut):
    """마지막 b 를 받은 직후의 ABORT: 벡터는 이미 다 받았으므로 결과가 나와야 한다 (파이프라인 S1·S2 진행 중)."""
    t = Bench(dut, 17)
    await t.start()
    for _ in range(20):
        before = len(t.got)
        a, b = t.rand()
        await t.vector(a, b)
        await t.abort()
        await t.drain(before + 1)
        assert t.got[-1] == ref(a, b), f"{t.got[-1]} != {ref(a, b)}"
