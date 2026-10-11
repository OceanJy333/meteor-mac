# 用 REA 取证

[REA](https://github.com/morluto/rea)（`rea-agents` MCP，后端 Hopper）负责回答“原程序到底怎么做的”。AI 负责按证据写实现。原则：**先查证据再写代码**，不要凭经验猜 API 用法。

## 问题 → 工具

| 想知道 | 用 | 例子 |
|---|---|---|
| 整体情况、导入表 | `binary_overview` | 第一步必做 |
| 某个配置、文件名、按键名在哪用 | `search_strings` → `xrefs` | 搜 `"level %d"` 找到存档读写函数 |
| 某个 API 被谁调、怎么用返回值 | `find_xrefs_to_name` → `procedure_pseudo_code` | `sendto` 找到 socket 封装，确认是 UDP |
| 崩溃地址属于哪个函数 | `resolve_containing_procedure` | 拿 EIP 查 |
| 函数伪代码 | `procedure_pseudo_code`，多个用 `batch_decompile` | |
| 调用者 | `procedure_callers` | |
| 地址附近的指令和数据 | `read_function_instructions`、`inspect_address_context` | |

参数名别猜：`search_strings` 用 `pattern`，`xrefs` / `resolve_containing_procedure` 用 `address`，`procedure_pseudo_code` / `procedure_callers` 用 `procedure`，`find_xrefs_to_name` 用 `name`，`batch_decompile` 用 `addresses`。报 `Input validation error` 时按提示改参数名。

静态看不清时，配合运行时追踪：`METEOR_TRACE=0x51f3c0,0x519400` 在执行到这些地址时打印栈参数和 EAX。静态 + 运行时两边对上再下结论。

## 本项目实际查过的问题

| 问题 | 证据 | 结论 |
|---|---|---|
| 关卡解锁存在哪 | 字符串 `"level %d\n"`，写在 `0x471710`，读在 `0x4717a0` | 存档是 `singlerec.ini`，每行 `level N`；`user.cfg` 的 `STAGE` 不是进度 |
| 联网用 TCP 还是 UDP | `sendto` 的调用者 `sub_49d6e0`，参数 1=UDP、2=TCP | 单机也起本地 UDP 服务，必须实现 Winsock |
| 音乐走哪条路 | `sub_51ec80` 初始化时先试 DirectSound，失败才用 waveOut + 线程 | 让 DirectSound 成功，省掉线程同步 |
| mp3 怎么播 | `sub_51a720` 用 DirectShow 的 6 个 IID | 模拟 FilterGraph |
| 鼠标能绑哪些键 | 按键名字符串只有 `MOUSE1`、`MOUSE2` | 不做中键、滚轮 |
| 为什么启动就开 config.exe | `CreateProcessA` 的调用点在检查 `config.ini` 之后 | 首次启动写默认配置 |
| D3D 初始化顺序 | `0x416b1e`–`0x4175b9` | 确定要实现的 DirectX 方法清单 |

## 让 REA 稳定可用

- MCP 会话可能被锁（`already open in REA session`、`unreadable_output`），通常是别的进程占着 Hopper。先结束残留的 REA/Hopper 进程。
- 一次性批量查询更稳：用 `tools/rea_batch.py` 直接起一个 stdio MCP 会话，顺序执行一组调用，结果追加到证据文件。

```bash
REA_BINARY=/path/Meteor.exe python3 tools/rea_batch.py '[["search_strings",{"pattern":"level %d"}],["procedure_pseudo_code",{"procedure":"0x471710"}]]'
```

- 把每次查询结果存成 jsonl，写报告和复盘时能引用地址和证据。
