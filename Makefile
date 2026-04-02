
.ONESHELL:
SHELL := /bin/bash

make-image:
	podman build . -f containers/amsc.Containerfile --cap-add sys_ptrace -t amsc --format docker

make-toolbox:
	toolbox create --image=amsc amsc

clear-toolbox:
	podman stop -i amsc
	toolbox rm amsc

mount_cvmfs:
	sudo mount -t cvmfs oasis.opensciencegrid.org /cvmfs/oasis.opensciencegrid.org/

build_rest_lib:
	source /group/halld/Software/build_scripts/gluex_env_boot_jlab.sh
	gxenv
	cd src/cpp/hddm_r
	hddm-cpp ../../../schemas/hddm_r.xml
	hddm-py ..../../schemas/hddm_r.xml
	python setup_hddm_r.py

