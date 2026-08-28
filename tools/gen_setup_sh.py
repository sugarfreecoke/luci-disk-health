"""Generate pure-shell self-extracting installer for luci-app-disk-health."""
from string import Template
import os
import subprocess
import tempfile

with open("out/luci-app-disk-health_data.b64", "r") as f:
    b64 = f.read().strip()

tpl = Template(r"""#!/bin/sh
# luci-app-disk-health pure-shell installer (no ar, no opkg, no upload UI)
# Generated for MT7981 / OpenWrt / iStoreOS
# Data embedded: base64-encoded data.tar.gz
# Usage: scp to router -> sh /tmp/dh_setup.sh
printf '\n==> luci-app-disk-health pure-shell installer\n'

TMPD=$$(mktemp -d)
trap "rm -rf $$TMPD" EXIT

# 1) Decode data.tar.gz
printf '==> Decoding data.tar.gz ...\n'
base64 -d > "$$TMPD"/data.tar.gz <<'__B64_BEGIN__'
${B64}
__B64_END__

# 2) Extract to system root
printf '==> Extracting files to / ...\n'
tar -xzf "$$TMPD"/data.tar.gz -C /

# 3) Clear LuCI cache and restart services
printf '==> Clearing cache and restarting services ...\n'
rm -rf /tmp/luci-* 2>/dev/null || true
/etc/init.d/rpcd restart 2>/dev/null || true
/etc/init.d/uhttpd restart 2>/dev/null || true

# 4) Verify
if [ -f /usr/lib/lua/luci/controller/disk_health.lua ]; then
    printf '\n[OK] Controller is in place: /usr/lib/lua/luci/controller/disk_health.lua\n'
    printf '\nDone! Open LuCI -> Services -> Disk Health\n'
else
    printf '\n[!!!] Controller is NOT installed. Check disk space / overlay permissions.\n'
    exit 1
fi
exit 0
""")

content = tpl.substitute(B64=b64)
with open("out/dh_setup.sh", "w", newline="\n") as f:
    f.write(content)
os.chmod("out/dh_setup.sh", 0o755)
print(f"Wrote out/dh_setup.sh: {len(content)} bytes")

# Syntax check
r = subprocess.run(["sh", "-n", "out/dh_setup.sh"], capture_output=True, text=True)
print(f"sh -n: rc={r.returncode}, stderr={r.stderr!r}")

# Simulate: extract to a temp dir to verify the full chain works
sim = tempfile.mkdtemp(prefix="dh_sim_")
print(f"\nSimulating install (extracting to {sim}) ...")

script = open("out/dh_setup.sh").read()
script_sim = script.replace('TMPD=$$(mktemp -d)', f'TMPD={sim}')
script_sim = script_sim.replace('tar -xzf "$$TMPD"/data.tar.gz -C /',
                                 f'tar -xzf "$$TMPD"/data.tar.gz -C {sim}')
script_sim = script_sim.replace('rm -rf $$TMPD', 'true')
script_sim = script_sim.replace('/usr/lib/lua/luci/controller/disk_health.lua',
                                 f'{sim}/usr/lib/lua/luci/controller/disk_health.lua')
script_sim = script_sim.replace('/etc/init.d/rpcd restart 2>/dev/null || true', 'true')
script_sim = script_sim.replace('/etc/init.d/uhttpd restart 2>/dev/null || true', 'true')
script_sim = script_sim.replace('rm -rf /tmp/luci-* 2>/dev/null || true', 'true')

sim_script = os.path.join(sim, "_run.sh")
with open(sim_script, "w", newline="\n") as f:
    f.write(script_sim)
r = subprocess.run(["sh", sim_script], capture_output=True, text=True)
print("Output:")
print(r.stdout)
print("Stderr:", r.stderr)
print("Return code:", r.returncode)

# Check files
checks = [
    f"{sim}/etc/config/disk_health",
    f"{sim}/usr/lib/lua/luci/controller/disk_health.lua",
    f"{sim}/usr/lib/lua/luci/model/disk_health.lua",
    f"{sim}/usr/lib/lua/luci/view/disk_health/overview.htm",
    f"{sim}/usr/lib/lua/luci/model/cbi/disk_health.lua",
    f"{sim}/usr/share/rpcd/acl.d/luci-app-disk-health.json",
    f"{sim}/usr/lib/lua/luci/po/zh_Hans/disk_health.po",
    f"{sim}/usr/lib/lua/luci/po/en/disk_health.po",
]
print("\nFile presence check:")
all_ok = True
for c in checks:
    ok = os.path.exists(c)
    print(f"  {'OK ' if ok else 'MISS'}: {c.replace(sim, '<SIM>')}")
    if not ok:
        all_ok = False
print(f"\n{'ALL FILES IN PLACE' if all_ok else 'SOMETHING IS MISSING'}")
