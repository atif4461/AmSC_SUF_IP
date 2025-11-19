
FROM docker.io/rootproject/root:6.34.00-ubuntu24.04
# Source: https://github.com/root-project/root-docker/blob/6.34.00-ubuntu24.04/ubuntu2404/Dockerfile


####################
# FIXES FOR TOOLBX
####################
# Image:  quay.io/toolbx/ubuntu-toolbox
# Source: https://github.com/containers/toolbox/blob/main/images/ubuntu/24.04/Containerfile

RUN apt install -y libcap2-bin sudo xdg-utils

# Remove apt configuration optimized for containers
# Remove docker-gzip-indexes to help with "command-not-found"
RUN rm /etc/apt/apt.conf.d/docker-gzip-indexes /etc/apt/apt.conf.d/docker-no-languages

# Enable myhostname nss plugin for clean hostname resolution without patching
# hosts (at least for sudo), add it right after 'files' entry. We expect that
# this entry is not present yet. Do this early so that package postinst (which
# adds it too late in the order) skips this step
RUN sed -Ei 's/^(hosts:.*)(\<files\>)\s*(.*)/\1\2 myhostname \3/' /etc/nsswitch.conf

# Enable the use of p11-kit-client.so to access CA certificates from the host
RUN mkdir --parents /etc/pkcs11/modules

# Fix empty bind-mount to clear selinuxfs (see #337)
RUN mkdir /usr/share/empty

# Having anything in /home prevents toolbx from symlinking /var/home there,
# and 'ubuntu' user with UID 1000 will most likely conflict with host user as well
RUN userdel --remove ubuntu


####################
# INSTALL DEV TOOLS
####################

RUN apt update -y \
 && apt install -y build-essential gdb valgrind cmake wget unzip vim libasan6 less bat git zlib1g-dev pip \
                   python3-dev python3-zmq libczmq-dev libxerces-c-dev libx11-dev libxpm-dev libxft-dev libxext-dev \
                   libyaml-dev python3-jinja2 python3-yaml python3-arrow python3-pandas python3-matplotlib python3-numpy libz3-dev


# For everything else we use spack
RUN git clone --depth=2 https://github.com/spack/spack.git /opt/spack

