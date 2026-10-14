# VirtualDisplay — 虚拟显示器统一方案

单一目录、单一入口、单进程。2026-10-14 重构，取代原来散落各处的旧方案。

---

## 目录结构

```
C:\VirtualDisplay\
├─ vdd.ps1                    引擎控制脚本（CLI，被 GUI 和脚本共用）
├─ vdd-keepalive.py           保活引擎（自带 self-heal）
├─ vdd-switch.py              显示器切换逻辑
├─ vdd-keepalive.log          运行日志
├─ panel\                     现代 GUI 的源码
│  ├─ app.py                  PySide6 界面
│  ├─ backend.py              后端封装（复用引擎脚本，不重实现驱动逻辑）
│  └─ VirtualDisplayPanel.spec
├─ gui\                       旧 tkinter 面板源码（已弃用，留档）
└─ _archive_old_ParsecVDD\    旧方案归档（49 个文件，只读留存）
```

**桌面唯一入口**：`C:\Users\PC\Desktop\虚拟显示器.exe`（双击即用）

GUI 是自包含的（backend 已打进 exe），所以放桌面不会产生第二份逻辑；
它只通过命令行调用 `C:\VirtualDisplay\` 里的引擎脚本。

---

## 用法

**日常**：双击桌面 `虚拟显示器.exe`

界面分五张卡片：

| 卡片 | 内容 |
|---|---|
| 状态 | 驱动版本、保活进程、物理/虚拟显示器、开机自启 |
| 虚拟显示器 | 分辨率下拉（9 个预设，也可手填）、跟随 Moonlight 开关、启动/停止/重启 |
| 桌面显示在 | 仅真实 / 仅虚拟 / 扩展 / 切换（分段按钮） |
| 维护 | 打开日志、清理残留、开机自启开关 |
| 驱动重置 | 一键禁用→启用适配器，清空污染槽位表 |

需要管理员的两个动作（重置驱动、开机自启）会**在程序内自动弹 UAC 提权**，
其余全部普通权限。

**命令行备用**（脚本/自动化用）：

```bat
C:\VirtualDisplay\vdd.ps1 status
C:\VirtualDisplay\vdd.ps1 start 2560x1440@60
C:\VirtualDisplay\vdd.ps1 switch virtual
```

| 子命令 | 作用 | 要管理员 |
|---|---|---|
| `start [WxH@Hz]` | 启动保活 | 否 |
| `stop` | 停止并拔除虚拟屏 | 否 |
| `restart` | 重启 | 否 |
| `status` | 驱动/显示器/进程状态 | 否 |
| `switch [real\|virtual\|both\|toggle]` | 切换桌面显示目标 | 否 |
| `resolution X` | 设分辨率，如 `2560x1440@60` | 否 |
| `clean` | 强制清理残留虚拟屏 | 否 |
| `reset` | 重置 Parsec 驱动后启动 | **是** |
| `autostart [rm]` | 安装/移除开机自启计划任务 | **是** |
| `panel` | 打开 GUI | 否 |

自检（不弹窗，验证打包完整性 + 后端 + UI 构造）：

```bat
C:\Users\PC\Desktop\虚拟显示器.exe --selftest
```

---

## 相比旧方案改了什么

| | 旧（`C:\ParsecVDD-KeepAlive\`） | 新（`C:\VirtualDisplay\` + 桌面 exe） |
|---|---|---|
| 目录 | 1 个 + 桌面 1 个 exe | **1 个** |
| 文件数 | 22 + 2 子目录 | **9 + 2 子目录**（另 49 个归档） |
| 桌面入口 | 1 个 11MB tkinter exe | **1 个 49MB 现代 Qt6 exe** |
| 内部入口 | 6 个 bat + 1 GUI = 7 种 | **1 个 GUI** + 1 个 `vdd.ps1`（备用 CLI） |
| 常驻进程 | **2 个**（keepalive + guardian） | **1 个** |
| 重复 exe | 2 份共 22MB | **1 份**（自包含，无第二份逻辑） |
| 混入的无关物 | Sunshine 修复脚本、`measure.py`、`probe2.py` | 已分离/归档 |
| 自启 | 2 个 HKCU Run 项 | **1 个计划任务**（自带失败重启） |
| UI | tkinter 旧式 | **PySide6 / Qt6 深色卡片式** |

** guardian 为什么能去掉**：它的职责是「保活进程死了就拉起来」。
现在改用 Windows 计划任务自带的 **restart-on-failure**（999 次 / 每 1 分钟）
来完成同一件事，少一个常驻 pythonw。

### GUI 技术选型

环境里 PySide6 6.11.1 和 flet 0.86.1 都已安装，**选 PySide6**：

- 打包**零网络依赖**（flet pack 可能要去拉 Flutter engine）
- Qt 认真做样式完全能达到现代质感（Telegram 桌面版就是 Qt）
- 49MB 含完整 Qt 运行时，可接受

界面为深色卡片式：状态点带脉冲动画、分段按钮、圆角卡片、细分边框、
`Segoe UI` 字体栈。后端 `panel/backend.py` **只做封装，不重实现驱动逻辑**，
所有动作都 shell out 给经过验证的 `vdd-keepalive.py` / `vdd-switch.py`。

---

## ⚠️ 已知问题与 2026-10-14 修复

### 已修复：保活进程失控累积显示器（引擎 bug）

**症状**：`status` 出现越来越多 `\\.\DISPLAY22、23、24…` 的虚拟显示器，
几分钟增加到 16 个还在涨；日志每 15 秒刷
`self-heal: 驱动里没有监视器对象了 - 清闩锁重新 ADD`。

**根因（2026-10-14 实验定性）**：`attached_parsec()` 用
`EnumDisplayDevicesW(None, i)` 枚举，传 `NULL` 拿到的是**适配器级**条目，
而这些条目的 `StateFlags` **恒为 `0x0`**（bit0 `ATTACHED_TO_DESKTOP` 不置位）：

```
adapter '\\.\DISPLAY22' flags=0x0  bit0(ATTACHED)=False
adapter '\\.\DISPLAY23' flags=0x0  bit0(ATTACHED)=False
... 共 16 条，全为 0x0
```

所以该函数**数学上永远返回 0**。一个坏函数同时杀死两套保护：

| 依赖它的机制 | 后果 |
|---|---|
| 健康检查 `if att > 0` | 永不通过 → 自愈无限触发 |
| 过多护栏 `if att > displays` | 永不触发 → 累积无人拦 |

→ 自愈反复清闩锁 → 反复 ADD → 显示器无限增多。

**修复（三处）**：

1. `attached_parsec()` / `real_attached_count()` 改为**两级枚举**
   （先用 `NULL` 取适配器，再用适配器名取监视器）——
   bit0 只在监视器级可信。
2. 新增 `parsec_adapter_entries()`：按适配器条目计数，
   **完全不看 StateFlags**，作为独立第二道保险。
3. ADD 前硬护栏：条目数已达目标就**绝不再 ADD**，改为走
   `reattach_desktop()`。即使健康检查再坏也不会无限累积。

**验证**：修复后启动 45 秒，条目数稳定在 16 不增长，日志出现
`ADD skipped: 16 parsec display(s) already exist (target 1) - forcing reattach instead`。

### 待处理：16 个孤儿条目（需驱动重置）

上面那 16 个是历史累积的**孤儿条目** —— 存在但挂不上桌面，
`DisplaySwitch` 也选不中。新的护栏能防止继续变多，但清不掉已有的。

**解法**：面板里点「重置驱动并启动」（自动提权，禁用→启用适配器清槽位表），
或重启电脑。重置后再启动保活，就是干净的 1 个显示器。

### 曾经的误判（存档）

2026-10-12 曾把虚拟屏建不起来归因为「Sunshine 的
`ensure_only_display` 与虚拟屏互殴」。这只是**诱因之一**：
互殴产生的 672 次增删循环污染了驱动槽位表，而保活自身的
StateFlags 判定 bug 才是让污染无法自愈、反而持续扩大的真正原因。
两者叠加才形成当时的死循环。

---

## 依赖

- Python 3.12（`C:\Program Files\Python312\`，仅标准库）
- Parsec Virtual Display Driver v0.45（已安装，`ROOT\DISPLAY\0000`，`oem67.inf`）
- PyInstaller 6.21（仅重打包 GUI 时需要）

## 重建 GUI

```bat
cd C:\VirtualDisplay\panel
"C:\Program Files\Python312\python.exe" -m PyInstaller --noconfirm --clean ^
  --onefile --windowed --name VirtualDisplayPanel --icon ..\gui\app.ico ^
  --add-data "backend.py;." --hidden-import backend app.py
copy dist\VirtualDisplayPanel.exe "C:\Users\PC\Desktop\虚拟显示器.exe"
```

**关于路径硬编码**：`backend.py` 里 `ROOT = r"C:\VirtualDisplay"` 是写死的。
整合的意义就是只有一个固定位置，硬编码反而比相对路径稳
（PyInstaller onefile 下 `__file__` 指向临时解包目录，不可用）。

**exe 是自包含的**：`backend.py` 已通过 `--add-data` 打进包，
所以从任何目录运行都正常（已从 `C:\` 和桌面分别验证）。

## 自检（不弹窗）

```bat
C:\Users\PC\Desktop\虚拟显示器.exe --selftest
```

依次验证：引擎脚本存在 → 状态解析（驱动版本/进程/显示器/物理模式）→
11 个后端方法可调用 → `Main()` 能否构造 → 下拉项数 → 分段模式数。
全部通过打 `RESULT = OK`。
