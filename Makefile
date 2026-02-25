
.ONESHELL:
SHELL := /bin/bash

mount_cvmfs:
	sudo mount -t cvmfs oasis.opensciencegrid.org /cvmfs/oasis.opensciencegrid.org/

build_rest_lib:
	source /group/halld/Software/build_scripts/gluex_env_boot_jlab.sh
	gxenv
	cd src/cpp/hddm_r
	hddm-cpp ../../../schemas/hddm_r.xml
	hddm-py ..../../schemas/hddm_r.xml
	python setup_hddm_r.py

