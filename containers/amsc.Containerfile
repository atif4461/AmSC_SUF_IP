
FROM nbrei/amsc_dev:latest

WORKDIR /amsc_expedition

RUN apt-get install -y python3-venv
RUN python -m venv /venv --system-site-packages
ENV PATH="/venv/bin:$PATH"

COPY . .

RUN cd /amsc_expedition/src/cpp/hddm_r \
 && export HDDM_DIR=/usr/local \
 && hddm-cpp hddm_r.xml \
 && hddm-py hddm_r.xml \
 && python setup_hddm_r.py \
 && cp hddm_r.cpython-312-x86_64-linux-gnu.so /usr/lib/python3/dist-packages/

RUN ln -s /e2sar-install/lib/python3/dist-packages/e2sar_py.cpython-312-x86_64-linux-gnu.so /usr/lib/python3/dist-packages/

RUN cd /amsc_expedition \
 && pip install -e .

CMD ["amsc-cli"]
