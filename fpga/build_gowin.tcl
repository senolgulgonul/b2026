# b2026 build_gowin.tcl v0.1 (20260821)
# Batch build: gw_sh build_gowin.tcl   (run from the fpga/ directory)
set_device GW1NR-LV9QN88PC6/I5 -device_version C
add_file ../rtl/fnbox.v
add_file ../rtl/fiu.v
add_file ../rtl/useq.v
add_file ../rtl/b26.v
add_file b26_fpga.v
add_file b26.cst
add_file b26.sdc
set_option -top_module b26_fpga
set_option -use_sspi_as_gpio 1
set_option -use_mspi_as_gpio 1
run all
