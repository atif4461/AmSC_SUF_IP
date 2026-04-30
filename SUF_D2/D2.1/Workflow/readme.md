# amsc_expedition

## Description

NP demonstrator for AmSC-SUF.

## Project status
This is a fast-moving research project, so everything is subject to change and nothing is supported. If you are 
interested in contributing or using any code you find here, please contact the authors directly.

## Authors
- Nathan Brei

## License

This work is licensed under a permissive BSD-like license granting free use and redistribution, subject to attribution and disclaimer requirements, with an added clause reserving full government-use rights due to federal funding.


## How to run

```bash

# Launch an interactive SLURM job
srun --exclusive --pty /bin/bash

# Download the GlueX dataset
wget https://zenodo.org/records/18024575/files/dana_rest_011650_000.hddm

# Set the initial EJFAT credentials
export EJFAT_URI=ejfats://TOKEN@ejfat-1.jlab.org:18347

# To reserve an EJFAT load balancer instance
amsc.sh reserve-ejfat

# Obtain the reservation credentials
source instance.env

# To run the ejfat source
amsc.sh run-ejfat-source dana_rest_011650_000.hddm

# To run an ejfat worker
amsc.sh run-ejfat-worker

# To launch a shell
amsc-shell.sh

```


## How to build

```bash

# Use the Makefile to build and push the container
# The Makefile calls `podman build` on `amsc.Containerfile`, which calls `pip install`, which calls CMake
# But CMake requires a very custom environment, hence the container
make

```


