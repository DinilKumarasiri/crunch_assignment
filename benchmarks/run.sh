#!/usr/bin/env bash
# Runs the benchmark suite: mixed workload at 10/50/100 users, then a contention test.
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.bench.yml"
DURATION="${DURATION:-60s}"
mkdir -p benchmarks/results

run() {  # run <users> <csv-prefix> <user classes...>
  local users=$1 prefix=$2; shift 2
  echo ""
  echo "=== ${prefix}: ${users} concurrent users for ${DURATION} ==="
  $COMPOSE run --rm locust -f locustfile.py --headless \
    --host http://backend:8000 -u "$users" -r "$users" -t "$DURATION" \
    --csv "results/${prefix}" --only-summary "$@"
}

run 10  u10        EmployeeUser ManagerUser
run 50  u50        EmployeeUser ManagerUser
run 100 u100       EmployeeUser ManagerUser
run 100 contention HotSlotEmployee HotSlotManager

python3 benchmarks/summarize.py
