
FROM docker.io/ibaldin/e2sar:0.3.1
WORKDIR /amsc_expedition

# -------------
# Toolbx fixes
# -------------
# These were mostly taken from
# https://github.com/containers/toolbox/blob/main/images/ubuntu/22.04/Containerfile
# 
# Note that I had to make a couple additional modifications:
# - unminimize lives in /usr/bin, not /usr/sbin
# - needed to delete user 1000 and /home so that toolbx could correctly recreate them

# Remove apt configuration optimized for containers
# Remove docker-gzip-indexes to help with "command-not-found"
RUN rm /etc/apt/apt.conf.d/docker-gzip-indexes /etc/apt/apt.conf.d/docker-no-languages

# Enable myhostname nss plugin for clean hostname resolution without patching
# hosts (at least for sudo), add it right after 'files' entry. We expect that
# this entry is not present yet. Do this early so that package postinst (which
# adds it too late in the order) skips this step
RUN sed -Ei 's/^(hosts:.*)(\<files\>)\s*(.*)/\1\2 myhostname \3/' /etc/nsswitch.conf

# Restore documentation but do not upgrade all packages
# Install ubuntu-minimal & ubuntu-standard
# Install extra packages as well as libnss-myhostname
COPY containers/extra-packages /
RUN sed -Ei '/apt-get (update|upgrade)/s/^/#/' /usr/bin/unminimize && \
    apt-get update && \
    yes | /usr/bin/unminimize && \
    DEBIAN_FRONTEND=noninteractive apt-get -y install \
        ubuntu-minimal ubuntu-standard \
        libnss-myhostname \
        flatpak-xdg-utils \
        $(cat extra-packages | xargs) && \
    rm -rd /var/lib/apt/lists/*
RUN rm /extra-packages

# Enable the use of p11-kit-client.so to access CA certificates from the host
RUN mkdir --parents /etc/pkcs11/modules

# Fix empty bind-mount to clear selinuxfs (see #337)
RUN mkdir /usr/share/empty

# Add flatpak-spawn to /usr/bin
RUN ln -s /usr/libexec/flatpak-xdg-utils/flatpak-spawn /usr/bin/

# Disable APT ESM hook which tries to enable some systemd services on each apt invocation
#RUN rm /etc/apt/apt.conf.d/20apt-esm-hook.conf

# Remove pre-existing user with UID 1000 if present
RUN if getent passwd 1000; then \
        userdel -r $(getent passwd 1000 | cut -d: -f1); \
    fi

# Remove conflicting home directory
RUN rm -rf /home

# -------------

# Install missing tools
RUN apt-get update && apt-get -y install \
  git cmake clang libbz2-dev libz-dev libxerces-c-dev libhdf5-dev \
  python3 python-is-python3 python3-pip python3-zmq python3-pandas \
  neovim fzf tmux curl

RUN echo "nbrei/amsc_expedition:v6" > /container.md

RUN cd / \
 && git clone https://github.com/JeffersonLab/HDDM \
 && mkdir HDDM/build \
 && cmake -S HDDM -B HDDM/build -DENABLE_ISTREAM_OVER_HTTP=0 -DENABLE_ISTREAM_OVER_XROOTD=0 \
 && LIBRARY_PATH=/usr/lib/x86_64-linux-gnu/hdf5/serial cmake --build HDDM/build -j 8 \
 && cmake --install HDDM/build


RUN apt-get install -y python3-venv
RUN python -m venv /venv --system-site-packages
ENV PATH="/venv/bin:$PATH"
ENV PS1="(venv) $PS1"

RUN git clone https://code.jlab.org/davidl/AmSC-SUF-IP.git /AmSC-SUF-IP \
 && pip install -e /AmSC-SUF-IP/SUF_D2/D2.1/Workflow \
 && pip install -r /AmSC-SUF-IP/SUF_D2/requirements.txt \
 && pip install -r /AmSC-SUF-IP/SUF_D2/D2.1/Monitor/requirements.txt

RUN cd /AmSC-SUF-IP/SUF_D2/D2.1/Workflow/src/cpp/hddm_r \
 && export HDDM_DIR=/usr/local \
 && hddm-cpp hddm_r.xml \
 && hddm-py hddm_r.xml \
 && python setup_hddm_r.py \
 && cp hddm_r.cpython-312-x86_64-linux-gnu.so /usr/lib/python3/dist-packages/

RUN ln -s /e2sar-install/lib/python3/dist-packages/e2sar_py.cpython-312-x86_64-linux-gnu.so /usr/lib/python3/dist-packages/


