#!/usr/bin/env bash
set -euo pipefail

mkdir -p bin

g++ -O3 -std=c++17 -pthread cpp/lb_dataplane.cpp -o bin/lb_dataplane

echo "Built bin/lb_dataplane"
