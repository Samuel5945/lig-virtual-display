# VirtualDisplay — 虚拟显示器（MttVDD）

**v0.3.0** · **单文件 exe**：装驱动、控制、串流配置，全在「虚拟显示器.exe」里。

## v0.3.0（2026-10-16）

- **显示器布局卡加了示意图**：按 Windows 真实坐标画每块屏，标出物理/虚拟·主屏·
  分辨率，图下两行完整读数；点参照屏的某一侧就直接把虚拟屏挪过去
- **「虚拟屏位置」终于有选中态**：此前那四个按钮只调 `setEnabled()`、从没调
  `mark()`，所以永远同色。现在当前在哪一侧由坐标**反推**（`virtual_side()`，与
  写入坐标的 `place_beside()` 共用一套公式），你在系统设置里手动拖它也跟着变
- **串流画面拆成两个轴**：抓哪块屏（跟随系统 / 物理屏 / 虚拟屏）× 另一块屏
  （保持扩展 / 串流时关掉）。以前只有两态，想让手机看物理屏只能绕去改主显示器
- **串流卡加一行明说去向**：「手机看到 = 物理屏 `\\.\DISPLAY1` …」以及看不到的
  是哪块；`python streamcheck.py --where` 能从会话日志证明这句话是真的
- **修：主显示器切不到虚拟屏** —— 单次 `ChangeDisplaySettingsEx` 返回成功却静默
  不动，改成 `CDS_NORESET` 批量预置再一次应用
- **修：点任务栏图标不收回** —— 无边框窗口缺 `WS_MINIMIZEBOX`/`WS_SYSMENU`，
  shell 判定"这窗口不能最小化"；顺带修好一处把扩展样式误写进 `GWL_STYLE` 的老 bug
- **修：面板每 3 秒整读 1.7 GB 的 sunshine.log** → 只读头部 4 MB（单次 5-6 ms）
- **修：在系统设置里拖动虚拟屏，面板不刷新**（轮询签名里没含坐标）
- **自检从 11 项加到 22 项**：选中态、示意图读数、串流两轴回读、窗口样式位都有
  正面 PASS 标记，缺任何一项 `RESULT` 就是 FAIL

### 下载

发布页：<https://github.com/Samuel5945/lig-virtual-display/releases/tag/v0.3.0>

| 附件 | 给谁 |
|---|---|
| `VirtualDisplay-v0.3.0.exe` | **新机器也只要这一个**。下载后改名为「虚拟显示器.exe」（发布页把中文名转成了 ASCII，内容同一份）。打开后检测到没驱动会弹横幅，点「安装驱动」即用 exe 自带的驱动文件装（弹 UAC）；已装过的机器直接替换旧 exe |
| `VirtualDisplay-v0.3.0.zip` | 需要命令行和脚本时才下：`vdd.py` / `vdd_core.py`、`install-driver.bat`、`finish-setup.bat`、`sunshine-setup.bat`、驱动文件的磁盘副本和本 README |

装驱动**不需要** zip —— exe 里带着 `MttVDD.inf/dll/cat` 与 `devcon.exe`，
`install_driver_bundled()` 会把它们解到配置目录旁边再 `devcon install`，
并且先查已存在的设备实例，重复点不会装出第二个 `ROOT\DISPLAY\000x`。
zip 多出来的是命令行、串流配置脚本和文档。

SHA-256（exe）：`857023cb3fee9805a7c84ffc9f4e82b3459836b4677c5e0358e2f1393d29783c`
（zip 里就是这份 exe 加驱动与脚本，不单独校验；否则改一个字的文档都要重新算一次）

2026-10-14 用 MttVDD 取代了坏掉的 Parsec VDD，并把整套工具链重写为静态配置模型：
驱动读 XML 建屏，屏就一直在，不需要保活进程，也没有"驱动卡死"可恢复。

v0.1 覆盖：

- **虚拟屏**：MttVDD 驱动安装/收尾脚本，静态 XML 配置（数量、可选分辨率）
- **控制**：`vdd.py` 命令行 + Qt6 面板（同一份 `vdd_core.py`，单一实现）
- **面板**：深色无边框 UI；与 Windows 设置**实时联动**；多显示器布局
  （扩展 / 仅虚拟屏 / 仅物理屏 / 复制、虚拟屏摆位、主显示器）；真实像素分辨率与缩放显示
- **串流（Sunshine）**：两个轴分开选，切换会自动重启 Sunshine 生效
  - **串流画面**（手机看哪块屏）：跟随系统 / 物理屏 / 虚拟屏。后两项把该屏的
    device_id 写进 `output_name`（id 从 Sunshine 自己的启动枚举里取），
    「跟随系统」则删掉它，让 Sunshine 抓主显示器那块
  - **另一块屏**（只在钉住时才有意义）：保持扩展（`dd_configuration_option =
    disabled`，另一块照常可用，只是手机看不到它）/ 串流时关掉
    （`ensure_only_display`，断开后自动还原，适合外出时不想让旁人看见 PC 内容）
  - 前提事实：Sunshine 每场会话**只复制一块屏**。「跟随系统」不等于"整个桌面" ——
    窗口拖到另一块屏上，手机就看不到了。要手机看虚拟屏，要么钉住虚拟屏，
    要么把主显示器改成虚拟屏
- **可分享**：exe 内置 vdd_core/backend/应用图标/**驱动四件套 + 配置模板**，
  单文件拷到新机器即可装驱动并管理；设备实例号动态发现（不再绑定 0001）

---

## 相关文档

| 文档 | 内容 |
|---|---|
| [`docs/Sunshine-Moonlight 配置指南.md`](docs/Sunshine-Moonlight%20配置指南.md) | 整套 Sunshine + Moonlight 串流的配置与排查记录。虚拟屏只是其中第 8、11 章 |

---

## 为什么是 MttVDD

原先用的是 **Parsec VDD 0.45**，它靠 IOCTL 频繁 ADD 来维持显示器存活，
为此需要保活进程 + 守护进程 + 一整套「驱动卡死」恢复逻辑（约 750 行）。

2026-10-14 该驱动彻底失效：`IOCTL_ADD` 返回 `err=0` 但监视器级枚举恒为 0，
`REMOVE` 对索引 0~17 全部无效，**禁用/启用、restart-device、重启三样都救不回来**。
注册表里也没有可清的脏配置 —— 是驱动本身坏了。

换成 **MttVDD（VirtualDrivers/Virtual-Display-Driver 25.7.23，笔记本同款）** 后：

| | Parsec VDD | MttVDD |
|---|---|---|
| 控制模型 | IOCTL ping 保活 | **静态配置**（读 XML 建显示器）|
| 常驻进程 | 需要（2 个）| **不需要** |
| 显示器存活 | 靠持续 ping | 驱动加载即存在 |
| 「卡死」状态 | 会，且不可恢复 | **不存在这个环节** |
| 代码量 | ~750 行引擎 | **0 行引擎** |

代价：**改配置（虚拟屏数量、提供哪些分辨率）需要重载驱动**。
但日常使用几乎不需要动配置。

---

## 目录结构

```
C:\VirtualDisplay\
├─ vdd.py                       命令行入口
├─ vdd_core.py                  核心：XML 配置 + 设备查询 + 分辨率设置
├─ streamcheck.py               Sunshine/Moonlight 串流链路体检（只读诊断为主）
├─ install-driver.bat           一次性：装驱动
├─ finish-setup.bat             一次性：清重复设备、重载驱动
├─ driver\                      驱动文件（MttVDD + devcon）
│  ├─ MttVDD.inf / .dll / .cat
│  ├─ devcon.exe                创建 Root\MttVDD 设备用它
│  └─ vdd_settings.xml          我们的配置模板
├─ panel\                       现代 Qt6 面板
│  ├─ app.py                    界面
│  └─ backend.py                桥接层，import vdd_core，不自带逻辑
├─ docs\                        相关文档
└─ _archive_old_ParsecVDD\      旧 Parsec 方案归档
   └─ engine\                   750 行保活引擎、切换脚本、旧面板源码

C:\VirtualDisplayDriver\vdd_settings.xml    驱动强制要求的配置路径
```

**桌面入口**：`C:\Users\PC\Desktop\虚拟显示器.exe`

> `C:\VirtualDisplayDriver\` 是**驱动写死的路径**，无法移动 ——
> 这是唯一一处不在 `C:\VirtualDisplay\` 下的东西。

---

## 用法

### 图形界面

双击桌面 `虚拟显示器.exe`：

| 卡片 | 内容 |
|---|---|
| 状态 | 驱动设备、虚拟屏/物理屏及各自**当前分辨率与缩放**、配置摘要 |
| **显示器布局（多显示器）** | **布局示意图**（按真实坐标画每块屏，标出物理/虚拟、分辨率、主屏、缩放）+ **显示模式**（扩展 / 仅虚拟屏 / 仅物理屏 / 复制）、**虚拟屏摆位**（上下左右，当前生效那一侧会高亮）、**主显示器**切换 |
| **串流（Sunshine）** | **串流画面**（跟随系统 / 物理屏 / 虚拟屏）×**另一块屏**（保持扩展 / 串流时关掉）+ 一行明说「手机看到 = 哪块屏」，以及看不到的是哪块 |
| 虚拟屏分辨率（现在用哪个） | 从驱动提供的模式里选一个并应用，**立即生效**。滚轮要先点一下选中才生效，翻页不会误切 |
| 驱动配置（驱动提供什么） | 虚拟屏数量、分辨率清单（可增删）、重载驱动 |
| 其他 | 打开配置目录 / 项目目录 |

面板每 3 秒轮询一次，**在 Windows 设置里改分辨率/缩放/显示模式，面板会跟着变**。

> ⚠️「仅虚拟屏」会把物理显示器关掉。如果你正对着它看这个面板，屏幕会立刻变黑 ——
> 所以点了会弹二次确认。恢复方法：**`Win + P`** 循环切换，或直接点「扩展」。

需要管理员的两处（装驱动、重载驱动）会**在程序内自动弹 UAC**。

#### 示意图与「虚拟屏位置」是一体的

示意图不是装饰：每块屏的位置和大小都直接来自 `EnumDisplaySettings` 读到的真实
坐标，所以「虚拟屏在左边还是右边」一眼可判，不必点按钮试。当前生效的那一侧是
从坐标**反推**出来的（`vdd_core.virtual_side()`，与写入坐标的 `place_beside()`
共用同一套公式，四向往返自测过），因此你在 Windows 设置里手动拖动，面板的高亮
会立刻跟着变；拖到一半（不在标准摆位上）时，图下会写明「偏向某侧」。
点示意图里参照屏的某一侧，等同于点那个方向的按钮。

#### 「跟随系统」抓的是主显示器那一块，不是整个桌面

Sunshine 每场会话只复制**一块**屏：`output_name` 指定的那块，或者（未设时）
主显示器。所以扩展拓扑下把窗口拖到另一块屏，手机看不到 —— 这是这套机制的
固有行为，不是坏在这里。要让手机看虚拟屏有两条路：串流画面选「虚拟屏」，
或者把主显示器切成虚拟屏。

面板那行「手机看到 = …」是按配置推断的。要拿会话级的实证：

```bat
python streamcheck.py --where
```

它把日志里的 `Capture size / Offset` 与 Windows 当前几何对账，最后一行给
`VERDICT PASS/FAIL`。

### 命令行

```bat
vdd.py status                 当前状态（含拓扑、位置、缩放）
vdd.py modes                  驱动提供的全部模式
vdd.py set 2560x1440@60       切换虚拟屏当前模式
vdd.py config                 显示配置
vdd.py count 2                设虚拟屏数量（需 reload）
vdd.py add 1920x1200@60       往清单里加一个分辨率
vdd.py remove 1920x1080@60    从清单里删一个
vdd.py reload                 重载驱动让配置生效（需管理员）
vdd.py doctor                 完整体检
```

### 自检

```bat
虚拟显示器.exe --selftest
```

输出 `RESULT`（构建与 UI 是否正常）与 `DRIVER`（驱动实际状态）两行 ——
刻意分开，否则驱动未安装会把「代码有问题」和「环境没配好」混为一谈。

面板的 `--selftest` 还带 11 项布局卡自检：显示模式与位置按钮各只亮一个、
亮的那一侧等于坐标反推的结果、示意图拿到两块在位的屏、图下完整读数非空、
串流去向说得出是哪块屏、四个方向的点击区各自命中、点参照屏正中不挪屏。
缺任何一项 `RESULT` 就是 FAIL —— 不把「没报错」当通过。

### 串流链路体检

```bat
python streamcheck.py                静态体检：服务状态 / 端口 / conf BOM / IPv6 实测 / 上一场清理有没有挂死
python streamcheck.py --where        手机看到的到底是物理屏还是虚拟屏
python streamcheck.py --sessions     逐场会话并排对比（对端、时长、清理、协商参数、抓取的是哪块屏）
python streamcheck.py --watch 60     采样 60 秒，期间在手机上点连接（必须先人工确认没暂停）
```

判定一律打在最后一行（`VERDICT PASS/FAIL`），退出码 0/1/2，机器可读。
默认全程只读；只有 `--loglevel` / `--restart-service` / `--fix-service`
会写 conf 或动服务，且都要管理员。

---

## 配置说明

`C:\VirtualDisplayDriver\vdd_settings.xml`：

```xml
<vdd_settings>
    <monitors>
        <count>1</count>            <!-- 要几块虚拟屏 -->
    </monitors>
    <global>
        <g_refresh_rate>60</g_refresh_rate>   <!-- 这些刷新率会复制到每个分辨率上 -->
        <g_refresh_rate>120</g_refresh_rate>
        <g_refresh_rate>144</g_refresh_rate>
    </global>
    <resolutions>
        <resolution>
            <width>2560</width>     <!-- 对外提供哪些模式 -->
            <height>1440</height>
            <refresh_rate>60</refresh_rate>
        </resolution>
    </resolutions>
</vdd_settings>
```

两条要点：

1. **配置文件只决定「提供哪些模式」，不决定「当前用哪个」。**
   当前模式由 Windows 决定（并在 `ChangeDisplaySettingsEx` 里持久化）。
   要换模式用 `vdd.py set` 或面板的「当前模式」卡片。
2. **改完配置必须重载驱动**才生效。

> ⚠️ XML 注释里**不能出现连续两个连字符**（XML 语法禁止），否则驱动解析失败。

---

## 重建面板

```bat
cd C:\VirtualDisplay\panel
"C:\Program Files\Python312\python.exe" -m PyInstaller --noconfirm --clean ^
  --onefile --windowed --name VirtualDisplayPanel --icon ..\gui\app.ico ^
  --add-data "backend.py;." ^
  --hidden-import backend ^
  --hidden-import xml --hidden-import xml.etree --hidden-import xml.etree.ElementTree ^
  --hidden-import ctypes --hidden-import ctypes.wintypes ^
  app.py
copy dist\VirtualDisplayPanel.exe "C:\Users\PC\Desktop\虚拟显示器.exe"
```

**那几个 `--hidden-import` 不能省。** `panel/backend.py` 在运行时才
`import vdd_core`（从 `C:\VirtualDisplay\` 动态加载，避免逻辑重复），
PyInstaller 静态分析看不到它，于是 `vdd_core` 依赖的 `xml.etree.ElementTree`
和 `ctypes.wintypes` 都不会被打进去，运行时报 `ModuleNotFoundError`。

## 设计要点

- **单一实现**：`vdd_core.py` 是唯一的逻辑所在。CLI、面板、任何脚本都用它。
  面板的 `backend.py` 只是薄桥接（`sys.path` 插入项目根后 import），
  所以**改 `vdd_core.py` 无需重新打包面板**。
- **安全守卫**：`set_mode()` 拒绝任何非虚拟显示器，方法名写错也不会动到物理屏。
- **分辨率一律读真实像素**：用 `EnumDisplaySettings`，不用返回逻辑坐标的 API。
  否则 4K 屏在 200% 缩放下会被报成 1920x1080。
- **没有保活进程**，因此没有「进程崩了要拉起」「驱动卡死要重置」这类问题。

## 实现备注（踩过的坑）

| 现象 | 真因 |
|---|---|
| 点「主显示器 → 虚拟屏」提示成功，实际什么都没变 | `ChangeDisplaySettingsEx` 在**单次调用**里做这种会互相冲突的改动时，会**返回 0 却静默不动**：把虚拟屏设为主屏（旧主屏还占着 (0,0)）是 0 且无变化，单独把主屏挪开 (0,0) 同样是 0 且无变化（都实测过）。必须把「新主屏落 (0,0)」和「旧主屏让开」用 `CDS_NORESET` 攒成一批，最后用一次 NULL 调用统一应用 |
| exe 打包后报 `No module named 'json'` | vdd_core 新增 import 后，`--hidden-import` 清单必须同步 —— **这条已发生三次**（xml / ctypes.wintypes / json）|
| `SetDisplayConfig` 恒返回 87 | 常量记错了：`SDC_TOPOLOGY_SUPPLIED` 是 `0x10` 不是 `0x400`，且**不能**与其他拓扑标志并用。正确写法 `SDC_APPLY \| SDC_TOPOLOGY_xxx`，两个数组必须为 NULL 且长度为 0 |
| 缩放一律读成 100% | 进程未声明 DPI 感知时，Windows 会**谎报 96 dpi**。模块导入时调 `SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)` 才拿到真值 |
| 数字框黑字、列表选中项是绿的 | QSS 的 `color` 覆盖不到**走调色板渲染**的部件。必须同时装深色 `QPalette` |
| 下拉箭头背后多一块、或出现两个箭头 | 给 `::drop-down` / `::down-arrow` 写任何样式都会让 Qt 停止绘制原生部件。现在用透明 `QLabel` 覆盖层画箭头 |
| 窗口顶部一条贯穿全宽的亮线 | 子类重写 `QComboBox.paintEvent` 会破坏样式化渲染 |
| 标题栏是绿的 | Win10 上 `DWMWA_USE_DARK_MODE` 返回成功但**无任何效果**（那是 Win11 特性）。改用无边框窗口 + 自绘标题栏 |

**缩放为什么只读**：Windows 把每显示器缩放存在以 EDID 哈希命名的注册表键里
（如 `MSBDD_...^F0D7A079...`），第三方应用无法可靠推导键名，
也没有受支持的 Win32 设置接口。写错键会把**物理屏**的缩放改乱，
所以面板只显示当前值，改动交给 Windows 自己的显示设置。

## 依赖

- Python 3.12（`C:\Program Files\Python312\`，仅标准库）
- MttVDD 25.7.23 驱动（已安装，设备 `ROOT\DISPLAY\0001`）
- PyInstaller 6.21（仅重建面板时需要）

## 已知限制

- 改配置后必须重载驱动 —— 这是静态配置模型的代价，MttVDD 本身不支持热改。
- 切换串流目标要重启 Sunshine（它只在启动时读配置），所以那排按钮的高亮会在点下去
  几秒之后才回读上来 —— 那是配置还没生效完，不是没有选中态。
- 重载驱动需要管理员权限。
- 驱动二进制（`MttVDD.dll` / `.cat` / `devcon.exe`）不入版本控制，
  见 `.gitignore` 里的下载地址。
