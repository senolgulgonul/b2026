# b2026 compare build_picorv32.tcl v0.2 (20260822)
# Run from the compare directory:
#   gw_sh build_picorv32.tcl
# Outputs land in pico_prj/impl/.
set here [file normalize [file dirname [info script]]]
create_project -name picorv32 -dir $here/pico_prj -pn GW1NR-LV9QN88PC6/I5 -device_version C -force
add_file $here/rtl/picorv32.v
add_file $here/rtl/picorv32_fpga.v
add_file $here/b26.cst
add_file $here/b26.sdc
set_option -top_module picorv32_fpga
set_option -use_sspi_as_gpio 1
set_option -use_mspi_as_gpio 1
run all
