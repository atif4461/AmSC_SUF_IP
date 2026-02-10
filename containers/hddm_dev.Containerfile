
FROM registry.fedoraproject.org/fedora-toolbox:43

RUN dnf -y install g++ gdb cmake bzip2-devel zlib-devel \
                   xerces-c-devel hdf5-devel \
                   python3-devel python3-setuptools

