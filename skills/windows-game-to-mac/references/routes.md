# 选路线与 API 对照

先判断游戏属于哪一类，再决定路线。判断全部靠证据：PE 头、导入表、文件清单，用 REA `binary_overview` 和 `inspect_artifact` 拿。

## 第一步：分类

| 看什么 | 怎么看 | 意味着 |
|---|---|---|
| 位数 | PE `Machine`：`0x14c` = x86，`0x8664` = x64 | Unicorn 两种都支持；x64 用 Windows x64 调用约定（RCX/RDX/R8/R9 + 32 字节影子空间），桩写法不同 |
| 有没有托管代码 | 有 CLR 头，或目录里有 `*.dll` + `Assembly-CSharp.dll`、`Mono`、`UnityPlayer.dll` | 走托管路线，见下表 |
| 图形 API | 导入了 `ddraw` / `d3d8` / `d3d9` / `d3d11` / `opengl32`，或只有 `gdi32` | 决定图形层工作量 |
| 声音 | `dsound`、`winmm`（waveOut / MCI CD 音轨）、`xaudio2`、FMOD/Miles/BASS 等 DLL | 第三方音频 DLL 也是 x86 代码，一起模拟执行，只实现它们导入的系统 API |
| 视频 | Bink（`binkw32.dll`）、Smacker、私有格式 | 第三方 DLL 一起模拟；私有格式可先让打开失败跳过 |
| 网络 | `wsock32` / `ws2_32` / `dplayx` | 单机游戏也可能起本地服务器，不能直接返回失败 |
| 保护 | 光盘检查、加壳（UPX、SecuROM、SafeDisc） | UPX 可先脱壳；驱动级保护（SafeDisc 2+）这条路线做不了 |

## 第二步：选路线

| 游戏类型 | 路线 | 说明 |
|---|---|---|
| 2005 年前的 x86 游戏，DirectX 3–9 / OpenGL / GDI | **本 skill 的主路线**：Unicorn 执行原版 + 自写 API | 《流星蝴蝶剑》属于这一类。工作量主要在图形层 |
| 有官方开源代码或引擎源码（id Tech、Build 引擎等） | 直接原生编译，SDL2 做平台层 | 比模拟快得多；用户限定“不用社区实现”时仍用本路线 |
| .NET / XNA 游戏 | 托管代码在 Mac 的 .NET 上直接跑，只替换 XNA 等框架为同接口实现 | 用 REA 的 managed 工具（`inspect_managed_artifact`、`inspect_managed_native_boundaries`）找出原生边界 |
| Unity / Unreal 等现代引擎，D3D11/12，x64 | 不建议本路线 | D3D11+ 的接口量和着色器翻译远超一个人能做的范围 |
| DOS 游戏 | 不是 Windows 程序 | 用 DOS 模拟器 |

主路线工作量参考（《流星蝴蝶剑》，DX6）：运行时约 2400 行，其中图形约 1000 行、声音约 400 行、Win32 和 COM 约 400 行。

## 第三步：API 对照

### 图形

| Windows | Mac 实现 | 要点 |
|---|---|---|
| DirectDraw（2D 游戏） | 表面放 guest 内存，软件 Blt，呈现时上传成一张贴图画满窗口 | 调色板 8 位模式要在上传时查表；`Lock` 返回 guest 指针 |
| Direct3D 5–7 | OpenGL 2.1 固定管线 | 见 [directx.md](directx.md)：RHW 顶点、深度范围、TSS→`GL_COMBINE`、DX6 光照衰减 |
| Direct3D 8/9 固定管线 | 同上 | 顶点缓冲、索引缓冲、`SetTextureStageState` 基本相同 |
| Direct3D 8/9 着色器 | 把 `vs_1_1`/`ps_1_x`–`3_0` 字节码翻译成 GLSL | 工作量大，先确认游戏是否真的用了 |
| OpenGL（opengl32） | 直接转发给 macOS 的 OpenGL 2.1 兼容上下文 | 最省事；`wglGetProcAddress` 要返回扩展函数的桩 |
| GDI 绘图 | 软件绘制到 DIB，必要时 C 加速 | `TextOutA` 用 PIL 或 CoreText 画字，按显示倍率栅格化 |
| 全屏 / 分辨率切换 | 不切真实分辨率，固定画布 + 窗口内等比缩放 | 以 `SetDisplayMode` / `ChangeDisplaySettings` 为准 |

macOS 的 OpenGL 已弃用但仍可用，最高 4.1 core / 2.1 兼容。固定管线游戏用 2.1 兼容上下文最直接。

### 输入

| Windows | Mac 实现 |
|---|---|
| 窗口消息 `WM_KEY*`、`WM_MOUSE*` | NSEvent → 虚拟键码 → 消息队列 |
| `GetAsyncKeyState` / `GetKeyState` | 宿主维护的按键表 |
| DirectInput 键盘 | DIK 扫描码表（`input.py` 有完整映射） |
| DirectInput 鼠标 | 原始相对位移；点击画面锁定鼠标 |
| DirectInput / WinMM 手柄、XInput | GameController 框架 |
| 触摸板 | 双指滑动（精确滚动增量）当鼠标位移，键盘代替按键 |

### 声音

| Windows | Mac 实现 |
|---|---|
| DirectSound / 3D 声音 | CoreAudio AudioUnit 混音，直接读 guest 缓冲 |
| waveOut | 同一个混音器的队列 |
| DirectShow 播 mp3 | ExtAudioFile 解码 |
| MCI CD 音轨 | 映射到目录里的音轨文件（玩家从光盘抓取） |
| `timeSetEvent` | 在消息循环里按时触发回调 |

### 系统

| Windows | Mac 实现 |
|---|---|
| 文件 | 游戏目录只读 + 数据目录覆盖层；文件名不区分大小写；`\` → `/` |
| 注册表 | 内存字典，初值从安装器逆向得出（序列号、安装路径） |
| 线程、事件、临界区 | 优先避开（让游戏走单线程路径）；必须时用协作式调度，在 API 调用点切换 |
| Winsock | BSD socket 直通 |
| 光盘检查 | `GetDriveTypeA` 返回光驱，`GetVolumeInformationA` 返回原盘卷标 |
