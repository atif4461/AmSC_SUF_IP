#!/bin/bash

# This only runs on ejfat-1 right now

lbadm -4 --reserve -l nbrei_test -d 01:00:00 --export > instance.env

source instance.env


#lbadm --status -u $EJFAT_URI

