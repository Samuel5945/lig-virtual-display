r"""Assemble a shareable release folder.

Everything a fresh PC needs, laid out the way the scripts expect:

    VirtualDisplay-vX.Y.Z\
        虚拟显示器.exe              the panel (bundles vdd_core + backend)
        vdd.py / vdd_core.py        CLI + the core it shares
        driver\                     MttVDD files + the config template
        install-driver.bat          portable, finds .\driver itself
        finish-setup.bat            dedupe / reload helper
        sunshine-setup.bat/.ps1     point Sunshine at the virtual display
        docs\images\                the screenshots README links to
        README.md

Nothing here installs Python. It does not need to install the driver either:
the panel exe carries the driver files and installs them itself (banner ->
「安装驱动」, admin via UAC). `install-driver.bat` is the scripted alternative
for people who would rather run it from an elevated prompt.
"""
import os
import shutil

ROOT = r"C:\VirtualDisplay"
REL = os.path.join(ROOT, "release")
VERSION = "v0.3.0"          # keep in sync with the badge at the top of README.md
NAME = "VirtualDisplay-" + VERSION
DEST = os.path.join(REL, NAME)

EXE_CANDIDATES = [
    r"C:\Users\PC\Desktop\虚拟显示器.exe",
    os.path.join(ROOT, "panel", "dist", "VirtualDisplayPanel.exe"),
]

FILES = [
    (r"C:\Users\PC\Desktop\虚拟显示器.exe", "虚拟显示器.exe", True),
    (os.path.join(ROOT, "vdd.py"), "vdd.py", True),
    (os.path.join(ROOT, "vdd_core.py"), "vdd_core.py", True),
    (os.path.join(ROOT, "install-driver.bat"), "install-driver.bat", True),
    (os.path.join(ROOT, "finish-setup.bat"), "finish-setup.bat", True),
    (os.path.join(ROOT, "sunshine-setup.bat"), "sunshine-setup.bat", True),
    (os.path.join(ROOT, "sunshine-setup.ps1"), "sunshine-setup.ps1", True),
    (os.path.join(ROOT, "README.md"), "README.md", True),
]

DRIVER_FILES = ["MttVDD.inf", "MttVDD.dll", "MttVDD.cat", "devcon.exe",
                "vdd_settings.xml"]

missing = []

if os.path.isdir(DEST):
    shutil.rmtree(DEST)
os.makedirs(os.path.join(DEST, "driver"), exist_ok=True)
print("目标:", DEST)
print()

for src, dst, required in FILES:
    if not os.path.exists(src):
        # the exe may live in panel\dist instead of the desktop
        alt = os.path.join(ROOT, "panel", "dist", "VirtualDisplayPanel.exe")
        if dst == "虚拟显示器.exe" and os.path.exists(alt):
            src = alt
    if not os.path.exists(src):
        missing.append(dst)
        print("  缺失!", dst, "<-", src)
        continue
    shutil.copy2(src, os.path.join(DEST, dst))
    print("  ok  ", dst, "(%d KB)" % (os.path.getsize(src) // 1024))

print()
# README links its screenshots by relative path, so they have to travel with it
# or the offline copy shows broken images.
IMG_SRC = os.path.join(ROOT, "docs", "images")
IMG_DST = os.path.join(DEST, "docs", "images")
if os.path.isdir(IMG_SRC):
    os.makedirs(IMG_DST, exist_ok=True)
    for f in sorted(os.listdir(IMG_SRC)):
        if not f.lower().endswith(".png"):
            continue
        shutil.copy2(os.path.join(IMG_SRC, f), os.path.join(IMG_DST, f))
        print("  ok  ", "docs\\images\\" + f,
              "(%d KB)" % (os.path.getsize(os.path.join(IMG_DST, f)) // 1024))
else:
    missing.append("docs\\images")

print()
for f in DRIVER_FILES:
    src = os.path.join(ROOT, "driver", f)
    if not os.path.exists(src):
        missing.append("driver\\" + f)
        print("  缺失!", "driver\\" + f, "<-", src)
        continue
    shutil.copy2(src, os.path.join(DEST, "driver", f))
    print("  ok  ", "driver\\" + f, "(%d KB)" % (os.path.getsize(src) // 1024))

print()
if missing:
    print("结果: 不完整，缺 %d 项 -> %s" % (len(missing), missing))
    raise SystemExit(1)

total = sum(os.path.getsize(os.path.join(dp, f))
            for dp, _, fs in os.walk(DEST) for f in fs)
print("结果: 完整 ✓   共 %d 个文件, %.1f MB" % (
    sum(len(fs) for _, _, fs in os.walk(DEST)), total / 1024 / 1024))
print("位置:", DEST)
print()
print("分享方式：只发 虚拟显示器.exe 也够用（驱动由它自己装）；")
print("          要命令行和串流脚本，再发整个 %s 文件夹。" % NAME)
print("对方步骤：1) 双击 虚拟显示器.exe —— 没驱动时横幅上点「安装驱动」（弹 UAC）")
print("          2) 想用脚本装：右键 install-driver.bat -> 以管理员身份运行")
print("          3) 串流需再跑 sunshine-setup.bat（在对方那台机器上配）")
