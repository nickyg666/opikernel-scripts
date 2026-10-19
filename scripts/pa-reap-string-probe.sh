#!/bin/bash
# PA: locate the emitter of the gc_execution_queue reap reasons in the web-ui bundle.
J=/usr/local/lib/node_modules/hermes-web-ui/dist/server/index.js
ls -l --time-style=+%m-%d_%H:%M:%S "$J"
for s in room_guard undelivered_reaped stale_running_reaped drift_guard undelivered; do
  n=$(grep -o -F "$s" "$J" | wc -l)
  printf "%-24s %s\n" "$s" "$n"
done
echo "--- windows around undelivered"
grep -o -E '.{120}undelivered.{100}' "$J" | head -4
