# -*- coding: utf-8 -*-
"""
main.py — 摄像头悬浮窗入口。

用法：
    python main.py

效果：
    屏幕上出现一块纯摄像头画面，无外框、置顶在所有窗口之上。
    - 左键拖动 = 移动窗口
    - 左键拖动窗口边缘 = 调整大小（带方向光标提示）
    - 右键 = 弹出菜单（置顶切换 / 退出）
    - ESC 或 Q = 退出

长时间运行不卡的关键：渲染交给 QtMultimedia 后端（GPU），
不在 Python 层逐帧搬运图像数据。
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from camera_window import CameraWindow
from config import Config


def main() -> int:
    # 高 DPI 支持：画面在缩放显示下也清晰
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("摄像头悬浮窗")
    app.setQuitOnLastWindowClosed(True)

    try:
        window = CameraWindow()
    except RuntimeError as exc:
        # 摄像头不可用等错误，弹窗提示而不是直接崩溃
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.critical(None, "摄像头启动失败", str(exc))
        return 1

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
