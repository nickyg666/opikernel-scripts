#!/bin/bash
SCP='sshpass -p orangepi ssh -o StrictHostKeyChecking=accept-new -o PubkeyAuthentication=no -o Tunnel=no'
for a in $(seq 1 10); do
  if ping -c1 -W1 192.168.0.151 >/dev/null 2>&1; then
    echo "BOARD UP after $((a-1)) retries" >> /home/tab/boot_retry.log
    exit 0
  fi
  date >> /home/tab/boot_retry.log
  echo "attempt $a: sending boot script" >> /home/tab/boot_retry.log
  $SCP orangepi@192.168.0.167 'sh /home/orangepi/uart_capture/uboot_boot_proven.sh >/dev/null 2>&1' >> /home/tab/boot_retry.log 2>&1
  # wait for reset -> prompt cycle + boot to complete
  for w in $(seq 1 24); do
    sleep 5
    if ping -c1 -W1 192.168.0.151 >/dev/null 2>&1; then
      echo "BOARD UP after ~$((w*5))s on attempt $a" >> /home/tab/boot_retry.log
      exit 0
    fi
  done
  echo "attempt $a: still down, board likely re-panicked" >> /home/tab/boot_retry.log
done
echo "GAVE UP after 10 attempts" >> /home/tab/boot_retry.log
