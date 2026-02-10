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


## Building


```bash

# If the outer install is spack, it will leak things into the venv
unset PYTHONPATH

# Clear command path cache, otherwise you'll
# end up using the wrong interpreter all the time
hash -r

# Create a venv where everything gets installed
python -m venv venv
source venv/bin/activate

# Install the build system (only necessary due to no-isolation later)
python -m pip install scikit-build-core pybind11

# Build without isolation so that the IDE can find pybind11 dependency
python -m pip install --no-build-isolation -e .

# Run python tests
python -m pytest

# Run ctests
ctest --output-on-failure --progress --test-dir build/cp*

```

### Building HDDM
```
git clone https://github.com/JeffersonLab/HDDM
cd HDDM
cmake -S . -B build -DCMAKE_INSTALL_PREFIX=`pwd` -DENABLE_ISTREAM_OVER_HTTP=Off -DENABLE_ISTREAM_OVER_XROOTD=Off
```

## Usage

``` bash

# Run CLI
amsc-cli

```

