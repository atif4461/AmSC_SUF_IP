
FROM nbrei/amsc_dev:latest

WORKDIR /amsc_expedition

COPY . .

RUN cd /amsc_expedition/src/cpp/hddm_r \
 && export HDDM_DIR=/usr/local \
 && hddm-cpp hddm_r.xml \
 && hddm-py hddm_r.xml \
 && python setup_hddm_r.py

# - Create venv
# - Move hddm_r into venv site-packages
# - Pip install everything else


