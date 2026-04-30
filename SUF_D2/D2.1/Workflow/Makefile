
.ONESHELL:
SHELL := /bin/bash

make-image:
	podman build . -f containers/amsc.Containerfile --cap-add sys_ptrace -t amsc --format docker

push-image:
	podman login codecr.jlab.org
	podman push localhost/amsc:latest docker://codecr.jlab.org/nbrei/amsc_expedition

pull-image:
	podman login codecr.jlab.org
	podman pull docker://codecr.jlab.org/nbrei/amsc_expedition:latest

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

download_gluex_data:
	wget https://zenodo.org/records/18024575/files/dana_rest_011650_000.hddm?download=1
