#!/bin/bash

# This only runs on ejfat-1 right now

lbadm --reserve -l nbrei_amsc_demo -d 01:00:00 --export > instance.env

source instance.env

python source.py --id=0
python source.py --id=1

python worker.py --id=0 --starting-port=12345
python worker.py --id=1 --starting-port=12346
python worker.py --id=2 --starting-port=12347

lbadm --status
