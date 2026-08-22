# b2026 compare build_serv.tcl v0.2 (20260822)
# Run from the compare directory:
#   gw_sh build_serv.tcl
# Outputs land in serv_prj/impl/ so the two cores never overwrite each
# other. File paths are absolute-from-script so create_project's
# directory change cannot break them.
set here [file normalize [file dirname [info script]]]
create_project -name serv -dir $here/serv_prj -pn GW1NR-LV9QN88PC6/I5 -device_version C -force
foreach f {serv_rf_top serv_top serv_alu serv_bufreg serv_bufreg2 serv_csr
           serv_ctrl serv_decode serv_immdec serv_mem_if serv_rf_if
           serv_rf_ram serv_rf_ram_if serv_state serv_fpga} {
    add_file $here/rtl/$f.v
}
add_file $here/b26.cst
add_file $here/b26.sdc
set_option -top_module serv_fpga
set_option -use_sspi_as_gpio 1
set_option -use_mspi_as_gpio 1
run all
