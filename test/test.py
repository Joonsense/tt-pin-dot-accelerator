# SPDX-License-Identifier: Apache-2.0
# chip-lab 내보내기: 기대값은 chip-lab 고정 기준 모델(reference-1.0, seed 42)에서 계산했다.

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, Timer


async def reset(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="us").start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)

N = 8
INTERVAL = 16
NBYTES = 3
WIDTH = 20
CASES = [[[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 0], [[-128, -128, -128, -128, -128, -128, -128, -128, -128, -128, -128, -128, -128, -128, -128, -128], 131072], [[127, 127, 127, 127, 127, 127, 127, 127, 127, 127, 127, 127, 127, 127, 127, 127], 129032], [[-128, 127, -128, 127, -128, 127, -128, 127, -128, 127, -128, 127, -128, 127, -128, 127], -130048], [[127, 1, -128, 1, 127, 1, -128, 1, 127, 1, -128, 1, 127, 1, -128, 1], -4], [[-71, 88, -116, -112, 12, -113, -3, -81, -14, -17, -57, -9, -76, -115, -84, -27], 17390], [[86, 14, -16, -49, 101, -18, 14, 44, -125, -76, -47, -81, 88, 66, 46, -79], 16267], [[55, 22, 48, 57, 7, -30, -106, -93, 107, -105, -65, -12, 65, 20, -88, -88], 12183], [[-9, 53, -77, -21, 66, 8, 14, -92, 104, -41, 58, -3, -45, -45, 61, 108], 4555], [[66, 77, 10, 9, -16, -95, 38, -20, -100, 33, -11, -20, -112, 127, 33, 74], -8930], [[106, 57, -55, -16, 7, -58, -57, 124, -2, -82, 6, -104, 91, -72, 76, -50], -11364], [[-47, -70, 88, 8, -96, 46, 69, -71, 67, 22, 111, 94, 0, -48, -123, 104], -6205], [[-127, -46, 6, -128, -37, 37, -74, 122, 24, -119, -27, -71, -50, 57, 63, 29], -7285], [[-6, -63, -99, 115, -5, -44, -88, 7, -85, 88, 120, -20, -93, -26, -64, 31], -20849], [[76, 45, 63, -118, 96, -11, 103, -16, -67, -125, -2, -92, -13, -98, -96, -11], 4171], [[-94, -61, -112, 114, 41, -4, -92, 114, -7, 80, 14, -31, 120, -80, -19, -79], -26779], [[92, 78, 53, 45, 88, -73, 82, -1, 111, -30, -101, -31, -78, 101, -97, -57], 507], [[88, -103, -35, -121, 14, -81, 108, -7, -1, -43, -90, 80, 98, 120, -78, 118], -11320], [[-19, 104, 77, 18, -98, 88, -44, 121, 66, -49, -127, -31, 71, 23, 7, -17], -12321], [[-99, -87, -97, -33, 32, -93, -99, -94, -103, -8, 116, 78, -48, -67, -99, -2], 31430], [[-108, 7, -87, 74, 86, -61, 33, 25, 5, 106, -24, 33, 32, -91, -6, -124], -14045], [[106, -3, -77, 61, -91, 17, -19, -48, 7, 96, -61, 26, 50, -124, -93, 25], -15089], [[-75, -21, -60, 47, 7, -24, -69, 7, -74, 122, -49, 0, 11, -102, 16, -81], -13342], [[88, 98, 13, 90, -106, -124, -127, -71, 42, -90, -62, -52, 6, -110, -46, 61], 27933], [[-53, -21, 92, -1, -63, -76, -107, 53, 29, 80, 58, -49, -108, -7, 55, -45], -2103], [[-38, -47, 83, -73, -116, 67, -37, -109, 42, 112, 82, -15, -1, -26, 8, 107], -3656], [[51, 14, 28, -93, -12, 14, -14, 51, -116, 76, -30, 41, 76, -114, 40, -69], -24242], [[5, 95, -37, -69, 7, 69, -109, -31, -73, 2, 94, -106, 48, 95, 32, -128], -2756], [[-28, 30, 58, 81, 92, 39, -93, 78, 41, 23, 32, -63, -65, -30, 25, 87], 3244]]


def pin(dut, bit):
    return (dut.uio_out.value.to_unsigned() >> bit) & 1


def signed(value, bits):
    value &= (1 << bits) - 1
    return value - (1 << bits) if value >> (bits - 1) else value


@cocotb.test()
async def test_dot_product_over_parallel_pins(dut):
    await reset(dut)
    got, cycle, done_at = [], 0, []

    async def reader():
        nonlocal cycle
        raw, count = 0, 0
        while True:
            await FallingEdge(dut.clk)
            cycle += 1
            if pin(dut, 5):          # OUT_VALID, OUT_READY 는 항상 1 → 이번 상승에서 한 바이트 넘어간다
                raw |= dut.uo_out.value.to_unsigned() << (8 * count)
                count += 1
                if count == NBYTES:
                    got.append(signed(raw, WIDTH))
                    done_at.append(cycle)
                    raw, count = 0, 0

    await FallingEdge(dut.clk)
    dut.uio_in.value = 0b100
    cocotb.start_soon(reader())
    stream = [byte for bytes_, _ in CASES for byte in bytes_]
    index = 0
    while index < len(stream):
        dut.ui_in.value = stream[index] & 0xFF
        dut.uio_in.value = 0b101
        await Timer(1, unit="us")
        ready = pin(dut, 4)
        await FallingEdge(dut.clk)
        if ready:
            index += 1
    dut.uio_in.value = 0b100
    for _ in range(4 * NBYTES + 8):
        await FallingEdge(dut.clk)
    assert got == [expected for _, expected in CASES], f"{got} != {[e for _, e in CASES]}"
    gaps = {b - a for a, b in zip(done_at, done_at[1:])}
    assert gaps == {INTERVAL}, f"벡터 간격 {gaps} (기대 {INTERVAL} 클록)"
    dut.uio_in.value = 0b001
    dut.ui_in.value = 0x55
    await FallingEdge(dut.clk)
    dut.uio_in.value = 0b010
    await FallingEdge(dut.clk)
    dut.uio_in.value = 0
    await Timer(1, unit="us")
    assert pin(dut, 7), "ABORT 뒤 ERR 가 켜지지 않음"


# 호스트 드라이버(host/pin_client.py, 데모보드와 같은 코드)를 그대로 RTL 에 붙여 돌린다.
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "host"))
import pin_client  # noqa: E402
from cocotb.task import bridge, resume  # noqa: E402


class CocotbPort:
    def __init__(self, dut):
        self.dut = dut

    @resume
    async def write(self, data, control):
        self.dut.ui_in.value = data
        self.dut.uio_in.value = control

    @resume
    async def read(self):
        await Timer(1, unit="us")
        return self.dut.uio_out.value.to_unsigned(), self.dut.uo_out.value.to_unsigned()

    @resume
    async def tick(self):
        await FallingEdge(self.dut.clk)


@cocotb.test()
async def test_host_driver_against_rtl(dut):
    await reset(dut)
    await FallingEdge(dut.clk)
    chip = pin_client.PinDot(CocotbPort(dut), N, WIDTH)
    vectors = [(stream[0::2], stream[1::2]) for stream, _ in CASES]
    vectors = [([x - 256 if x > 127 else x for x in a], [y - 256 if y > 127 else y for y in b]) for a, b in vectors]
    results = await bridge(chip.stream)(vectors)
    assert results == [expected for _, expected in CASES], f"{results}"
    assert chip.cycles <= len(CASES) * INTERVAL + NBYTES + 4, f"드라이버 사이클 {chip.cycles}"
    assert await bridge(chip.abort)(), "드라이버 ABORT 뒤 ERR 없음"
