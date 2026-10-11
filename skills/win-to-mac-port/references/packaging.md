# 打包分发

参考 `runtime/build.sh`、`runtime/launcher.c`、`runtime/paths.py`。目标：别人下载解压，双击就能玩，不用装 Python。

## .app 结构

```
流星蝴蝶剑.app/Contents/
  Info.plist
  MacOS/MeteorMac              ← C 启动器
  Resources/
    AppIcon.icns
    python/                    ← python-build-standalone 3.12 + unicorn/pefile/pillow/capstone
    runtime/                   ← .py + 编好的 .dylib (+ 可选预置 serial.txt)
```

## 步骤

1. `uv python install 3.12` 拿到 python-build-standalone；整目录拷进 `Resources/python`，删掉 test、tkinter、idlelib、include。
2. 用包内 Python `pip install` 依赖，固定版本，装完卸掉 pip。
3. 替换包内文本文件里的构建机路径（`_sysconfigdata` 等）。
4. `install_name_tool -id @rpath/libpython3.12.dylib`；启动器链接时加 `-rpath @executable_path/../Resources/python/lib`。
5. 启动器：`_NSGetExecutablePath` + `realpath` 找到 `Resources`，设 `PYTHONHOME`、`PYTHONNOUSERSITE=1`、`PYTHONDONTWRITEBYTECODE=1`，调 `Py_BytesMain` 跑 `runner.py`。
6. 编 C/ObjC 动态库：`-arch arm64 -mmacosx-version-min=12.0`。
7. 图标：脚本画 1024px 原图，`sips` 出各尺寸，`iconutil` 打 icns。**不要用游戏美术**。
8. Info.plist：`CFBundleName`/`CFBundleDisplayName`（菜单栏和 Dock 显示的名字）、`CFBundleIconFile`、`NSHighResolutionCapable`。
9. 最后检查：`grep -rlI "$HOME"` 有结果就失败。
10. `codesign --force --deep -s -`（ad-hoc），`ditto -c -k --keepParent` 打 zip。

## 数据和首次运行

| 东西 | 放哪 |
|---|---|
| 游戏文件 | 玩家自己的目录，首次运行选择后记进 `config.json`；安装盘目录用 `unshield` 解包 |
| 可写文件（存档、配置） | `~/Library/Application Support/<App>`，同时作读文件的覆盖层 |
| 日志、截图 | 数据目录下 `logs/` |
| 原版缺了就会出问题的文件 | 首次运行写默认值（本项目：`config.ini`、`singlerec.ini`） |

路径只在 `paths.py` 一处定义，其他模块只引用。

## 发布检查

- 新建空数据目录（`METEOR_DATA=/tmp/x`），从选目录开始完整跑一遍。
- 从 Finder 双击打开一次，确认窗口出现、菜单栏名字和图标正确。
- 包内不含游戏文件、构建机路径、个人数据。
- README 写清：下载、解除隔离、选游戏目录、操作表、已验证、已知限制、从源码构建。
