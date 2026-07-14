# -*- coding: utf-8 -*-
"""
probe_cameras.py — 探测系统摄像头设备列表与默认分辨率。

输出可用于在 config.py 里精确指定 CAMERA_DEVICE_INDEX / 分辨率。
用法：  python probe_cameras.py
"""

from PySide6.QtCore import QCoreApplication
from PySide6.QtMultimedia import QMediaDevices


def main() -> None:
    # 必须先有 QCoreApplication 实例，Qt 的媒体后端才能正常枚举设备
    app = QCoreApplication([])
    cams = QMediaDevices.videoInputs()
    print(f"detected {len(cams)} camera device(s):")
    for i, cam in enumerate(cams):
        print(f"  [{i}] {cam.description()}")
        for fmt in cam.videoFormats():
            w, h = fmt.resolution().width(), fmt.resolution().height()
            lo = float(fmt.minFrameRate()) if fmt.minFrameRate() > 0 else 0.0
            hi = float(fmt.maxFrameRate()) if fmt.maxFrameRate() > 0 else 0.0
            if lo and hi:
                fps = f"{lo:.1f} ~ {hi:.1f}"
            elif hi:
                fps = f"{hi:.1f}"
            else:
                fps = "?"
            print(f"        -> {w}x{h} @ {fps} fps  ({fmt.pixelFormat()})")


if __name__ == "__main__":
    main()
