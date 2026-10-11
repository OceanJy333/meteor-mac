# 踩坑表

按症状查。每条都是《流星蝴蝶剑》移植中真实发生过的。

## 启动和执行

| 症状 | 原因 | 修法 |
|---|---|---|
| 崩在 CRT 浮点函数（`_ld12mul`），地址看着正常 | `emu_start` 用了 timeout，超时打断破坏 CPU 状态 | 去掉 timeout，`emu_start(pc, 0xffffffff)`；事件在 `PeekMessageA` 里处理 |
| 跳到 EIP 0，指令是 `call [edx+0x38]` | COM 虚表槽位编号错了，调到空槽 | 用 SDK 头文件数槽位（IUnknown 占 0–2）。例：`IDirect3DViewport3` 的 AddLight/DeleteLight/NextLight 是 13/14/15 |
| 崩在离 API 调用很远的地方 | stdcall 参数个数写错，栈错位 | 核对每个桩返回的参数个数；对照 MSDN 原型 |
| `'int' object has no attribute 'pop'` 一类 Python 错 | 回调队列新旧格式混用 | 所有 guest 回调（WndProc、枚举回调、定时器）走同一个队列 |
| 启动后马上 `CreateProcessA("config.exe")` 然后退出 | 首次运行缺 `config.ini`，原版去开设置工具 | 首次启动写一份默认配置 |
| 文件找不到，但文件明明在 | Windows 文件名不区分大小写 | 路径解析时按小写匹配目录项 |
| 存档写进了游戏目录 | 没区分只读游戏目录和可写数据目录 | 写操作一律落到数据目录；读时数据目录优先（覆盖层） |
| `SetFilePointer` 抛 OSError | 游戏对空文件 seek 到 -1 | 照 Windows 返回 `0xFFFFFFFF`，错误码 131 |
| 序列号校验不过 | 安装器会把 CD Key 变换后写进注册表 | 用 REA 读安装器的变换函数，按原算法生成注册表值 |

## 窗口和事件

| 症状 | 原因 | 修法 |
|---|---|---|
| 双击 .app，Dock 图标一直跳，没有窗口 | 游戏主循环里没处理 macOS 事件，系统认为 App 没启动完 | 在 `PeekMessageA` 里每 8ms 调一次 `host_pump`（`nextEventMatchingMask` 循环） |
| 脚本测试一切正常，用户却打不开 | 脚本只读渲染结果，不经过真实的窗口显示 | 每次打包后从 Finder 双击实测一次 |
| 红绿灯、标题栏点不动 | 游戏把所有鼠标点击都吞了 | 鼠标未锁定且点在内容区外的事件交给 `[NSApp sendEvent:]` |
| ⌘Q 没反应 | 没有主菜单 | `finishLaunching` 前建菜单：退出 ⌘Q、隐藏 ⌘H、最小化 ⌘M、全屏 ⌃⌘F；带 ⌘ 的键盘事件交给 AppKit |
| 关窗口进程还在 | 没处理窗口关闭 | 窗口代理 `windowWillClose` → `[NSApp terminate:nil]` |
| 窗口大小 0×0 | 同 Dock 跳动，事件没处理 | 同上 |
| 你说窗口在，用户看不到 | 你的终端/IDE 在全屏空间，游戏在桌面空间 | 先排除这个再改代码 |

## 画面

| 症状 | 原因 | 修法 |
|---|---|---|
| 调 OpenGL 函数段错误（游戏自己调 `glDisable`） | 游戏引擎共用初始化代码，D3D 模式下也调 opengl32 | 没有当前 WGL 上下文时，opengl32 全部当空操作（Windows 就是这样） |
| `glPushAttrib` 段错误 | 软件路径先加载了图形库，误以为 GL 上下文已建好 | 把“库已加载”和“上下文已就绪”分成两个状态 |
| 主菜单很暗 | 点光源衰减按 DX7+ 公式算 | DX5/6 的 `D3DLIGHT2`：先把距离归一化 `d'=(range-d)/range`，再算 `att0+att1·d'+att2·d'²`；超出 range 熄灭。详见 directx.md |
| 以为“暗是原版美术” | 只查了伽马和贴图混合 | 菜单是 3D 面片加点光源。暗先查光照 |
| 截图一直不更新 | Present 不走 Flip，而是 `Blt(后缓冲 → 主表面)` | 在那条 Blt 路径上也做交换和截图 |
| 文字、HUD 不见 | 游戏在渲染目标上 `GetDC` 后用 GDI 画字 | `GetDC` 不回读显存；`TextOutA`/`FillRect` 直接用 GL 画 |
| 中文字模糊 | 按 640×480 栅格化后放大 | 按显示倍率栅格化文字并缓存 |
| 画面锯齿、贴图糊 | 默认最近点采样 | 3D 贴图开三线性 + 各向异性，开 4x MSAA；Retina 用 `wantsBestResolutionOpenGLSurface` |
| 改了 user.cfg 分辨率没用 | 游戏实际按 `SetDisplayMode` 的参数走 | 以 `SetDisplayMode` 为分辨率唯一来源，窗口缩放交给宿主 |

## 输入

| 症状 | 原因 | 修法 |
|---|---|---|
| 菜单点击时灵时不灵 | 脚本点击早于菜单加载完 | 脚本时间留余量，或等截图确认画面后再点 |
| 关卡内鼠标转视角不动 | DirectInput 读的是相对位移，不是光标位置 | 宿主提供未截断的原始累计位移（raw），DirectInput 取差值 |
| 鼠标出窗口后乱转 | 没锁定鼠标 | 点击画面锁定（`CGAssociateMouseAndMouseCursorPosition(false)` + 隐藏光标），按 ⌘ 或失焦释放 |
| 中键、滚轮没反应 | 原版只绑定了 MOUSE1/MOUSE2 | REA 搜按键名字符串确认，别实现不存在的绑定 |
| 触摸板没法边滑边按 | 物理限制 | 双指滑动（精确滚动增量）当视角，J/K 代替左右键 |
| 程序模拟的滚动事件没反应 | `CGEventPostToPid` 的滚动事件不会路由到窗口 | 这项无法自动验证，交给用户实测 |

## 声音

| 症状 | 原因 | 修法 |
|---|---|---|
| 菜单无声 | 音乐是 mp3，走 DirectShow `IGraphBuilder::RenderFile` | 模拟 FilterGraph（RenderFile、IMediaControl、IMediaSeeking、IMediaEventEx、IBasicAudio），解码用 ExtAudioFile |
| 引擎走 waveOut + 线程，要 `CreateEventA` 等一堆同步原语 | DirectSound 创建失败时的后备路径 | 让 `CoCreateInstance(CLSID_DirectSound)` 成功，引擎改走 DirectSound + 定时器，路径更简单 |
| 音效断断续续 | 引擎用 `timeSetEvent` 25ms 定时器填循环缓冲 | 实现定时器，在 `PeekMessageA` 里按时触发回调 |
| 3D 音效 QueryInterface 失败 | 缺 `IDirectSound3DListener` / `IDirectSound3DBuffer` | 实现简单的距离衰减 + 左右声道 |
| 片头视频 `.mv` | 私有格式 | 让打开失败，游戏会跳过 |

## 性能

按顺序排查，每步测帧时间：

| 现象 | 原因 | 修法 | 效果 |
|---|---|---|---|
| 关卡 20fps | `TextOutA` 用 Python 逐像素画字 | 改 C | 20 → 46fps |
| 每帧上万次 COM 调用 | 每次调用都走名字判断链 | 缓存 “Kind:槽位” 分发 | 明显 |
| 每 2 秒一次 35–40ms 卡顿 | Python GC | 启动后 `gc.freeze()` 并调高阈值 | 小 |
| 参数读取慢 | 逐个 `mem_read` | guest 内存就是宿主 mmap，`struct.unpack_from` 一次读 17 个 | 明显 |
| 每帧回读整个渲染目标 | GDI 画字触发回读 | GL 直接画字 | 明显 |
| 剩余开销在 Python 桩 | 热点 D3D 方法（SetRenderState、DrawPrimitive 等） | C 快速路径直接挂 Unicorn 钩子，不进 Python；状态不满足时跳回 Python 桩 | 38 → 60fps |
| C 库 `dlopen` 报找不到 `_uc_hook_add` | Python 私有加载的 libunicorn 符号不可见 | 从 Python 把函数指针传给 C | 修复 |
| Python 块钩子慢到进不了菜单 | 每个基本块回调 Python | 统计放 C 里 | 修复 |
| 进关卡 9 秒 | Unicorn 内部写内存脏页跟踪 | 已排除自修改代码；没有便宜的修法，接受 | — |

## 打包

| 症状 | 原因 | 修法 |
|---|---|---|
| 包里残留开发机路径 | Python 的 `_sysconfigdata` 等写死了构建路径 | 构建时替换，最后 `grep -r "$HOME"` 有就失败 |
| 别人机器上找不到 libpython | 动态库 install name 是绝对路径 | `install_name_tool -id @rpath/...`，启动器加 rpath |
| 打包脚本的检查误伤注释 | 注释里出现了被检查的字符串 | 改注释措辞，检查保持严格 |
| 首次打开被拦截 | 未公证 | README 写右键打开或 `xattr -dr com.apple.quarantine` |
| Dock 图标还是旧的 | 图标缓存 | 重新打开或 `lsregister -f` |
