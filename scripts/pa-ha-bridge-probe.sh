#!/bin/bash
# PA: HA -> Hermes webhook bridge census (read-only). No room post, no power, no serial.
echo "--- pid 2193 (serves 127.0.0.1:8645) ---"
ps -o pid,ppid,etime,cmd -p 2193 2>/dev/null
echo "--- stdout/stderr target ---"
sudo ls -l /proc/2193/fd/1 /proc/2193/fd/2 2>&1 | head -4
echo "--- HA docker log traces (google-work / hermes_work / rest_command) ---"
sudo docker logs homeassistant 2>&1 | grep -icE 'google-work|hermes_work'
sudo docker logs --tail 6000 homeassistant 2>&1 | grep -iE 'google-work|hermes_work|rest_command' | tail -6
echo "--- HA rest_command service registered? ---"
sudo docker exec homeassistant sh -c 'grep -n "hermes_work" /config/configuration.yaml; sed -n "10,30p" /config/configuration.yaml'
