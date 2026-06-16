import sys, os
from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")

def make_rounded_logo(path, size):
    out = QPixmap(size, size); out.fill(Qt.GlobalColor.transparent)
    src = QPixmap(path)
    scaled = src.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
    from PyQt6.QtGui import QPainter
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    ox = (size - scaled.width()) // 2
    oy = (size - scaled.height()) // 2
    p.drawPixmap(ox, oy, scaled)
    p.end()
    return out

app = QApplication(sys.argv)
d = QDialog(); d.setFixedSize(300, 300)
d.setStyleSheet("background:#0e1621;")
lo = QVBoxLayout(d)
icon = QLabel()
icon.setPixmap(make_rounded_logo(LOGO_PATH, 112))
icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
lo.addWidget(icon, alignment=Qt.AlignmentFlag.AlignHCenter)
print("Logo pixmap size:", icon.pixmap().size())
d.exec()