"""Find every machine-specific hardcode, and dump pnputil output decoded the
way vdd_core decodes it (to write a portable device parser)."""
import io
import os
import re
import subprocess

print("=== 1. 硬编码的机器相关路径 ===")
for f in (r"C:\VirtualDisplay\panel\backend.py",
          r"C:\VirtualDisplay\vdd_core.py",
          r"C:\VirtualDisplay\panel\app.py"):
    print("  --", os.path.basename(f))
    for i, line in enumerate(io.open(f, encoding="utf-8"), 1):
        if re.search(r'C:\\\\VirtualDisplay|C:\\VirtualDisplay|C:\\\\Program Files'
                     r'|ROOT\\\\DISPLAY|VirtualDisplayDriver|DISPLAY\\\\0*1\b', line):
            print("     %4d  %s" % (i, line.rstrip()[:120]))
print()


def run(args):
    p = subprocess.run(args, capture_output=True, creationflags=0x08000000)
    raw = p.stdout
    for enc in ("utf-8", "gbk", "cp936"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


out = run(["pnputil", "/enum-devices", "/class", "Display"])
print("=== 2. pnputil /enum-devices /class Display（已按 vdd_core 的方式解码）===")
print(out[:2200])
print()
print("=== 3. 提取 ROOT\\DISPLAY\\NNNN 与设备描述 ===")
for blk in re.split(r"\n\s*\n", out):
    if "Virtual Display Driver" in blk or "Radeon" in blk:
        ids = re.findall(r"(?:ROOT\\DISPLAY\\\d+|PCI\\[^\s]+)", blk)
        desc = re.search(r"([^\n]*(?:Virtual Display Driver|Radeon)[^\n]*)", blk)
        print("   ids=%s  desc=%s" % (ids, desc.group(1).strip()[:60] if desc else "?"))
