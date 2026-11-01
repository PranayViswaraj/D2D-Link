// d2d_checks.svh - enables embedded immediate assertions in simulation (+define+SIM)
// and formal (Yosys read -formal defines FORMAL). Included at file scope.
`ifndef D2D_CHECKS_SVH
`define D2D_CHECKS_SVH
`ifdef SIM
`define D2D_CHECKS
`endif
`ifdef FORMAL
`define D2D_CHECKS
`endif
`endif
