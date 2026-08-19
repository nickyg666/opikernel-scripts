#!/bin/bash
D=/dev/ttyS0
cmd() {
  printf "\r" > $D; sleep 0.3
  printf "%s\r" "$1" > $D; sleep 0.7
}
cmd "setenv kernel_addr_r 0x41000000"
cmd "setenv fdt_addr_r 0x44000000"
cmd "setenv ramdisk_addr_r 0x45000000"
cmd "setenv load_addr 0x46000000"
cmd "setenv bootargs 'root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 rootwait rootfstype=ext4 earlyprintk=sunxi-uart,0x02500000 earlycon=uart,mmio32,0x2500000 initcall_debug=1 console=tty1 console=ttyS0,115200 consoleblank=0 loglevel=7 clk_ignore_unused swiotlb=65536 usb-storage.quirks= fbcon=map:1 cgroup_enable=cpuset cgroup_memory=1 cgroup_enable=memory swapaccount=1'"
cmd "printenv bootargs"
cmd "load mmc 0:1 \${ramdisk_addr_r} /boot/mainline/tiny-uInitrd"
cmd "load mmc 0:1 \${kernel_addr_r} /boot/mainline/Image"
cmd "load mmc 0:1 \${fdt_addr_r} /boot/mainline/sun60i-a733-orangepi-zero3w.dtb.bak-audio-usb-npu"
cmd "fdt addr \${fdt_addr_r}"
cmd "fdt resize 65536"
cmd "booti \${kernel_addr_r} \${ramdisk_addr_r} \${fdt_addr_r}"
echo "=== sent; tail ==="
tail -8 /home/orangepi/uart_capture/ttyS0.log
