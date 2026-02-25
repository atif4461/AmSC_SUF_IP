
FROM nbrei/e2sar_toolbx:latest

RUN cd / \
 && git clone https://github.com/JeffersonLab/HDDM \
 && mkdir HDDM/build \
 && cmake -S HDDM -B HDDM/build -DENABLE_ISTREAM_OVER_HTTP=0 -DENABLE_ISTREAM_OVER_XROOTD=0 \
 && LIBRARY_PATH=/usr/lib/x86_64-linux-gnu/hdf5/serial cmake --build HDDM/build -j 8 \
 && cmake --install HDDM/build


