"""
MttVDD virtual display - command line.

    vdd.py status                 what exists right now
    vdd.py modes                  modes the driver offers
    vdd.py set WxH[@Hz]           switch the virtual display to a mode
    vdd.py config                 show the config file
    vdd.py count N                set how many virtual displays to create
    vdd.py add WxH[@Hz]           add a resolution to the offered list
    vdd.py remove WxH[@Hz]        remove one from the offered list
    vdd.py reload                 apply config changes (needs admin)
    vdd.py doctor                 full health report

There is no daemon and no keepalive: the driver reads its config at load
time and the displays then persist. So 'reload' is only needed after
changing the config, and 'set' only changes the active mode.
"""

import sys

import vdd_core as c


def _fmt_mode(m):
    return "%dx%d@%d" % m


def _parse_mode(text, default_hz=60):
    """'2560x1440' or '2560x1440@120' -> (w, h, hz)."""
    t = text.lower().replace(" ", "")
    hz = default_hz
    if "@" in t:
        t, hzs = t.split("@", 1)
        hz = int(hzs)
    w, h = t.split("x", 1)
    return int(w), int(h), hz


def cmd_status(argv=None):
    s = c.status()
    print("=== VirtualDisplay status ===")
    print("device installed :", s["device_installed"], "  (%s)" % s["device_id"])
    print("config file      :", s["config_path"])
    if s["config_error"]:
        print("config           : ERROR -", s["config_error"])
    else:
        cfg = s["config"]
        print("config count     :", cfg["count"])
        print("config refresh   :", cfg["refresh_rates"])
        print("config modes     :", ", ".join(_fmt_mode(r) for r in cfg["resolutions"]))
    print()
    print("--- displays (real pixel modes) ---")
    for d in s["displays"]:
        if not d["attached"] and not d["virtual"]:
            continue
        tags = []
        if d["primary"]:
            tags.append("PRIMARY")
        if d["virtual"]:
            tags.append("VIRTUAL")
        if not d["attached"]:
            tags.append("detached")
        print("  %-13s %4dx%-5d @%3dHz  %-16s %s"
              % (d["device"], d["width"], d["height"], d["hz"],
                 " ".join(tags), d["adapter"][:30]))
    print()
    print("virtual displays :", s["virtual_count"])
    return 0 if s["device_installed"] else 1


def cmd_modes(argv=None):
    vds = c.virtual_displays()
    if not vds:
        print("no virtual display attached - is the driver installed?")
        return 1
    dev = vds[0]["device"]
    cur = (vds[0]["width"], vds[0]["height"], vds[0]["hz"])
    print("modes offered by %s:" % dev)
    for m in c.available_modes(dev):
        print("  %s%s" % (_fmt_mode(m), "   <-- current" if m == cur else ""))
    return 0


def cmd_set(argv):
    if not argv:
        print("usage: vdd.py set WxH[@Hz]   e.g. set 2560x1440@60")
        return 1
    try:
        w, h, hz = _parse_mode(argv[0])
    except Exception:                                          # noqa: BLE001
        print("cannot parse:", argv[0])
        return 1
    vds = c.virtual_displays()
    if not vds:
        print("no virtual display attached")
        return 1
    r = c.set_mode(vds[0]["device"], w, h, hz)
    print(r.get("out") or r.get("error"))
    return 0 if r["ok"] else 1


def cmd_config(argv=None):
    try:
        cfg = c.read_config()
    except Exception as exc:                                   # noqa: BLE001
        print("cannot read config:", exc)
        return 1
    print("file        :", cfg["path"])
    print("count       :", cfg["count"])
    print("gpu         :", cfg["gpu"])
    print("refresh     :", cfg["refresh_rates"])
    print("resolutions :")
    for r in cfg["resolutions"]:
        print("   ", _fmt_mode(r))
    print("options     :", cfg["options"])
    return 0


def cmd_count(argv):
    if not argv:
        print("usage: vdd.py count N")
        return 1
    try:
        n = int(argv[0])
    except ValueError:
        print("not a number:", argv[0])
        return 1
    cfg = c.read_config()
    cfg["count"] = max(1, min(8, n))
    c.write_config(cfg)
    print("count set to %d - run 'reload' to apply" % cfg["count"])
    return 0


def cmd_add(argv):
    if not argv:
        print("usage: vdd.py add WxH[@Hz]")
        return 1
    try:
        m = _parse_mode(argv[0])
    except Exception:                                          # noqa: BLE001
        print("cannot parse:", argv[0])
        return 1
    cfg = c.read_config()
    if m in cfg["resolutions"]:
        print("already present:", _fmt_mode(m))
        return 0
    cfg["resolutions"].append(m)
    c.write_config(cfg)
    print("added %s - run 'reload' to apply" % _fmt_mode(m))
    return 0


def cmd_remove(argv):
    if not argv:
        print("usage: vdd.py remove WxH[@Hz]")
        return 1
    try:
        m = _parse_mode(argv[0])
    except Exception:                                          # noqa: BLE001
        print("cannot parse:", argv[0])
        return 1
    cfg = c.read_config()
    if m not in cfg["resolutions"]:
        print("not in the list:", _fmt_mode(m))
        return 1
    if len(cfg["resolutions"]) <= 1:
        print("refusing to remove the last resolution")
        return 1
    cfg["resolutions"].remove(m)
    c.write_config(cfg)
    print("removed %s - run 'reload' to apply" % _fmt_mode(m))
    return 0


def cmd_reload(argv=None):
    if not c.is_admin():
        print("reload needs administrator rights.")
        print("re-run this from an elevated prompt, or use install-driver.bat")
        return 1
    r = c.reload_driver()
    print(r.get("out") or r.get("error"))
    return 0 if r["ok"] else 1


def cmd_doctor(argv=None):
    s = c.status()
    print("=== doctor ===")
    ok = True

    print("device installed :", s["device_installed"])
    ok = ok and s["device_installed"]

    if s["config_error"]:
        print("config           : ERROR -", s["config_error"])
        ok = False
    else:
        print("config           : OK (count=%d, %d modes)"
              % (s["config"]["count"], len(s["config"]["resolutions"])))
        mismatch = s["config"]["count"] != s["virtual_count"]
        print("count vs actual  : config=%d actual=%d%s"
              % (s["config"]["count"], s["virtual_count"],
                 "   <-- MISMATCH, run reload" if mismatch else "   OK"))

    print("virtual attached :", s["virtual_count"])
    if s["virtual_count"]:
        vd = s["virtual"]
        print("  %s  %dx%d@%d" % (vd["device"], vd["width"], vd["height"], vd["hz"]))
        print("modes offered    :", len(s["modes"]))
    else:
        ok = False

    print("admin            :", s["admin"])
    print()
    print("verdict          :", "HEALTHY" if ok else "NEEDS ATTENTION")
    return 0 if ok else 1


COMMANDS = {
    "status": cmd_status,
    "modes": cmd_modes,
    "set": cmd_set,
    "config": cmd_config,
    "count": cmd_count,
    "add": cmd_add,
    "remove": cmd_remove,
    "reload": cmd_reload,
    "doctor": cmd_doctor,
}


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    fn = COMMANDS.get(argv[0])
    if not fn:
        print("unknown command:", argv[0])
        print("known:", ", ".join(sorted(COMMANDS)))
        return 1
    return fn(argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
