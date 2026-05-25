import sys
import mss
import mss.tools
import time
import random
import os
import tempfile
from fpdf import FPDF
from pynput.keyboard import Controller, Key
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSpinBox, QProgressBar, QMessageBox,
    QComboBox, QFileDialog, QGroupBox, QDoubleSpinBox
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtGui import QGuiApplication, QPainter, QPen, QColor, QFont, QDesktopServices

import platform

APP_NAME = "BookScanner"
APP_VERSION = "1.1.0"
FREE_PAGE_LIMIT = 10
IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"

DARK_STYLE = """
QMainWindow {
    background-color: #1e1e2e;
}
QWidget {
    color: #cdd6f4;
    font-family: "Helvetica Neue", "Apple SD Gothic Neo", sans-serif;
    font-size: 13px;
}
QGroupBox {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 8px;
    margin-top: 12px;
    padding: 16px 12px 12px 12px;
    font-weight: bold;
    font-size: 13px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: #89b4fa;
}
QPushButton {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    border-radius: 6px;
    padding: 10px 16px;
    font-weight: bold;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #b4d0fb;
}
QPushButton:pressed {
    background-color: #74a8fc;
}
QPushButton:disabled {
    background-color: #45475a;
    color: #6c7086;
}
QPushButton#stopBtn {
    background-color: #f38ba8;
    color: #1e1e2e;
}
QPushButton#stopBtn:hover {
    background-color: #f5a0b8;
}
QPushButton#stopBtn:pressed {
    background-color: #e67a97;
}
QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #45475a;
    border: 1px solid #585b70;
    border-radius: 6px;
    padding: 6px 10px;
    color: #cdd6f4;
    min-height: 28px;
}
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #89b4fa;
}
QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #45475a;
    color: #cdd6f4;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
    border-radius: 4px;
}
QProgressBar {
    background-color: #45475a;
    border: none;
    border-radius: 6px;
    text-align: center;
    color: #cdd6f4;
    min-height: 22px;
    font-size: 11px;
}
QProgressBar::chunk {
    background-color: #a6e3a1;
    border-radius: 6px;
}
QLabel#statusLabel {
    color: #a6adc8;
    font-size: 12px;
}
QLabel#titleLabel {
    font-size: 18px;
    font-weight: bold;
    color: #cdd6f4;
}
QLabel#coordLabel {
    color: #a6e3a1;
    font-size: 12px;
}
QLabel#versionLabel {
    color: #6c7086;
    font-size: 11px;
}
QLabel#licenseLabel {
    color: #f9e2af;
    font-size: 11px;
}
"""


def check_screen_capture_permission():
    if IS_WINDOWS:
        return True
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            region = {
                "top": monitor["top"],
                "left": monitor["left"],
                "width": 1,
                "height": 1,
            }
            sct.grab(region)
        return True
    except Exception as e:
        if "Permissions" in str(e) or "권한" in str(e):
            return False
        return True


def get_device_pixel_ratio():
    screens = QGuiApplication.screens()
    if screens:
        return screens[0].devicePixelRatio()
    return 1.0


PAGE_TURN_METHODS = {
    "오른쪽 화살표 (→)": Key.right,
    "왼쪽 화살표 (←)": Key.left,
    "스페이스바": Key.space,
    "Page Down": Key.page_down,
    "Enter": Key.enter,
}


class SelectionWindow(QWidget):
    selection_completed = Signal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 120);")
        self.setCursor(Qt.CrossCursor)
        self.showFullScreen()

        self.start_pos = None
        self.current_pos = None
        self.is_selecting = False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = event.pos()
            self.is_selecting = True

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            self.current_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_selecting:
            self.is_selecting = False
            if self.start_pos and self.current_pos:
                x1, y1 = self.start_pos.x(), self.start_pos.y()
                x2, y2 = self.current_pos.x(), self.current_pos.y()

                left = min(x1, x2)
                top = min(y1, y2)
                width = abs(x2 - x1)
                height = abs(y2 - y1)

                if width < 10 or height < 10:
                    self.close()
                    return

                ratio = get_device_pixel_ratio()
                bbox = {
                    "top": int(top * ratio),
                    "left": int(left * ratio),
                    "width": int(width * ratio),
                    "height": int(height * ratio),
                }
                self.selection_completed.emit(bbox)
                self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self.start_pos and self.current_pos and self.is_selecting:
            pen = QPen(QColor(137, 180, 250), 2)
            painter.setPen(pen)
            fill = QColor(137, 180, 250, 30)
            x = min(self.start_pos.x(), self.current_pos.x())
            y = min(self.start_pos.y(), self.current_pos.y())
            w = abs(self.current_pos.x() - self.start_pos.x())
            h = abs(self.current_pos.y() - self.start_pos.y())
            painter.fillRect(x, y, w, h, fill)
            painter.drawRect(x, y, w, h)

            size_text = f"{int(w * get_device_pixel_ratio())} x {int(h * get_device_pixel_ratio())} px"
            painter.setPen(QColor(255, 255, 255))
            _font = "Segoe UI" if IS_WINDOWS else "Helvetica Neue"
            painter.setFont(QFont(_font, 12))
            painter.drawText(x, y - 8, size_text)

        if not self.is_selecting and not self.start_pos:
            painter.setPen(QColor(205, 214, 244))
            _font = "Segoe UI" if IS_WINDOWS else "Helvetica Neue"
            painter.setFont(QFont(_font, 16))
            painter.drawText(self.rect(), Qt.AlignCenter, "캡처할 영역을 드래그하세요 (ESC로 취소)")


class CaptureThread(QThread):
    progress = Signal(int, str)
    finished_signal = Signal(str)
    error = Signal(str)

    def __init__(self, bbox, total_pages, page_turn_key, delay_seconds, save_path):
        super().__init__()
        self.bbox = bbox
        self.total_pages = total_pages
        self.page_turn_key = page_turn_key
        self.delay_seconds = delay_seconds
        self.save_path = save_path
        self.keyboard = Controller()
        self.is_running = True
        self._temp_dir = tempfile.mkdtemp(prefix="bookscanner_")

    def run(self):
        try:
            pdf = FPDF(orientation='L', unit='mm', format='A4')
            screenshot_files = []

            with mss.mss() as sct:
                for page in range(1, self.total_pages + 1):
                    if not self.is_running:
                        break

                    if page > 1:
                        self.keyboard.press(self.page_turn_key)
                        time.sleep(random.uniform(0.05, 0.15))
                        self.keyboard.release(self.page_turn_key)
                        time.sleep(self.delay_seconds + random.uniform(0, 0.3))
                    else:
                        time.sleep(max(0.5, self.delay_seconds * 0.5))

                    screenshot = sct.grab(self.bbox)
                    image_path = os.path.join(self._temp_dir, f"page_{page}.png")
                    mss.tools.to_png(screenshot.rgb, screenshot.size, output=image_path)
                    screenshot_files.append(image_path)

                    remaining = self.total_pages - page
                    eta = remaining * (self.delay_seconds + 0.5)
                    if eta >= 60:
                        eta_str = f" (약 {int(eta // 60)}분 {int(eta % 60)}초 남음)"
                    elif remaining > 0:
                        eta_str = f" (약 {int(eta)}초 남음)"
                    else:
                        eta_str = ""
                    self.progress.emit(page, f"{page}/{self.total_pages} 페이지 캡처 완료{eta_str}")

                    pdf.add_page()
                    img_width, img_height = screenshot.size
                    aspect_ratio = img_height / img_width
                    pdf_width = 277
                    pdf_height = pdf_width * aspect_ratio

                    if pdf_height > 190:
                        pdf_height = 190
                        pdf_width = pdf_height / aspect_ratio

                    x = (297 - pdf_width) / 2
                    y = (210 - pdf_height) / 2
                    pdf.image(image_path, x=x, y=y, w=pdf_width)

            if screenshot_files:
                pdf.output(self.save_path)
                self.progress.emit(
                    min(self.total_pages, len(screenshot_files)),
                    "PDF 저장 완료!"
                )

            for file in screenshot_files:
                try:
                    os.remove(file)
                except OSError:
                    pass
            try:
                os.rmdir(self._temp_dir)
            except OSError:
                pass

            self.finished_signal.emit(self.save_path)

        except Exception as e:
            self.error.emit(f"캡처 중 오류가 발생했습니다:\n{str(e)}")

    def stop(self):
        self.is_running = False


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setFixedSize(460, 580)

        if not check_screen_capture_permission():
            if IS_MAC:
                msg = ("화면 캡처 권한이 필요합니다.\n\n"
                       "시스템 설정 > 개인 정보 보호 및 보안 > 화면 기록에서\n"
                       "이 앱에 권한을 부여해주세요.")
            else:
                msg = "화면 캡처 권한이 필요합니다.\n프로그램을 관리자 권한으로 실행해주세요."
            QMessageBox.critical(None, "권한 필요", msg)
            sys.exit(1)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        header_layout = QHBoxLayout()
        title_label = QLabel(APP_NAME)
        title_label.setObjectName("titleLabel")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        version_label = QLabel(f"v{APP_VERSION}")
        version_label.setObjectName("versionLabel")
        header_layout.addWidget(version_label)
        layout.addLayout(header_layout)

        license_label = QLabel(f"무료 버전 (최대 {FREE_PAGE_LIMIT}페이지)")
        license_label.setObjectName("licenseLabel")
        layout.addWidget(license_label)

        # --- Area Selection ---
        area_group = QGroupBox("캡처 영역")
        area_layout = QVBoxLayout(area_group)

        self.coord_label = QLabel("선택된 영역이 없습니다")
        self.coord_label.setObjectName("coordLabel")
        area_layout.addWidget(self.coord_label)

        self.select_area_btn = QPushButton("영역 선택하기")
        self.select_area_btn.clicked.connect(self.select_area)
        area_layout.addWidget(self.select_area_btn)

        layout.addWidget(area_group)

        # --- Capture Options ---
        options_group = QGroupBox("캡처 설정")
        options_layout = QVBoxLayout(options_group)

        page_row = QHBoxLayout()
        page_row.addWidget(QLabel("페이지 수"))
        self.page_spinbox = QSpinBox()
        self.page_spinbox.setMinimum(1)
        self.page_spinbox.setMaximum(1000)
        self.page_spinbox.setValue(10)
        page_row.addWidget(self.page_spinbox)
        options_layout.addLayout(page_row)

        turn_row = QHBoxLayout()
        turn_row.addWidget(QLabel("넘김 방식"))
        self.turn_combo = QComboBox()
        self.turn_combo.addItems(PAGE_TURN_METHODS.keys())
        turn_row.addWidget(self.turn_combo)
        options_layout.addLayout(turn_row)

        delay_row = QHBoxLayout()
        delay_row.addWidget(QLabel("캡처 간격"))
        self.delay_spinbox = QDoubleSpinBox()
        self.delay_spinbox.setMinimum(0.5)
        self.delay_spinbox.setMaximum(10.0)
        self.delay_spinbox.setValue(1.5)
        self.delay_spinbox.setSingleStep(0.5)
        self.delay_spinbox.setSuffix(" 초")
        delay_row.addWidget(self.delay_spinbox)
        options_layout.addLayout(delay_row)

        layout.addWidget(options_group)

        # --- Execution ---
        exec_group = QGroupBox("실행")
        exec_layout = QVBoxLayout(exec_group)

        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("캡처 시작")
        self.start_btn.clicked.connect(self.start_capture)
        self.start_btn.setEnabled(False)
        btn_row.addWidget(self.start_btn)

        self.stop_btn = QPushButton("중지")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.clicked.connect(self.stop_capture)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setFixedWidth(80)
        btn_row.addWidget(self.stop_btn)
        exec_layout.addLayout(btn_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFormat("%p%")
        exec_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("영역을 선택한 후 캡처를 시작하세요")
        self.status_label.setObjectName("statusLabel")
        exec_layout.addWidget(self.status_label)

        layout.addWidget(exec_group)
        layout.addStretch()

        self.bbox = None
        self.capture_thread = None
        self.selection_window = None
        self._countdown_remaining = 0
        self._pending_save_path = None
        self._pending_total_pages = 0

    def select_area(self):
        self.hide()
        QTimer.singleShot(300, self._show_selection_window)

    def _show_selection_window(self):
        self.selection_window = SelectionWindow()
        self.selection_window.selection_completed.connect(self.area_selected)
        self.selection_window.destroyed.connect(self._on_selection_closed)
        self.selection_window.show()

    def _on_selection_closed(self):
        if not self.bbox:
            self.show()

    def area_selected(self, bbox):
        self.bbox = bbox
        w, h = bbox['width'], bbox['height']
        self.coord_label.setText(f"{w} x {h} px  ({bbox['left']}, {bbox['top']})")
        self.start_btn.setEnabled(True)
        self.status_label.setText("준비 완료 — 캡처 시작을 눌러주세요")
        self.show()

    def start_capture(self):
        if not self.bbox:
            return

        total_pages = self.page_spinbox.value()
        if total_pages > FREE_PAGE_LIMIT:
            reply = QMessageBox.question(
                self, "무료 버전 제한",
                f"무료 버전에서는 최대 {FREE_PAGE_LIMIT}페이지까지 캡처할 수 있습니다.\n"
                f"{FREE_PAGE_LIMIT}페이지만 캡처할까요?\n\n"
                "전체 페이지를 캡처하려면 정식 버전을 구매해주세요.",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                total_pages = FREE_PAGE_LIMIT
                self.page_spinbox.setValue(FREE_PAGE_LIMIT)
            else:
                return

        save_path, _ = QFileDialog.getSaveFileName(
            self, "PDF 저장 위치 선택",
            os.path.expanduser("~/Desktop/scan_output.pdf"),
            "PDF 파일 (*.pdf)"
        )
        if not save_path:
            return
        if not save_path.endswith(".pdf"):
            save_path += ".pdf"

        self._pending_save_path = save_path
        self._pending_total_pages = min(total_pages, FREE_PAGE_LIMIT)
        self._set_ui_capturing(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(self._pending_total_pages)
        self._countdown_remaining = 3
        self._run_countdown()

    def _run_countdown(self):
        if self._countdown_remaining > 0:
            self.status_label.setText(f"{self._countdown_remaining}초 후 캡처가 시작됩니다...")
            self._countdown_remaining -= 1
            QTimer.singleShot(1000, self._run_countdown)
        else:
            self.status_label.setText("캡처 중...")
            self._launch_capture()

    def _launch_capture(self):
        turn_method_name = self.turn_combo.currentText()
        page_turn_key = PAGE_TURN_METHODS[turn_method_name]
        delay = self.delay_spinbox.value()

        self.capture_thread = CaptureThread(
            self.bbox,
            self._pending_total_pages,
            page_turn_key,
            delay,
            self._pending_save_path,
        )
        self.capture_thread.progress.connect(self.update_progress)
        self.capture_thread.finished_signal.connect(self.capture_finished)
        self.capture_thread.error.connect(self.show_error)
        self.capture_thread.start()

    def stop_capture(self):
        if self.capture_thread and self.capture_thread.isRunning():
            self.capture_thread.stop()
            self.stop_btn.setEnabled(False)
            self.status_label.setText("중지 요청됨...")

    def update_progress(self, page, message):
        self.progress_bar.setValue(page)
        self.status_label.setText(message)

    def capture_finished(self, save_path):
        self._set_ui_capturing(False)
        self.status_label.setText(f"완료! {os.path.basename(save_path)}")

        reply = QMessageBox.question(
            self, "캡처 완료",
            f"PDF가 저장되었습니다:\n{save_path}\n\n파일을 열어볼까요?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(save_path))

    def show_error(self, message):
        self._set_ui_capturing(False)
        QMessageBox.critical(self, "오류 발생", message)

    def _set_ui_capturing(self, capturing):
        self.select_area_btn.setEnabled(not capturing)
        self.start_btn.setEnabled(not capturing and self.bbox is not None)
        self.page_spinbox.setEnabled(not capturing)
        self.turn_combo.setEnabled(not capturing)
        self.delay_spinbox.setEnabled(not capturing)
        self.stop_btn.setEnabled(capturing)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    style = DARK_STYLE
    if IS_WINDOWS:
        style = style.replace(
            '"Helvetica Neue", "Apple SD Gothic Neo", sans-serif',
            '"Segoe UI", "Malgun Gothic", sans-serif'
        )
    app.setStyleSheet(style)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
