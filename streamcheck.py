"""Sunshine / Moonlight 串流链路体检.

为什么需要它：这类问题的证据只在"会话那十几秒"里存在（UDP 通道是否齐全、
视频到底有没有真的发出去），事后翻日志看不出来。手动敲命令采样的结果是
采样窗口和点击时机对不上，白测一轮。所以这里把采集和判定都固化下来。

用法：
    python streamcheck.py                # 静态体检，立刻出结论
    python streamcheck.py --where        # 手机看到的到底是物理屏还是虚拟屏
    python streamcheck.py --watch 60     # 开始采样，这 60 秒内去手机点连接

退出码：0 = PASS，1 = FAIL，2 = 没采到会话（需要重跑 --watch）。
判定打印在最后一行，机器可读。
"""
import argparse
import ctypes
import io
import json
import os
import re
import socket
import struct
import subprocess
import sys
import time

CONF = r"C:\Program Files\Sunshine\config\sunshine.conf"
LOG = r"C:\Program Files\Sunshine\config\sunshine.log"
STATE = r"C:\Program Files\Sunshine\config\sunshine_state.json"
TCP_PORTS = (47984, 47989, 47990, 48010)
UDP_PORTS = (47998, 47999, 48000, 48010)


def sh(args):
    p = subprocess.run(args, capture_output=True)
    return (p.stdout.decode("gbk", "replace") + p.stderr.decode("gbk", "replace"))


def ps(script):
    return sh(["powershell", "-NoProfile", "-Command", script]).strip()


# ---------------------------------------------------------------- listeners
def listeners():
    """-> (tcp {(port, family)}, udp {(port, family)}) from netstat."""
    tcp, udp = set(), set()
    # netstat lines start with the protocol column, and IPv6 endpoints are
    # written as [::]:47990 -- both of those have to be in the pattern.
    for line in sh(["netstat", "-ano", "-p", "TCP"]).splitlines():
        m = re.match(r"\s*TCP\s+(\S+?):(\d+)\s+\S+\s+LISTENING\s+(\d+)", line)
        if m:
            tcp.add((int(m.group(2)), "v6" if m.group(1).startswith("[") else "v4"))
    for line in sh(["netstat", "-ano", "-p", "UDP"]).splitlines():
        m = re.match(r"\s*UDP\s+(\S+?):(\d+)\s+\*", line)
        if m:
            udp.add((int(m.group(2)), "v6" if m.group(1).startswith("[") else "v4"))
    return tcp, udp


# ------------------------------------------------------------------- config
def conf_facts():
    if not os.path.exists(CONF):
        return {"exists": False}
    raw = open(CONF, "rb").read()
    txt = raw.decode("utf-8-sig", "replace")
    got = dict(re.findall(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+?)\s*$",
                          txt, re.M))
    return {
        "exists": True,
        "bom": raw.startswith(b"\xef\xbb\xbf"),
        "address_family": got.get("address_family"),
        "dd_configuration_option": got.get("dd_configuration_option"),
        "output_name": got.get("output_name"),
    }


def bitrates_in(start, end):
    """"Streaming bitrate is N" timestamps inside [start, end] (HH:MM:SS.mmm).

    The startup encoder probe also logs a bitrate (always 1 Mbps), so taking the
    last value in the file gives a bogus reference. Only values timestamped
    inside the session count.
    """
    if not os.path.exists(LOG):
        return []
    out = []
    for line in io.open(LOG, encoding="utf-8", errors="replace"):
        m = re.match(r"\[[\d\-]+ ([\d:.]+)\]: Info: Streaming bitrate is (\d+)", line)
        if m and start <= m.group(1) <= end:
            out.append(int(m.group(2)))
    return out


def last_bitrate():
    """Informational only: bitrate from the newest *session* in the log."""
    if not os.path.exists(LOG):
        return None
    txt = io.open(LOG, encoding="utf-8", errors="replace").read()
    marks = [m.start() for m in re.finditer(r"New streaming session started", txt)]
    if not marks:
        return None
    hits = re.findall(r"Streaming bitrate is (\d+)", txt[marks[-1]:])
    return int(hits[-1]) if hits else None


def log_events(since):
    """CLIENT CONNECTED / DISCONNECTED / Fatal / Error lines after a timestamp."""
    if not os.path.exists(LOG):
        return []
    out = []
    for line in io.open(LOG, encoding="utf-8", errors="replace"):
        m = re.match(r"\[([\d\- :.]+)\]: (\w+): (.{0,90})", line)
        if not m:
            continue
        stamp, level, msg = m.groups()
        if stamp < since:
            continue
        if re.search(r"CLIENT (CONNECTED|DISCONNECTED)", msg) or level in ("Fatal", "Error"):
            out.append("%s %s: %s" % (stamp[11:], level, msg))
    return out


def ipv6_probe():
    """Actually try to connect. netstat prints a dual-stack socket as
    0.0.0.0:port, so parsing it cannot tell IPv6 apart -- measured this the hard
    way while writing this tool."""
    txt = ps("Get-NetIPAddress -InterfaceAlias WLAN -AddressFamily IPv6 "
             "| Where-Object { $_.IPAddress -notlike 'fe80*' } "
             "| Select-Object -ExpandProperty IPAddress")
    ip = txt.split()[0] if txt.split() else None
    if not ip:
        return None, "WLAN 上没有全局 IPv6 地址"
    s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    s.settimeout(3)
    try:
        s.connect((ip, 47990, 0, 0))
        return ip, "可连（双栈生效）"
    except Exception as exc:
        return ip, "连不上：%s" % exc
    finally:
        s.close()


# ------------------------------------------------------------------- static
def report_static():
    print("== Sunshine 串流链路体检 ==")
    print("服务         :", ps("(Get-Service SunshineService).Status"))
    c = conf_facts()
    if not c.get("exists"):
        print("conf         : 找不到", CONF)
        return
    print("conf BOM     :", "有  <-- address_family 等首个键会被 Sunshine 判为 Unrecognized"
          if c["bom"] else "无 (ok)")
    print("address_family:", c["address_family"])
    print("dd_configuration_option:", c["dd_configuration_option"])
    print("串流画面     :", claimed_target()["why"])
    tcp, udp = listeners()
    sun_tcp = sorted(p for p, _ in tcp if p in TCP_PORTS)
    sun_udp = sorted(p for p, _ in udp if p in UDP_PORTS)
    print("Sunshine TCP :", ", ".join(map(str, sun_tcp)) or "(无)")
    print("Sunshine UDP :", ", ".join(map(str, sun_udp)) or "(无，空闲时正常)")
    ip, how = ipv6_probe()
    print("IPv6 实测    : %s %s" % (ip or "-", how))
    print("防火墙 profile:", ps("Get-NetFirewallProfile | ForEach-Object { $_.Name + '=' + $_.Enabled }").replace("\r\n", " "))
    if os.path.exists(STATE):
        age = (time.time() - os.path.getmtime(STATE)) / 3600
        print("配对文件     : %.1f 小时前改过" % age)
    print("上一场清理   :", "挂死在视频线程（主机现在是坏的，必须重启才能再测）"
          if hung_session() else "干净（All broadcasting threads ended）")
    print("日志最近事件 :")
    for e in log_events("1970-01-01")[-6:]:
        print("   ", e)



# ------------------------------------------------------------------ sessions
NEG_KEYS = ("clientViewportWd", "clientViewportHt", "maxFPS", "packetSize",
            "initialBitrateKbps", "rateControlMode", "fec.enable",
            "encFPS", "encBitrateKbps", "videoFormat", "audioBufferSize",
            "enableSuperraming", "multiFramingMode", "surroundAudioInfo")

KEY_INFO = ("Creating encoder", "Streaming bitrate is", "Desktop resolution",
            "Requested frame rate", "Capture size", "Offset", "Color depth")


def session_blocks():
    """Split the log into per-session blocks by position.

    A block runs from one `CLIENT CONNECTED` to the next `CLIENT DISCONNECTED`;
    the RTSP `a=x-nv-...` negotiation lines have no timestamp of their own, so
    position is the only thing that can attribute them to a session.
    """
    if not os.path.exists(LOG):
        return []
    lines = io.open(LOG, encoding="utf-8", errors="replace").read().splitlines()
    # Anchoring took three tries, all of them my mistake, so it is written down:
    # the client's RTSP `a=x-nv-...` negotiation dump sits BEFORE the session
    # start line, and the cleanup lines (`All broadcasting threads ended`) sit
    # AFTER `CLIENT DISCONNECTED`. So each block spans from the end of the
    # previous block up to its own cleanup line -- which is exactly what lets
    # one block also tell whether that session's teardown hung.
    starts = [k for k, l in enumerate(lines) if "New streaming session started" in l]
    blocks, prev = [], 0
    for n, s in enumerate(starts):
        nxt = starts[n + 1] if n + 1 < len(starts) else len(lines)
        cl = next((k for k in range(s, nxt) if "All broadcasting threads ended" in lines[k]), None)
        end = cl if cl is not None else nxt
        blocks.append(lines[prev:end + 1])
        prev = end + 1
    return [b for b in blocks if any("CLIENT CONNECTED" in l for l in b)]


def stamp_of(line):
    m = re.search(r"(\d{2}:\d{2}:\d{2}\.\d+)", line or "")
    return m.group(1) if m else None


def session_report():
    """Side-by-side of every session in the current log."""
    from datetime import datetime as DT
    blocks = session_blocks()
    if not blocks:
        print("日志里没有完整会话（sunshine.log 每次启动会被清空，跑完一轮别重启再来看）")
        return 1
    boxes = display_boxes()
    for n, blk in enumerate(blocks, 1):
        txt = "\n".join(blk)
        peer = re.search(r"RAISE: ::ffff:([\d.]+):\d+ :: VIDEO", txt)
        first = next((l for l in blk if "CLIENT CONNECTED" in l), "")
        last = next((l for l in reversed(blk) if "CLIENT DISCONNECTED" in l), "")
        stamp, end = stamp_of(first), stamp_of(last)
        try:
            dur = (DT.strptime(end, "%H:%M:%S.%f") - DT.strptime(stamp, "%H:%M:%S.%f")).total_seconds()
        except (TypeError, ValueError):
            dur = 0.0
        cleaned = "All broadcasting threads ended" in txt
        live = not any("CLIENT DISCONNECTED" in l for l in blk)
        top = [int(x) for x in re.findall(r"Frame (\d+): IDR", txt)]
        fec = [int(x) for x in re.findall(r"Increasing FEC percentage to (\d+)", txt)]
        print("--- 会话 %d  %s  时长 %.1f s  对端 %s  清理 %s"
              % (n, stamp, dur, peer.group(1) if peer else "?",
                 "完成" if cleaned else
                 ("进行中（还没断开，不判）" if live else "!! 挂死在视频线程")))
        print("    最后编码帧号 Frame %s   FEC 抬升 %d 次（健康会话也会，别当丢包证据）"
              % (max(top) if top else "-", len(fec)))
        for k in NEG_KEYS:
            # [a-z0-9...] -- the "video[0]" part contains a digit; leaving it out
            # matched nothing for a whole round.
            v = sorted(set(re.findall(r"a=x-nv-[a-z0-9\[\]\.]*\." + k + r":([\w.-]+)", txt)))
            if v:
                print("    %-22s %s" % (k, "/".join(v)))
        ci = next((i for i, l in enumerate(blk) if "CLIENT CONNECTED" in l), 0)
        seen_key = set()
        for line in blk[ci:]:      # the startup encoder probe is not this session's business
            for k in KEY_INFO:
                if k in line and k not in seen_key:
                    seen_key.add(k)
                    print("    " + re.sub(r"\s+", " ", line[:100]))
        # Which screen the phone saw, per session -- the number people actually
        # want, and the one Sunshine only ever reports as size + offset.
        pairs = capture_pairs("\n".join(blk[ci:]))
        if pairs:
            cap, off, _ = pairs[-1]
            label, how, _box = attribute(cap, off, boxes)
            print("    抓取源 %dx%d@%dx%d -> %s（%s，本场共 %d 次）"
                  % (cap[0], cap[1], off[0], off[1], label, how, len(pairs)))
        else:
            print("    抓取源 这场没有 Capture size/Offset 行（视频没起来，或日志被冲掉）")
    return 0


# -------------------------------------------------------------------- watch
WLAN_TX_SCRIPT = r"""
$ErrorActionPreference='SilentlyContinue'
$st = Get-NetAdapterStatistics -Name WLAN
$pids = @(Get-Process sunshine -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
$paths = @(
  '\Process(sunshine*)\IO Other Bytes/sec',
  '\Process(sunshine*)\IO Data Bytes/sec',
  '\Process(sunshine*)\% Processor Time'
)
$cs = (Get-Counter $paths -ErrorAction SilentlyContinue).CounterSamples
$other = 0.0; $data = 0.0; $cpu = 0.0
foreach ($c in $cs) {
  if ($c.Path -like '*IO Other*') { $other += $c.CookedValue }
  elseif ($c.Path -like '*IO Data*') { $data += $c.CookedValue }
  else { $cpu += $c.CookedValue }
}
$ports = (Get-NetUDPEndpoint -ErrorAction SilentlyContinue |
          Where-Object { $pids -contains $_.OwningProcess } |
          ForEach-Object { $_.LocalPort } | Sort-Object -Unique) -join '+'
'{0}|{1}|{2}|{3}|{4}|{5}|{6}' -f [DateTime]::Now.ToString('HH:mm:ss.fff'),
  $st.SentBytes, $st.ReceivedBytes, [long]$other, [long]$data, [long]$cpu, $ports
"""


def sample():
    """One 1-Hz reading: (stamp, wlan_tx_bytes, wlan_rx, sunshine_out_bytes_s,
    sunshine_io_data_bytes_s, sunshine_cpu_pct, sunshine_udp_ports).

    Two independent instruments for "did video leave the host": the WLAN
    adapter counts link-layer bytes, the process counters count what Sunshine
    itself pushed. If they disagree, one of them is not covering sockets --
    printing both keeps the verdict honest.
    """
    out = ps(WLAN_TX_SCRIPT)
    parts = out.split("|")
    if len(parts) != 7:
        return None
    stamp, tx, rx, other, data, cpu, ports = parts
    try:
        return (stamp, int(tx), int(rx), int(other), int(data), int(cpu),
                sorted(int(p) for p in ports.split("+") if p))
    except ValueError:
        return None


# ------------------------------------------------------------- refresh rate
# DEVMODEW is a union soup: the documented field order does not line up with
# what this driver actually fills. Measured on this box (4K@160 + VDD@60):
# width/height/refresh live at byte offsets 172/176/184, and the driver writes
# its own dmSize=188 no matter what the caller claims. A struct built from the
# docs read 3840 out of the slot named dmLogPixels -- so read and write raw
# bytes at measured offsets, and refuse to print numbers that came back zero.
DM_BYTES = 220
DM_SIZE_OFF, DM_FIELDS_OFF = 68, 72
DM_W_OFF, DM_H_OFF, DM_HZ_OFF = 172, 176, 184
DM_X_OFF, DM_Y_OFF = 76, 80                 # LONG and signed: a screen on the left is negative
DM_FREQ_FLAG = 0x00000020                 # DM_DISPLAYFREQUENCY
DD_ATTACHED, DD_PRIMARY = 0x1, 0x4        # 0x4 is primary, not 0x2 (0x2 is MultiDriver)

U32 = ctypes.windll.user32
ENUM_CURRENT = 0xFFFFFFFF


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_uint32), ("DeviceName", ctypes.c_wchar * 32),
        ("DeviceString", ctypes.c_wchar * 128), ("StateFlags", ctypes.c_uint32),
        ("DeviceID", ctypes.c_wchar * 128), ("DeviceKey", ctypes.c_wchar * 128),
    ]


def dm_read(name, index=ENUM_CURRENT):
    buf = ctypes.create_string_buffer(DM_BYTES)
    struct.pack_into("<H", buf, DM_SIZE_OFF, DM_BYTES)
    if not U32.EnumDisplaySettingsW(name, index, buf):
        return None
    return buf


def dm_mode(buf):
    """(w, h, hz) from the measured offsets."""
    return (struct.unpack_from("<I", buf, DM_W_OFF)[0],
            struct.unpack_from("<I", buf, DM_H_OFF)[0],
            struct.unpack_from("<I", buf, DM_HZ_OFF)[0])


def displays():
    """[(name, string, primary, hz, w, h)] for every attached display device."""
    out, i = [], 0
    while i < 16:
        dd = DISPLAY_DEVICEW()
        dd.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        if not U32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
            break
        if dd.StateFlags & DD_ATTACHED:
            buf = dm_read(dd.DeviceName)
            if buf:
                w, h, hz = dm_mode(buf)
                out.append((dd.DeviceName, dd.DeviceString,
                            bool(dd.StateFlags & DD_PRIMARY), hz, w, h))
        i += 1
    return out


def supported_hz(name, width, height):
    hz, i = [], 0
    while i < 500:
        buf = dm_read(name, i)
        if buf is None:
            break
        w, h, r = dm_mode(buf)
        if (w, h) == (width, height):
            hz.append(r)
        i += 1
    return sorted(set(hz))


# ----------------------------------------------------------- capture source
# Sunshine never prints the *name* of the screen it duplicated, only its size
# and where it sits inside the virtual desktop:
#
#     Capture size : 3840x2160
#     Offset       : 2560x0
#     Virtual Desktop : 6400x2160
#
# The offset is relative to the top-left of the bounding box of all attached
# displays, so pairing it with Windows' own geometry is what turns those two
# numbers into "物理屏" or "虚拟屏". Calibrated on this box against the 20
# sessions in today's log: 3840x2160@2560x0 (x60) is the primary panel while
# the VDD screen sat at -2560; the same log also contains 2560x1440@3840x0 and
# 2560x1440@0x2160, which are the VDD screen placed to the right and below.
# Every placement this machine has actually used comes back with the right
# label, which is the positive control this rule needed before being trusted.
DRIVER_MATCH = "Virtual Display Driver"    # same substring vdd_core uses


def dm_pos(buf):
    return (struct.unpack_from("<i", buf, DM_X_OFF)[0],
            struct.unpack_from("<i", buf, DM_Y_OFF)[0])


def display_boxes():
    """[(name, string, primary, w, h, x, y)] -- positions included.

    `displays()` above cannot answer "which screen is the phone seeing" because
    it drops the coordinates; this is the same enumeration plus x/y.
    """
    out, i = [], 0
    while i < 16:
        dd = DISPLAY_DEVICEW()
        dd.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        if not U32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
            break
        if dd.StateFlags & DD_ATTACHED:
            buf = dm_read(dd.DeviceName)
            if buf:
                w, h, _ = dm_mode(buf)
                x, y = dm_pos(buf)
                out.append((dd.DeviceName, dd.DeviceString,
                            bool(dd.StateFlags & DD_PRIMARY), w, h, x, y))
        i += 1
    return out


def kind_of(string, primary):
    return ("虚拟屏" if DRIVER_MATCH in (string or "") else "物理屏") + \
           ("·主屏" if primary else "")


def offset_table(boxes):
    """{(w, h, ox, oy): label} as Sunshine would report the current layout."""
    if not boxes:
        return {}
    min_x = min(b[5] for b in boxes)
    min_y = min(b[6] for b in boxes)
    return {(b[3], b[4], b[5] - min_x, b[6] - min_y): label_of(b)
            for b in boxes}


def capture_pairs(txt):
    """[(('WxH','WxH'), byte_offset)] -- every Capture size/Offset pair in txt.

    Pairs, not single values: the startup encoder probe also prints a Capture
    size, and only the Offset next to it says which screen that was.
    """
    out = []
    for m in re.finditer(r"Capture size\s*:\s*(\d+)x(\d+)\s*\n\s*Offset\s*:\s*(\d+)x(\d+)",
                         txt):
        out.append(((int(m.group(1)), int(m.group(2))),
                    (int(m.group(3)), int(m.group(4))), m.start()))
    return out


def attribute(cap, off, boxes):
    """-> (label, how, box). Exact geometry first, then size only, then unknown.

    A session that ran before the screens were moved cannot match today's
    geometry, and saying so is better than silently labelling it wrong.
    """
    min_x = min(b[5] for b in boxes)
    min_y = min(b[6] for b in boxes)
    for b in boxes:
        if (b[3], b[4], b[5] - min_x, b[6] - min_y) == (cap[0], cap[1], off[0], off[1]):
            return label_of(b), "几何完全对得上", b
    by_size = [b for b in boxes if (b[3], b[4]) == cap]
    if len(by_size) == 1:
        return label_of(by_size[0]), \
               "只有尺寸对得上（这块屏在会话之后被挪过位置）", by_size[0]
    if len(by_size) > 1:
        return "两块屏同为 %dx%d，分不开" % cap, "尺寸撞车，必须靠 offset", None
    return "没有一块屏是 %dx%d" % cap, "当前接的屏和那场会话不是同一套", None


def label_of(b):
    return "%s %s %dx%d" % (kind_of(b[1], b[2]), b[0], b[3], b[4])



# -------------------------------------------------------- "what does the phone see"
SUNSHINE_MARK = "Currently available display devices:"


def sunshine_display_map():
    """{device_id: (display_name, friendly_name, primary)} from the newest block.

    Head-only read, same reason as vdd_core: the block is printed once at
    startup and this box's log runs to gigabytes of encoder spam.
    """
    if not os.path.exists(LOG):
        return {}
    with open(LOG, "rb") as f:
        head = f.read(4_000_000).decode("utf-8", "replace")
    blocks = re.findall(re.escape(SUNSHINE_MARK) + r"\s*(\[.*?\n\])", head, re.S)
    if not blocks:
        return {}
    try:
        devs = json.loads(blocks[-1])
    except ValueError:
        return {}
    return {d.get("device_id"): (d.get("display_name"), d.get("friendly_name"),
                                 bool((d.get("info") or {}).get("primary")))
            for d in devs}


def claimed_target():
    """What the config claims the phone should see, resolved to a Windows screen.

    Three states now, not two - 跟随系统 / 钉住物理屏 / 钉住虚拟屏 all differ only
    in output_name and dd_configuration_option - so the claim has to be joined
    against Sunshine's own enumeration before it can face the capture record.
    """
    c = conf_facts()
    if not c.get("exists"):
        return {"mode": "none", "device": None, "id": None, "dd": None,
                "why": "conf 找不到"}
    out_name = (c.get("output_name") or "").strip()
    mode = (c.get("dd_configuration_option") or "disabled").strip()
    if out_name:
        ent = sunshine_display_map().get(out_name)
        dev = ent[0] if ent else None
        if dev:
            b = next((x for x in display_boxes() if x[0] == dev), None)
            kind = "虚拟屏" if b and DRIVER_MATCH in b[1] else "物理屏"
            label = "钉住 %s（%s）" % (dev, kind)
        else:
            label = "钉住一个当前不在位的 id"
        return {"mode": "pinned", "device": dev, "id": out_name, "dd": mode,
                "why": "%s：output_name=%s…，dd_configuration_option=%s"
                       % (label, out_name[:14], mode)}
    if mode in ("", "disabled"):
        return {"mode": "follow", "device": None, "id": None, "dd": mode,
                "why": "串流画面=跟随系统（output_name 未设 -> 抓主显示器那块）"}
    return {"mode": "dd-" + mode, "device": None, "id": None, "dd": mode,
            "why": "dd_configuration_option=%s 但没写 output_name" % mode}


def where_report():
    """VERDICT on which physical screen the phone is actually looking at."""
    print("== 手机看到的是哪块屏 ==")
    boxes = display_boxes()
    if not boxes:
        print("VERDICT FAIL 枚举不到任何显示设备")
        return 1
    print("当前接好的屏：")
    for b in boxes:
        print("    %-14s %-22s %dx%d @(%d,%d) %s"
              % (b[0], kind_of(b[1], b[2]), b[3], b[4], b[5], b[6], b[1][:22]))
    claim = claimed_target()
    print("配置声称     :", claim["why"])
    if not os.path.exists(LOG):
        print("VERDICT FAIL 没有日志，没法证明实际抓了哪块屏")
        return 1
    txt = io.open(LOG, encoding="utf-8", errors="replace").read()
    starts = [m.start() for m in re.finditer(r"New streaming session started", txt)]
    if not starts:
        print("VERDICT FAIL 日志里没有完整会话：跑一轮 Moonlight 连接再来看")
        return 2
    tail = txt[starts[-1]:]
    pairs = capture_pairs(tail)
    if not pairs:
        print("VERDICT FAIL 最后一场会话里没有 Capture size/Offset 行"
              "（日志级别被刷屏冲掉，或这场根本没起视频）")
        return 1
    cap, off, _ = pairs[-1]
    label, how, box = attribute(cap, off, boxes)
    print("实测抓取     : Capture %dx%d Offset %dx%d  ->  %s"
          % (cap[0], cap[1], off[0], off[1], label))
    print("   （判定依据：%s；同一场里共 %d 次抓取记录）" % (how, len(pairs)))
    is_virtual = box is not None and DRIVER_MATCH in (box[1] or "")
    is_primary = box is not None and bool(box[2])
    captured = box[0] if box else None
    blank = claim["dd"] == "ensure_only_display"
    if claim["mode"] == "pinned":
        if captured and captured == claim["device"]:
            print("VERDICT PASS 钉住的屏和被抓的屏是同一块（%s）；另一块屏%s。"
                  % (captured, "串流期间会黑（ensure_only_display）" if blank
                     else "照常可用（disabled）"))
            return 0
        print("VERDICT FAIL 声称钉住 %s，实测抓的是 %s —— 两者对不上，"
              "面板那行「手机看到」不能信。" % (claim["device"] or "(id 不在位)", label))
        return 1
    if claim["mode"] == "follow":
        if is_primary and not is_virtual:
            print("VERDICT PASS 抓的是主显示器（物理屏），和「跟随系统」的说法一致。"
                  "手机看不到另一块屏是这套配置的预期行为；要它看虚拟屏，"
                  "用「串流画面=虚拟屏」，或把主显示器改成虚拟屏。")
            return 0
        if is_virtual and is_primary:
            print("VERDICT PASS 主显示器当前就是虚拟屏，所以「跟随系统」抓到的正是虚拟屏。")
            return 0
        print("VERDICT FAIL 声称跟随系统（应抓主屏），实测抓的是 %s —— 主屏判据对不上，"
              "这套说法不能再用。" % label)
        return 1
    print("VERDICT FAIL 配置状态没法解释（%s），先别信面板" % claim["why"])
    return 1



def set_refresh(hz):
    """Change the primary display's refresh rate without touching the registry,
    so it is a temporary lever you flip back with `--refresh <原值>`."""
    ds = displays()
    if not ds:
        print("VERDICT FAIL 枚举不到任何显示设备")
        return 1
    if not any(d[3] for d in ds):
        print("VERDICT FAIL 读回来的刷新率全是 0：这块驱动的 DEVMODE 偏移和我量的"
              "不一样，下面的数字一个都别信")
        return 1
    if hz == "show":
        for name, desc, primary, cur, w, h in ds:
            print("  %-14s %-26s %s %dx%d @ %dHz  可选 %s"
                  % (name, desc[:26], "主屏" if primary else "-", w, h, cur,
                     supported_hz(name, w, h)))
        return 0
    target = next((d for d in ds if d[2]), None) or ds[0]
    name, _, _, cur, w, h = target
    want = int(hz)
    opts = supported_hz(name, w, h)
    if want not in opts:
        print("VERDICT FAIL %s 在 %dx%d 下不支持 %dHz，可选 %s" % (name, w, h, want, opts))
        return 1
    buf = dm_read(name)
    struct.pack_into("<I", buf, DM_FIELDS_OFF, DM_FREQ_FLAG)
    struct.pack_into("<I", buf, DM_HZ_OFF, want)
    code = U32.ChangeDisplaySettingsExW(name, buf, None, 0, None)
    print("改 %s (%dx%d) %dHz -> %dHz  返回码 %d" % (name, w, h, cur, want, code))
    after = next((d[3] for d in displays() if d[0] == name), None)
    print("改后实际     :", after, "Hz")
    if code != 0 or after != want:
        print("VERDICT FAIL 刷新率没改成功（返回码 %d，实际 %s）" % (code, after))
        return 1
    print("VERDICT PASS 已改成 %dHz；测完改回：python streamcheck.py --refresh %d"
          % (want, cur))
    return 0


def frame_events(start, end):
    """Keyframe lines inside [start, end]: (raw, highest_frame_number).

    Read this one carefully, it burned me once: at Debug level Sunshine logs
    ONLY keyframes -- a session that encoded 479 frames prints just two lines
    ("Frame 1", "Frame 479"). So one line does NOT mean "only one frame was
    encoded"; the frame *number* on the last line is what tells you the
    pipeline kept producing. Pair it with the byte counters below.
    """
    raw, top = [], 0
    if not os.path.exists(LOG):
        return raw, top
    for line in io.open(LOG, encoding="utf-8", errors="replace"):
        m = re.match(r"\[[\d\-]+ ([\d:.]+)\]: (\w+): (.*)", line)
        if not m or not (start <= m.group(1) <= end):
            continue
        stamp, level, msg = m.groups()
        k = re.search(r"Frame (\d+): IDR Keyframe", msg)
        if k:
            top = max(top, int(k.group(1)))
            raw.append("%s %s: %s" % (stamp, level, msg[:70]))
        elif "did not produce IDR" in msg:
            raw.append("%s %s: %s" % (stamp, level, msg[:70]))
    return raw, top


def loss_events(start, end):
    """FEC ramp-up lines inside the session -- context only, NOT a loss proof.

    I first read this as "the client is NAKing, so packets died on the wire".
    Wrong: the healthy 221 s PC loopback session raised FEC 1336 times up to
    200%. FEC is part of Sunshine's normal rate control, so it cannot separate
    a working stream from a dead one."""
    pct, rtsp = [], []
    if not os.path.exists(LOG):
        return pct, rtsp
    for line in io.open(LOG, encoding="utf-8", errors="replace"):
        m = re.match(r"\[[\d\-]+ ([\d:.]+)\]: \w+: (.*)", line)
        if not m or not (start <= m.group(1) <= end):
            continue
        k = re.search(r"Increasing FEC percentage to (\d+)", m.group(2))
        if k:
            pct.append(int(k.group(1)))
        elif "PING" in m.group(2) and "Recv" in m.group(2):
            rtsp.append(m.group(2)[:60])
    return pct, rtsp


# A moving window is the only way to guarantee the desktop actually changes
# pixels while the phone is connected; relying on the user to keep dragging
# things is not repeatable. Cursor motion alone would not do it either -- a
# hardware pointer moves without dirtying the captured image.
WIGGLE = r"""
import sys, time, tkinter as tk
sec = float(sys.argv[1])
root = tk.Tk()
root.title('streamcheck 动帧')
root.attributes('-topmost', True)
root.geometry('240x150+400+300')
tk.Label(root, text='MOVING', bg='#00aa44', fg='white', font=('Consolas', 28)).pack()
t0 = time.time()
while time.time() - t0 < sec:
    root.geometry('+%d+%d' % (60 + int(time.time() * 7) % 900, 60 + int(time.time() * 11) % 500))
    root.update()
    time.sleep(0.03)
root.destroy()
"""


def start_wiggle(seconds):
    try:
        return subprocess.Popen([sys.executable, "-c", WIGGLE, str(seconds)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        print("动帧窗口起不来（不影响采样，但桌面可能一直是静止的）:", exc)
        return None



def tail_text(path, n=300000):
    """Last n bytes of a file. The verbose log is already ~100 MB, so `read()`
    on every event would stall the sampling loop."""
    if not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - n))
        return f.read().decode("utf-8", "replace")


def ping_peer(ip, count=4):
    """(values_ms, loss_pct) from `ping`. Decoded from GBK because the labels
    are Chinese on this box; parsed by ASCII pattern so the wording does not
    matter."""
    p = subprocess.run(["ping", "-n", str(count), "-w", "500", ip], capture_output=True)
    txt = p.stdout.decode("gbk", "replace")
    vals = [int(x) for x in re.findall(r"=(\d+)ms", txt)]
    vals += [int(x) for x in re.findall(r"<(\d+)ms", txt)]
    lost = re.findall(r"\((\d+)%", txt)
    return vals, (int(lost[0]) if lost else None)


def watch(seconds, pause_checked):
    if not pause_checked:
        print("拒绝开始采样：我无法自动判断 Sunshine 是否处于暂停。")
        print("  paused 不写日志、不写配置；mTLS 读 serverstatus 需要配对客户端证书，")
        print("  Web UI 的 /api/state 需要登录密码。两条都没有，所以只能人工确认。")
        print("  看一眼托盘或 Web UI 首页，确认不是暂停状态，再加 --pause-checked 重跑。")
        return 2
    if hung_session():
        print("VERDICT FAIL 上一场会话的清理挂死在「Waiting for main video thread to end」，")
        print("  没走到「All broadcasting threads ended」。主机现在是坏的：这时候谁连都没")
        print("  画面（PC 端也一样失败），采到的只是挂死主机的假故障。")
        print("  先重启再测：python streamcheck.py --restart-service")
        print("  （它会等那个 taskkill 杀不动的僵尸进程自己消失，最多 90 秒）")
        return 1
    target = None
    bitrate = last_bitrate()
    if bitrate:
        target = bitrate
        print("参照码率（日志里最近一次）: %.1f Mbps" % (target / 1e6))
    print("开始采样 %d 秒——现在去手机上点连接。" % seconds)
    mover = start_wiggle(seconds)
    print("桌面动帧窗口已开（绿色 MOVING 方块自动换位），静止桌面这个变量已排除。")
    t0 = time.time()
    last_t = t0
    prev = sample()
    if prev is None:
        print("VERDICT FAIL 采样器一次都没读到数据：WLAN 网卡名或性能计数器不可用。")
        return 1
    seen_udp = set()
    events = []
    rows = []                      # (stamp, wlan_mbps, out_mbps, cpu, ports)
    lats = []                      # (stamp, avg_ms, max_ms, loss%) 只在会话进行中采样
    last_ping = 0.0
    live = False
    peer = None
    base = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t0))
    while time.time() - t0 < seconds:
        t1 = time.time()
        cur = sample()
        if cur and cur[1] != prev[1]:
            dt = max(t1 - last_t, 0.5)
            wlan = (cur[1] - prev[1]) * 8.0 / 1e6 / dt
            out_mbps = max(cur[3], cur[4]) * 8.0 / 1e6
            rows.append((cur[0], wlan, out_mbps, cur[5], cur[6]))
            seen_udp |= set(cur[6])
            print("  %s  wlan出 %5.1f Mbps  sunshine出 %5.1f Mbps  cpu %3.0f%%  udp=%s"
                  % (cur[0], wlan, out_mbps, cur[5], cur[6] or "-"), flush=True)
        if cur:
            prev = cur
            last_t = t1
        for e in log_events(base):
            if e not in events:
                events.append(e)
                print("  " + e, flush=True)
                live = "CLIENT CONNECTED" in e
                if live:
                    # 对端 IP 从 RAISE 行里拿，别写死：手机换 IP 是常事
                    got = re.search(r"RAISE: ::ffff:([\d.]+):\d+ :: VIDEO",
                                    tail_text(LOG))
                    peer = got.group(1) if got else peer
        # 只有会话真的连着才量延迟：空闲态的几十毫秒是手机省电态，量了只会误导
        if live and peer and time.time() - last_ping > 10:
            last_ping = time.time()
            vals, lost = ping_peer(peer)
            if vals:
                lats.append((stamp_of(cur[0]) or cur[0], sum(vals) / len(vals),
                             max(vals), lost))
                print("      ^ 会话中 PC->%s 延迟 均 %.1f ms 峰 %d ms 丢包 %s%%"
                      % (peer, lats[-1][1], lats[-1][2], lost), flush=True)
        time.sleep(0.2)
    if mover:
        mover.terminate()
    # ---- align the trace with every session the log reported ---------------
    wins = session_windows(events)
    win = wins[-1] if wins else None
    for a, b, d, peer in wins:
        br = bitrates_in(a, b)
        ev, top = frame_events(a, b)
        pct, _ = loss_events(a, b)
        print("  会话 %s->%s  %.1f s  对端 %-13s 码率 %s Mbps  最后帧号 Frame %-5s FEC 抬升 %s 次"
              % (a[:8], b[:8], d, peer,
                 "%.1f" % (max(br) / 1e6) if br else "-", top, len(pct)))
    in_win = [r for r in rows if win and win[0] <= r[0] <= win[1]] or rows
    wlan_peak = max([r[1] for r in in_win] or [0.0])
    out_peak = max([r[2] for r in in_win] or [0.0])
    cpu_peak = max([r[3] for r in in_win] or [0.0])
    print("-" * 60)
    print("采到会话     :", "是" if win else "否")
    print("UDP 通道峰值 :", sorted(seen_udp) or "(从未出现)")
    print("WLAN 发送峰值: %.1f Mbps" % wlan_peak)
    print("Sunshine 出流峰值: %.1f Mbps（进程计数，含音频）  CPU %.0f%%"
          % (out_peak, cpu_peak))
    if lats:
        print("会话中 PC->手机: 均 %.1f ms（峰值 %d ms，丢包 %s%%）—— 注意只有会话进行中的"
              "数字才有意义，空闲态跳到 30-90ms 是手机省电态"
              % (sum(x[1] for x in lats) / len(lats), max(x[2] for x in lats),
                 max((x[3] or 0) for x in lats)))
    else:
        print("会话中 PC->手机: 没采到（会话太短或没建立）——这条不采就别拿空闲 ping 定罪链路")
    if not win:
        print("VERDICT FAIL 窗口内没有会话发生。按概率排序：Sunshine 处于暂停（最常见，")
        print("  且服务状态仍显示 Running，两者互不矛盾）、地址不对、或根本没点。")
        return 2
    real = bitrates_in(win[0], win[1])
    if real:
        print("本次会话协商码率: %.1f Mbps" % (max(real) / 1e6))
        target = max(real)
    ev, top = frame_events(win[0], win[1])
    pct, _rtsp = loss_events(win[0], win[1])
    print("帧级证据     : 关键帧日志 %d 条，最后一条编号 Frame %d（Debug 只记 IDR，"
          "编号才是出帧进度）" % (len(ev), top))
    for e in ev[:6]:
        print("    ", e)
    if pct:
        print("丢包证据     : Sunshine 把 FEC 拉高过 %d 次，最高 %s%%"
              "（FEC 只在客户端报丢包时才抬，这条=视频 UDP 在路上死了）"
              % (len(pct), max(pct)))
    dur = win[2]
    want_frames = 60.0 * dur             # 客户端请求 60fps
    print("编码进度     : 会话内最后记录到 Frame %d，这一场理论上该有 %.0f 帧"
          % (top, want_frames))
    # 出流量只能看趋势，不能拿来定罪：协商码率是上限不是产出。实测同一天 PC 端回环
    # 会话（画面正常、自己不断）的 Sunshine 进程出流也只有 ~2.2 Mbps，协商 16.6 Mbps
    # ——静止桌面 VBR 本来就只有几 Mbps。所以我之前那句"只发出 4.7 Mbps 所以卡在发送
    # 侧"是过度解读，这里改成只打印不判定。
    print("出流量参考   : WLAN 峰 %.1f Mbps / Sunshine 进程峰 %.1f Mbps（仅供参考，不作判据）"
          % (wlan_peak, out_peak))
    if dur > 20:
        print("VERDICT PASS 会话活了 %.1f s 没有自断，这次连接是成功的（对照样本）。" % dur)
        return 0
    if win[3] != "?" and not win[3].startswith("192.168.2.7"):
        print("VERDICT FAIL 手机端会话 %.1f s 自断。主机侧已经没有可用的判据了：FEC 抬升"
              "在健康的回环会话里也一样发生（1336 次/200%%），关键帧又只在 IDR 时打印。"
              "要定性只能看接收端——Moonlight 打开「显示连接质量统计」再连一次，读 ping/"
              "丢包率/已丢弃帧数。" % dur)
        return 1
    if top >= 0.4 * want_frames:
        print("VERDICT FAIL 会话 %.1f s 自断，但编码一路出到第 %d 帧（约 %.0f fps）：主机在"
              "正常产帧送帧，客户端却说没收到画面。没看到 FEC 抬升，说明客户端连零头都没"
              "凑出来。下一步只看接收端：Moonlight 打开「显示连接质量统计」再连一次。"
              % (dur, top, top / max(dur, 0.1)))
        return 1
    print("VERDICT FAIL 会话 %.1f s 自断，但证据不够定方向：既没看到 FEC 抬升，关键帧编号"
          "也没走到下一次 IDR（Debug 只在 IDR 时打印）。别再猜，开 Moonlight「显示连接"
          "质量统计」拿 ping/丢包率/已丢弃帧数。" % dur)
    return 1
    print("VERDICT FAIL 出流 %.1f-%.1f Mbps，够不上协商的 %.0f Mbps：编码在跑但只吐出零头。"
          % (min(wlan_peak, out_peak), max(wlan_peak, out_peak), target / 1e6))
    return 1


def session_windows(events):
    """Every complete CONNECTED->DISCONNECTED pair in the window.

    [(start, end, seconds, peer)] ordered by start. A window can hold several
    sessions (the PC control run overlapped a phone attempt once), so picking
    only the first one reported the wrong client. `peer` comes from the RAISE
    line: 192.168.2.7 is this host talking to itself, anything else is remote.
    """
    out = []
    start = None
    for e in events:
        stamp = e.split(" ")[0]
        if "CLIENT CONNECTED" in e:
            start = stamp
        elif "CLIENT DISCONNECTED" in e and start is not None:
            out.append((start, stamp, 0.0, peer_between(start, stamp)))
            start = None
    from datetime import datetime as DT
    fmt = "%H:%M:%S.%f"
    fixed = []
    for a, b, _d, peer in out:
        try:
            fixed.append((a, b, (DT.strptime(b, fmt) - DT.strptime(a, fmt)).total_seconds(), peer))
        except ValueError:
            continue
    return fixed


def peer_between(start, end):
    """Client address the video channel was raised for inside [start, end]."""
    if not os.path.exists(LOG):
        return "?"
    for line in io.open(LOG, encoding="utf-8", errors="replace"):
        m = re.match(r"\[[\d\-]+ ([\d:.]+)\]: \w+: RAISE: ::ffff:([\d.]+):\d+ :: VIDEO", line)
        if m and start <= m.group(1) <= end:
            return m.group(2)
    return "?"


def session_window(events):
    """(start_hms, end_hms, seconds) from the first CONNECTED/DISCONNECTED pair,
    None if the pair never completed inside the window."""
    start = end = None
    for e in events:
        stamp = e.split(" ")[0]
        if "CLIENT CONNECTED" in e and start is None:
            start = stamp
        elif "CLIENT DISCONNECTED" in e and start is not None:
            end = stamp
            break
    if not (start and end):
        return None
    from datetime import datetime as DT
    fmt = "%H:%M:%S.%f"
    dur = (DT.strptime(end, fmt) - DT.strptime(start, fmt)).total_seconds()
    return start, end, dur


LOG_LEVELS = {"verbose": 0, "debug": 1, "info": 2, "warning": 3,
              "error": 4, "fatal": 5, "none": 6}


def set_log_level(value):
    """Write (or with value=None remove) `min_log_level` in sunshine.conf.

    Assert-before-write: the new text is validated in memory before anything
    touches the file, so a bug here can never leave a 0-byte conf behind.
    LF and no BOM -- Sunshine reads a BOM as part of the first key name.
    The Web UI stores this as a number (0=verbose .. 6=none), so names are
    mapped rather than written verbatim.
    """
    raw = open(CONF, "rb").read()
    if raw.startswith(b"\xef\xbb\xbf"):
        print("VERDICT FAIL conf 带 BOM，先修掉再改（address_family 会被读成乱码键）")
        return 1
    txt = raw.decode("utf-8", "replace")
    lines = [l for l in txt.split("\n")
             if not re.match(r"^\s*min_log_level\s*=", l)]
    if value is not None:
        level = LOG_LEVELS[value]
        lines.insert(0, "min_log_level = %d" % level)
    new = "\n".join(lines).rstrip("\n") + "\n"
    if value is not None:
        assert new.startswith("min_log_level = %d\n" % level), "写入内容不含新键"
        assert "address_family" in new, "写入内容丢了 address_family"
    assert len(new) > 20, "新内容短得可疑，拒绝写入"
    with io.open(CONF, "w", encoding="utf-8", newline="\n") as f:
        f.write(new)
    print("conf 现在:", new.replace("\n", " | ")[:160])
    return None


def elevate(argv):
    """Re-run this script elevated through UAC and show what it printed.

    A generated .bat keeps the quoting honest -- nesting quotes through
    Start-Process -ArgumentList is where this usually breaks.
    """
    import tempfile
    out = os.path.join(tempfile.gettempdir(), "streamcheck_elevated.txt")
    bat = os.path.join(tempfile.gettempdir(), "streamcheck_elevated.bat")
    for p in (out, bat):
        if os.path.exists(p):
            os.remove(p)
    with io.open(bat, "w", encoding="mbcs", newline="") as f:
        f.write("@echo off\r\nset PYTHONIOENCODING=utf-8\r\n")
        f.write('"%s" %s > "%s" 2>&1\r\n'
                % (sys.executable, " ".join('"%s"' % a for a in argv), out))
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Start-Process -FilePath '%s' -Verb RunAs -Wait" % bat],
                   capture_output=True)
    txt = io.open(out, encoding="utf-8", errors="replace").read() if os.path.exists(out) else ""
    print(txt.rstrip())
    if not txt:
        print("（提权窗口没有产出——要么 UAC 被取消，要么 python 路径不对）")
        return 2
    for p in (out, bat):
        try:
            os.remove(p)
        except OSError:
            pass
    return 0 if "VERDICT PASS" in txt else 1


def orphans():
    """sunshine/sunshinesvc processes still alive -- after `net stop` the image
    can stay held by an orphan, which is what makes `net start` fail with
    system error 32 (hit twice now, so the restart path clears them)."""
    txt = ps("Get-Process -ErrorAction SilentlyContinue | Where-Object { "
             "$_.ProcessName -match '^(sunshine|sunshinesvc)$' } | "
             "ForEach-Object { $_.ProcessName + ':' + $_.Id }")
    return [o for o in txt.split() if o]


def clear_orphans(wait=90):
    left = orphans()
    if not left:
        return True
    print("残留进程     :", " ".join(left), "-- 清理后重试")
    for entry in left:
        pid = entry.split(":")[1]
        # /IM cannot hit this kind of process (taskkill then lies with "没有此
        # 任务的实例在运行"), so go at it by PID, then by Stop-Process. If even
        # that does not take, the process is blocked in a kernel call and can
        # only be waited out -- the 90s budget is from watching that happen.
        for cmd in (["taskkill", "/PID", pid, "/T", "/F"],
                   ["powershell", "-NoProfile", "-Command",
                    "Stop-Process -Id %s -Force -ErrorAction Continue" % pid]):
            p = subprocess.run(cmd, capture_output=True)
            msg = (p.stdout.decode("gbk", "replace")
                   + p.stderr.decode("gbk", "replace")).strip().replace("\r\n", " ")
            print("  %-14s rc=%d : %s" % (cmd[0], p.returncode, msg[:110] or "(无输出)"))
    for i in range(wait):
        time.sleep(1)
        if not orphans():
            print("  等 %d s 后进程已消失" % (i + 1))
            return True
    print("  等 %d s 仍在（内核调用没返回，杀不动）" % wait)
    return False


def restart_service(wait_stop=30):
    """Stop then start with backoff: `net stop` straight into `net start` hits
    system error 32 while Windows still holds the image (measured twice)."""
    if not is_admin():
        print("VERDICT FAIL 重启服务需要管理员（由 main() 统一提权，别直接调这里）")
        return 2
    print("停止:", sh(["net", "stop", "SunshineService"]).strip().replace("\r\n", " ")[:80])
    for _ in range(wait_stop):
        time.sleep(1)
        if ps("(Get-Service SunshineService).Status") == "Stopped":
            break
    ok = False
    budget = 90
    for attempt in range(1, 11):
        # error 32 is "another process is using the file": wait it out, and if
        # waiting does not help, clear the orphan holding the image. A process
        # entry that refuses to die does NOT prove the image is still locked,
        # so keep trying to start and let the return code say who is right.
        time.sleep(10 if attempt == 1 else 8)
        clear_orphans(wait=budget)
        budget = 15                      # first round gets the long wait, not all ten
        out = sh(["net", "start", "SunshineService"]).strip().replace("\r\n", " | ")
        ok = "mmand completed" in out or "成功" in out
        print("启动 第 %d 次: %s" % (attempt, out[:90]))
        if ok and ps("(Get-Service SunshineService).Status") == "Running":
            break
        ok = False
    time.sleep(12)
    tcp, _ = listeners()
    up = sorted({p for p, _ in tcp if p in TCP_PORTS})
    print("服务状态     :", ps("(Get-Service SunshineService).Status"))
    print("TCP 监听     :", ", ".join(map(str, up)) or "(无)")
    log_head = ""
    if os.path.exists(LOG):
        lines = io.open(LOG, encoding="utf-8", errors="replace").read().splitlines()
        log_head = " | ".join(l for l in lines[-40:]
                              if "min_log_level" in l or "Unrecognized" in l)[:200]
    if log_head:
        print("日志回读     :", log_head)
    if ok and len(up) == len(TCP_PORTS):
        print("VERDICT PASS 服务已重启，四个端口齐全")
        return 0
    print("VERDICT FAIL 服务没真正起来")
    return 1


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return os.geteuid() == 0 if hasattr(os, "geteuid") else False


def fix_service(wait=25):
    """Recover from the zombie state you get by quitting Sunshine from the tray
    while it runs as a Windows service: SCM still says Running, but the process
    is stuck mid-shutdown and holds the files, so nothing listens and `net start`
    does nothing at all.
    """
    if not is_admin():
        print("fix-service 需要管理员（要 taskkill 服务进程并 net start）")
        return 2
    print("当前状态     :", ps("(Get-Service SunshineService).Status"))
    print("卡住的进程   :", ps("Get-Process -ErrorAction SilentlyContinue | "
                              "Where-Object { $_.ProcessName -match "
                              "'^(sunshine|sunshinesvc)$' } | ForEach-Object { "
                              "$_.ProcessName + ':' + $_.Id }").replace("\r\n", " ")
          or "(无)")
    ps("Stop-Service SunshineService -Force -ErrorAction SilentlyContinue")
    for img in ("sunshinesvc.exe", "sunshine.exe"):
        p = subprocess.run(["taskkill", "/IM", img, "/F"], capture_output=True)
        msg = (p.stdout.decode("gbk", "replace")
               + p.stderr.decode("gbk", "replace")).strip().replace("\r\n", " ")
        print("  taskkill %-18s rc=%d : %s" % (img, p.returncode, msg[:90]))
    still = ps("Get-Process -ErrorAction SilentlyContinue | Where-Object { "
               "$_.ProcessName -match '^(sunshine|sunshinesvc)$' } | "
               "ForEach-Object { $_.ProcessName + ':' + $_.Id }").replace("\r\n", " ")
    print("强杀后残留   :", still or "(无)")
    # wait for SCM to notice the process is gone, otherwise it stays "Running"
    for _ in range(wait):
        time.sleep(1)
        if ps("(Get-Service SunshineService).Status") == "Stopped":
            break
    print("复位后状态   :", ps("(Get-Service SunshineService).Status"))
    # After a force-kill Windows holds the image a while; starting too soon dies
    # with system error 32 ("another process is using this file"). Back off and
    # retry instead of giving up on the first attempt.
    ok = False
    out = ""
    for attempt in range(1, 8):
        time.sleep(8 if attempt == 1 else 10)
        p = subprocess.run(["net", "start", "SunshineService"],
                           capture_output=True)
        out = (p.stdout.decode("gbk", "replace")
               + p.stderr.decode("gbk", "replace")).strip().replace("\r\n", " | ")
        ok = p.returncode == 0
        print("启动 第 %d 次 rc=%d : %s" % (attempt, p.returncode, out[:100]))
        if ok:
            break
    time.sleep(12)
    tcp, _ = listeners()
    up = {p for p, _ in tcp if p in TCP_PORTS}
    print("TCP 监听     :", ", ".join(str(p) for p in sorted(up)) or "(无)")
    if len(up) == len(TCP_PORTS):
        print("VERDICT PASS 服务已恢复，四个端口齐全")
        return 0
    print("VERDICT FAIL 端口不齐，服务没真正起来")
    return 1


def hung_session():
    """True when the last session's teardown never finished.

    A clean teardown reads `Waiting for main video thread to end...` and then
    `All broadcasting threads ended`. The phone session of 20:40:31 stopped at
    the first line and never got to the second -- Sunshine's video thread hung,
    and from then on NO client could connect (he tried PC Moonlight right after
    and it failed). Testing against such a host gives fake failures, so this is
    a gate, not a footnote.
    """
    if not os.path.exists(LOG):
        return False
    txt = io.open(LOG, encoding="utf-8", errors="replace").read()
    i = txt.rfind("Waiting for main video thread to end")
    if i < 0:
        return False
    return "All broadcasting threads ended" not in txt[i:]


def main():
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", metavar="PATH",
                    help="分析指定的 sunshine 日志文件（默认 sunshine.log；每次启动会被清空，"
                         "刚跑完的那几场往往已经滚动到 sunshine.log.1）")
    ap.add_argument("--watch", type=int, metavar="SEC",
                    help="采样 N 秒，期间在手机点连接，结束给判定")
    ap.add_argument("--pause-checked", action="store_true",
                    help="已人工确认 Sunshine 不是暂停状态（配合 --watch 使用）")
    ap.add_argument("--fix-service", action="store_true",
                    help="从托盘退出导致的僵尸态里恢复服务（需管理员）")
    ap.add_argument("--restart-service", action="store_true",
                    help="普通重启服务：net stop -> 退避 -> net start，并回读端口（需管理员）")
    ap.add_argument("--loglevel", metavar="LEVEL",
                    help="把 min_log_level 写进 conf 并重启（debug/verbose/info，off 删除该键）")
    ap.add_argument("--sessions", action="store_true",
                    help="逐场会话并排对比（对端/时长/清理是否挂死/协商参数/抓取的是哪块屏）")
    ap.add_argument("--where", action="store_true",
                    help="判定手机实际看到的是哪块屏（配置声称 vs 日志实测，出 VERDICT）")
    ap.add_argument("--refresh", metavar="HZ",
                    help="show 列出各屏当前/可选刷新率；数字=把主屏临时改成该 HZ（不写注册表）")
    a = ap.parse_args()
    if a.log:
        LOG = a.log
    if a.where:
        return where_report()
    if a.sessions:
        return session_report()
    if a.refresh:
        return set_refresh(a.refresh)
    if a.fix_service:
        if not is_admin():
            print("需要管理员（taskkill + net start），走 UAC 提权重跑……")
            return elevate([os.path.abspath(__file__), "--fix-service"])
        return fix_service()
    if a.restart_service or a.loglevel:
        if not is_admin():
            # Program Files is not writable and net stop/start needs it too,
            # so the whole edit+restart goes through one UAC prompt.
            argv = [os.path.abspath(__file__)]
            if a.loglevel:
                argv += ["--loglevel", a.loglevel]
            argv.append("--restart-service")
            print("需要管理员（写 conf + 重启服务），走 UAC 提权重跑……")
            return elevate(argv)
        if a.loglevel:
            name = a.loglevel.lower()
            if name in ("off", "remove", "default"):
                v = None
            elif name in LOG_LEVELS:
                v = name
            else:
                print("日志级别不认识：%s（可选 %s）" % (a.loglevel, "/".join(LOG_LEVELS)))
                return 2
            r = set_log_level(v)
            if r:
                return r
        return restart_service()
    report_static()
    if a.watch:
        return watch(a.watch, a.pause_checked)
    print("\n（静态体检看不到会话期间的证据。要抓真凭据就跑："
          "python streamcheck.py --watch 60）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
