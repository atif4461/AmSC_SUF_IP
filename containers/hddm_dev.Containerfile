
FROM registry.fedoraproject.org/fedora-toolbox:43

RUN dnf -y install g++ gdb cmake bzip2-devel zlib-devel \
                   xerces-c-devel hdf5-devel \
                   python3-devel python3-setuptools

# Next steps:
# - Clone, build, and install HDDM
# - Build hddm_r
# - Create venv
# - Move hddm_r into venv site-packages
# - Pip install everything else

