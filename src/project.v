/*
 * chip-lab 내보내기 · 설계 e22f0adb-9783-453d-8cdf-c61c776774b7
 * 병렬 핀 INT8 내적 가속기 N=8, 결과 20bit saturate, 클록당 1바이트 (a0,b0,a1,b1,…)
 * SPDX-License-Identifier: Apache-2.0
 *
 *   ui_in[7:0]  IN_DATA   (호스트 → 칩, IN_VALID·IN_READY 가 둘 다 1 인 클록 상승에서 받음)
 *   uio[0] in   IN_VALID
 *   uio[1] in   ABORT     (받던 벡터 폐기, ERR 켬)
 *   uio[2] in   OUT_READY
 *   uio[4] out  IN_READY  (결과를 다 읽기 전에는 다음 벡터의 마지막 바이트만 막음)
 *   uio[5] out  OUT_VALID
 *   uio[6] out  BUSY
 *   uio[7] out  ERR
 *   uo_out      OUT_DATA  (결과 3 바이트, 하위 바이트부터, OUT_VALID·OUT_READY 상승에서 다음 바이트)
 */
`default_nettype none

module tt_um_joonsense_pin_dot_e22f0adb (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);
  wire in_ready, out_valid, busy, err_seen;
  wire [2:0] count;

  tt_um_joonsense_pin_dot_e22f0adb_core core (.clk(clk), .rst(!rst_n), .in_valid(uio_in[0]), .in_data(ui_in), .abort(uio_in[1]), .out_ready(uio_in[2]),
      .in_ready(in_ready), .out_valid(out_valid), .out_data(uo_out), .busy(busy), .err_seen(err_seen), .count(count));

  assign uio_out = {err_seen, busy, out_valid, in_ready, 4'b0000};
  assign uio_oe  = 8'b1111_0000;

  wire _unused = &{ena, uio_in[7:3], count, 1'b0};

endmodule

`default_nettype wire
