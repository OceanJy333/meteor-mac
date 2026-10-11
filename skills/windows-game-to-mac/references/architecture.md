# 架构

代码在仓库 `runtime/`。新项目先把这几块原样搬过去，再按目标程序的导入表增删 API。

## 内存布局

| guest 地址 | 用途 |
|---|---|
| `0x0–0x10000` | TIB（fs:0），SEH 链头写 `0xFFFFFFFF` |
| `0x400000–0x800000` | PE 映像（`pefile.get_memory_mapped_image()`） |
| `0x1000000–0x2000000` | 栈，ESP 初值 `0x1FFFF00`，栈顶放一个 `ExitProcess` 返回地址 |
| `0x10000000–0x60000000` | 堆（`heap.py`，2 的幂分级 + 空闲链表） |
| `0x70000000` 起 | API 桩，每个 16 字节，内容是 `ret` |
| `0x70080000` 起 | C 快速路径桩 |

关键做法：**整个 guest 内存是一块宿主 `mmap`**，用 `mem_map_ptr` 挂给 Unicorn。于是“宿主指针 = 基址 + guest 地址”，C 代码直接读写 guest 内存，零拷贝。顶点数组、贴图、声音缓冲都这样传给 OpenGL 和 CoreAudio。见 `runner.py` 开头。

## API 桩分发

1. 遍历导入表，每个函数分配一个桩地址写进 IAT。按序号导入的命名为 `DLL#序号`。
2. 在桩地址范围挂 `UC_HOOK_CODE`。命中时从栈上一次读出返回地址和 16 个参数。
3. 调 `Win32.call(name, args)`，返回 `(结果, 参数个数)`。
4. 写 EAX，ESP 加 `4 + 4×参数个数`，EIP 设为返回地址。

COM 方法也走同一套：每种接口一张 64 槽虚表，槽位桩名为 `Kind:槽位`（如 `Dev3:28` 是 DrawIndexedPrimitive）。`com.py` 负责：
- 同一个对象每种接口一个 guest 指针，QueryInterface 来回稳定。
- QueryInterface 按 IID 的 Data1 查表；不支持的打印 `QI unsupported` 和完整 GUID，便于补。
- 槽位 0/1/2 是 IUnknown，Release 到 0 调 `on_release`。

## guest 回调

窗口过程、枚举回调（`EnumDevices`、`EnumDisplayModes`）、多媒体定时器都要“从 API 里回调游戏代码”。做法：
- API 实现里调用 `queue_callbacks([(函数地址, [参数...])], final)`。
- API 返回后，保存寄存器，把参数和 `CallbackDone` 桩作为返回地址压栈，跳到回调。
- 回调返回到 `CallbackDone`：队列还有且上次返回非 0 就继续下一个（枚举语义），否则恢复寄存器，回到原调用点。

## 消息循环

游戏的 `PeekMessageA` 是唯一的“心跳”：
- 处理 macOS 事件（`host_pump`），不然窗口不上屏。
- 触发到期的 `timeSetEvent` 定时器。
- 每 2 秒写 `logs/live.json`（API 计数、堆、错误）。

## 渲染目标状态

渲染目标的像素可能在系统内存，也可能在 GL 后缓冲。用 `loc` 记录：
- `sys`：系统内存里的是最新的（软件 Blt、Lock 写过）。
- `gl`：GL 里的是最新的（D3D 画过）。
- `lost`：刚交换完，内容无效。

需要哪边就按需上传或回读（`to_sys` / `to_gl`）。尽量不回读，回读很慢。

## C 快速路径

热点 D3D 方法（`Dev3` 的 21/22/25/26/28/29/37/38/39/40）由 `fast.c` 直接处理，不进 Python：
- Python 把 Unicorn 的 `uc_hook_add`、`uc_reg_read`、`uc_reg_write` 函数指针传给 C。
- 有一个“闸门”：渲染目标不在 GL、灯光或材质有改动时关闭，C 直接跳到同名 Python 桩。
- 贴图 GL id 按 guest 指针缓存，表面变脏就作废。

先用 Python 把行为做对，再把测出来的热点搬进 C。

## 文件职责

| 层 | 文件 |
|---|---|
| 入口、装载、分发 | `runner.py` `heap.py` `com.py` `paths.py` |
| Win32 | `win32.py` `window.py` `registry.py` `file_search.py` |
| 图形 | `ddraw.py` `d3d.py` `gdi.py` `opengl.py` `opengl_noop.py` + `d3dgl.c` `fast.c` `pixels.c` |
| 声音 | `dsound.py` `dshow.py` + `audio.c` |
| 网络 | `winsock.py` |
| 宿主 | `host.m` `host.py` `input.py` |
| 打包 | `launcher.c` `build.sh` `make_icon.py` |
