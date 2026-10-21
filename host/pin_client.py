# SPDX-License-Identifier: Apache-2.0
# chip-lab 병렬 핀 INT8 내적 가속기 호스트 드라이버 (MicroPython·CPython 공용).
#
# 핀 (칩 기준): ui_in = IN_DATA, uio[0] IN_VALID · uio[1] ABORT · uio[2] OUT_READY (호스트가 구동),
#               uio[4] IN_READY · uio[5] OUT_VALID · uio[6] BUSY · uio[7] ERR, uo_out = OUT_DATA (칩이 구동).
# 한 사이클 = 호스트가 값을 올리고 → 칩 출력을 읽고 → 클록 한 번. 상승 순간에 IN_VALID·IN_READY 가 1 이면 바이트가
# 넘어가고, OUT_VALID·OUT_READY 가 1 이면 결과 바이트가 넘어간다. 그래서 읽기는 반드시 tick 전에 한다.
#
# 같은 코드를 두 곳에서 쓴다: TT 데모보드(DemoBoardPort, 수동 클록) 와 cocotb 시뮬레이션(test.py 의 CocotbPort).
# 수동 클록이라 보드에서는 느리다 (프로토콜 확인용). 클록당 1바이트 속도는 RP2040 PIO 가 필요하다 (미구현).

IN_VALID, ABORT, OUT_READY = 1, 2, 4
IN_READY, OUT_VALID, BUSY, ERR = 16, 32, 64, 128


class PinDot:
    def __init__(self, port, n, width):
        self.port, self.n, self.width = port, n, width
        self.nbytes = (width + 7) // 8
        self.cycles = 0

    def signed(self, raw):
        raw &= (1 << self.width) - 1
        return raw - (1 << self.width) if raw >> (self.width - 1) else raw

    def stream(self, vectors, limit=100000):
        """vectors = [(a, b), ...] → 내적 결과 목록. 입력과 결과 읽기를 같은 사이클에 겹쳐 진행한다."""
        data = []
        for a, b in vectors:
            if len(a) != self.n or len(b) != self.n:
                raise ValueError('vector length must be N=%d' % self.n)
            for x, y in zip(a, b):
                data.append(x & 255)
                data.append(y & 255)
        results, raw, got, index = [], 0, 0, 0
        while len(results) < len(vectors):
            if self.cycles >= limit:
                raise RuntimeError('timeout after %d cycles' % self.cycles)
            valid = index < len(data)
            self.port.write(data[index] if valid else 0, (IN_VALID if valid else 0) | OUT_READY)
            status, out = self.port.read()
            self.port.tick()
            self.cycles += 1
            if valid and status & IN_READY:
                index += 1
            if status & OUT_VALID:
                raw |= out << (8 * got)
                got += 1
                if got == self.nbytes:
                    results.append(self.signed(raw))
                    raw, got = 0, 0
        self.port.write(0, OUT_READY)
        return results

    def dot(self, a, b):
        return self.stream([(a, b)])[0]

    def abort(self):
        """받던 벡터를 버린다. ERR 가 켜져야 한다."""
        self.port.write(0, ABORT)
        self.port.tick()
        self.port.write(0, OUT_READY)
        status, _ = self.port.read()
        return bool(status & ERR)


class DemoBoardPort:
    """TT 데모보드 MicroPython SDK (ttboard). 프로젝트를 enable 한 뒤 쓴다."""

    def __init__(self, tt):
        self.tt = tt
        tt.uio_oe_pico.value = IN_VALID | ABORT | OUT_READY   # uio[2:0] 은 RP2040 이 구동, 나머지는 칩이 구동

    def write(self, data, control):
        self.tt.ui_in.value = data
        self.tt.uio_in.value = control

    def read(self):
        return int(self.tt.uio_out.value), int(self.tt.uo_out.value)

    def tick(self):
        self.tt.clock_project_once()


def main(n, width, cases):
    """데모보드 REPL 에서: import pin_client; pin_client.main(**설정) — vectors.json 의 n·acc_width·cases 를 넘긴다."""
    from ttboard.demoboard import DemoBoard
    tt = DemoBoard.get()
    chip = PinDot(DemoBoardPort(tt), n, width)
    tt.reset_project(True)
    tt.clock_project_once()
    tt.reset_project(False)
    failures = 0
    for index, (a, b, expected) in enumerate(cases):
        got = chip.dot(a, b)
        failures += got != expected
        print('%2d %s got %d expected %d' % (index, 'OK' if got == expected else 'FAIL', got, expected))
    print('%d/%d match, %d cycles' % (len(cases) - failures, len(cases), chip.cycles))
    return failures
