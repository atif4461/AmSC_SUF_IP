
.ONESHELL:
SHELL := /bin/bash

setup_env:
	source /group/halld/Software/build_scripts/gluex_env_boot_jlab.sh
	gxenv

build_rest_lib:
	source /group/halld/Software/build_scripts/gluex_env_boot_jlab.sh
	gxenv
	cd python/rest_to_pandas
	hddm-cpp ../../schemas/rest.xml
	hddm-py ../../schemas/rest.xml
	python setup_hddm_r.py

