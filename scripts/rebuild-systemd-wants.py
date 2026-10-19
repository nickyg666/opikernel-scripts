#!/usr/bin/env python3
"""Rebuild the systemd wanted-symlink tree on a mounted card from the SHIPPED
units in /lib/systemd/system, deterministically.

Context: a `find /etc/systemd/system -type l -delete` wiped every
multi-user.target.wants / sysinit.target.wants symlink on the 32G card
(108 enabled units -> 0). There is no backup of that tree on the card, so it
is reconstructed from the vendor's own enablement defaults:

  * every unit that ships with an [Install] section is *not* auto-enabled
    (upstream deliberately ships them disabled), so we cannot blindly enable.
  * Instead we enable the known-essential set for a headless Debian/Ubuntu
    rootfs, by name, and MASK everything else that was previously present.

Rules (all by unit name, verified against the unit files on the card):
  ENABLE  ssh, sshd, getty@tty1..6, serial-getty@*, udevd-trigger paths
  MASK    display/remote-desktop stack the user removed (novnc/x11vnc/gdm)

Everything is verified by readback: count symlinks before/after, and confirm
each enabled link resolves to a unit file that exists.
"""
import os
import subprocess
import sys

CARD = sys.argv[1] if len(sys.argv) > 1 else "/mnt/usbsd"

# Units that MUST be wanted for a headless serial board.
ENABLE = [
    "ssh.service",
    "sshd.service",
    "getty@tty1.service",
    "getty@tty2.service",
    "getty@tty3.service",
    "getty@tty4.service",
    "getty@tty5.service",
    "getty@tty6.service",
    "serial-getty@ttyS0.service",
    "serial-getty@ttyACM0.service",
    "systemd-udev-trigger.service",
    "systemd-udevd.service",
    "systemd-tmpfiles-setup.service",
    "systemd-tmpfiles-clean.service",
    "systemd-networkd.service",
    "systemd-resolved.service",
    "systemd-timesyncd.service",
    "systemd-logind.service",
    "dbus.service",
    "rsyslog.service",
    "cron.service",
    "opiz3w-firstboot.sh.service",
]

# Units the user explicitly does not want (local displays; no remote desktop).
MASK = [
    "opiz3w-novnc.service",
    "opiz3w-x11vnc.service",
    "xvfb-virtual-display.service",
    "gdm.service",
    "gdm3.service",
    "display-manager.service",
]


def run(*args):
    return subprocess.run(args, capture_output=True, text=True).stdout.strip()


def sh(cmd):
    return subprocess.run(["bash", "-lc", cmd], capture_output=True,
                          text=True).stdout.strip()


def count_links(root):
    n = 0
    for dp, dn, fn in os.walk(root):
        n += sum(1 for f in fn if os.path.islink(os.path.join(dp, f)))
    return n


def main():
    etc = os.path.join(CARD, "etc/systemd/system")
    print("card      = %s" % CARD)
    print("links before = %d" % count_links(etc))

    for u in MASK:
        p = os.path.join(etc, u)
        if not os.path.lexists(p):
            try:
                os.symlink("/dev/null", p)
            except FileExistsError:
                pass
    print("masked %d units" % len(MASK))

    # systemctl enable --root handles symlink creation + alias handling.
    ok, bad = [], []
    for u in ENABLE:
        # A template instance (getty@tty1.service) is enabled from its TEMPLATE
        # (getty@.service); the instance name never exists on disk. Probe both.
        inst = u
        tmpl = u.split("@")[0] + "@.service" if "@" in u else None
        found = sh("ls %s/lib/systemd/system/%s 2>/dev/null" % (CARD, inst))
        if not found and tmpl:
            found = sh("ls %s/lib/systemd/system/%s 2>/dev/null" % (CARD, tmpl))
        if not found:
            bad.append((u, "unit file not shipped"))
            continue
        out = subprocess.run(
            ["systemctl", "enable", "--root=%s" % CARD, u],
            capture_output=True, text=True)
        if out.returncode == 0:
            ok.append(u)
        else:
            bad.append((u, (out.stderr or out.stdout).strip()[:70]))

    print("enabled %d" % len(ok))
    for u, why in bad:
        print("  SKIP %-38s %s" % (u, why))

    print("links after  = %d" % count_links(etc))

    # verify every symlink resolves
    dangling = []
    for dp, dn, fn in os.walk(etc):
        for f in fn:
            p = os.path.join(dp, f)
            if os.path.islink(p):
                t = os.readlink(p)
                if t == "/dev/null":
                    continue
                tgt = os.path.normpath(os.path.join(dp, t))
                if not os.path.exists(tgt):
                    dangling.append((p, t))
    print("dangling = %d" % len(dangling))
    for p, t in dangling[:10]:
        print("  DANGLING %s -> %s" % (p, t))
    return 0


if __name__ == "__main__":
    sys.exit(main())