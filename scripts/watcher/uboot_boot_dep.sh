D=/dev/ttyS0
send(){ printf "\r" > $D; sleep 0.4; printf "%s\r" "$1" > $D; sleep 1.3; }
BA='root=UUID=442af407-cb84-48f8-845e-4be5cd18ce13 rootwait rootfstype=ext4 earlyprintk=sunxi-uart,0x02500000 earlycon=uart,mmio32,0x2500000 console=tty1 console=ttyS0,115200 consoleblank=0 loglevel=7 clk_ignore_unused swiotlb=65536 usb-storage.quirks= fbcon=map:1'
send "setenv bootargs $BA"
send "setenv kernel_addr_r 0x41000000"
send "setenv fdt_addr_r 0x44000000"
send "setenv ramdisk_addr_r 0x45000000"
send "setenv load_addr 0x46000000"
send "load mmc 0:1 0x46000000 /boot/mainline/tiny-uInitrd"
send "load mmc 0:1 0x41000000 /boot/mainline/Image"
send "load mmc 0:1 0x44000000 /boot/mainline/sun60i-a733-orangepi-zero3w.dtb"
send "fdt addr 0x44000000"
send "fdt resize 65536"
send "booti 0x41000000 0x46000000 0x44000000"
echo SEND_DONE
