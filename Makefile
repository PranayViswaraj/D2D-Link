# D2D-Link top-level flow. Tools run inside the d2d-eda container by default
# (scripts/dk.sh); on a Linux host with the tools installed use `make ... DK=`.
DK ?= scripts/dk.sh
SEEDS ?= 2

.PHONY: all image lint unit regress regress-small formal syn report clean

all: lint unit regress formal syn report

image:
	docker build -t d2d-eda -f docker/Dockerfile .

lint:
	$(DK) "scripts/run_lint.sh"

unit:
	$(DK) "cd tb/unit && timeout 900 python -m pytest -q test_common.py test_link_blocks.py --junitxml=../../logs/unit_junit.xml"

regress:
	$(DK) "timeout 960 python scripts/run_regression.py --seeds $(SEEDS) --configs default,small --cap-min 15"

regress-small:
	$(DK) "timeout 600 python scripts/run_regression.py --seeds 1 --configs small --cap-min 8"

formal:
	$(DK) "timeout 1200 scripts/run_formal.sh"

syn:
	$(DK) "timeout 900 scripts/run_syn.sh"

report:
	$(DK) "python scripts/report.py"

clean:
	rm -rf sim_build tb/unit/*.None tb/unit/__pycache__ tb/uvm/__pycache__ \
	       formal/*_bmc formal/*_cover formal/*_prove logs/regress
