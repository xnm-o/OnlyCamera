# OnlyCamera

一个用 PySide6 / Qt 写的轻量级摄像头悬浮窗：**纯画面、无外框、置顶、可拖动、可缩放、可旋转**，适合把摄像头画面常驻在屏幕一角做演示、直播辅助或日常监控。

渲染交给 QtMultimedia 后端（GPU），不在 Python 层逐帧搬运图像数据，30fps 长时间运行占用极低。

![platform](https://img.shields.io/badge/platform-Windows-blue)
![python](https://img.shields.io/badge/python-3.10+-blue)
![PySide6](https://img.shields.io/badge/PySide6-6.5+-green)
![license](https://img.shields.io/badge/license-MIT-yellow)

## 功能特性

- **纯画面悬浮窗**：无标题栏、无外框，不占用任务栏，始终置顶。
- **拖动 & 缩放**：左键拖动移动；点窗口边缘拖动可调整大小，光标自动提示方向。
- **画面旋转**：随时按 `R` 顺时针旋转 90°（0/90/180/270），适合横竖屏切换。
- **多摄像头切换**：右键菜单可实时选择系统中的任意摄像头，切换失败自动回滚。
- **零黑边填充**：任意缩放比例下画面始终填满窗口、严格覆盖，不留黑边。
- **低占用长跑**：GPU 渲染 + 原生格式（NV12/YUYV）优先，避开需解码的 JPEG。
- **高 DPI 友好**：缩放显示下画面依然清晰。

## 环境要求

- Windows 10 / 11
- Python 3.10 及以上（在 3.14 上测试通过）
- 一个可用的摄像头
- [PySide6](https://doc.qt.io/qtforpython-6/) ≥ 6.5

> 跨平台说明：代码使用 Qt 的标准多媒体/窗口 API，理论上可在 macOS / Linux 运行，
> 但仅在实际开发与测试于 Windows。其他平台如有问题欢迎提 issue。

## 安装

```bash
git clone https://github.com/YinShengJie/OnlyCam.git
cd OnlyCam
pip install -r requirements.txt
```

## 使用

```bash
python main.py
```

也可以双击仓库根目录下的 `启动摄像头悬浮窗.bat` 快速启动（Windows）。

### 操作说明

| 操作 | 效果 |
| --- | --- |
| 左键拖动窗口 | 移动窗口 |
| 左键拖动窗口边缘 | 调整大小（带方向光标提示） |
| 右键 | 弹出菜单：选择摄像头 / 旋转 / 切换置顶 / 退出 |
| `R` | 画面顺时针旋转 90° |
| `Esc` 或 `Q` | 退出 |

### 配置摄像头

所有可调参数集中在 [`config.py`](config.py)：

```python
class Config:
    CAMERA_DEVICE_INDEX: int = -1            # -1 = 系统默认摄像头
    PREFERRED_RESOLUTION: tuple[int, int] | None = (720, 1080)
    PREFERRED_FRAME_RATE: float = 30.0
    INITIAL_SIZE: tuple[int, int] = (480, 640)
    ...
```

想精确指定某个摄像头？先运行探测脚本查看设备列表：

```bash
python probe_cameras.py
```

输出示例：

```
detected 2 camera device(s):
  [0] CamSplitter
        -> 1920x1080 @ 30.0 fps  (Format_Jpeg)
  [1] HD Pro Webcam C920
        -> 1280x720 @ 30.0 fps  (Format_NV12)
        -> 1920x1080 @ 30.0 fps  (Format_Jpeg)
```

然后把 `CAMERA_DEVICE_INDEX` 改成对应的序号即可。

## 项目结构

```
.
├── main.py              # 入口：创建 QApplication 与 CameraWindow
├── camera_window.py     # 核心：无外框置顶窗口、渲染、拖动/缩放/旋转、菜单
├── config.py            # 所有可调参数集中于此
├── probe_cameras.py     # 摄像头设备探测工具
├── requirements.txt     # 依赖
├── 启动摄像头悬浮窗.bat   # Windows 一键启动脚本
└── README.md
```

## 技术要点

- 用 `QGraphicsView` + `QGraphicsVideoItem` 而非 `QVideoWidget`：两者都走 GPU 渲染，但只有前者支持 `setRotation()`，可实现 90° 步进旋转。
- 让 `QGraphicsView` 对鼠标事件透明（`WA_TransparentForMouseEvents`），鼠标事件穿透到父窗口，拖动/缩放才能由 `CameraWindow` 统一处理。
- 不用 `fitInView`（存在 1-2px 精度误差会露白边），改为手动计算缩放比例 + `QTransform`，确保画面严格覆盖 viewport。
- 摄像头格式选择优先匹配目标分辨率 + 原生格式（NV12/YUYV）+ 接近帧率，避开需要解码的 JPEG，长时间运行占用最低。
- 摄像头切换失败时保留旧摄像头对象用于回滚，并弹窗提示，避免黑屏。

## 许可证

[MIT License](LICENSE) © 2026 

## 贡献

欢迎提 issue 或 PR。如果是大改动，建议先开 issue 讨论方案。
