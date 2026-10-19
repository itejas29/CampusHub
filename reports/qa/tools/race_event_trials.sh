#!/bin/sh
# RACE-1 repeated from a clean slate: clears event $1's registrations each trial.
EVENT=$1; TRIALS=${2:-10}; FREE=${3:-5}; N=${4:-40}
for t in $(seq 1 $TRIALS); do
  docker exec campushub-qa-pg psql -U qa -d campushub_qa -qtAc "delete from event_registrations where event_id=$EVENT" >/dev/null
  ../../../.venv/bin/python race_event_capacity.py $EVENT $FREE $N | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"trial $t: capacity={d['capacity']} confirmed={d['confirmed_after']} over={d['oversubscribed_by']} {d['verdict']}\")"
done
