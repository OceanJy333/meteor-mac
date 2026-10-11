---
name: win-to-mac-port
description: 把 Windows 9x/2000 时代的 32 位 EXE（老游戏、老工具，DirectX 5–7、Win32 GDI）不改原程序、不用 Wine，移植到 Apple Silicon Mac 原生运行并打包成 .app。用 REA 逆向取证，Unicorn 执行 x86，自写 Win32/DirectX → AppKit/OpenGL/CoreAudio 接口。适用于“把某个老 Windows 程序弄到 Mac 上跑”。
---

# 老 Windows 程序移植 Mac

参考实现：本仓库 `runtime/`，把 2002 年《流星蝴蝶剑》`Meteor.exe` 跑到 60fps、能玩、能分发。遇到同类问题先读对应文件，照着改，不要从零想。

## 路线

```
原版 EXE（不改）
  └─ Unicorn 执行 x86-32 指令
       └─ 导入表每个函数指向一个桩地址 → Python 实现该 API
            ├─ Win32 / GDI / Winsock      → Python + macOS
            ├─ DirectDraw / Direct3D 6     → C(OpenGL 2.1)
            ├─ DirectSound / DirectShow    → C(CoreAudio)
            └─ 窗口、键鼠、DirectInput      → Objective-C(AppKit)
```

不选的路线：
- Wine/CrossOver：用户通常明确不要，而且学不到东西。
- 重写游戏：工作量大十倍，行为对不上原版。
- 改 EXE、hook 游戏内部函数：Codex 在这条路上卡在黑屏。**只在 API 边界做事**，游戏内部一律按原样执行。

## 硬规则

1. **EXE 一字节不改，不 hook 游戏内部地址。** 只实现它导入的 API。行为不对时，错的是你的 API 实现，不是游戏。
2. **按 Windows 文档语义实现每个 API，包括失败。** 不认识的参数返回 Windows 会返回的错误码，不要返回“成功”糊过去。例：负偏移 `SetFilePointer` 返回 `0xFFFFFFFF` 并设错误 131。
3. **stdcall 要弹栈。** 每个桩返回 `(结果, 参数个数)`，参数个数错一个，栈就乱，崩在很远的地方。cdecl（msvcrt 的 `printf` 等）返回 0 个。
4. **碰到 NotImplemented 就停下来实现它**，不要先写一堆“可能用到”的 API。运行时会精确告诉你缺什么。
5. **先用 REA 看调用点再实现。** 一个 API 有多种用法时，看游戏传了什么、拿返回值做什么，只实现用到的分支。
6. **每次修改都跑到画面。** 用脚本化输入 + 定时截图看实际画面，不靠日志猜。
7. **一次只改一处，改完就跑。** 崩溃时先看“最近 15 次 API 调用 + 寄存器 + 反汇编”，再动代码。
8. **不用 Unicorn 的 `emu_start(timeout=...)`。** 超时中断会破坏 CPU 状态（本项目崩在 CRT `_ld12mul`）。事件处理放在游戏自己的 `PeekMessageA` 里。

## 阶段与过关标准

每个阶段过关后才进入下一个。卡住超过 3 次尝试，回到 [踩坑表](references/pitfalls.md) 查同类症状。

| 阶段 | 做什么 | 过关标准 |
|---|---|---|
| 0 盘点 | 记录 EXE 哈希；REA `binary_overview`；按 DLL 列出全部导入函数 | 有一张“DLL → 函数”清单，标出 DirectX 版本（看 IID 和 `DirectDrawCreate`/`Direct3DCreate`） |
| 1 装载 | PE 映射到 0x400000；一块 mmap 做 guest 内存；导入表填桩地址；建 TIB 和栈 | 跑到第一个 API 调用并打印出来 |
| 2 补 API | 循环：运行 → 缺哪个补哪个 → 再运行 | 走到 `CreateWindowExA` 和主循环 `PeekMessageA` |
| 3 窗口 | AppKit 窗口 + OpenGL 上下文；在 `PeekMessageA` 里处理 macOS 事件 | 双击 .app 能看到窗口，Dock 图标不一直跳 |
| 4 画面 | DirectDraw 表面、Present、Direct3D 绘制、GDI 文字 | 截图里主菜单和原版一致（亮度、文字、位置） |
| 5 输入 | 窗口消息（菜单点击）+ DirectInput（关卡内） | 脚本能点进关卡，角色能移动、攻击 |
| 6 声音 | DirectSound 缓冲、3D 声音、音乐（mp3 多走 DirectShow） | 导出的音频里有菜单音乐、关卡音乐、音效 |
| 7 性能 | 先测再改：帧时间、`sample` 原生栈 | 关卡内 60fps，无周期性卡顿 |
| 8 打包 | 自带 Python 的 .app，数据目录、首次设置 | 新建空数据目录、从 Finder 双击能完整跑一遍 |
| 9 体验 | 菜单栏、⌘Q、红绿灯、图标、全屏、触摸板 | 用户亲手试过 |

阶段细节：
- 架构和代码对应关系：[architecture.md](references/architecture.md)
- DirectX → OpenGL 的坑：[directx.md](references/directx.md)
- 怎么用 REA 取证：[rea-playbook.md](references/rea-playbook.md)
- 调试和自动验证：[debugging.md](references/debugging.md)
- 打包分发：[packaging.md](references/packaging.md)
- 全部踩坑记录：[pitfalls.md](references/pitfalls.md)

## 每轮循环

```
1. 运行（带 METEOR_SCRIPT 和 METEOR_SNAP）
2. 看结果：
   - NotImplementedError: X     → 用 REA 看 X 的调用点 → 实现 X → 回到 1
   - 内存错误 / 跳到 EIP 0       → 看最近的 API 和 COM 调用，多半是虚表槽位或参数个数错了
   - 没报错但画面不对            → 看截图，对照 directx.md
   - 卡住不动                    → 看 logs/live.json 的 API 计数，找在等什么（事件、定时器、回调）
3. 只改一处，回到 1
```

## 判断“完成”

全部满足才算完成，并写进 README 的“已验证”：
- 从空数据目录、Finder 双击启动。
- 主菜单 → 进入关卡 → 操作角色 → 战斗 → 声音 → 退回菜单 → 退出，全程截图或录屏为证。
- 关卡内帧率实测数字。
- 包里没有游戏文件、开发机路径（`grep -r "$HOME"`）、用户私人数据。
- 用户没法自动验证的项目（真触摸板、真按键手感）明确告诉用户去试，不写“已验证”。
