import sys
import mss
import mss.tools
import pyautogui
import time
import random
import os
from fpdf import FPDF
from pynput.keyboard import Controller, Key
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                              QPushButton, QLabel, QSpinBox, QProgressBar, QMessageBox, QCheckBox)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QScreen, QGuiApplication

class SelectionWindow(QWidget):
    selection_completed = Signal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 100);")
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
                
                # 좌표를 정규화 (시작점이 항상 왼쪽 위가 되도록)
                left = min(x1, x2)
                top = min(y1, y2)
                width = abs(x2 - x1)
                height = abs(y2 - y1)
                
                bbox = {
                    "top": top,
                    "left": left,
                    "width": width,
                    "height": height
                }
                self.selection_completed.emit(bbox)
                self.close()

    def paintEvent(self, event):
        if self.start_pos and self.current_pos and self.is_selecting:
            from PySide6.QtGui import QPainter, QPen, QColor
            painter = QPainter(self)
            painter.setPen(QPen(QColor(255, 0, 0), 2))
            x = min(self.start_pos.x(), self.current_pos.x())
            y = min(self.start_pos.y(), self.current_pos.y())
            width = abs(self.current_pos.x() - self.start_pos.x())
            height = abs(self.current_pos.y() - self.start_pos.y())
            painter.drawRect(x, y, width, height)

class CaptureThread(QThread):
    progress = Signal(int, str)
    finished = Signal()
    error = Signal(str)

    def __init__(self, bbox, total_pages, use_delay=False):
        super().__init__()
        self.bbox = bbox
        self.total_pages = total_pages
        self.use_delay = use_delay
        self.keyboard = Controller()
        self.is_running = True

    def run(self):
        try:
            pdf = FPDF(orientation='L', unit='mm', format='A4')
            screenshot_files = []

            with mss.mss() as sct:
                for page in range(1, self.total_pages + 1):
                    if not self.is_running:
                        break

                    if page > 1:  # 첫 페이지는 이미 준비된 상태
                        # 다음 페이지로 이동
                        self.keyboard.press(Key.right)
                        time.sleep(random.uniform(0.1, 0.5))
                        self.keyboard.release(Key.right)

                        # 지연 시간 옵션이 켜져 있으면 3초 대기
                        if self.use_delay:
                            time.sleep(3)
                    else:
                        # 첫 페이지는 기본 대기시간만
                        random_delay = random.uniform(0.2, 2)
                        time.sleep(random_delay)

                    screenshot = sct.grab(self.bbox)
                    image_path = f"screenshot_page_{page}.png"
                    mss.tools.to_png(screenshot.rgb, screenshot.size, output=image_path)
                    screenshot_files.append(image_path)
                    
                    self.progress.emit(page, f"{page}/{self.total_pages} 페이지 캡처 완료")

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

            pdf_output = "output.pdf"
            pdf.output(pdf_output)
            self.progress.emit(self.total_pages, "PDF 저장 완료")

            for file in screenshot_files:
                try:
                    os.remove(file)
                except Exception as e:
                    self.error.emit(f"파일 삭제 중 에러 발생: {str(e)}")

            self.finished.emit()

        except Exception as e:
            self.error.emit(f"에러 발생: {str(e)}")

    def stop(self):
        self.is_running = False

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("화면 캡처 프로그램")
        self.setGeometry(100, 100, 400, 300)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        self.coord_label = QLabel("선택된 영역: 없음")
        layout.addWidget(self.coord_label)

        self.select_area_btn = QPushButton("캡처 영역 선택")
        self.select_area_btn.clicked.connect(self.select_area)
        layout.addWidget(self.select_area_btn)

        self.page_spinbox = QSpinBox()
        self.page_spinbox.setMinimum(1)
        self.page_spinbox.setMaximum(1000)
        self.page_spinbox.setValue(1)
        layout.addWidget(QLabel("캡처할 페이지 수:"))
        layout.addWidget(self.page_spinbox)

        # 지연 시간 체크박스 추가
        self.delay_checkbox = QCheckBox("페이지 로딩 지연시간 추가 (3초)")
        layout.addWidget(self.delay_checkbox)

        self.start_btn = QPushButton("캡처 시작")
        self.start_btn.clicked.connect(self.start_capture)
        self.start_btn.setEnabled(False)
        layout.addWidget(self.start_btn)

        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        self.bbox = None
        self.capture_thread = None
        self.selection_window = None

    def select_area(self):
        self.hide()  # 메인 창 숨기기
        QMessageBox.information(None, "안내", "캡처할 영역을 드래그하여 선택하세요.")
        
        self.selection_window = SelectionWindow()
        self.selection_window.selection_completed.connect(self.area_selected)
        self.selection_window.show()

    def area_selected(self, bbox):
        self.bbox = bbox
        self.coord_label.setText(
            f"선택된 영역: ({bbox['left']}, {bbox['top']}) - "
            f"({bbox['left'] + bbox['width']}, {bbox['top'] + bbox['height']})"
        )
        self.start_btn.setEnabled(True)
        self.show()  # 메인 창 다시 표시

    def start_capture(self):
        if not self.bbox:
            return

        self.select_area_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.page_spinbox.setEnabled(False)
        self.delay_checkbox.setEnabled(False)
        self.progress_bar.setValue(0)
        
        # 3초 카운트다운 메시지
        QMessageBox.information(None, "안내", "3초 후에 캡처가 시작됩니다.")
        self.status_label.setText("3초 후 캡처 시작...")
        
        # 3초 대기 후 캡처 시작
        QThread.msleep(3000)
        
        self.status_label.setText("캡처 준비 중...")
        total_pages = self.page_spinbox.value()
        self.progress_bar.setMaximum(total_pages)

        self.capture_thread = CaptureThread(self.bbox, total_pages, self.delay_checkbox.isChecked())
        self.capture_thread.progress.connect(self.update_progress)
        self.capture_thread.finished.connect(self.capture_finished)
        self.capture_thread.error.connect(self.show_error)
        self.capture_thread.start()

    def update_progress(self, page, message):
        self.progress_bar.setValue(page)
        self.status_label.setText(message)

    def capture_finished(self):
        self.select_area_btn.setEnabled(True)
        self.start_btn.setEnabled(True)
        self.page_spinbox.setEnabled(True)
        self.delay_checkbox.setEnabled(True)
        self.status_label.setText("캡처 완료!")

    def show_error(self, message):
        self.status_label.setText(f"에러: {message}")
        self.select_area_btn.setEnabled(True)
        self.start_btn.setEnabled(True)
        self.page_spinbox.setEnabled(True)
        self.delay_checkbox.setEnabled(True)

    def closeEvent(self, event):
        if self.capture_thread and self.capture_thread.isRunning():
            self.capture_thread.stop()
            self.capture_thread.wait()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
