# Sunshine + Moonlight 手机远控电脑配置指南

> **关于本文档里的地址**：公开发布版已把所有真实 IP、MAC、账号与密码换成示例值（`100.64.1.x`、`192.168.2.10x`、`<尖括号占位符>`）。方法、端口、参数和踩坑结论均属实，照做即可；具体地址请用自己机器上 `ipconfig` / `tailscale ip` 的实测值。

> 针对本机配置定制：Windows 10 专业版 (19045) / AMD RX 7800 XT / Ryzen 5 7500F / 32GB
> 生成日期：2026-09-08

---

## ⚠️ 先分清是哪台机器（2026-10-12 补充，非常重要）

这个串流项目有**两台机器**，方案不同、坑不同，历史上已经混过一次。

| | **台式主机**（本文档主体） | **笔记本**（另一套方案） |
|---|---|---|
| Tailscale | `100.64.1.10` | `100.64.1.20`（名 `node`） |
| 主机名 | `<你的主机名>` / `<主机设备名>` | — |
| EasyTier | `.2`（<主机设备名>） | `.4`（<笔记本设备名>） |
| 角色 | **Sunshine 主机**（被串流） | **Moonlight 客户端** + 自建 VDD 扩展屏 |
| 虚拟屏方案 | Parsec VDD（`C:\ParsecVDD-KeepAlive\`）—— **2026-10-12 已拆除** | MttVDD（`C:\VDD\install-vdd.ps1`）—— 仍在使用 |
| 虚拟屏用途 | 顶替物理屏，让关机后仍能串流 | 给手机当**扩展屏**（非镜像） |
| Sunshine 版本 | `2026.906.222525` | `2026.914.233613` |
| 显示器 | P2710V 3840x2160 @160Hz | 笔记本内屏 |

**易混淆点**：Moonlight 列表里「航」= 笔记本自己的 Sunshine；`<你的主机名>` 才是这台台式主机。**两台都装了 Sunshine。**

- 台式主机方案 → 本文档第 1~10 章 + 第 8 章（虚拟屏，已废弃）
- 笔记本扩展屏方案 → 见本文档**第 11 章**
- 跨网通道（Tailscale / EasyTier）→ 见**第 6 章** + 第 11 章拓扑表

---

## 📋 方案总览（一页看懂）

### 一句话

电脑上跑 **Sunshine** 当主机、手机装 **Moonlight** 当客户端，中间用 **Tailscale** 打通外网；
再靠一个 **虚拟显示器** 解决"关掉物理显示器就没画面"的问题。

### 架构图

```
      手机（Moonlight）                        电脑（Sunshine 主机）
   ┌──────────────────┐                  ┌──────────────────────────────────┐
   │   Moonlight      │                  │  SunshineService（系统服务）      │
   │   荣耀 Magic8     │ ◄─── 串流 ─────► │    ├─ AMF 硬件编码 hevc_amf      │
   └────────┬─────────┘    H.265        │    ├─ DXGI 抓屏                  │
            │              ~31 Mbps      │    └─ DDX 显示管理               │
            │                           │                                  │
            │   Tailscale 加密隧道        │   ┌────────────────────────────┐ │
            └──── IPv6 直连 19ms ────────┼───┤ 物理显示器 P2710V  4K@160  │ │
                 （非中继）                │   │ Parsec 虚拟显示器   2K@60  │★│
                                          │   └────────────────────────────┘ │
                                          │        ▲                         │
                                          │        │ 保活进程每 70ms ping     │
                                          │   C:\ParsecVDD-KeepAlive\        │
                                          └──────────────────────────────────┘
```

### 五个组成部分（2026-10-12 更新）

| # | 组件 | 作用 | 位置 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | **Sunshine** | 主机端串流服务 | `C:\Program Files\Sunshine\` | ✅ 运行中，开机自启 |
| 2 | **Moonlight** | 手机端播放器 | 手机 App | ✅ 已配对 |
| 3 | **Tailscale** | 外网访问的加密隧道 | 系统服务 + 手机 App | ✅ 可用 |
| 4 | ~~Parsec VDD 虚拟显示器~~ | ~~物理屏关掉后顶替它~~ | `mm.inf` 官方签名驱动 | ❌ **已拆除（2026-10-12）** |
| 5 | ~~保活守护进程~~ | ~~每 70ms ping 驱动~~ | `C:\ParsecVDD-KeepAlive\` | ❌ **已停止并删除自启** |

> **第 4、5 项已于 2026-10-12 拆除**，原因见第 8 章（与 Sunshine 的
> `ensure_only_display` 结构性互斥，导致虚拟屏永久建不起来）。
> **现在的模式：Sunshine 直接抓物理显示器，物理屏必须常开（不能断电）。**
> 驱动仍保留安装，想恢复随时可以。

### 关键参数（2026-10-12 更新）

| 项目 | 值 |
| --- | --- |
| 电脑局域网 IP | `192.168.2.101`（WLAN，DHCP 分配，**会变**；同 Wi-Fi 时用自动扫描添加，别手填这个） |
| 电脑 Tailscale IP | `100.64.1.10`（另有 IPv6 `fd7a:<Tailscale ULA>`） |
| 手机 Tailscale IP | `100.64.1.30` |
| Sunshine Web UI | `https://localhost:47990` |
| 编码器 / 码率 | `hevc_amf` / 约 31 Mbps |
| 延迟 | 同网段局域网直连最低；跨网走 EasyTier IPv6 直连 28ms（见第 6 章） |
| 物理显示器 | `\\.\DISPLAY1`　**3840x2160 @160Hz @200% 缩放** |
| 物理屏 device_id | `{2bdc1e09-1701-5f00-9100-e77eacc6e2aa}`（稳定 GUID，取法见第 11.2 节） |
| ~~虚拟显示器~~ | ~~`\\.\DISPLAY22` 2560x1440 @60Hz~~ → 已拆除 |

### 日常怎么用（2026-10-12 更新）

1. **电脑开机** → Sunshine 自动就绪，不用任何操作
2. **手机打开 Moonlight** → 点电脑名字 → 连上就能看到桌面
3. **物理显示器保持常开**（可以待机，但**不要按电源键断电** —— 现在没有虚拟屏顶替它了）
4. **不需要任何显示器切换操作** —— 不再有虚拟屏抢桌面这回事
5. 若发现缩放/刷新率跑偏 → 双击桌面 `恢复显示器配置.bat`（见第 8 章后的「显示模式不还原」节）

### 出问题先查这三处（2026-10-12 更新）

| 症状 | 先查什么 |
| --- | --- |
| 连不上 | Tailscale / EasyTier 是否在线；Sunshine 服务是否在跑（`SunshineService`） |
| 连上黑屏 | 物理显示器是否被断电了；`dxgi-info.exe` 看 `\\.\DISPLAY1` 是否 `AttachedToDesktop: yes` |
| 能连但卡顿 | 手机端码率；路径是否掉到中继（看第 6 章判定方法） |
| **串流后缩放/刷新率不对** | 跑桌面 `恢复显示器配置.bat`，并**注销重登**（第 8 章后的专节） |

### 章节索引

| 想要什么 | 看哪节 |
| --- | --- |
| **搞清哪台机器是哪套方案** | **文首「先分清是哪台机器」** |
| 装 Sunshine、Web UI 设置、A 卡编码器 | 第 0~3 章 |
| 手机配对、画质参数调校 | 第 4~5 章 |
| 在外面也能连（Tailscale / IPv6 / EasyTier） | 第 6 章 |
| 远程自动开机（智能插座 / WoL） | 第 7 章 |
| ~~关掉显示器还能串流~~ | 第 8 章（**已废弃**，存档） |
| **串流后缩放/刷新率跑偏怎么修** | **第 8 章后的「显示模式不还原」节** |
| 出问题排查 | 第 9 章 |
| 硬件能玩到的上限（AV1 等） | 第 10 章 |
| **笔记本用 VDD 给手机做扩展屏** | **第 11 章** |
| 两台机器的网络拓扑与通道 | 第 11 章前的「跨网拓扑」节 |

---

## ✅ 本机实测验收结果（2026-09-08 已跑通）

| 项目 | 实测结果 |
| --- | --- |
| Sunshine 版本 | v2026.906.222525 |
| 服务状态 | `SunshineService` 运行中，开机自动启动 |
| 监听端口 | 47984 / 47989 / 47990 / 48010 四个全部正常 |
| Web 管理界面 | `https://localhost:47990` 返回 HTTP 200，可访问 |
| **AMF 编码器** | **H.264 ✅ + HEVC ✅ + AV1 ✅ 三个全部识别成功** |
| 防火墙 | Sunshine 安装程序已自动添加程序级放行规则（TCP+UDP 全端口），**不用手动加** |
| 屏幕捕获 | 3840x2160（4K） |
| **本机局域网 IP** | **`192.168.2.102`**（WLAN，DHCP 分配，光猫重分租约会变，**不要拿它当固定配对地址**） |
| HAGS（硬件加速 GPU 调度） | 已禁用 —— A 卡下这是正常状态，编码器工作正常，**不要去开** |

日志原文（证明 AMF 真的被识别了）：
```
Info: Found H.264 encoder: h264_amf [amdvce]
Info: Found HEVC encoder: hevc_amf [amdvce]
Info: Found AV1  encoder: av1_amf  [amdvce]
```

### 最终联调结果（2026-09-08 11:01 全部跑通）

| 项目 | 结果 |
| --- | --- |
| 手机 Tailscale | `100.64.1.30`，**active; direct** |
| 连接方式 | **IPv6 直连，未走中继** |
| 延迟 | **19 ms** |
| 串流编码器 | `hevc_amf`（HEVC + AMF，A 卡最优解） |
| 捕获分辨率 | 3840x2160 @ 160Hz → 输出 60fps |
| 码率 | 约 31 Mbps（局域网/同网场景） |
| 色彩 | SDR / Rec.709 / 8-bit，HDR 已关闭 ✅ |
| 音频 | Opus 48kHz 立体声，虚拟声卡正常 |

**Tailscale 打洞成功没有落到中继** —— 洛杉矶中继是 159ms，直连只要 19ms，差了 8 倍。这是本机有公网 IPv6 + 路由器开 UPnP 带来的好处。

### 现在只差一步：手机配对

1. 手机装 **Moonlight**（官方名 Moonlight Game Streaming）
2. 手机连同一个 Wi-Fi
3. Moonlight 首页等它**自动扫描**出电脑卡片 → 点开 → 电脑 Web UI 弹 4 位 PIN → 手机输入（扫不到才用 `+` 手填当前 IP 作为临时手段）
4. 长按电脑图标进 Settings，按下表改：

| 手机端设置 | 值 |
| --- | --- |
| Resolution | 1080p |
| FPS | 60 |
| Video bitrate | **无线网络 20~25 Mbps**（插网线后可拉到 50） |
| Video codec | HEVC（卡就换 H.264） |
| HDR | 关 |
| Touch mode | Trackpad（相对模式） |

> **提醒**：你这是 4K 屏捕获 + 无线传输。如果觉得卡，第一个该降的是手机端分辨率而不是码率。

---

## 0. 先记住三个和 N 卡教程不一样的地方

| 项目 | 网上通用教程（N卡） | 你的情况（A卡 7800 XT） |
| --- | --- | --- |
| 编码器 | NVENC | **AMF**（RDNA3，支持 H.264 / HEVC / AV1 编码） |
| 安装包 | Sunshine-xxx.exe | **只有 .msi** —— 新版已废弃 exe 安装包 |
| 色彩 | 提 NVENC 的 4:4:4 | AMF 对 4:4:4 支持有限，靠**拉高码率**保清晰 |

---

## 1. 电脑端：安装 Sunshine

最新版 **v2026.906.222525**（2026-09-06 发布）

下载地址（AMD64 也就是你的 x64 机器）：

```
https://github.com/LizardByte/Sunshine/releases/download/v2026.906.222525/Sunshine-Windows-AMD64-installer.msi
```

GitHub 下载慢的话，去 LizardByte 官方下载页或用镜像加速。

安装时注意：

- **右键 → 以管理员身份运行**，否则服务注册会失败
- 一路 Next 即可，装完会自动注册成 Windows 服务（开机自启）
- 装完浏览器会自动打开 `https://localhost:47990`，**证书警告点「高级 → 继续访问」**，这是自签证书，正常

### 设置管理员账号密码

第一次打开 Web UI 会要求设置 Sunshine 自己的账号密码（**不是 Windows 密码，但要记牢**，忘了只能删配置文件重来）。

---

## 2. Web UI 关键设置（Configuration → Video）

装完先进 `https://localhost:47990` → 右上角 **Configuration** → **Video** 标签页。

按下表改，其余保持默认：

| 设置项 | 建议值 | 说明 |
| --- | --- | --- |
| **Encoder** | `amf` | 新版通常自动识别成 AMF。若显示 `n/a` 或空白 = 显卡驱动没装好，去装最新 Adrenalin |
| **Codec** | `HEVC`（主用）/ `H.264`（备用） | HEVC 省带宽、同码率画质更好；连不上再退回 H.264 |
| **Bitrate** | 局域网 `50~80 Mbps`，外网 `20~30 Mbps` | 你是设计用途，别省码率，这是清晰度的主要来源 |
| **FPS** | `60` | 静态看稿 30 也够，但鼠标拖动的顺滑感 60 差很多 |
| **Resolution** | 默认（跟随手机） | 手机端单独设更方便 |
| **HDR** | **关** | 开了会触发色彩映射，看设计稿色偏，别开 |

改完点 **Save**，页面右上角会提示要重启 Sunshine 才生效 → 点 **Apply / Restart**。

### 找不到 Encoder 选项？

新版 Sunshine 部分版本把编码器选择移到 `Advanced` 或按应用单独配。找不到就别动，**让 Sunshine 自动选**，A 卡环境下它默认就是 AMF。

### AMF 初始化失败（黑屏 / 报错 "Failed to initialize encoder"）

按以下顺序排查：

1. 显卡驱动版本低于 23.x 必挂 → 装最新 Adrenalin（你当前 32.0.31007.1017，够新）
2. 关闭 Windows HDR：设置 → 系统 → 显示 → 关闭 HDR
3. 把 Codec 从 HEVC 换成 H.264 试一次（HEVC AMF 偶发不稳）
4. 任务管理器确认没有其他程序独占编码器（OBS、直播软件、录制工具抢 AMF）

---

## 3. 防火墙放行端口

Windows 防火墙会拦掉 Sunshine。**以管理员身份**打开 PowerShell，一次跑完：

```powershell
New-NetFirewallRule -DisplayName "Sunshine-TCP" -Direction Inbound -Protocol TCP -LocalPort 47984-48010 -Action Allow -Profile Any
New-NetFirewallRule -DisplayName "Sunshine-UDP" -Direction Inbound -Protocol UDP -LocalPort 47984-48010 -Action Allow -Profile Any
```

端口用途（方便你看日志）：

| 端口 | 用途 |
| --- | --- |
| 47989 TCP/UDP | 控制信令 |
| 47990 TCP | Web 管理界面（HTTPS） |
| 48010 TCP/UDP | RTSP 串流协商 |
| 47998 / 47999 / 48000 UDP | 音视频数据流 |

> 只在局域网用的话，把 `-Profile Any` 改成 `-Profile Private` 更安全。

---

## 4. 手机端：安装 Moonlight

Android 端官方名 **Moonlight Game Streaming**，最新版 **v12.1**。

- 优先 Google Play 搜 "Moonlight Game Streaming"
- 装不上就下 APK（非 root 版，6.7 MB）：
  ```
  https://github.com/moonlight-stream/moonlight-android/releases/download/v12.1/app-nonRoot-release.apk
  ```
- 国内商店里的「月光」「Moonlight 中文版」多为旧版改包，功能残缺，不建议

### 连接步骤

1. 手机和电脑连**同一个 Wi-Fi**（首次配对必须同网）
2. 打开 Moonlight → **优先用自动扫描出来的电脑卡片**添加主机（走 mDNS，每次连接重新解析，电脑换 IP 会自动跟上）；只有扫描不出来时才点右上角 `+` 手填局域网 IP
3. 电脑 Web UI 会弹出 4 位 PIN → 在手机输入配对
4. 配对成功，直接连

**连不上先查电脑 IP**：PowerShell 跑 `ipconfig`，找 IPv4 地址（一般是 192.168.x.x）。

### 三种主机条目的可靠性（2026-10-10 血泪补充）

| 加法 | 电脑换局域网 IP 后会怎样 | 适用 |
| --- | --- | --- |
| **自动扫描卡片（mDNS）** | **自动跟上**，每次连接重新解析 | 在家同 Wi-Fi，首选 |
| `+` 手填局域网 IP | **冻结成字符串，永久失效**，得手动编辑 | 只当临时救急 |
| `+` 手填 Tailscale IP | 不受局域网变化影响（tailnet 地址固定） | 出门首选 |

踩坑记录：2026-10-09 手机突然"看不到本机"，原因不是 Sunshine 挂了、不是防火墙、也不是 Tailscale，而是光猫在 19:43 重分租约时把本机从 `192.168.2.103` 改成了 `192.168.2.102` —— 手机里那条手填的 `.103` 就指向了空地址。

自动扫描能扛住这类漂移，但有两个前提：手机和电脑在**同一二层网段**（不是访客/IoT 网络、路由器没开 AP 隔离），且路由器没过滤 mDNS 组播。想彻底根除，就在光猫做 **DHCP 地址保留**（绑无线网卡 MAC），地址从此不变，三种加法都不会坏。

> 证据边界：本机已实测的是「Windows mDNS 应答 `_googlevirtualprivate._tcp.local` 查询」以及「手填 IP 条目不跟随漂移」；「自动扫描条目会自动跟上新 IP」属于 mDNS 标准行为推断，尚未在手机上实测。

---

## 5. 手机端参数（设计师专用调校）

Moonlight 里长按电脑图标 → **Settings**，按下面改：

| 设置 | 值 | 为什么 |
| --- | --- | --- |
| **Resolution** | 1080p（2K 屏手机可上 1440p） | 手机屏幕小，1080p 已经很锐利，再高浪费带宽 |
| **FPS** | 60 | 拖动、滚动的跟手感 |
| **Video bitrate** | 局域网 30~50 Mbps / 外网 15~25 Mbps | **设计师别压码率**，低码率下 UI 细线和文字会糊成一团 |
| **Video codec** | HEVC | 同码率画质更好；卡顿就换 H.264 |
| **Force YUV 4:4:4** | 试着开 | 消除色度二次采样，文字边缘不发虚。**A 卡 AMF 不一定支持，开了黑屏就关掉** |
| **HDR** | 关 | 同上，避免色偏 |
| **Stretch video to fullscreen** | 按需 | 手机比例和电脑不一致时选一个不别扭的 |
| **Touch → Mouse mode** | 用「Trackpad Mode（相对模式）」 | 绝对模式在远程桌面场景下很难精准点中图标 |

### 操作建议

- 手机上看稿、盯进度：触控板模式 + 双指缩放够用
- 要真干活：配一套**蓝牙键鼠**，Moonlight 支持直连，体验接近本地
- Moonlight 有虚拟按键（返回 / Home / 任务），在侧边栏

### ⚠️ 校色警告

串流画面**永远不能用来判断颜色**。编码压缩 + 手机屏幕色域完全不可控。只能看构图、排版、大关系。要校色回电脑前看。

---

## 6. 外网访问：Tailscale + IPv6

Sunshine 默认只在同一个 Wi-Fi 下可用。要出门在外连，有两个办法。

### 方案 A：Tailscale（主力，稳定）

**装：**

- 电脑：`https://pkgs.tailscale.com/stable/tailscale-setup-latest.exe`（已下载到 `C:\Users\PC\Downloads\tailscale-setup.exe`）
- 手机：Google Play 搜 Tailscale；装不了就下 APK（搜索 "Tailscale apk"）
- **首次登录可能很慢或失败**（协调服务器在境外）——开着代理装和登录，装上以后日常使用不需要代理

**配：**

1. 两端登录**同一个账号**（微软 / Google / GitHub 均可）
2. 电脑端 Tailscale 分到一个 `100.x.x.x` 地址，**这个地址是永久固定的**
3. Moonlight 点 `+` → 手动填这个 `100.x.x.x` → 手机显示 4 位 PIN → 回电脑 Web UI 输入 → 配对完成

**关键建议：出门用的那条主机填 Tailscale IP；在家用的那条靠自动扫描，别再手填局域网 IP。**

手填 `192.168.2.x` 是这次断连的根源 —— 它是个冻结的字符串，光猫重分租约就失效。Tailscale 的 `100.x` 地址永久固定，所以只加它也能覆盖两种场景：在家时 Tailscale 会检测到本地网段自动走直连，速度跟局域网一模一样；出门就走加密隧道。代价是**手机必须先确认 Tailscale 是 Connected**，否则在家反而连不上（2026-10-09 就卡在这：手机 Tailscale 掉线 2 天，只剩中继路径）。自动扫描那条不依赖 Tailscale，在家更稳。

**出门用的流程：**

1. 手机先开 Tailscale，确认状态是 **Connected**（这一步最容易忘）
2. 再开 Moonlight，点那个 `100.x` 的主机
3. 结束

> 外网码率降到 **15~25 Mbps**，移动网络扛不住局域网那套 50 Mbps。

### 方案 B：IPv6 直连（提速备选）

**本机实测有公网 IPv6**（电信 `240e:` 段）：

```
240e:xxxx:xxxx:xxxx:<EUI-64 接口 ID，由 MAC 派生>    ← 这个含 fffe，是 EUI-64 稳定地址
240e:xxxx:xxxx:xxxx:<临时隐私地址>    ← 临时隐私地址，会变，别用
240e:xxxx:xxxx:xxxx:<临时隐私地址>    ← 临时隐私地址，会变，别用
```

如果你的手机流量也有 IPv6（现在 4G/5G 基本都有），可以**绕过 Tailscale 直接连**，速度取决于移动网络直连质量，通常比走境外中继快。

在 Moonlight 里手动添加上面那个**稳定地址**（第一个）。

**三个前提，缺一不可：**

1. 手机所在网络必须有 IPv6 —— 连的 Wi-Fi 不支持就作废，只能用方案 A
2. 电信 IPv6 前缀会变（重拨后可能换），变了就得重新查地址，长期用建议配 DDNS
3. 运营商可能封入站端口 —— 测试方法：在外面用手机浏览器访问 `https://[你的IPv6]:47990`，能打开就说明没封

### 怎么判断 Tailscale 走的是直连还是中继

电脑端 PowerShell 跑：

```powershell
tailscale status
tailscale ping 手机的100.x地址
```

- 显示 `direct` = 直连，延迟低，恭喜
- 显示 `relay "xxx"` = 走了 DERP 中继，慢，这时候试试方案 B 的 IPv6 直连

两端都有 IPv6 时，Tailscale 打洞成功率很高，多半能直连。

---

## 7. 无人值守 / 远程唤醒

### 先搞清一个致命前提

**电脑一旦关机或睡眠，Tailscale 也跟着断。** 手机在外面就没有任何通道把"开机"这个指令送进你家局域网。

所以"远程开机"从来不是单个设置，而是**两段链路**：

```
手机（外面）──如何把信号送进家里──▶ 家里网络 ──如何让主板通电──▶ 电脑开机
                    ↑ 这段才是真正的难点
```

WoL（网络唤醒）只解决第二段。第一段要靠路由器端口转发，或者另找一条不依赖电脑的通道。下面三个方案的区别主要就在这里。

---

### 方案 A：智能插座（推荐，最省心）

**成本：20~50 元**

原理是绕开 WoL：直接给电脑断电再上电，让主板自己开机。**不需要网线、不需要 WoL、不需要路由器配置、不受快速启动影响。**

**要做的：**

1. 买一个智能插座（小米 / 公牛 / 涂鸦都行），电脑主机插在上面
2. 进 BIOS 找这几项之一，设为开启：
   - `Restore on AC Power Loss` → `Power On`
   - `AC Power Loss` → `Always On` / `Power On`
   - `电源恢复时` → `开机`
3. 用手机插座 App：**断电 → 等 5 秒 → 通电** → 电脑自动启动

**注意**：断电前确保电脑已经**正常关机**（不是强制断电），避免损伤硬盘。所以流程是「远程关机 → 插座断电 → 插座通电 → 开机」。

**为什么推荐**：这是唯一 100% 可靠、且天然支持外网操作的方案。

---

### 方案 B：插网线 + Wake-on-LAN（免费，但坑多）

**必须用有线**，无线网卡基本不支持 WoL。

**要做的（缺一不可）：**

1. **插网线**（用你的 Realtek 2.5GbE 口）
2. **BIOS 设置**：
   - `Wake on LAN` / `Power On By PCI-E` / `Resume By LAN` → **Enabled**
   - `ErP Ready` / `ErP` → **Disabled**（开了会切断关机后的网卡供电，WoL 直接失效）
3. **关闭 Windows 快速启动**（最常见的坑，管理员执行）：
   ```powershell
   powercfg /h off
   ```
   快速启动是"混合关机"，会让网卡处于收不到魔包的状态。
4. **网卡高级属性**（设备管理器 → 网络适配器 → Realtek → 属性）：
   - `Wake on Magic Packet` → Enabled
   - `Shutdown Wake-On-Lan` → Enabled
   - `节能以太网` / `Energy Efficient Ethernet` / `Green Ethernet` → **全部 Disabled**
     （这些节能特性是 WoL 失效的头号原因）
5. **电源管理标签页**：勾选「允许此设备唤醒计算机」+「只允许幻数据包唤醒计算机」
6. **给电脑设固定内网 IP**（路由器里做 DHCP 保留，绑定 MAC）
7. **路由器端口转发**：`UDP 9` → 电脑内网 IP。这是让外网魔包能进局域网的关键
8. **配 DDNS**（公网 IP 会变，需要一个域名指向它）
9. 手机装 WoL App（如 "Wake On Lan"），向 `你的DDNS域名:9` 发魔包

**卡点提示**：

- 第 7 步需要路由器支持，且你的宽带要有**公网 IPv4**。本机 netcheck 曾显示一个电信公网段 IPv4（具体地址已略去），大概率满足
- 一般家用路由器不支持 IPv6 端口转发，所以走 IPv6 发魔包这条路基本不通
- 这一整套配下来，任何一个环节没设对都会失败，而且很难排查

---

### 方案 C：向日葵开机棒 / 开机盒子

**成本：约 100 元**

独立小硬件，插网线 + 主板 USB 供电。它自己连向日葵服务器，所以**哪怕电脑完全关机也能收到唤醒指令**——相当于花钱买通了"第一段链路"。

适合不想折腾路由器、又想要 WoL 那种"不用物理断电"体验的人。

---

### 三个方案怎么选

| | 成本 | 要插网线 | 要配路由器 | 外网可用 | 可靠性 |
| --- | --- | --- | --- | --- | --- |
| **A 智能插座** | 20~50 元 | 否 | 否 | ✅ 天然支持 | 最高 |
| **B WoL** | 0 元 | ✅ 必须 | ✅ 必须 | ⚠️ 要端口转发+DDNS | 中，坑多 |
| **C 开机棒** | ~100 元 | ✅ 必须 | 否 | ✅ 天然支持 | 高 |

**给本机的建议**：走方案 A。

顺便说，**网线还是插上**——不为 WoL 也该插，你的 2.5GbE 口空着，串流码率可以从 31 Mbps 拉到 50 Mbps，4K 下细线条明显更干净。这跟用哪个开机方案无关。

---

### 另外两件事（与开机方案无关，但影响远程可用性）

**① 电脑别睡**：已通过脚本设置 `从不睡眠`（`standby-timeout-ac 0`）。

**② 别锁屏**：Sunshine 在锁屏状态推不了流。建议设一个很长的锁屏超时，或直接关掉锁屏。

---

## 8. 关闭显示器后如何继续串流（虚拟显示器）—— ⚠️ 已废弃（2026-10-12）

### 最终结论（2026-10-12 决策）

**虚拟显示器方案已拆除。改用 Sunshine 直接抓物理显示器。**

决策原因：`dd_configuration_option = ensure_only_display` 与虚拟显示器
**结构性互斥**（见下方根因分析），每次手机连上串流都会把虚拟屏拔掉，
保活脚本随即进入无限自愈死循环。该方案自 2026-10-12 07:20 起已实际失效，
但用户毫无感知 —— 说明「关显示器串流」这个能力并没有在被真正使用。

**拆除内容**：

| 项 | 处置 |
|---|---|
| `vdd-keepalive.py` 进程 | 已用官方 `stop` 命令干净退出（同时拔掉虚拟显示器） |
| `vdd-guardian.py` 进程 | 已退出 |
| HKCU Run 自启 ×2 | 已删除（`ParsecVDD-KeepAlive` / `ParsecVDD-Guardian`） |
| 计划任务 / 服务 | 审计确认**无**相关项 |
| Parsec VDD 驱动 | **保留安装**（内核驱动，零成本，想恢复随时能用） |
| `sunshine.conf` 的 `dd_*` | 改为 `disabled`（见桌面 `关掉Sunshine显示管理.bat`） |

**重启后不会复活** —— 四个自启途径（Run / 计划任务 / 服务 / 启动文件夹）
已全部审计干净。

### 代价（必须知道）

**物理显示器不能再按电源键断电。** 必须保持常开（可以只是黑屏/待机状态，
但不能断电）。串流时 Sunshine 直接抓物理显示器。

### 根因分析（为什么必须拆）

`ensure_only_display` 的语义是「只保留我要抓的那个显示器，**禁用其他所有**」。
Sunshine 一开串流就重排显示拓扑，虚拟屏必然被禁用。

**完整证据链（2026-10-12 双日志对齐）**：

```
sunshine.log:
  07:20:24.699  Info: Scheduling display device configuration
  07:20:25.032  Info: Display device configuration applied successfully

vdd-keepalive.log:
  07:20:19        alive - attached virtual displays: 1   ← 正常
  07:20:34        alive - attached virtual displays: 0   ← +9 秒后掉了
  07:20:49        self-heal: DisplaySwitch /external
  07:21:04        alive - attached virtual displays: 0, driver slots: 0
  07:21:34        self-heal: 驱动里没有监视器对象 - 清闩锁重新 ADD
  07:21:34        virtual display added, driver index=0
  ...             无限循环，672 个周期 / 约 2.8 小时
```

**症状识别**：`attached virtual displays: 0` 且 `driver slots reported: 0`
持续出现，同时日志里反复「驱动里没有监视器对象 → 重新 ADD」——
这就是在互殴，不是保活脚本的 bug。

### Sunshine 的能力边界（2026-10-12 三层证据实测）

**结论：官方 LizardByte Sunshine 没有创建虚拟显示器的能力**，只能管理/切换/禁用已有显示设备。

#### 证据 1：二进制扫描（sunshine.exe v2026.906.222525，70 MB）

| 检索项 | 命中 | 说明 |
|---|---|---|
| `zako` / `Zako` | **0** | 无 ZakoVDD 集成代码 |
| `vdd`（小写） | **0** | 无 VDD 驱动代码 |
| `VDD`（大写） | 1 | 仅是文档字符串 `dd_wa_hdr_toggle_delay` 里的 "(VDD)" |
| `iddsample` / `IddSample` | **0** | 无 IddSampleDriver 集成 |
| `virtual_display` / `display_vdd` | **0** | 无虚拟显示模块 |
| `virtual`（全部 150 处 ASCII） | 150 | 全是**输入**（libvirtualhid 手柄/键鼠/触控/笔）、**音频**（virtual sink）、日志标签 `Virtual Desktop :`、Qt/OS/FFmpeg 内部符号 |
| UTF-16LE 字符串 | 28023 条 | `virtual` 相关只有 LIBVIRTUALHID（输入） |
| `headless` | 2 | 都是 x265 参数 `lookaheadless`，非无头模式 |

#### 证据 2：Web UI 配置 schema（assets/web/assets/config-*.js）

`dd_configuration_option` 实际有 **5 个值**（容易漏掉第 2 个）：

| 值 | 官方语义 |
|---|---|
| `disabled` | 不做任何额外配置（**并禁用所有其他 dd_ 选项**） |
| `verify_only` | 只验证显示设备处于活动状态，**不做任何变更** |
| `ensure_active` | 若非活动则激活它 |
| `ensure_primary` | 若非活动则激活并设为主显示器 |
| `ensure_only_display` | 若非活动则激活，**并禁用其他所有显示器** ← 元凶 |

完整显示管理面（Web UI 共 40 个 `dd_*` 键，真实显示相关的）：

```
dd_configuration_option      5 值，见上表
dd_resolution_option         disabled / auto / manual
dd_manual_resolution         配合 manual
dd_refresh_rate_option       disabled / auto / manual
dd_manual_refresh_rate       配合 manual
dd_hdr_option                disabled / auto
dd_wa_hdr_toggle_delay       VDD 用户的 HDR 兼容补丁（0~3000ms）
dd_config_revert_delay       断开后恢复配置的延迟（默认 3000ms）
dd_config_revert_on_disconnect  断开即恢复而非等应用关闭
dd_mode_remapping            请求分辨率/FPS → 实际显示模式重映射
```

全部是「**管理**」，没有一项是「**创建**」。

#### 证据 3：官方文档反向证明

`dd_wa_hdr_toggle_delay` 的官方说明原文：

> "When using **virtual display device (VDD)** for streaming, it might incorrectly
> display HDR color. Sunshine can try to mitigate this issue..."

**这句话本身就是证据** —— Sunshine 专门为「使用第三方 VDD 的用户」准备了一个 HDR 兼容补丁，
说明它明确假设虚拟显示器由用户自己解决，自己不提供。

#### 附带发现：`verify_only` 是比 `disabled` 更温和的选择

| | `disabled` | `verify_only` |
|---|---|---|
| 显示拓扑 | 完全不动 | 完全不动 |
| 其他 dd_ 选项 | **全部禁用** | 仍然生效 |
| 分辨率跟随客户端 | ❌ 不跟随 | ✅ 跟随（`dd_resolution_option = auto`） |
| 物理屏模式被改 | 不会 | **会**（手机请求 1080p 时物理屏切 1080p） |

**已交付的 bat 设的是 `disabled`**（物理屏保持原生 4K 捕获，画质最好、屏幕不被切模式）。
如果希望「手机请求什么分辨率物理屏就切什么」，改成 `verify_only` 即可。

---

## ⚠️ 已知坑：串流后显示模式不还原（刷新率 / DPI 被 stranded）

### 症状（2026-10-12 实测）

手机串流断开后，物理显示器**分辨率还是 4K，但刷新率卡在 60Hz**
（这块屏支持 160Hz，Sunshine 自己记录的原始值就是 `3840x2160 @ 160Hz`）。
DPI 也出现不一致：`LogPixels=192`(200%) vs `AppliedDPI=144`(150%)。
观感就是「大小不对、鼠标发涩」。

### 根因：Sunshine 只在启动时还原，客户端断开不还原

**Sunshine 自己的日志证据**：

```
# 开机时（10-12 06:36）—— 会尝试还原上次遗留的设置
[06:36:01] Trying to revert applied display device settings. API is available: false
[06:36:06] Trying to revert applied display device settings. API is available: false
[06:36:11] Trying to revert applied display device settings. API is available: false
[06:36:16] Trying to revert applied display device settings. API is available: false
[06:36:21] Trying to revert applied display device settings. API is available: true

# 串流时（10-11 10:51:08）—— 按客户端请求改模式
Scheduling display device configuration:
  "device_prep": "EnsureOnlyDisplay",
  "refresh_rate": { "numerator": 30 }        ← 刷新率被改成 30Hz

# 客户端断开后（10-12 07:35:42 CLIENT DISCONNECTED）
→ 日志里一次 revert 都没有
```

**为什么断开不还原**：

- `dd_config_revert_delay` 的官方语义是「app 已关闭**或最后一个 session 终止**时还原」
- 但串流对象是**桌面**而不是具体 App → 没有 App 关闭事件可触发
- `dd_config_revert_on_disconnect` 默认 **disabled** → 光断开客户端不触发还原

→ **模式被 stranded，直到 Sunshine 下次重启才还原。**

### 虚拟屏在这里面的角色（重要澄清）

**虚拟屏不是根因，但它让问题更难自愈。**

`Trying to revert ... API is available: false` 连续 4 次失败（20 秒）——
Windows 显示配置 API 不可用。而 VDD 保活脚本当时正在每 15 秒反复
ADD/移除虚拟显示器，显示栈一直处于变动中，API 自然抢不到。

所以：**虚拟屏放大了故障，但病根是 Sunshine 的还原触发条件。**

### 修复

**长期（推荐，已交付）**：跑桌面 `关掉Sunshine显示管理.bat`，
把 `dd_configuration_option` 设为 `disabled`。这会**禁用所有 dd_ 选项**
（含 `dd_resolution_option = auto`、`dd_refresh_rate_option = auto`）
→ Sunshine 再也不改显示模式 → 不存在「改了要还原」这回事。
物理屏保持原生 4K@160 被捕获后缩放，画质也最好。

**短期补救**（已经乱了的时候）：

1. 设置 → 系统 → 显示 → 高级显示设置 → 刷新率选回 **160Hz**
2. 设置 → 系统 → 显示 → 缩放与布局 → 选回 **200%**
3. **注销重新登录**（DPI 变更必须重新登录才完全生效，`AppliedDPI` 只在登录时更新）

**如果坚持要「分辨率跟随客户端」**：改成
`dd_configuration_option = verify_only`（只验证活动状态、不改拓扑），
并在 Web UI 打开 `dd_config_revert_on_disconnect`。
代价是物理屏会被切成客户端请求的模式。

---

### ⭐ 真想用「Sunshine 自带虚拟屏」→ 只有一个选择：换分支版

**官方版没有，但社区分支有，而且做得相当完整。**

**`AlkaidLab/foundation-sunshine`**（原 `qiin2333/Sunshine-Foundation`，fork 自 LizardByte/Sunshine）

| 维度 | 情况 |
|---|---|
| 虚拟显示器 | **深度集成 ZakoVDD**，`src/platform/windows/display_vdd.cpp`，驱动随包分发 `src_assets/windows/misc/vdd/driver/vdd_settings.xml` |
| 捕获方式 | **Zako Direct 零拷贝** —— 直接向驱动借帧纹理，不经 DXGI 桌面复制 |
| 生命周期 | 默认**仅串流时创建**，结束后销毁（v2025.0212 起） |
| 屏幕模式 | 5 种，支持多客户端 GUID 会话 |
| HDR | 完整 HDR10(PQ) + HLG + HDR Vivid(CUVA) 管线，逐帧 GPU 亮度分析 |
| 音频 | 7.1.4 十二声道、Opus DRED 神经网络丢包恢复 |
| A 卡支持 | ✅ Windows 侧编码器含 **AMF**（另有 NVENC SDK 13.0 / QSV） |
| 维护状态 | **极活跃** —— 最新 `v2026.1011.150654`（2026-10-11，即昨天），约月更 |
| 其他 | 控制面板 Tauri 2 + Vue 3、DLSS NR 预编码增强、PyroWave 编解码、动态 FEC |

**为什么这条对 LIG 特别相关**：2026-09-12 排查 ZakoVDD 失败的根因是
「这一代构建把创建显示器改成了外部命令驱动，控制管道 `\\.\pipe\ZakoVDDPipe`
在本机从未被创建」。而该分支 v2025.0212 的发布说明正是：

> 「虚拟显示器加固，在原 vdd 基础上**增加了显示器创建/销毁能力**」

且仓库有专门的 `vdd_pipe` 分支 —— **当年踩的坑，这个分支声称已经修了**。

**但不建议现在换**，理由：

1. 刚做完减法，换分支等于重新引入整套复杂性（要卸官方版、重配对、重调参数）
2. 分支版新增的 HDR 管线 / DLSS NR / PyroWave 大量偏向 NVIDIA，A 卡用户用上的概率低
3. 「仅串流时创建虚拟屏」依赖驱动 IOCTL 动态配置，稳定性和官方版 + 物理常开是两种风险模型
4. 社区项目（中文社区「杂鱼」版本号），信任模型和官方 LizardByte 不同

**什么时候再考虑**：真的重新需要「关显示器串流」、且不愿意接受物理屏常开时。

---

### 以下为 2026-09-12 的原始方案记录（已废弃，仅存档）

当时实测通过的状态：

```
driver ver  : 45
monitors    : 2
   \\.\DISPLAY1   -> Monitor0  | AMD Radeon RX 7800 XT          ← 物理显示器 P2710V
   \\.\DISPLAY22  -> Monitor0  | Parsec Virtual Display Adapter  ← 虚拟显示器 2560x1440@60
daemon      : RUNNING
```

#### 当时排查过的路

| 尝试 | 结果 | 根因 |
| --- | --- | --- |
| **按显示器电源键** | 黑屏 | 单显示器系统，DP 断链后 Windows 判定无显示设备，桌面渲染目标销毁 |
| **让 Windows 自动关屏（DPMS）** | 无用 | **Moonlight 一连上，Sunshine 会把显示器设成客户端的分辨率/刷新率 → 显示模式变更 → 立刻唤醒显示器**。实测串流一开屏幕就亮 |
| **Zako VDD（9 轮排查）** | 失败 | 适配器初始化完全正常，但这一代构建把"创建显示器"改成了**外部命令驱动**，而它的控制管道 `\\.\pipe\ZakoVDDPipe` 在本机**从未被创建**（设备重启 ×3 + 整机重启 ×1 验证）。属构建缺陷，不改源码绕不过 |

**核心洞察**：只要物理显示器还留在显示拓扑里，串流时的模式变更就随时会把它点亮。**唯一出路是让虚拟显示器顶替它。**

---

### 现在的方案：Parsec VDD 官方签名驱动 + 自研保活脚本

**零未签名程序、零管理员权限、零第三方 companion。**

#### 为什么是这个方案

- **驱动是 Parsec 官方签名的**（WinVerifyTrust 实测 `0x00000000` = 可信，证书 Parsec/DigiCert）
- **设备句柄在普通用户权限下就能打开** —— 这是关键。ZakoVDD 的控制通道要管理员权限且建不出来，Parsec VDD 完全没这个问题
- **内核通信协议是公开的**（`nomi-san/parsec-vdd` 的 `core/parsec-vdd.h`），所以可以自己写保活，不需要装那个未签名的社区管理程序

#### 内核协议速查

```
设备接口 GUID : {00b41627-04c4-429e-a26e-0265cf50c8fa}
设备路径      : \\?\ROOT#DISPLAY#0000#{00b41627-04c4-429e-a26e-0265cf50c8fa}
                （也可枚举 HKLM\SYSTEM\CurrentControlSet\Control\DeviceClasses\{GUID} 得到）

VDD_IOCTL_VERSION = 0x0022E010   查驱动版本（本机返回 45）
VDD_IOCTL_ADD     = 0x0022E004   添加显示器，返回 index
VDD_IOCTL_REMOVE  = 0x0022A008   移除，传 16 位大端索引，之后必须再调一次 UPDATE
VDD_IOCTL_UPDATE  = 0x0022A00C   保活 ping，必须每 <100ms 一次

打开句柄 : GENERIC_READ|WRITE, share=FILE_SHARE_READ|FILE_SHARE_WRITE, OPEN_EXISTING,
           FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OVERLAPPED|FILE_FLAG_WRITE_THROUGH
调用方式 : DeviceIoControl 入缓冲固定 32 字节、出缓冲 4 字节 DWORD，
           必须用 OVERLAPPED + WaitForSingleObject(5000ms) + GetOverlappedResult
```

⚠️ **保活是硬性要求**：停止 ping 后约 1 秒，虚拟显示器会被驱动自动拔掉。

#### 虚拟显示器能力

支持 **91 种分辨率**，最高 4096x2160@240 / 3840x2160@240 / 3440x1440@240 / 2560x1440@240。默认创建时是 1920x1080@60。

---

### 部署内容：`C:\ParsecVDD-KeepAlive\`

| 文件 | 作用 |
| --- | --- |
| `vdd-keepalive.py` | 保活主进程。含单实例、日志轮转、断线重连、退出自动清理、分辨率设置与自愈 |
| `vdd-guardian.py` | **自愈守护**：每 60s 检查主进程是否存活、虚拟显示器是否还在，任一丢失就重新拉起。`--once` 可做单次自检 |
| `Start-VirtualDisplay.bat` | 启动（主进程 + guardian 一起拉起） |
| `Stop-VirtualDisplay.bat` | 停止（写 `stop.flag` + 结束主进程和 guardian + 拔除虚拟显示器） |
| `Restart-VirtualDisplay.bat` | **一键重启**：stop → start → 拉起 guardian → 报状态。出任何问题先点这个 |
| `Status-VirtualDisplay.bat` | 查状态（含进程说明和 PID） |
| `vdd-keepalive.log` | 运行日志（>1MB 自动轮转） |
| `vdd-keepalive.err` | stderr 落盘 —— 未捕获异常会写到这里，**排查死因必看** |

### ★ GUI 控制面板（推荐入口，2026-09-13 新增）

**`C:\Users\PC\Desktop\虚拟显示器控制面板.exe`**（也在 `C:\ParsecVDD-KeepAlive\`）

可视化小工具，不用再记命令、不用双击一堆 bat：

| 区域 | 功能 |
| --- | --- |
| **状态** | 驱动版本 · 虚拟显示器在线状态 · 保活进程 · 自愈守护 · 当前分辨率（彩色圆点指示） |
| **虚拟显示器** | 分辨率 + 刷新率下拉（**91 种模式全列出**）· **跟随 Moonlight** 开关 · 应用并重启保活 · 启动 · 停止 · 刷新 |
| **桌面显示在（切换）** | 仅真实显示器 / 仅虚拟显示器 / 扩展 |
| **Sunshine 集成** | 显示当前 `dd_*` 三项配置是否合规（✅/⚠），一键写入推荐配置（自动请求管理员） |
| **日志** | 每次操作都有记录 |

**「跟随 Moonlight」怎么用**：勾选 → 点「应用并重启保活」。
面板会写 `C:\ParsecVDD-KeepAlive\gui_settings.json`（`follow_moonlight: true`），
保活进程读到后**不再强制分辨率**，于是 Sunshine（`dd_resolution_option = auto`）
就能在串流开始/结束时按 Moonlight 客户端的请求自动设置虚拟显示器分辨率。

不勾选则指定一个固定分辨率 —— 保活进程每 15 秒复查一次，被系统或 Sunshine 改掉会自动改回来。

**源码与重建**：`C:\ParsecVDD-KeepAlive\gui\vdd_gui.py`（tkinter，纯标准库）

```bat
cd C:\ParsecVDD-KeepAlive\gui
"C:\Program Files\Python312\python.exe" -m PyInstaller --noconfirm --clean ^
  --onefile --windowed --name ParsecVDD-Panel --icon app.ico vdd_gui.py
```

自检（不弹窗，结果写 `C:\ParsecVDD-KeepAlive\gui_selftest.txt`）：
`虚拟显示器控制面板.exe --selftest`

### ★ 一键切换：真实显示器 ↔ 虚拟显示器（2026-09-13 新增）

**痛点**：虚拟显示器是**扩展屏**，鼠标会跑到看不见的屏幕上；手动切换要开"显示设置"点好几下。
更糟的是桌面可能"留在"虚拟显示器上，导致物理屏看着像没信号。

**桌面已放好三个入口**（`C:\Users\PC\Desktop\`）：

| 文件 | 作用 |
| --- | --- |
| `切换显示器.bat` | **双击即切**：自动切到"另一个"显示器（真 ↔ 虚），无需任何选择 |
| `切换显示器-选择目标.bat` | 菜单版：只在真实 / 只在虚拟 / 扩展两者 / 只看状态（8 秒不选则默认第一项） |
| `虚拟显示器-状态.bat` | 查看当前激活的显示器 + 进程说明 |

脚本本体在 `C:\ParsecVDD-KeepAlive\vdd-switch.py`，模式：`toggle` / `real` / `virtual` / `both` / `status`。

**原理**：调用 Windows 自带的 `DisplaySwitch.exe`
- `/internal` = 仅电脑屏幕 → 只留第一个显示器（真实）
- `/external` = 仅第二屏幕 → 只留第二个显示器（虚拟）
- `/extend` = 扩展

> 若发现方向反了，把 `vdd-switch.py` 顶部的 `FLAG_REAL` 与 `FLAG_VIRTUAL` 互换即可。

**键盘备用方案**：`Win + P` → 选 `仅电脑屏幕` / `仅第二屏幕` / `扩展`。
**任何时候屏幕"看起来黑了"，按 `Win + P` 就能切回来。**

**想彻底不用手动切** —— 让 Sunshine 自动做（改 `C:\Program Files\Sunshine\config\sunshine.conf`，需管理员）：

```ini
dd_configuration_option = ensure_only_display
```

一开串流，Sunshine 自动把桌面切到它要抓取的显示器、其余显示器关掉；断开串流自动恢复。
物理屏关着时它自然会选虚拟显示器，你连切换都不用管。

### ★ 进程识别与停止（重要，2026-09-13 补充）

任务管理器里会看到**两个无窗口的 `pythonw.exe`**，都属于本方案，别删：

| 脚本 | 作用 |
| --- | --- |
| `vdd-keepalive.py` | 保活主进程，每 70ms ping 驱动 |
| `vdd-guardian.py` | 自愈守护，每 60s 检查；主进程没了会在一分钟内拉回来 |

- **要停止请双击 `Stop-VirtualDisplay.bat`**，不要从任务管理器杀
  （杀了 guardian 也会拉回来；`Stop` 会写 `stop.flag`，guardian 才就此罢手）
- **想一眼认出是哪个**：任务管理器 → `详细信息` 标签 → 右键任意列头 → `选择列` → 勾选 **命令行**，
  就能看到 `"…\pythonw.exe" "…\vdd-keepalive.py" run`
- ⚠️ **不要误杀**：`C:\Users\<用户>\.workbuddy\binaries\python\…\pythonw.exe` 是 WorkBuddy 自己的进程，
  和本方案无关（本方案用的是 `C:\Program Files\Python312\pythonw.exe`）

**命令行参数**（改 `Start-VirtualDisplay.bat` 即可）：

```bat
vdd-keepalive.py start --resolution 2560x1440@60     :: 分辨率（可改 3840x2160@60 / 1920x1080@120 等）
vdd-keepalive.py status                              :: 查状态
vdd-keepalive.py stop                                :: 停守护 + 拔显示器
vdd-keepalive.py clean                               :: 强制拔掉所有残留虚拟显示器
vdd-keepalive.py run --duration 15                   :: 前台跑 15 秒（调试用）
```

**开机自启**已配置在
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run` →
`"C:\Program Files\Python312\pythonw.exe" "C:\ParsecVDD-KeepAlive\vdd-keepalive.py" run`
（pythonw 无控制台窗口，登录时静默拉起）

#### 依赖

- Parsec Virtual Display Driver v0.45（`mm.inf_amd64_*`，签名驱动）
  - 备用：v0.41（更稳），下载源 `https://builds.parsec.app/vdd/parsec-vdd-0.41.0.0.exe`
- Python 3.12（`C:\Program Files\Python312\`，仅用标准库）

---

### 日常使用

1. **开机即自动带虚拟显示器**，无需操作
2. **要关显示器：直接按电源键** —— 物理屏断电后从系统消失，桌面自动落到虚拟显示器，串流正常，且物理屏**不可能**被点亮
3. 不想让虚拟显示器存在时：双击 `Stop-VirtualDisplay.bat`

---

### 可选增强：让 Sunshine 自动切走物理屏

编辑 `C:\Program Files\Sunshine\config\sunshine.conf`（需管理员）：

```ini
dd_configuration_option = ensure_only_display
```

这样**一开串流就自动只保留虚拟显示器**，物理屏自动变黑——连电源键都不用按。断开串流后自动恢复。当前值是 `ensure_primary`。

> 注意：`ensure_only_display` 意味着你在电脑前时，只要手机连上串流，本地屏幕就会黑。按需选择。

---

### 出问题时的排查顺序

1. 双击 `Status-VirtualDisplay.bat` —— 看 `virtual` 是不是 1、`daemon` 是不是 RUNNING
2. 如果是 0 / not running → 双击 `Start-VirtualDisplay.bat`
3. 还是不行 → 双击 `Stop-VirtualDisplay.bat` 再 `Start-VirtualDisplay.bat`
4. 看日志 `C:\ParsecVDD-KeepAlive\vdd-keepalive.log`
5. 驱动层面：`pnputil /enum-devices /class Display`，应能看到 `Parsec Virtual Display Adapter` 状态"已启动"
6. 驱动状态码（`vdd-keepalive.py status` 里的 `driver ver`）：
   `0=OK 1=INACCESSIBLE 4=DISABLED 5=DRIVER_ERROR 6=RESTART_REQUIRED 7=DISABLED_SERVICE 8=NOT_INSTALLED`

---

## 9. 排查清单

| 症状 | 原因 / 解法 |
| --- | --- |
| 手机搜不到电脑 | 不同网段；防火墙没放行；Sunshine 服务没启动（服务里看 `SunshineSvc`） |
| 连上黑屏 | 编码器挂了 → 见第 2 节 AMF 排查；或电脑锁屏/休眠了 |
| 画面卡成 PPT | 码率过高 → 降到 20 Mbps；或 Wi-Fi 是 2.4G → 切 5G |
| 有画面没声音 | 装 Sunshine 时勾选的虚拟声卡驱动，在 Windows 声音设置里把「Steam Streaming Speakers」设为默认输出 |
| 鼠标乱飘 | 关掉「绝对触控模式」，改用 Trackpad 相对模式 |
| 手机发热严重 | 降分辨率到 720p，或降帧率到 30 |
| 隔几分钟断连 | 路由器 AP 隔离 / 电脑网卡节能 → 设备管理器网卡取消「允许计算机关闭此设备以节约电源」 |

---

## 10. 你的硬件能玩到的上限

RX 7800 XT 的 AMF 支持 **AV1 编码**。如果你手机是近两年的旗舰（骁龙 8 Gen2 以上、天玑 9200 以上），可以在 Codec 里试 **AV1**：

- 同码率下画质明显好于 HEVC，看设计稿的细线条更干净
- 代价是编码延迟略高，快速拖动时可能不如 HEVC 跟手

**建议：日常用 HEVC，静态看稿时切 AV1。** 两个 Codec 切换只需在 Web UI 改一下重启，随时试。

---

## 🖥️ 跨网拓扑与通道（两台机器通用）

| 设备 | Tailscale | EasyTier | 说明 |
|---|---|---|---|
| 家里台式主机 | `100.64.1.10` | `.2`（<主机设备名>） | Sunshine 主机 |
| 笔记本 | `100.64.1.20`（名 `node`） | `.4`（<笔记本设备名>） | Moonlight 客户端 + VDD 扩展屏 |
| Honor Magic8 手机 | `100.64.1.30` | `.3` | 主客户端，同一 Tailscale 账号 `<你的 Tailscale 账号>` |

- 两边 NAT 都是 **PortRestricted**，Tailscale **IPv4 打洞失败**，长期走 DERP 中继
  （sfo/lax，约 400ms）—— 只够应急串流。所以才搭了 EasyTier。
- 网络名 `<EasyTier 网络名>` / 密码 `<EasyTier 密码，已移除>`，自建中继 `wss://<你的中继域名>/ws`（CF Worker）。
- 2026-09-16 笔记本拿到联通公网 IPv6（`240e:` 开头，RA 下发）后与主机打成 **quic6 P2P 直连**，
  但延迟仍有 ~360-430ms（跨境/绕路）。
- 手机在家里 WiFi 与主机同网段时**可局域网直连**串流（不走 VPN），此时延迟最低。

---

## 11. 笔记本方案：Sunshine + VDD 做「扩展屏」

> 与第 8 章的台式方案**目的完全不同**：
> 台式是用虚拟屏**顶替**物理屏（镜像/接管）；笔记本是用虚拟屏给手机**加一块扩展屏**（非镜像）。

### 11.1 虚拟屏驱动

- **VDD**：`VirtualDrivers/Virtual-Display-Driver 25.7.23`
- 安装位置 `C:\VDD\`，`control\SignedDrivers\x86\VDD\MttVDD.inf` 经 devcon 装 `Root\MttVDD`
- 驱动库 `oem128.inf`，枚举名 **"VDD by MTT"**
- 安装脚本：`install-vdd.ps1` / `install-vhid.ps1` / `install-vigembus.ps1` / `config-sunshine.ps1`，
  日志 `C:\VDD\install.log`
- ⚠️ VDD 默认分辨率列表**没有 1600 高度**（最高 1440 / 2160）

### 11.2 ⭐ 关键坑：串流目标必须用稳定 GUID，不能用 GDI 编号

```ini
# C:\Program Files\Sunshine\config\sunshine.conf
dd_configuration_option = ensure_active
dd_display_device_id = {9acddf6d-43cc-576e-9aff-0c5fc80b4cc8}   # VDD by MTT 的稳定 GUID
```

**Why**：Windows 重启后 GDI 显示器编号会变（`DISPLAY2` → `DISPLAY7`）。
写 `output_name = \\.\DISPLAY2` 重启后**找不到屏会回退主屏**，扩展屏就失效了。

**GUID 从哪来**：Sunshine 日志里的 `Currently available display devices` JSON 块。

本机（台式）实测该块长这样（2026-10-12，用于示范格式）：

```
[2026-10-12 10:00:24] Info: Currently available display devices:
[
  {
    "device_id": "{2bdc1e09-1701-5f00-9100-e77eacc6e2aa}",   ← 这个就是稳定 GUID
    "display_name": "\\.\DISPLAY1",                          ← 这个会变，别用
    "edid": { "manufacturer_id": "LHC", "product_code": "FFFF", "serial_number": 0 },
    "friendly_name": "P2710V",
    "info": { "hdr_state": "Disabled", ... }
  }
]
```

取 `device_id` 字段，**不要取 `display_name`**。

### 11.3 ⭐⭐ DPI 被重置的真正机制（2026-10-12 定位）

> **这是历史上反复出现的「串流后缩放跑掉」的根因，两台机器都适用。**

**机制**：`spacedesk` / Honor 多屏协同这类**无 EDID 的虚拟屏**接入时，
会触发 Windows **重新枚举显示器** → 每显示器 DPI 重算 → **把主屏缩放重置成 100%**。

**处置记录（2026-09-25）**：

- `spacedesk` 已卸载：`msiexec /X{1ACC56E2-AE29-4983-95BF-3E942D9ABE38} /qn`
- 残留的 `DpiValue=4` 记录 `MSNILNOEDID_...` 已删除
- Honor Virtual Display 仍在（多屏协同要用）

**与台式主机的关联**：2026-10-12 台式上发现
`LogPixels=192`(200%) 与 `AppliedDPI=144`(150%) 不一致 ——
今天只观察到结果，这份笔记补上了触发机制。

**判定与修复**：

| 现象 | 含义 | 修法 |
|---|---|---|
| `PerMonitorSettings` 下有脏键（如 `MSNILNOEDID_...`） | 无 EDID 虚拟屏留下的残留 | 删掉该键 |
| `PerMonitorSettings` 下键为空，但 `AppliedDPI != LogPixels` | 单纯没刷新 | 设置里确认缩放 → **注销重登** |
| 缩放掉到 100%（不是 150%） | 典型的虚拟屏重新枚举后遗症 | 检查是否有无 EDID 虚拟屏在接入 |

**关键**：`AppliedDPI` 只在登录时刷新，**改完缩放必须注销重登**才真正生效。

### 11.4 输入设备：libvirtualhid → ViGEmBus 回退

- Sunshine `2026.914.233613` + Moonlight `6.2.0.0`
- 早期「906 与 libvirtualhid 914 版本不匹配」问题已消失
- 现状：`libvirtualhid` 驱动（`oem120.inf`）**装着但 license 无效**，
  日志 `Virtual HID Driver license is not valid; using the ViGEmBus gamepad fallback`
- 虚拟手柄改由 **ViGEmBus**（`oem121.inf`，Nefarius Virtual Gamepad Emulation Bus
  `1.21.442.0`）提供，安装脚本 `C:\VDD\install-vigembus.ps1`
- 触控 / 鼠标走 `SendInput`，**一直不受影响**

### 11.5 Sunshine 配置注意事项（两台通用）

- 服务名是 **`SunshineService`**（不是 `sunshinesvc`）
- `sunshine.conf` 必须 **UTF-8 不带 BOM** —— BOM 会让首行显示成乱码
- `C:\Program Files\Sunshine` 下写文件**需提权**
- 排查显示器状态用 `C:\Program Files\Sunshine\tools\dxgi-info.exe`
  （看 Output Name / 分辨率 / `AttachedToDesktop`）

### 11.6 笔记本显示栈隐患

笔记本的显示适配器（含 AMD Radeon）曾出现全部
**`CM_PROB_FAILED_POST_START`**（等待重启状态）→ 后果：

- 推荐缩放掉到 100%
- 编码器只剩 `libx264` 软编

**重启可清。** 遇到「突然只剩软编 + 缩放变 100%」先怀疑这个，别去调 Sunshine。

---

## 快速核对清单

- [ ] 下载 msi 并以管理员安装
- [ ] Web UI 设置账号密码
- [ ] Encoder = amf / Codec = HEVC / 关 HDR
- [ ] PowerShell 跑两条防火墙命令
- [ ] 手机装 Moonlight，同 Wi-Fi 下 PIN 配对
- [ ] 手机端码率拉到 30 Mbps 以上
- [ ] 装 Tailscale 打通外网
- [ ] 电源改成从不睡眠
- [ ] ~~启动虚拟显示器~~ → **已废弃（2026-10-12）**，改跑桌面 `关掉Sunshine显示管理.bat`
      （`dd_configuration_option = disabled`，Sunshine 不再碰显示拓扑）
- [ ] 确认物理屏是 3840x2160 @160Hz @200% 缩放；跑偏了双击桌面 `恢复显示器配置.bat`
      （改完缩放还需注销重登）
