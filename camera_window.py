# -*- coding: utf-8 -*-
"""
camera_window.py — 无外框、置顶、可拖动可缩放、可旋转的摄像头悬浮窗。

设计要点（对应"播一天不卡"的诉求）：
  * 用 QtMultimedia 的 QCamera + QGraphicsVideoItem，渲染走 GPU，
    不在 Python 层逐帧拷贝图像，30fps 长跑占用极低。
  * QGraphicsVideoItem 支持 setRotation()，可 90° 步进旋转画面。
  * 窗口无外框(FramelessWindowHint) + 工具窗口样式，
    实现"纯画面嵌在屏幕里"的效果。
  * 拖动靠 mousePressEvent/mouseMoveEvent 自己算偏移；
    缩放靠 mousePressEvent 命中边缘区域。
  * 右键菜单提供：旋转、切换置顶、关闭。
  * ESC 退出，R 旋转 90°。
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, QSizeF, QTimer, Qt, Signal
from PySide6.QtGui import QTransform
from PySide6.QtGui import QAction, QKeySequence, QMouseEvent, QShortcut
from PySide6.QtMultimedia import QCamera, QMediaCaptureSession, QMediaDevices
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QMenu, QWidget

from config import Config


class CameraWindow(QWidget):
    """无外框置顶的摄像头悬浮窗。"""

    # 外部可监听：关闭信号
    closed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._drag_offset: QPoint | None = None
        self._resize_dir: str | None = None
        self._resize_start_pos: QPoint = QPoint()
        self._resize_start_rect = self.rect()

        self._camera: QCamera | None = None
        self._session: QMediaCaptureSession | None = None
        self._current_device_index: int = Config.CAMERA_DEVICE_INDEX
        self._video_item: QGraphicsVideoItem | None = None
        self._graphics_view: QGraphicsView | None = None
        self._graphics_scene: QGraphicsScene | None = None
        self._rotation: int = 0  # 当前旋转角度，0/90/180/270

        self._build_ui()
        self._apply_window_flags()
        self._apply_initial_geometry()
        self._setup_camera()
        self._setup_shortcuts()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        # QGraphicsView + QGraphicsVideoItem 组合：
        #   - 渲染仍然走 GPU（和 QVideoWidget 一样）
        #   - 但支持 setRotation()，QVideoWidget 不支持
        self._graphics_scene = QGraphicsScene(self)
        self._video_item = QGraphicsVideoItem()
        self._graphics_scene.addItem(self._video_item)

        self._graphics_view = QGraphicsView(self._graphics_scene, self)
        # 背景纯黑：任何边缘缝隙都不会露出白边
        self._graphics_view.setStyleSheet("background-color: black;")
        self._graphics_scene.setBackgroundBrush(Qt.GlobalColor.black)
        # 无滚动条、无边框，画面填满视图
        self._graphics_view.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._graphics_view.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._graphics_view.setFrameStyle(0)
        self._graphics_view.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.FullViewportUpdate
        )
        # 关键：让 GraphicsView 对鼠标事件透明，
        # 这样鼠标事件会穿透到父窗口 CameraWindow，拖动/缩放才能工作。
        self._graphics_view.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self._graphics_view.show()

        # 监听视频首帧到达，触发 fit（刚启动时 nativeSize 为 0x0）
        self._video_item.nativeSizeChanged.connect(self._fit_video_item)

        # 开启鼠标追踪：不按住鼠标键时也能收到 mouseMoveEvent，用于更新光标形状。
        self.setMouseTracking(True)

    def _apply_window_flags(self) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint  # 无外框
            | Qt.WindowType.Tool  # 不出现在任务栏，保持轻量
            | Qt.WindowType.WindowStaysOnTopHint  # 置顶
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMinimumSize(*Config.MIN_SIZE)

    def _apply_initial_geometry(self) -> None:
        w, h = Config.INITIAL_SIZE
        if Config.INITIAL_POSITION is not None:
            self.move(*Config.INITIAL_POSITION)
        else:
            screen_geo = self.screen().availableGeometry()
            self.move(
                screen_geo.center().x() - w // 2,
                screen_geo.center().y() - h // 2,
            )
        self.resize(w, h)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        super().resizeEvent(event)
        if self._graphics_view is not None:
            self._graphics_view.resize(self.size())
        self._fit_video_item()

    # ------------------------------------------------------------ 摄像头

    def _setup_camera(self) -> None:
        devices = QMediaDevices.videoInputs()
        if not devices:
            raise RuntimeError(
                "未检测到任何摄像头设备。请检查摄像头是否已被占用或未连接。"
            )
        self._start_camera(self._current_device_index)

    def _start_camera(self, device_index: int, stop_old: bool = True) -> None:
        """启动指定序号的摄像头。

        stop_old=True 时会先停掉当前摄像头（初始化场景）。
        stop_old=False 时保留旧摄像头对象（切换场景，旧对象留给回滚）。
        """
        devices = QMediaDevices.videoInputs()
        if not devices:
            raise RuntimeError("未检测到任何摄像头设备。")

        # 钳位到有效范围
        if 0 <= device_index < len(devices):
            idx = device_index
        else:
            idx = 0
        self._current_device_index = idx
        device = devices[idx]

        if stop_old and self._camera is not None:
            self._camera.stop()

        self._camera = QCamera(device)
        if Config.PREFERRED_RESOLUTION is not None:
            w, h = Config.PREFERRED_RESOLUTION
            fmt = self._pick_format(device, w, h, Config.PREFERRED_FRAME_RATE)
            if fmt is not None:
                self._camera.setCameraFormat(fmt)

        if self._session is None:
            self._session = QMediaCaptureSession()
        self._session.setCamera(self._camera)
        assert self._video_item is not None
        self._session.setVideoSink(self._video_item.videoSink())

        self._camera.start()

        # 首帧到达后触发 fit（延迟 300ms 确保渲染管线就绪）
        QTimer.singleShot(300, self._fit_video_item)

    def _switch_camera(self, device_index: int) -> None:
        """切换到指定序号的摄像头。

        如果新摄像头启动失败（如被其他程序占用），
        自动回滚到之前的摄像头并弹出提示。
        """
        if device_index == self._current_device_index:
            return

        old_index = self._current_device_index
        old_camera = self._camera

        # 不停旧的，保留对象供回滚
        self._start_camera(device_index, stop_old=False)

        # 监听新摄像头的错误信号
        assert self._camera is not None
        self._camera.errorOccurred.connect(
            lambda error, msg: self._on_camera_error(error, msg, old_index, old_camera)
        )

    def _on_camera_error(
        self, error, msg: str, fallback_index: int, fallback_camera: QCamera | None
    ) -> None:
        """摄像头启动失败时的回调：回滚到旧摄像头并提示用户。"""
        if error == QCamera.Error.NoError:
            return

        # 停掉失败的新摄像头，断开信号
        failed_camera = self._camera
        if failed_camera is not None:
            failed_camera.errorOccurred.disconnect()
            failed_camera.stop()

        # 弹出提示
        from PySide6.QtWidgets import QMessageBox

        device_name = "摄像头"
        devices = QMediaDevices.videoInputs()
        if 0 <= self._current_device_index < len(devices):
            device_name = devices[self._current_device_index].description()

        QMessageBox.warning(
            None,
            "摄像头切换失败",
            f"「{device_name}」无法启动，可能正在被其他程序占用。\n已自动切回之前的摄像头。",
        )

        # 回滚：恢复旧摄像头
        self._current_device_index = fallback_index
        self._camera = fallback_camera
        if fallback_camera is not None and self._session is not None:
            self._session.setCamera(fallback_camera)
            fallback_camera.start()

    @staticmethod
    def _pick_format(device, w: int, h: int, fps: float):
        """从设备支持的格式里挑一个最接近期望的。

        选择优先级（影响长时间运行的占用与流畅度）：
          1) 完全匹配目标分辨率，且帧率最接近；
          2) 在同分辨率里优先原生格式(NV12/YUYV)，避开需要解码的 JPEG；
          3) 都没有则取最接近分辨率的任意格式。
        """
        candidates = list(device.videoFormats())
        if not candidates:
            return None

        def res_dist(f) -> int:
            return (f.resolution().width() - w) ** 2 + (f.resolution().height() - h) ** 2

        def fps_dist(f) -> float:
            return abs(float(f.maxFrameRate()) - fps)

        # 原生格式（无需解码，最省资源）。JPEG 视为需解码。
        def is_native(f) -> bool:
            name = str(f.pixelFormat())
            return "Jpeg" not in name

        exact_res = [f for f in candidates if res_dist(f) == 0]
        if exact_res:
            # 优先原生 + 帧率接近
            native_exact = [f for f in exact_res if is_native(f)]
            pool = native_exact or exact_res
            return min(pool, key=fps_dist)

        return min(candidates, key=lambda f: (res_dist(f), fps_dist(f)))

    # ---------------------------------------------------------- 旋转

    def _rotate_90(self) -> None:
        """顺时针旋转画面 90°。"""
        self._rotation = (self._rotation + 90) % 360
        assert self._video_item is not None
        self._video_item.setRotation(self._rotation)
        self._fit_video_item()

    def _fit_video_item(self) -> None:
        """让 video item 严格填满 graphics view，不留任何边缘缝隙。

        不用 fitInView（它有 1-2px 精度误差会露白边），
        改为手动计算缩放比例 + QTransform，确保画面完全覆盖 viewport。
        """
        if self._video_item is None or self._graphics_view is None:
            return

        # 从摄像头格式获取视频尺寸（比 nativeSize 更可靠）
        vw, vh = self._video_resolution()
        if vw <= 0 or vh <= 0:
            return

        # 旋转 90/270° 时，有效尺寸宽高互换
        if self._rotation in (90, 270):
            effective_w, effective_h = vh, vw
        else:
            effective_w, effective_h = vw, vh

        # 设置 item 的尺寸为原始尺寸（旋转由 setRotation 处理）
        self._video_item.setSize(QSizeF(vw, vh))

        # 设置 scene 的范围匹配旋转后的有效尺寸
        self._graphics_scene.setSceneRect(0, 0, effective_w, effective_h)

        # 旋转后 item 的位置需要偏移，使画面居中在 sceneRect 内
        if self._rotation == 90:
            self._video_item.setPos(vh, 0)
        elif self._rotation == 180:
            self._video_item.setPos(vw, vh)
        elif self._rotation == 270:
            self._video_item.setPos(0, vw)
        else:
            self._video_item.setPos(0, 0)

        # 手动计算缩放：取较大的缩放比，确保画面严格覆盖整个 viewport
        view_w = self._graphics_view.viewport().width()
        view_h = self._graphics_view.viewport().height()
        if view_w <= 0 or view_h <= 0:
            return

        scale_x = view_w / effective_w
        scale_y = view_h / effective_h
        # KeepAspectRatioByExpanding = 取较大的缩放比
        scale = max(scale_x, scale_y)

        # 居中偏移
        dx = (view_w - effective_w * scale) / 2.0
        dy = (view_h - effective_h * scale) / 2.0

        transform = QTransform()
        transform.translate(dx, dy)
        transform.scale(scale, scale)
        self._graphics_view.setTransform(transform)

    def _video_resolution(self) -> tuple[float, float]:
        """获取当前视频的原始分辨率。优先从 cameraFormat 取（最可靠）。"""
        if self._camera is not None:
            fmt = self._camera.cameraFormat()
            if fmt is not None:
                r = fmt.resolution()
                if r.width() > 0 and r.height() > 0:
                    return float(r.width()), float(r.height())
        # 回退到 nativeSize
        if self._video_item is not None:
            ns = self._video_item.nativeSize()
            if ns.width() > 0 and ns.height() > 0:
                return ns.width(), ns.height()
        return 0.0, 0.0

    # ---------------------------------------------------------- 快捷键

    def _setup_shortcuts(self) -> None:
        # ESC 退出
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.close)
        # Q 退出
        QShortcut(QKeySequence(Qt.Key.Key_Q), self, activated=self.close)
        # R 旋转 90°
        QShortcut(QKeySequence(Qt.Key.Key_R), self, activated=self._rotate_90)

    # ---------------------------------------------------------- 拖动

    def _drag_button(self) -> Qt.MouseButton:
        return (
            Qt.MouseButton.LeftButton
            if Config.DRAG_BUTTON == "left"
            else Qt.MouseButton.RightButton
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        # 右键弹出菜单（不拖动）
        if event.button() == Qt.MouseButton.RightButton and Config.DRAG_BUTTON == "left":
            self._show_context_menu(event.globalPosition().toPoint())
            return

        if event.button() == self._drag_button():
            # 检测是否点在边缘 → 进入缩放
            edge = self._edge_at(event.position().toPoint())
            if edge is not None:
                self._resize_dir = edge
                self._resize_start_pos = event.globalPosition().toPoint()
                self._resize_start_rect = self.geometry()
            else:
                self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self._resize_dir = None
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        # 缩放中
        if self._resize_dir is not None:
            self._do_resize(event.globalPosition().toPoint())
            event.accept()
            return

        # 拖动中
        if self._drag_offset is not None and event.buttons() & self._drag_button():
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return

        # 空闲移动：更新边缘光标形状
        self._update_cursor(event.position().toPoint())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_offset = None
        self._resize_dir = None
        event.accept()

    # ---------------------------------------------------------- 缩放

    # 边缘判定宽度（像素）。点在这个区域内视为要缩放。
    _EDGE_THRESHOLD = 8

    def _edge_at(self, pos: QPoint) -> str | None:
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        t = self._EDGE_THRESHOLD
        on_left = x <= t
        on_right = x >= w - t
        on_top = y <= t
        on_bottom = y >= h - t

        if on_top and on_left:
            return "tl"
        if on_top and on_right:
            return "tr"
        if on_bottom and on_left:
            return "bl"
        if on_bottom and on_right:
            return "br"
        if on_left:
            return "l"
        if on_right:
            return "r"
        if on_top:
            return "t"
        if on_bottom:
            return "b"
        return None

    def _do_resize(self, global_pos: QPoint) -> None:
        delta = global_pos - self._resize_start_pos
        rect = self._resize_start_rect
        min_w, min_h = Config.MIN_SIZE
        new_left = rect.left()
        new_top = rect.top()
        new_right = rect.right()
        new_bottom = rect.bottom()

        d = self._resize_dir
        if d in ("r", "tr", "br"):
            new_right = rect.left() + max(min_w, rect.width() + delta.x())
        if d in ("l", "tl", "bl"):
            new_left = rect.right() - max(min_w, rect.width() - delta.x()) + 1
        if d in ("b", "bl", "br"):
            new_bottom = rect.top() + max(min_h, rect.height() + delta.y())
        if d in ("t", "tl", "tr"):
            new_top = rect.bottom() - max(min_h, rect.height() - delta.y()) + 1

        width = max(min_w, new_right - new_left + 1)
        height = max(min_h, new_bottom - new_top + 1)

        self.setGeometry(new_left, new_top, width, height)

    # ---------------------------------------------------------- 光标

    def _update_cursor(self, pos: QPoint) -> None:
        edge = self._edge_at(pos)
        cursor = {
            "tl": Qt.CursorShape.SizeFDiagCursor,
            "br": Qt.CursorShape.SizeFDiagCursor,
            "tr": Qt.CursorShape.SizeBDiagCursor,
            "bl": Qt.CursorShape.SizeBDiagCursor,
            "l": Qt.CursorShape.SizeHorCursor,
            "r": Qt.CursorShape.SizeHorCursor,
            "t": Qt.CursorShape.SizeVerCursor,
            "b": Qt.CursorShape.SizeVerCursor,
        }.get(edge)
        if cursor is None:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.setCursor(cursor)

    # ---------------------------------------------------------- 菜单

    def _show_context_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)

        # ---- 摄像头子菜单 ----
        cam_menu = menu.addMenu("选择摄像头")
        devices = QMediaDevices.videoInputs()
        for i, dev in enumerate(devices):
            action = QAction(dev.description(), cam_menu)
            action.setCheckable(True)
            action.setChecked(i == self._current_device_index)
            # 用默认参数捕获 i，避免闭包变量问题
            action.triggered.connect(lambda checked=False, idx=i: self._switch_camera(idx))
            cam_menu.addAction(action)

        menu.addSeparator()

        rotate_action = QAction("旋转 90°  (R)", menu)
        rotate_action.triggered.connect(self._rotate_90)
        menu.addAction(rotate_action)

        menu.addSeparator()

        toggle_top = QAction("取消置顶" if self._is_on_top() else "置顶", menu)
        toggle_top.triggered.connect(self._toggle_on_top)
        menu.addAction(toggle_top)

        menu.addSeparator()

        quit_action = QAction("退出  (ESC)", menu)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)

        menu.exec(global_pos)

    def _is_on_top(self) -> bool:
        return bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)

    def _toggle_on_top(self) -> None:
        flags = self.windowFlags()
        if self._is_on_top():
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        else:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()  # setWindowFlags 后需要重新显示

    # ---------------------------------------------------------- 关闭

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._camera is not None:
            self._camera.stop()
        self.closed.emit()
        super().closeEvent(event)
