# b2026 compare build_glacial.tcl v0.1 (20260822)
# Run from the compare directory:  gw_sh build_glacial.tcl
set here [file normalize [file dirname [info script]]]
create_project -name glacial -dir $here/glacial_prj -pn GW1NR-LV9QN88PC6/I5 -device_version C -force
add_file $here/rtl/glacial.v
add_file $here/rtl/glacial_fpga.v
add_file $here/b26_uart.cst
add_file $here/b26.sdc
set_option -top_module glacial_fpga
set_option -use_sspi_as_gpio 1
set_option -use_mspi_as_gpio 1
run all
