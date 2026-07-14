# -*- coding: utf-8 -*-
"""
config.py — 集中管理摄像头悬浮窗的所有可调参数。

把魔法数字集中在这里，方便日后调整，避免到处改。
"""


class Config:
    # ---- 摄像头 ----
    # -1 表示使用系统默认摄像头。
    # 运行 probe_cameras.py 查看可用设备后，填具体序号可精确选择。
    # 例如作者本机：[0] CamSplitter(虚拟) / [1] HD Pro Webcam C920(真实)
    CAMERA_DEVICE_INDEX: int = -1

    # 期望分辨率。None 表示让摄像头自选默认分辨率。
    # 720p@30 在多数摄像头(如 C920)上可用 NV12 原生格式硬解，
    # CPU/GPU 占用极低，适合"播一天不卡"。需要更高清可改 (1920,1080)。
    PREFERRED_RESOLUTION: tuple[int, int] | None = (720, 1080)

    # 期望帧率。30fps 长时间运行最稳，占用低，不卡。
    PREFERRED_FRAME_RATE: float = 30.0

    # ---- 窗口 ----
    # 初始尺寸（像素）。
    INITIAL_SIZE: tuple[int, int] = (480, 640)

    # 初始位置；None = 屏幕居中。
    INITIAL_POSITION: tuple[int, int] | None = None

    # 最小可缩放到的尺寸，防止缩成 0 后拖不回来。
    MIN_SIZE: tuple[int, int] = (80, 60)

    # ---- 交互 ----
    # 拖动窗口时按住哪个鼠标键。左键常被页面内的点击占用，
    # 但纯摄像头画面通常不需要点画面，左键拖动最自然。
    DRAG_BUTTON: str = "left"  # left / right

    # 画面缩放行为（自动，无需手动配置）：
    #   任何方向缩放窗口，画面始终填满，不留黑边，超出部分裁掉。
    #   横向拉宽 → 上下裁掉；横向收缩 → 左右裁掉。
