"""Sunshine / Moonlight 串流链路体检.

为什么需要它：这类问题的证据只在"会话那十几秒"里存在（UDP 通道是否齐全、
视频到底有没有真的发出去），事后翻日志看不出来。手动敲命令采样的结果是
采样窗口和点击时机对不上，白测一轮。所以这里把采集和判定都固化下来。

用法：
    python streamcheck.py                # 静态体检，立刻出结论
    python streamcheck.py --watch 60     # 开始采样，这 60 秒内去手机点连接

退出码：0 = PASS，1 = FAIL，2 = 没采到会话（需要重跑 --watch）。
判定打印在最后一行，机器可读。
"""
import argparse
import io
import os
import re
import socket
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


def last_bitrate():
    if not os.path.exists(LOG):
        return None
    hits = re.findall(r"Streaming bitrate is (\d+)",
                      io.open(LOG, encoding="utf-8", errors="replace").read())
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
    print("output_name  :", c["output_name"] or "(未设 -> 抓主屏，跟随系统显示模式)")
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
    print("日志最近事件 :")
    for e in log_events("1970-01-01")[-6:]:
        print("   ", e)


# -------------------------------------------------------------------- watch
def wlan_tx(prev, dt):
    """(mbps, new counter) from the OS interface counter. Seed once with the
    absolute value, otherwise the first sample reports the whole uptime."""
    row = ps("(Get-NetAdapterStatistics -Name WLAN).SentBytes")
    m = re.search(r"\d+", row)
    n = int(m.group(0)) if m else prev
    return max(0.0, (n - prev) * 8.0 / 1e6 / max(dt, 0.001)), n


def watch(seconds, pause_checked):
    if not pause_checked:
        print("拒绝开始采样：我无法自动判断 Sunshine 是否处于暂停。")
        print("  paused 不写日志、不写配置；mTLS 读 serverstatus 需要配对客户端证书，")
        print("  Web UI 的 /api/state 需要登录密码。两条都没有，所以只能人工确认。")
        print("  看一眼托盘或 Web UI 首页，确认不是暂停状态，再加 --pause-checked 重跑。")
        return 2
    target = None
    bitrate = last_bitrate()
    if bitrate:
        target = bitrate
        print("参照码率（日志里最近一次）: %.1f Mbps" % (target / 1e6))
    print("开始采样 %d 秒——现在去手机上点连接。" % seconds)
    t0 = time.time()
    prev_tx = wlan_tx(0, 1.0)[1]          # seed with the absolute counter
    last_t = t0
    connected = False
    seen_udp = set()
    peak = 0.0
    events = []
    base = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t0))
    while time.time() - t0 < seconds:
        _, udp = listeners()
        seen_udp |= {p for p, _ in udp if p in UDP_PORTS}
        now = time.time()
        mbps, prev_tx = wlan_tx(prev_tx, now - last_t)
        last_t = now
        peak = max(peak, mbps)
        for e in log_events(base):
            if e not in events:
                events.append(e)
                print("  " + e)
                if "CONNECTED" in e and "DISCONNECTED" not in e:
                    connected = True
        time.sleep(0.25)
    print("-" * 56)
    print("采到会话     :", "是" if connected else "否")
    print("UDP 通道峰值 :", sorted(seen_udp) or "(从未出现)")
    print("WLAN 发送峰值: %.1f Mbps" % peak)
    if not connected:
        print("VERDICT FAIL 窗口内没有会话发生。按概率排序：Sunshine 处于暂停（最常见，")
        print("  且服务状态仍显示 Running，两者互不矛盾）、地址不对、或根本没点。")
        return 2
    if len({47998, 47999, 48000} & seen_udp) < 3:
        print("VERDICT FAIL UDP 47998/47999/48000 没有全部建立：主机侧网络栈问题。")
        return 1
    if target and peak < target * 0.1:
        print("VERDICT FAIL 三个 UDP 口都建了，但发送峰值 %.1f Mbps 远低于码率 "
              "%.1f Mbps：主机没把视频帧推出去，卡在抓帧->编码这一段。"
              % (peak, target / 1e6))
        return 1
    print("VERDICT PASS 主机确实在按码率推流；若手机仍无画面，问题在下行链路或手机端解码。")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", type=int, metavar="SEC",
                    help="采样 N 秒，期间在手机点连接，结束给判定")
    ap.add_argument("--pause-checked", action="store_true",
                    help="已人工确认 Sunshine 不是暂停状态（配合 --watch 使用）")
    a = ap.parse_args()
    report_static()
    if a.watch:
        return watch(a.watch, a.pause_checked)
    print("\n（静态体检看不到会话期间的证据。要抓真凭据就跑："
          "python streamcheck.py --watch 60）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
