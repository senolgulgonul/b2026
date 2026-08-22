# b2026 tb Makefile v0.6 (20260821): make DUT=fnbox | fiu | useq | b26
SIM ?= icarus
TOPLEVEL_LANG ?= verilog
DUT ?= fnbox
ifeq ($(DUT),b26)
VERILOG_SOURCES += $(PWD)/../rtl/fnbox.v $(PWD)/../rtl/fiu.v $(PWD)/../rtl/useq.v $(PWD)/../rtl/uart_rx.v $(PWD)/../rtl/uart_tx.v $(PWD)/../rtl/b26.v
ifneq (,$(filter $(MODULE),test_loader test_lmtest))
COMPILE_ARGS += -Pb26.BAUD_DIV=4
endif
else
VERILOG_SOURCES += $(PWD)/../rtl/$(DUT).v
endif
TOPLEVEL = $(DUT)
MODULE ?= test_$(DUT)
include $(shell cocotb-config --makefiles)/Makefile.sim
