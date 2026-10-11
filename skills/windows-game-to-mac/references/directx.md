# DirectX 5–7 → OpenGL / CoreAudio

实现在 `runtime/ddraw.py` `d3d.py` `d3dgl.c` `dsound.py` `dshow.py` `audio.c`。下面是容易做错、做错后症状不明显的点。

## 先确定版本

看游戏 QueryInterface 了哪些 IID（Data1）：

| Data1 | 接口 |
|---|---|
| `6c14db80` / `b3a6f3e0` / `9c59509a` | IDirectDraw / IDirectDraw2 / IDirectDraw4 |
| `6c14db81` / `57805885` / `da044e00` / `0b2b8630` | IDirectDrawSurface / 2 / 3 / 4 |
| `3bba0080` / `6aae1ec1` / `bb223240` | IDirect3D / 2 / 3 |
| `2cdcd9e0` / `93281502` | IDirect3DTexture / 2 |
| `279afa85` / `279afa84` / `279afa86` | DirectSoundBuffer / 3DListener / 3DBuffer |
| `56a868a9` `56a868b1` `36b73880` `56a868c0` `56a868b3` | DirectShow FilterGraph、MediaControl、MediaSeeking、MediaEventEx、BasicAudio |

DX6（DDraw4 + D3D3 + Device3）用 `DrawPrimitive` + FVF 顶点格式，最好做。DX5 的执行缓冲（Execute Buffer）更麻烦。

虚表槽位以 SDK 头文件 `ddraw.h` / `d3d.h` 的方法顺序为准，自己数，IUnknown 占 0–2。

## 顶点和矩阵

- **已变换顶点（XYZRHW）**：按 `(x·w, y·w, z·w, w)` 提交，`w = 1/rhw`，配正交投影。这样透视校正插值才对。
- **D3D 深度范围是 [0,1]**，GL 是 [-1,1]：投影矩阵要修正。
- D3D 是行向量 × 矩阵，直接 `glLoadMatrixf` 同一块内存即可（两边的内存顺序刚好一致）。
- 顶点在 guest 内存里，C 直接按 FVF 解析，转成统一格式后用 client array 画。

## 光照

- FVF 带法线且没设 `D3DDP_DONOTLIGHT (0x10)` 才开光照。
- **DX5/6 `D3DLIGHT2` 的衰减和 DX7 不同**：

  ```
  d' = (range - d) / range         // 归一化距离，0..1
  a  = att0 + att1·d' + att2·d'²   // a 是亮度倍数，不是除数
  d > range 时灯熄灭
  ```

  按 DX7 的 `1/(att0 + att1·d + att2·d²)` 算，菜单只剩 0.3% 的光，整体发暗。GL 固定管线没有这种公式：按每次绘制的网格中心（顶点平均 × 世界矩阵）算出 `a`，设 `GL_CONSTANT_ATTENUATION = 1/a`，其余衰减为 0。
- 环境光来自 `SetLightState(AMBIENT)`；材质 17 个 float 照搬。

## 贴图

- 16 位格式：565、1555、4444、555，外加 8888。统一转成 RGBA8 上传。
- 色键（color key）透明：转换时把等于色键的像素 alpha 设 0，配合 alpha test。
- 纹理阶段状态（TSS）映射到 `GL_COMBINE`：MODULATE、MODULATE2X/4X（`GL_RGB_SCALE`）、SELECTARG、ADD 等。
- 老式渲染状态 `TEXTUREHANDLE (1)` 和 `TEXTUREMAPBLEND (21)` 也要支持，有的引擎混用。
- 3D 贴图开 mipmap、三线性、各向异性；2D 界面贴图（RHW）保持原样，不然文字会糊。

## 表面和呈现

- 主表面 + 后缓冲链、mipmap 链在 `CreateSurface` 里一次建好。链尾 `GetAttachedSurface` 返回 `DDERR_NOTFOUND`，是正常的。
- **呈现方式不一定是 Flip。** 本游戏用 `Blt(后缓冲 → 主表面)`。两条路都要能交换缓冲。
- `Lock` 直接返回 guest 内存里的像素指针；如果像素在 GL 里要先回读。
- `GetDC` 拿渲染目标的 DC 画 GDI 文字：别回读，记下这个 DC，`TextOutA` / `FillRect` 直接用 GL 画。
- 分辨率以 `SetDisplayMode` 为准，游戏坐标映射到窗口里 4:3 的区域，两侧留黑边。

## 引擎同时调 OpenGL

有的引擎初始化时无论用哪个渲染器都会调 opengl32（本游戏在 `0x4cd29d` 调 `glDisable`）。Windows 上没有当前 WGL 上下文时这些调用什么也不做。照做：没 `wglMakeCurrent` 时 `gl*` 全返回 0，并按 stdcall 参数个数弹栈（`opengl_noop.py` 有参数表）。

## 声音

- `IDirectSoundBuffer::Lock` 返回 guest 内存指针，混音器（CoreAudio AudioUnit 回调）直接读，不拷贝。
- 引擎常见做法：一个循环缓冲 + `timeSetEvent` 定时器往里填。定时器必须实现且按时触发。
- 能走 DirectSound 就别让它退回 waveOut：后者要线程、事件等同步原语。
- mp3 背景音乐多半走 DirectShow：`RenderFile` 时用 ExtAudioFile 解码成 44.1k 立体声；`GetEvent` 播完返回一次 `EC_COMPLETE`，游戏才会循环。
