import sys
import os
import requests
import websocket
import threading

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QHBoxLayout, QScrollArea, QTextEdit,
    QFileDialog, QFrame, QSizePolicy, QStackedWidget
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRect
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QPen, QPixmap,
    QLinearGradient, QPainterPath, QCursor
)
from PyQt6.QtCore import QThread, QObject
from datetime import datetime, timezone
from PyQt6.QtWidgets import QMenu
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

def format_last_seen(iso_str):
    if not iso_str:
        return "last seen recently"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", ""))
    except Exception:
        return "last seen recently"
    delta = datetime.now() - dt
    secs = delta.total_seconds()
    if secs < 60: return "online"
    if secs < 3600: return f"last seen {int(secs//60)} min ago"
    if secs < 86400: return f"last seen {int(secs//3600)} h ago"
    return f"last seen {int(secs//86400)} d ago"

class ApiWorker(QThread):
    done = pyqtSignal(object)
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn; self.args = args; self.kwargs = kwargs
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as ex:
            print("Worker error:", ex); result = None
        self.done.emit(result)

# ── Palette ───────────────────────────────────────────────
C = {
    "bg":       "#0e1621",
    "sidebar":  "#17212b",
    "panel":    "#1c2733",
    "card":     "#232e3c",
    "msg_in":   "#182533",
    "msg_out":  "#2b5278",
    "hover":    "#202b36",
    "selected": "#2b5278",
    "divider":  "#101a24",
    "accent":   "#5288c1",
    "accent_h": "#5e93cc",
    "text":     "#ffffff",
    "text2":    "#7d8e9e",
    "text3":    "#5a6b7a",
    "green":    "#54c75e",
    "red":      "#e15c5c",
    "orange":   "#e8a14b",
}

AVATAR_PALETTE = [
    "#e17076","#7bc862","#65aadd","#ee7aae",
    "#aa65dd","#6ec9cb","#faa774","#5288c1",
]

BASE_URL = "http://localhost:8000"
H = lambda token: {"Authorization": f"Bearer {token}"}
LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")


# ── Avatar ────────────────────────────────────────────────
def avatar_color(name):
    return AVATAR_PALETTE[sum(ord(c) for c in name) % len(AVATAR_PALETTE)]


def make_avatar(name, size, image_path=""):
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    path = QPainterPath(); path.addEllipse(0, 0, size, size)
    p.setClipPath(path)
    if image_path and os.path.exists(image_path):
        src = QPixmap(image_path)
        # Scale so the shorter side fills `size`, then center-crop
        scaled = src.scaled(size, size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation)
        x = (scaled.width() - size) // 2
        y = (scaled.height() - size) // 2
        p.drawPixmap(0, 0, scaled, x, y, size, size)
    else:
        col = QColor(avatar_color(name))
        g = QLinearGradient(0, 0, size, size)
        g.setColorAt(0, col.lighter(125)); g.setColorAt(1, col.darker(115))
        p.fillRect(0, 0, size, size, g)
        p.setPen(QPen(QColor("white")))
        p.setFont(QFont("Segoe UI", max(10, size // 3), QFont.Weight.Bold))
        p.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter,
                   (name[0] if name else "?").upper())
    p.end()
    return px


def make_rounded_logo(path, size, radius_ratio=0.30):
    """Logo cropped to a rounded square."""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    rr = size * radius_ratio
    clip = QPainterPath()
    clip.addRoundedRect(0, 0, size, size, rr, rr)
    p.setClipPath(clip)
    if path and os.path.exists(path):
        src = QPixmap(path)
        scaled = src.scaled(size, size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation)
        x = (scaled.width() - size) // 2
        y = (scaled.height() - size) // 2
        p.drawPixmap(0, 0, scaled, x, y, size, size)
    p.end()
    return px


class Avatar(QLabel):
    def __init__(self, name, size=42, image_path="", parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.refresh(name, image_path)
    def refresh(self, name, image_path=""):
        self.setPixmap(make_avatar(name, self.width(), image_path))


# ── Helpers UI ────────────────────────────────────────────
def btn(text, bg, fg="white", radius=10, font_size=13, bold=False, hover=""):
    b = QPushButton(text)
    w = "bold" if bold else "500"
    hov = hover or (QColor(bg).lighter(112).name() if bg != "transparent" else C["hover"])
    b.setStyleSheet(f"""
        QPushButton {{background:{bg};color:{fg};border:none;border-radius:{radius}px;
            padding:10px 18px;font-size:{font_size}px;font-weight:{w};font-family:'Segoe UI';}}
        QPushButton:hover {{background:{hov};}}
    """)
    b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    return b


def field(radius=10):
    return f"""
        QLineEdit,QTextEdit {{background:{C['panel']};color:{C['text']};
            border:1.5px solid {C['card']};border-radius:{radius}px;
            padding:10px 14px;font-size:13px;font-family:'Segoe UI';
            selection-background-color:{C['accent']};}}
        QLineEdit:focus,QTextEdit:focus {{border-color:{C['accent']};}}
    """


def api_get(path, token):
    try:
        r = requests.get(f"{BASE_URL}{path}", headers=H(token), timeout=8)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def api_post(path, token, payload):
    try:
        r = requests.post(f"{BASE_URL}{path}", json=payload, headers=H(token), timeout=8)
        return r.status_code, (r.json() if r.text else {})
    except Exception:
        return 0, {}

def api_upload(token, filepath):
    try:
        with open(filepath, "rb") as f:
            files = {"file": (os.path.basename(filepath), f)}
            r = requests.post(f"{BASE_URL}/chat/upload_file", files=files, headers=H(token), timeout=60)
        return r.json() if r.status_code == 200 else None
    except Exception as ex:
        print("upload error:", ex)
        return None


# ── Message bubble ────────────────────────────────────────
class Bubble(QWidget):
    def __init__(self, text, outgoing, parent=None):
        super().__init__(parent)
        lo = QHBoxLayout(self); lo.setContentsMargins(16, 2, 16, 2)
        lbl = QLabel(text); lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl.setFont(QFont("Segoe UI", 12))
        lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        lbl.setMaximumWidth(520)
        bg = C["msg_out"] if outgoing else C["msg_in"]
        br = "13px 13px 3px 13px" if outgoing else "13px 13px 13px 3px"
        lbl.setStyleSheet(f"QLabel{{background:{bg};color:{C['text']};border-radius:{br};padding:9px 14px;}}")
        if outgoing: lo.addStretch(); lo.addWidget(lbl)
        else: lo.addWidget(lbl); lo.addStretch()


# ── Contact / friend row ──────────────────────────────────
class FriendRow(QWidget):
    clicked = pyqtSignal(int)
    def __init__(self, user, parent=None):
        super().__init__(parent)
        self.uid = user["id"]; self.uname = user.get("username", "?")
        self._sel = False
        self.setFixedHeight(64)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lo = QHBoxLayout(self); lo.setContentsMargins(10, 7, 10, 7); lo.setSpacing(11)
        self.av = Avatar(self.uname, 46, user.get("avatar_url", ""))
        lo.addWidget(self.av)
        col = QVBoxLayout(); col.setSpacing(2)
        self.name = QLabel(self.uname)
        self.name.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        self.name.setStyleSheet(f"color:{C['text']};background:transparent;")
        self.preview = QLabel("@" + (user.get("slug") or self.uname.lower()))
        self.preview.setFont(QFont("Segoe UI", 11))
        self.preview.setStyleSheet(f"color:{C['text2']};background:transparent;")
        col.addWidget(self.name); col.addWidget(self.preview)
        lo.addLayout(col); lo.addStretch()
        self.unread = 0
        self.badge = QLabel("")
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setFixedHeight(20)
        self.badge.setMinimumWidth(20)
        self.badge.setStyleSheet(f"""
            background:{C['red']};color:white;border-radius:10px;
            font-size:11px;font-weight:bold;padding:0 6px;
        """)
        self.badge.setVisible(False)
        lo.addWidget(self.badge)
        self._upd()

    def add_unread(self):
        self.unread += 1
        self.badge.setText(str(self.unread))
        self.badge.setVisible(True)

    def clear_unread(self):
        self.unread = 0
        self.badge.setVisible(False)
    def set_preview(self, t):
        self.preview.setText(t[:38] + ("…" if len(t) > 38 else ""))
    def set_selected(self, v): self._sel = v; self._upd()
    def _upd(self):
        self.setStyleSheet(f"background:{C['selected'] if self._sel else 'transparent'};border-radius:10px;")
    def mousePressEvent(self, e): self.clicked.emit(self.uid)
    def enterEvent(self, e):
        if not self._sel: self.setStyleSheet(f"background:{C['hover']};border-radius:10px;")
    def leaveEvent(self, e): self._upd()


# ── Profile dialog (view another user) ────────────────────
class ProfileDialog(QDialog):
    action_done = pyqtSignal()
    def __init__(self, token, me, user, parent=None):
        super().__init__(parent)
        self.token = token; self.me = me; self.user = user
        self.setWindowTitle("Profile")
        self.setFixedSize(380, 500)
        self.setStyleSheet(f"background:{C['bg']};")
        self._build()
    def _build(self):
        lo = QVBoxLayout(self); lo.setContentsMargins(0, 0, 0, 22); lo.setSpacing(0)
        banner = QWidget(); banner.setFixedHeight(120)
        col = avatar_color(self.user.get("username", "?"))
        banner.setStyleSheet(f"background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                             f"stop:0 {col},stop:1 {QColor(col).darker(170).name()});")
        lo.addWidget(banner)
        avw = QWidget(); avw.setFixedHeight(94)
        avl = QHBoxLayout(avw); avl.setContentsMargins(0, 0, 0, 0)
        st_early = api_get(f"/friends/status/{self.user['id']}", self.token) or {"status": "none"}
        hide = self.user.get("is_private", False) and st_early.get("status") != "friends"
        avatar_img = "" if hide else self.user.get("avatar_url", "")
        av = Avatar(self.user.get("username", "?"), 88, avatar_img)
        avl.addStretch(); avl.addWidget(av); avl.addStretch()
        lo.addWidget(avw)

        name = QLabel(self.user.get("username", ""))
        name.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet(f"color:{C['text']};margin-top:8px;")
        lo.addWidget(name)

        handle = QLabel("@" + (self.user.get("slug") or self.user.get("username", "user").lower()))
        handle.setFont(QFont("Segoe UI", 12))
        handle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        handle.setStyleSheet(f"color:{C['accent']};")
        lo.addWidget(handle)
        if self.user.get("show_online", True):
            status = QLabel(format_last_seen(self.user.get("last_seen")))
            status.setFont(QFont("Segoe UI", 11))
            status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            is_online = format_last_seen(self.user.get("last_seen")) == "online"
            status.setStyleSheet(f"color:{C['green'] if is_online else C['text2']};")
            lo.addWidget(status)

        lo.addSpacing(16)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{C['divider']};"); lo.addWidget(sep)
        lo.addSpacing(12)

        st = api_get(f"/friends/status/{self.user['id']}", self.token) or {"status": "none"}
        is_friend = st.get("status") == "friends"
        is_private = self.user.get("is_private", False)

        bt = QLabel("BIO")
        bt.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        bt.setStyleSheet(f"color:{C['text3']};padding:0 24px;letter-spacing:1px;")
        lo.addWidget(bt)

        if is_private and not is_friend:
            bio = QLabel("🔒 This profile is private.")
            bio.setStyleSheet(f"color:{C['text2']};padding:4px 24px;font-style:italic;")
        else:
            bio = QLabel(self.user.get("bio", "") or "No bio yet.")
            bio.setStyleSheet(f"color:{C['text']};padding:4px 24px;")
        bio.setFont(QFont("Segoe UI", 12));
        bio.setWordWrap(True)
        lo.addWidget(bio)
        lo.addStretch()

        # Bouton selon le statut d'amitié
        self.status_box = QHBoxLayout()
        self.status_box.setContentsMargins(24, 0, 24, 0)
        lo.addLayout(self.status_box)
        self._refresh_action()

    def _refresh_action(self):
        while self.status_box.count():
            it = self.status_box.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        st = api_get(f"/friends/status/{self.user['id']}", self.token) or {"status": "none"}
        s = st.get("status")
        if s == "friends":
            rm = btn("Remove friend", C["red"], bold=True)
            rm.clicked.connect(self._remove)
            self.status_box.addWidget(rm)
        elif s == "request_sent":
            lbl = QLabel("Request sent ✓")
            lbl.setStyleSheet(f"color:{C['text2']};font-size:13px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.status_box.addWidget(lbl)
        elif s == "request_received":
            acc = btn("Accept", C["green"], bold=True)
            acc.clicked.connect(self._accept)
            dec = btn("Decline", C["card"], C["text2"])
            dec.clicked.connect(self._decline)
            self.status_box.addWidget(acc); self.status_box.addWidget(dec)
        else:
            add = btn("Add friend", C["accent"], bold=True, font_size=14)
            add.clicked.connect(self._add)
            self.status_box.addWidget(add)

    def _add(self):
        api_post("/friends/request", self.token, {"user_id": self.user["id"]})
        self._refresh_action(); self.action_done.emit()
    def _accept(self):
        api_post("/friends/accept", self.token, {"user_id": self.user["id"]})
        self._refresh_action(); self.action_done.emit()
    def _decline(self):
        api_post("/friends/decline", self.token, {"user_id": self.user["id"]})
        self._refresh_action(); self.action_done.emit()
    def _remove(self):
        api_post("/friends/decline", self.token, {"user_id": self.user["id"]})
        self._refresh_action();
        self.action_done.emit()

# ── Friend requests dialog ────────────────────────────────
class RequestsDialog(QDialog):
    changed = pyqtSignal()
    def __init__(self, token, me, parent=None):
        super().__init__(parent)
        self.token = token; self.me = me
        self.setWindowTitle("Friend requests")
        self.setFixedSize(380, 460)
        self.setStyleSheet(f"background:{C['bg']};")
        self._build()
    def _build(self):
        lo = QVBoxLayout(self); lo.setContentsMargins(20, 20, 20, 20); lo.setSpacing(10)
        t = QLabel("Friend requests")
        t.setFont(QFont("Segoe UI", 17, QFont.Weight.Bold))
        t.setStyleSheet(f"color:{C['text']};"); lo.addWidget(t)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("border:none;background:transparent;")
        self.box = QWidget(); self.box.setStyleSheet("background:transparent;")
        self.vbox = QVBoxLayout(self.box); self.vbox.setSpacing(8)
        self.vbox.addStretch()
        self.scroll.setWidget(self.box); lo.addWidget(self.scroll)
        self._load()
    def _load(self):
        while self.vbox.count() > 1:
            it = self.vbox.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        reqs = api_get("/friends/requests", self.token) or []
        if not reqs:
            empty = QLabel("No pending requests.")
            empty.setStyleSheet(f"color:{C['text2']};")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.vbox.insertWidget(0, empty)
            return
        for r in reqs:
            u = r["user"]
            card = QWidget()
            card.setStyleSheet(f"background:{C['card']};border-radius:12px;")
            cl = QHBoxLayout(card); cl.setContentsMargins(12, 10, 12, 10); cl.setSpacing(11)
            cl.addWidget(Avatar(u["username"], 42, u.get("avatar_url", "")))
            col = QVBoxLayout(); col.setSpacing(2)
            nm = QLabel(u["username"]); nm.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
            nm.setStyleSheet(f"color:{C['text']};background:transparent;")
            hd = QLabel("@" + u.get("slug", "")); hd.setFont(QFont("Segoe UI", 10))
            hd.setStyleSheet(f"color:{C['text2']};background:transparent;")
            col.addWidget(nm); col.addWidget(hd); cl.addLayout(col); cl.addStretch()
            acc = btn("Accept", C["green"], bold=True, font_size=12); acc.setFixedHeight(34)
            dec = btn("Decline", C["panel"], C["text2"], font_size=12); dec.setFixedHeight(34)
            acc.clicked.connect(lambda _, uid=u["id"]: self._accept(uid))
            dec.clicked.connect(lambda _, uid=u["id"]: self._decline(uid))
            cl.addWidget(acc); cl.addWidget(dec)
            self.vbox.insertWidget(self.vbox.count() - 1, card)
    def _accept(self, uid):
        api_post("/friends/accept", self.token, {"user_id": uid})
        self._load(); self.changed.emit()
    def _decline(self, uid):
        api_post("/friends/decline", self.token, {"user_id": uid})
        self._load(); self.changed.emit()

class Toggle(QPushButton):
    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(46, 26)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._update()
        self.toggled.connect(self._update)
    def _update(self):
        if self.isChecked():
            self.setStyleSheet(f"""QPushButton{{background:{C['accent']};
                border:none;border-radius:13px;}}""")
        else:
            self.setStyleSheet(f"""QPushButton{{background:{C['card']};
                border:none;border-radius:13px;}}""")
    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("white")); p.setPen(Qt.PenStyle.NoPen)
        x = self.width() - 22 if self.isChecked() else 4
        p.drawEllipse(x, 3, 20, 20)
        p.end()

# ── Settings dialog ───────────────────────────────────────
class SettingsDialog(QDialog):
    profile_updated = pyqtSignal(dict)
    notif_changed = pyqtSignal(bool)
    def __init__(self, token, user, parent=None):
        super().__init__(parent)
        self.token = token; self.user = user; self.avatar_path = ""
        self.setWindowTitle("Settings")
        self.setFixedSize(430, 560)
        self.setStyleSheet(f"background:{C['bg']};")
        self._build()
    def _build(self):
        lo = QVBoxLayout(self); lo.setContentsMargins(34, 30, 34, 30); lo.setSpacing(12)
        t = QLabel("My profile")
        t.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        t.setStyleSheet(f"color:{C['text']};"); lo.addWidget(t)
        av_row = QHBoxLayout()
        self.av_w = Avatar(self.user.get("username", "?"), 80, self.user.get("avatar_url", ""))
        self.av_w.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.av_w.mousePressEvent = lambda e: self._pick()
        ch = QLabel("Tap to change"); ch.setFont(QFont("Segoe UI", 10))
        ch.setStyleSheet(f"color:{C['text2']};")
        avc = QVBoxLayout(); avc.setSpacing(6)
        avc.addWidget(self.av_w, alignment=Qt.AlignmentFlag.AlignCenter)
        avc.addWidget(ch, alignment=Qt.AlignmentFlag.AlignCenter)
        av_row.addLayout(avc); av_row.addStretch(); lo.addLayout(av_row)
        ls = f"color:{C['text2']};font-size:11px;font-family:'Segoe UI';"
        def lbl(x): l = QLabel(x); l.setStyleSheet(ls); return l
        lo.addWidget(lbl("Username"))
        self.un = QLineEdit(self.user.get("username", "")); self.un.setFixedHeight(42)
        self.un.setStyleSheet(field()); lo.addWidget(self.un)
        lo.addWidget(lbl("Bio"))
        self.bio = QTextEdit(); self.bio.setFixedHeight(76)
        self.bio.setPlainText(self.user.get("bio", "")); self.bio.setStyleSheet(field())
        lo.addWidget(self.bio)
        self.status = QLabel(""); self.status.setFont(QFont("Segoe UI", 11))
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter); lo.addWidget(self.status)
        def toggle_row(label_text, desc_text, checked):
            row = QWidget()
            rl = QHBoxLayout(row);
            rl.setContentsMargins(0, 4, 0, 4)
            col = QVBoxLayout();
            col.setSpacing(1)
            lab = QLabel(label_text)
            lab.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
            lab.setStyleSheet(f"color:{C['text']};")
            desc = QLabel(desc_text)
            desc.setFont(QFont("Segoe UI", 10))
            desc.setStyleSheet(f"color:{C['text2']};")
            col.addWidget(lab);
            col.addWidget(desc)
            rl.addLayout(col);
            rl.addStretch()
            tog = Toggle(checked)
            rl.addWidget(tog)
            return row, tog

        sep2 = QFrame();
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color:{C['divider']};")
        lo.addWidget(sep2)

        priv_row, self.priv_toggle = toggle_row(
            "Private profile", "Only friends can see your bio and message you",
            self.user.get("is_private", False))
        lo.addWidget(priv_row)

        online_row, self.online_toggle = toggle_row(
            "Show online status", "Others can see when you're online",
            self.user.get("show_online", True))
        lo.addWidget(online_row)
        notif_row, self.notif_toggle = toggle_row(
            "Notifications", "Sound and desktop alerts for new messages",
            getattr(self.parent(), "notifications_on", True) if self.parent() else True)
        lo.addWidget(notif_row)
        self.notif_toggle.toggled.connect(self.notif_changed.emit)
        lo.addStretch()
        save = btn("Save changes", C["accent"], bold=True, font_size=14)
        save.setFixedHeight(46); save.clicked.connect(self._save); lo.addWidget(save)
    def _pick(self):
        p, _ = QFileDialog.getOpenFileName(self, "Choose image", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if p: self.avatar_path = p; self.av_w.refresh(self.user.get("username", "?"), p)
    def _save(self):
        payload = {
            "username": self.un.text().strip(),
            "bio": self.bio.toPlainText().strip(),
            "is_private": self.priv_toggle.isChecked(),
            "show_online": self.online_toggle.isChecked(),
        }
        if self.avatar_path: payload["avatar_url"] = self.avatar_path
        try:
            r = requests.patch(f"{BASE_URL}/auth/me", json=payload, headers=H(self.token))
            if r.status_code == 200:
                updated = r.json()
                if self.avatar_path: updated["avatar_url"] = self.avatar_path
                self.profile_updated.emit(updated)
                self.status.setStyleSheet(f"color:{C['green']};")
                self.status.setText("✓ Profile updated")
                QTimer.singleShot(1300, self.accept)
            else:
                self.status.setStyleSheet(f"color:{C['red']};")
                self.status.setText("Update failed.")
        except Exception:
            self.status.setStyleSheet(f"color:{C['red']};")
            self.status.setText("Cannot reach server.")


# ── Search dialog ─────────────────────────────────────────
class SearchDialog(QDialog):
    open_profile = pyqtSignal(dict)
    def __init__(self, token, me, parent=None):
        super().__init__(parent)
        self.token = token; self.me = me
        self.setWindowTitle("Find people")
        self.setFixedSize(400, 500)
        self.setStyleSheet(f"background:{C['bg']};")
        self._build()
    def _build(self):
        lo = QVBoxLayout(self); lo.setContentsMargins(20, 20, 20, 20); lo.setSpacing(12)
        t = QLabel("Find people")
        t.setFont(QFont("Segoe UI", 17, QFont.Weight.Bold))
        t.setStyleSheet(f"color:{C['text']};"); lo.addWidget(t)
        self.inp = QLineEdit(); self.inp.setPlaceholderText("Search by @username")
        self.inp.setFixedHeight(42); self.inp.setStyleSheet(field())
        self.inp.textChanged.connect(self._search); lo.addWidget(self.inp)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("border:none;background:transparent;")
        self.box = QWidget(); self.box.setStyleSheet("background:transparent;")
        self.vbox = QVBoxLayout(self.box); self.vbox.setSpacing(4); self.vbox.addStretch()
        self.scroll.setWidget(self.box); lo.addWidget(self.scroll)

    def _search(self):
        q = self.inp.text().strip()
        while self.vbox.count() > 1:
            it = self.vbox.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        if len(q) < 1: return
        # Cherche les utilisateurs
        users = api_get(f"/friends/search?q={q}", self.token) or []
        for u in users:
            row = FriendRow(u)
            row.clicked.connect(lambda _, usr=u: self._open(usr))
            self.vbox.insertWidget(self.vbox.count() - 1, row)
        # Cherche les groupes publics
        groups = api_get(f"/groups/search/public?q={q}", self.token) or []
        for g in groups:
            row = self._group_result(g)
            self.vbox.insertWidget(self.vbox.count() - 1, row)

    def _group_result(self, g):
        row = QWidget();
        row.setFixedHeight(60)
        row.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        row.setStyleSheet(f"background:{C['card']};border-radius:10px;")
        rl = QHBoxLayout(row);
        rl.setContentsMargins(10, 6, 10, 6);
        rl.setSpacing(10)
        rl.addWidget(Avatar(g["name"], 42, g.get("avatar_url", "")))
        col = QVBoxLayout();
        col.setSpacing(1)
        nm = QLabel("🌐 " + g["name"]);
        nm.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        nm.setStyleSheet(f"color:{C['text']};background:transparent;")
        sub = QLabel("Public group");
        sub.setFont(QFont("Segoe UI", 10))
        sub.setStyleSheet(f"color:{C['text2']};background:transparent;")
        col.addWidget(nm);
        col.addWidget(sub);
        rl.addLayout(col);
        rl.addStretch()
        join = btn("Join", C["accent"], font_size=12);
        join.setFixedHeight(30)
        join.clicked.connect(lambda: self._join_group(g["id"]))
        rl.addWidget(join)
        return row

    def _join_group(self, gid):
        api_post(f"/groups/{gid}/join", self.token, {})
        self.accept()
    def _open(self, user):
        self.open_profile.emit(user)


# ── Login ─────────────────────────────────────────────────
class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Velo")
        self.setFixedSize(420, 500)
        self.setStyleSheet(f"background:{C['bg']};")
        self.token = None; self.user = None
        self._build()
    def _build(self):
        lo = QVBoxLayout(self); lo.setContentsMargins(48, 44, 48, 40); lo.setSpacing(0)
        icon = QLabel()
        if os.path.exists(LOGO_PATH):
            icon.setPixmap(make_rounded_logo(LOGO_PATH, 104, radius_ratio=0.40))
        else:
            icon.setText("✈"); icon.setFont(QFont("Segoe UI Emoji", 52))
            icon.setStyleSheet(f"color:{C['accent']};")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lo.addWidget(icon)
        lo.addSpacing(14)
        t = QLabel("Velo"); t.setFont(QFont("Segoe UI", 25, QFont.Weight.Bold))
        t.setAlignment(Qt.AlignmentFlag.AlignCenter); t.setStyleSheet(f"color:{C['text']};")
        lo.addWidget(t)
        sub = QLabel("Fast and secure messaging"); sub.setFont(QFont("Segoe UI", 12))
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color:{C['text2']};margin-bottom:28px;"); lo.addWidget(sub)
        self.email = QLineEdit(); self.email.setPlaceholderText("Email address")
        self.email.setFixedHeight(44); self.email.setStyleSheet(field(12)); lo.addWidget(self.email)
        lo.addSpacing(10)
        self.pw = QLineEdit(); self.pw.setPlaceholderText("Password")
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw.setFixedHeight(44); self.pw.setStyleSheet(field(12))
        self.pw.returnPressed.connect(self._login); lo.addWidget(self.pw)
        lo.addSpacing(10)
        self.err = QLabel(""); self.err.setFont(QFont("Segoe UI", 11))
        self.err.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.err.setStyleSheet(f"color:{C['red']};"); lo.addWidget(self.err)
        lo.addSpacing(6)
        lb = btn("Log in", C["accent"], bold=True, font_size=14)
        lb.setFixedHeight(46); lb.clicked.connect(self._login); lo.addWidget(lb)
        lo.addSpacing(10)
        rb = QPushButton("Create account"); rb.setFixedHeight(44)
        rb.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        rb.setStyleSheet(f"""QPushButton{{background:transparent;color:{C['accent']};
            border:1.5px solid {C['accent']};border-radius:10px;font-size:13px;
            font-weight:500;font-family:'Segoe UI';}}
            QPushButton:hover{{background:{C['hover']};}}""")
        rb.clicked.connect(lambda: RegisterDialog(self).exec())
        lo.addWidget(rb); lo.addStretch()
    def _login(self):
        self.err.setText("")
        try:
            r = requests.post(f"{BASE_URL}/auth/login",
                              json={"email": self.email.text().strip(), "password": self.pw.text()})
            if r.status_code == 200:
                self.token = r.json()["access_token"]
                self.user = api_get("/auth/me", self.token); self.accept()
            else:
                self.err.setText("Wrong email or password.")
        except Exception:
            self.err.setText("Cannot reach server.")


class RegisterDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create account")
        self.setFixedSize(380, 410)
        self.setStyleSheet(f"background:{C['bg']};")
        lo = QVBoxLayout(self); lo.setContentsMargins(36, 36, 36, 36); lo.setSpacing(10)
        t = QLabel("Create account"); t.setFont(QFont("Segoe UI", 17, QFont.Weight.Bold))
        t.setStyleSheet(f"color:{C['text']};margin-bottom:10px;"); lo.addWidget(t)
        self.un = QLineEdit(); self.un.setPlaceholderText("Username")
        self.em = QLineEdit(); self.em.setPlaceholderText("Email")
        self.pw = QLineEdit(); self.pw.setPlaceholderText("Password")
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        for w in (self.un, self.em, self.pw):
            w.setFixedHeight(44); w.setStyleSheet(field(10)); lo.addWidget(w)
        self.msg = QLabel(""); self.msg.setFont(QFont("Segoe UI", 11))
        self.msg.setAlignment(Qt.AlignmentFlag.AlignCenter); lo.addWidget(self.msg)
        b = btn("Create", C["accent"], bold=True, font_size=14)
        b.setFixedHeight(46); b.clicked.connect(self._submit); lo.addWidget(b); lo.addStretch()
    def _submit(self):
        try:
            r = requests.post(f"{BASE_URL}/auth/register",
                              json={"username": self.un.text().strip(),
                                    "email": self.em.text().strip(),
                                    "password": self.pw.text()})
            if r.status_code == 200:
                self.msg.setStyleSheet(f"color:{C['green']};")
                self.msg.setText("✓ Account created! You can log in.")
                QTimer.singleShot(1300, self.accept)
            else:
                self.msg.setStyleSheet(f"color:{C['red']};")
                self.msg.setText("Username or email already taken.")
        except Exception:
            self.msg.setStyleSheet(f"color:{C['red']};")
            self.msg.setText("Cannot reach server.")

class CreateGroupDialog(QDialog):
    created = pyqtSignal(dict)
    def __init__(self, token, parent=None):
        super().__init__(parent)
        self.token = token
        self.setWindowTitle("New group")
        self.setFixedSize(380, 360)
        self.setStyleSheet(f"background:{C['bg']};")
        self._build()
    def _build(self):
        lo = QVBoxLayout(self); lo.setContentsMargins(32, 28, 32, 28); lo.setSpacing(12)
        t = QLabel("Create a group")
        t.setFont(QFont("Segoe UI", 17, QFont.Weight.Bold))
        t.setStyleSheet(f"color:{C['text']};"); lo.addWidget(t)
        self.name = QLineEdit(); self.name.setPlaceholderText("Group name")
        self.name.setFixedHeight(44); self.name.setStyleSheet(field()); lo.addWidget(self.name)
        self.bio = QLineEdit(); self.bio.setPlaceholderText("Description (optional)")
        self.bio.setFixedHeight(44); self.bio.setStyleSheet(field()); lo.addWidget(self.bio)
        # Toggle privé
        row = QWidget()
        rl = QHBoxLayout(row); rl.setContentsMargins(0, 4, 0, 4)
        col = QVBoxLayout(); col.setSpacing(1)
        lab = QLabel("Private group")
        lab.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        lab.setStyleSheet(f"color:{C['text']};")
        desc = QLabel("Members need an invitation to join")
        desc.setFont(QFont("Segoe UI", 10)); desc.setStyleSheet(f"color:{C['text2']};")
        col.addWidget(lab); col.addWidget(desc)
        rl.addLayout(col); rl.addStretch()
        self.priv = Toggle(False); rl.addWidget(self.priv)
        lo.addWidget(row)
        self.msg = QLabel(""); self.msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg.setFont(QFont("Segoe UI", 11)); lo.addWidget(self.msg)
        lo.addStretch()
        b = btn("Create group", C["accent"], bold=True, font_size=14)
        b.setFixedHeight(46); b.clicked.connect(self._create); lo.addWidget(b)
    def _create(self):
        name = self.name.text().strip()
        if not name:
            self.msg.setStyleSheet(f"color:{C['red']};")
            self.msg.setText("Please enter a group name.")
            return
        code, data = api_post("/groups/create", self.token, {
            "name": name, "bio": self.bio.text().strip(),
            "is_private": self.priv.isChecked(),
        })
        if code == 200:
            self.created.emit(data)
            self.accept()
        else:
            self.msg.setStyleSheet(f"color:{C['red']};")
            self.msg.setText("Could not create group.")

class GroupRow(QWidget):
    clicked = pyqtSignal(int)
    def __init__(self, group, parent=None):
        super().__init__(parent)
        self.gid = group["id"]; self.gname = group.get("name", "?")
        self._sel = False
        self.setFixedHeight(64)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lo = QHBoxLayout(self); lo.setContentsMargins(10, 7, 10, 7); lo.setSpacing(11)
        self.av = Avatar(self.gname, 46, group.get("avatar_url", ""))
        lo.addWidget(self.av)
        col = QVBoxLayout(); col.setSpacing(2)
        self.name = QLabel(self.gname)
        self.name.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        self.name.setStyleSheet(f"color:{C['text']};background:transparent;")
        lock = "🔒 " if group.get("is_private") else ""
        self.preview = QLabel(f"{lock}Group")
        self.preview.setFont(QFont("Segoe UI", 11))
        self.preview.setStyleSheet(f"color:{C['text2']};background:transparent;")
        col.addWidget(self.name); col.addWidget(self.preview)
        lo.addLayout(col); lo.addStretch()
        self._upd()
    def set_selected(self, v): self._sel = v; self._upd()
    def _upd(self):
        self.setStyleSheet(f"background:{C['selected'] if self._sel else 'transparent'};border-radius:10px;")
    def mousePressEvent(self, e): self.clicked.emit(self.gid)
    def enterEvent(self, e):
        if not self._sel: self.setStyleSheet(f"background:{C['hover']};border-radius:10px;")
    def leaveEvent(self, e): self._upd()

class InviteFriendDialog(QDialog):
    def __init__(self, token, me, gid, parent=None):
        super().__init__(parent)
        self.token = token; self.me = me; self.gid = gid
        self.setWindowTitle("Invite friend")
        self.setFixedSize(360, 440)
        self.setStyleSheet(f"background:{C['bg']};")
        self._build()
    def _build(self):
        lo = QVBoxLayout(self); lo.setContentsMargins(20, 20, 20, 20); lo.setSpacing(10)
        t = QLabel("Invite a friend")
        t.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        t.setStyleSheet(f"color:{C['text']};"); lo.addWidget(t)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("border:none;background:transparent;")
        self.box = QWidget(); self.box.setStyleSheet("background:transparent;")
        self.vbox = QVBoxLayout(self.box); self.vbox.setSpacing(6); self.vbox.addStretch()
        self.scroll.setWidget(self.box); lo.addWidget(self.scroll)
        self._load()
    def _load(self):
        friends = api_get("/friends/list", self.token) or []
        for u in friends:
            row = QWidget(); row.setStyleSheet(f"background:{C['card']};border-radius:8px;")
            rl = QHBoxLayout(row); rl.setContentsMargins(8, 6, 8, 6); rl.setSpacing(10)
            rl.addWidget(Avatar(u["username"], 36, u.get("avatar_url", "")))
            nm = QLabel(u["username"]); nm.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
            nm.setStyleSheet(f"color:{C['text']};background:transparent;")
            rl.addWidget(nm); rl.addStretch()
            inv = btn("Invite", C["accent"], font_size=11); inv.setFixedHeight(30)
            inv.clicked.connect(lambda _, uid=u["id"], b=inv: self._invite(uid, b))
            rl.addWidget(inv)
            self.vbox.insertWidget(self.vbox.count() - 1, row)
    def _invite(self, uid, button):
        api_post(f"/groups/{self.gid}/invite", self.token, {"user_id": uid})
        button.setText("Invited ✓")
        button.setEnabled(False)

class GroupProfileDialog(QDialog):
    changed = pyqtSignal()
    left = pyqtSignal()
    def __init__(self, token, me, group, parent=None):
        super().__init__(parent)
        self.token = token; self.me = me; self.group = group
        self.gid = group["id"]
        self.my_role = "member"
        self.setWindowTitle("Group")
        self.setFixedSize(400, 560)
        self.setStyleSheet(f"background:{C['bg']};")
        self.avatar_path = ""
        self._build()
        self._load_members()

    def _mod_menu(self, m):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{background:{C['card']};color:{C['text']};border:1px solid {C['divider']};
                border-radius:8px;padding:4px;font-family:'Segoe UI';font-size:12px;}}
            QMenu::item {{padding:8px 20px;border-radius:6px;}}
            QMenu::item:selected {{background:{C['hover']};}}
        """)
        # Promote / demote (owner only)
        if self.my_role == "owner":
            if m["role"] == "member":
                menu.addAction("⬆  Promote to admin", lambda: self._do("promote", m["user_id"]))
            elif m["role"] == "admin":
                menu.addAction("⬇  Demote to member", lambda: self._do("demote", m["user_id"]))
            menu.addSeparator()
        # Kick
        menu.addAction("👢  Kick", lambda: self._do("kick", m["user_id"]))
        # Ban (sous-menu durée)
        menu.addAction("🔨  Ban 1 day", lambda: self._ban(m["user_id"], 1))
        menu.addAction("🔨  Ban 7 days", lambda: self._ban(m["user_id"], 7))
        menu.addAction("🔨  Ban permanently", lambda: self._ban(m["user_id"], 0))
        menu.exec(QCursor.pos())

    def _do(self, action, uid):
        api_post(f"/groups/{self.gid}/{action}", self.token, {"user_id": uid})
        self._load_members()
        self.changed.emit()

    def _ban(self, uid, days):
        api_post(f"/groups/{self.gid}/ban", self.token, {"user_id": uid, "days": days})
        self._load_members()
        self.changed.emit()

    def _open_invite(self):
        dlg = InviteFriendDialog(self.token, self.me, self.gid, self)
        dlg.exec()

    def _build(self):
        lo = QVBoxLayout(self); lo.setContentsMargins(0, 0, 0, 16); lo.setSpacing(0)
        banner = QWidget(); banner.setFixedHeight(100)
        col = avatar_color(self.group.get("name", "?"))
        banner.setStyleSheet(f"background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                             f"stop:0 {col},stop:1 {QColor(col).darker(170).name()});")
        lo.addWidget(banner)
        avw = QWidget(); avw.setFixedHeight(90)
        avl = QHBoxLayout(avw); avl.setContentsMargins(0, 0, 0, 0)
        self.av = Avatar(self.group.get("name", "?"), 84, self.group.get("avatar_url", ""))
        self.av.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.av.mousePressEvent = lambda e: self._maybe_change_avatar()
        avl.addStretch(); avl.addWidget(self.av); avl.addStretch()
        lo.addWidget(avw)
        self.name_lbl = QLabel(self.group.get("name", ""))
        self.name_lbl.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self.name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_lbl.setStyleSheet(f"color:{C['text']};margin-top:8px;")
        lo.addWidget(self.name_lbl)
        priv = "🔒 Private group" if self.group.get("is_private") else "🌐 Public group"
        sub = QLabel(priv); sub.setFont(QFont("Segoe UI", 11))
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color:{C['text2']};")
        lo.addWidget(sub)
        bio = QLabel(self.group.get("bio", "") or "No description.")
        bio.setFont(QFont("Segoe UI", 12)); bio.setWordWrap(True)
        bio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bio.setStyleSheet(f"color:{C['text']};padding:8px 24px;")
        lo.addWidget(bio)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{C['divider']};"); lo.addWidget(sep)
        mt = QLabel("MEMBERS")
        mt.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        mt.setStyleSheet(f"color:{C['text3']};padding:10px 24px 4px 24px;letter-spacing:1px;")
        lo.addWidget(mt)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("border:none;background:transparent;")
        self.mbox = QWidget(); self.mbox.setStyleSheet("background:transparent;")
        self.mvbox = QVBoxLayout(self.mbox); self.mvbox.setContentsMargins(16, 0, 16, 0)
        self.mvbox.setSpacing(3); self.mvbox.addStretch()
        self.scroll.setWidget(self.mbox); lo.addWidget(self.scroll)
        self.invite_btn = btn("+ Invite friend", C["accent"], bold=True)
        self.invite_btn.clicked.connect(self._open_invite)
        self.invite_btn.setVisible(False)
        wrap_inv = QHBoxLayout();
        wrap_inv.setContentsMargins(24, 8, 24, 0)
        wrap_inv.addWidget(self.invite_btn)
        lo.addLayout(wrap_inv)
        self.leave_btn = btn("Leave group", C["red"], bold=True)
        self.leave_btn.clicked.connect(self._leave)
        wrap = QHBoxLayout(); wrap.setContentsMargins(24, 8, 24, 0)
        wrap.addWidget(self.leave_btn)
        lo.addLayout(wrap)
    def _load_members(self):
        members = api_get(f"/groups/{self.gid}/members", self.token) or []
        for m in members:
            if m["user_id"] == self.me["id"]:
                self.my_role = m["role"]
        # owner cannot leave
        if self.my_role == "owner":
            self.leave_btn.setVisible(False)
        if self.my_role in ("owner", "admin"):
            self.invite_btn.setVisible(True)
        while self.mvbox.count() > 1:
            it = self.mvbox.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        role_order = {"owner": 0, "admin": 1, "member": 2}
        members.sort(key=lambda x: role_order.get(x["role"], 3))
        for m in members:
            self.mvbox.insertWidget(self.mvbox.count() - 1, self._member_row(m))

    def _member_row(self, m):
        row = QWidget();
        row.setStyleSheet(f"background:{C['card']};border-radius:8px;")
        rl = QHBoxLayout(row);
        rl.setContentsMargins(8, 6, 8, 6);
        rl.setSpacing(10)
        rl.addWidget(Avatar(m["username"], 36, m.get("avatar_url", "")))
        col = QVBoxLayout();
        col.setSpacing(1)
        nm = QLabel(m["username"]);
        nm.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        nm.setStyleSheet(f"color:{C['text']};background:transparent;")
        hd = QLabel("@" + m.get("slug", ""));
        hd.setFont(QFont("Segoe UI", 10))
        hd.setStyleSheet(f"color:{C['text2']};background:transparent;")
        col.addWidget(nm);
        col.addWidget(hd);
        rl.addLayout(col);
        rl.addStretch()
        if m["role"] != "member":
            badge_color = C["orange"] if m["role"] == "owner" else C["accent"]
            badge = QLabel(m["role"].upper())
            badge.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            badge.setStyleSheet(f"color:white;background:{badge_color};border-radius:6px;padding:2px 8px;")
            rl.addWidget(badge)
        # Bouton de modération (si on a les droits et que ce n'est pas soi-même)
        can_moderate = (
                self.my_role in ("owner", "admin")
                and m["user_id"] != self.me["id"]
                and m["role"] != "owner"
                and not (self.my_role == "admin" and m["role"] == "admin")
        )
        if can_moderate:
            mod = QPushButton("⋮");
            mod.setFixedSize(28, 28)
            mod.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            mod.setStyleSheet(f"""QPushButton{{background:transparent;color:{C['text2']};
                border:none;border-radius:14px;font-size:16px;font-weight:bold;}}
                QPushButton:hover{{background:{C['hover']};color:{C['text']};}}""")
            mod.clicked.connect(lambda: self._mod_menu(m))
            rl.addWidget(mod)
        return row
    def _maybe_change_avatar(self):
        if self.my_role not in ("owner", "admin"):
            return
        p, _ = QFileDialog.getOpenFileName(self, "Group image", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if p:
            self.avatar_path = p
            self.av.refresh(self.group.get("name", "?"), p)
            try:
                requests.patch(f"{BASE_URL}/groups/{self.gid}", json={"avatar_url": p}, headers=H(self.token))
                self.changed.emit()
            except Exception: pass
    def _leave(self):
        api_post(f"/groups/{self.gid}/leave", self.token, {})
        self.left.emit(); self.accept()

class InviteCard(QWidget):
    joined = pyqtSignal()
    def __init__(self, token, me, group_id, parent=None):
        super().__init__(parent)
        self.token = token; self.me = me; self.group_id = group_id
        self._build()
    def _build(self):
        outer = QHBoxLayout(self); outer.setContentsMargins(16, 4, 16, 4)
        card = QWidget(); card.setFixedWidth(280)
        card.setStyleSheet(f"background:{C['card']};border-radius:12px;")
        cl = QVBoxLayout(card); cl.setContentsMargins(14, 12, 14, 12); cl.setSpacing(8)
        # Charge les infos du groupe
        g = api_get(f"/groups/{self.group_id}", self.token) or {}
        top = QHBoxLayout(); top.setSpacing(10)
        top.addWidget(Avatar(g.get("name", "?"), 44, g.get("avatar_url", "")))
        col = QVBoxLayout(); col.setSpacing(2)
        lab = QLabel("GROUP INVITATION")
        lab.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        lab.setStyleSheet(f"color:{C['accent']};letter-spacing:1px;background:transparent;")
        nm = QLabel(g.get("name", "Unknown"))
        nm.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        nm.setStyleSheet(f"color:{C['text']};background:transparent;")
        col.addWidget(lab); col.addWidget(nm)
        top.addLayout(col); top.addStretch()
        cl.addLayout(top)
        if g.get("bio"):
            bio = QLabel(g["bio"]); bio.setWordWrap(True)
            bio.setFont(QFont("Segoe UI", 11))
            bio.setStyleSheet(f"color:{C['text2']};background:transparent;")
            cl.addWidget(bio)
        self.join_btn = btn("Join group", C["accent"], bold=True, font_size=13)
        self.join_btn.clicked.connect(lambda: self._join(g))
        cl.addWidget(self.join_btn)
        outer.addWidget(card); outer.addStretch()
    def _join(self, g):
        api_post(f"/groups/{self.group_id}/join_invited", self.token, {})
        self.join_btn.setText("✓ Joined")
        self.join_btn.setEnabled(False)
        self.joined.emit()

class TypingBubble(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lo = QHBoxLayout(self); lo.setContentsMargins(16, 2, 16, 2)
        self.bubble = QLabel("●  ●  ●")
        self.bubble.setFont(QFont("Segoe UI", 12))
        self.bubble.setStyleSheet(f"""
            QLabel {{background:{C['msg_in']};color:{C['text2']};
                border-radius:13px 13px 13px 3px;padding:9px 14px;}}
        """)
        lo.addWidget(self.bubble); lo.addStretch()
        # Animation des points
        self._dots = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(400)
    def _animate(self):
        self._dots = (self._dots + 1) % 4
        states = ["●  ○  ○", "●  ●  ○", "●  ●  ●", "○  ●  ●"]
        self.bubble.setText(states[self._dots])
    def stop(self):
        self._timer.stop()

# ── Bulle image ───────────────────────────────────────────
class ImageBubble(QWidget):
    def __init__(self, url, token, outgoing, parent=None):
        super().__init__(parent)
        self.url = url; self.token = token
        lo = QHBoxLayout(self); lo.setContentsMargins(16, 3, 16, 3)
        self.lbl = QLabel("Loading image…")
        self.lbl.setStyleSheet(f"color:{C['text2']};background:{C['msg_out' if outgoing else 'msg_in']};"
                               f"border-radius:12px;padding:20px;")
        self.lbl.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        if outgoing: lo.addStretch(); lo.addWidget(self.lbl)
        else: lo.addWidget(self.lbl); lo.addStretch()
        # Télécharge l'image en arrière-plan
        self._worker = ImageLoader(url, token)
        self._worker.loaded.connect(self._show)
        self._worker.start()
    def _show(self, data):
        if not data:
            self.lbl.setText("⚠ Image failed")
            return
        src = QPixmap()
        src.loadFromData(data)
        self._full = QPixmap(); self._full.loadFromData(data)
        disp = src
        if src.width() > 320:
            disp = src.scaledToWidth(320, Qt.TransformationMode.SmoothTransformation)
        # Rounded corners
        rounded = QPixmap(disp.size())
        rounded.fill(Qt.GlobalColor.transparent)
        p = QPainter(rounded)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(0, 0, disp.width(), disp.height(), 12, 12)
        p.setClipPath(path)
        p.drawPixmap(0, 0, disp)
        p.end()
        self.lbl.setPixmap(rounded)
        self.lbl.setStyleSheet("background:transparent;")
        self.lbl.mousePressEvent = lambda e: self._open_full()
    def _open_full(self):
        dlg = QDialog(self); dlg.setWindowTitle("Image")
        dlg.setStyleSheet(f"background:{C['bg']};")
        v = QVBoxLayout(dlg)
        lbl = QLabel();
        show = self._full
        if show.width() > 900: show = show.scaledToWidth(900, Qt.TransformationMode.SmoothTransformation)
        lbl.setPixmap(show); v.addWidget(lbl)
        dlg.exec()


class ImageLoader(QThread):
    loaded = pyqtSignal(object)
    def __init__(self, url, token):
        super().__init__(); self.url = url; self.token = token
    def run(self):
        try:
            r = requests.get(self.url, headers=H(self.token), timeout=30)
            self.loaded.emit(r.content if r.status_code == 200 else None)
        except Exception:
            self.loaded.emit(None)


# ── Bulle fichier ─────────────────────────────────────────
class FileBubble(QWidget):
    def __init__(self, url, token, name, outgoing, parent=None):
        super().__init__(parent)
        self.url = url; self.token = token; self.name = name
        lo = QHBoxLayout(self); lo.setContentsMargins(16, 3, 16, 3)
        card = QWidget(); card.setFixedWidth(260)
        bg = C["msg_out"] if outgoing else C["msg_in"]
        card.setStyleSheet(f"background:{bg};border-radius:12px;")
        cl = QHBoxLayout(card); cl.setContentsMargins(12, 10, 12, 10); cl.setSpacing(10)
        icon = QLabel("📄"); icon.setFont(QFont("Segoe UI Emoji", 22))
        icon.setStyleSheet("background:transparent;")
        cl.addWidget(icon)
        col = QVBoxLayout(); col.setSpacing(1)
        nm = QLabel(name if len(name) < 24 else name[:21]+"…")
        nm.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        nm.setStyleSheet(f"color:{C['text']};background:transparent;")
        sub = QLabel("Click to download"); sub.setFont(QFont("Segoe UI", 9))
        sub.setStyleSheet(f"color:{C['text2']};background:transparent;")
        col.addWidget(nm); col.addWidget(sub); cl.addLayout(col); cl.addStretch()
        card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        card.mousePressEvent = lambda e: self._download()
        if outgoing: lo.addStretch(); lo.addWidget(card)
        else: lo.addWidget(card); lo.addStretch()
    def _download(self):
        save_path, _ = QFileDialog.getSaveFileName(self, "Save file", self.name)
        if not save_path: return
        try:
            r = requests.get(self.url, headers=H(self.token), timeout=60)
            with open(save_path, "wb") as f:
                f.write(r.content)
        except Exception as ex:
            print("download error:", ex)


# ── Bulle vidéo ───────────────────────────────────────────
class VideoBubble(QWidget):
    def __init__(self, url, token, name, outgoing, parent=None):
        super().__init__(parent)
        self.url = url; self.token = token
        lo = QHBoxLayout(self); lo.setContentsMargins(16, 3, 16, 3)
        card = QWidget(); card.setFixedWidth(300)
        bg = C["msg_out"] if outgoing else C["msg_in"]
        card.setStyleSheet(f"background:{bg};border-radius:12px;")
        cl = QVBoxLayout(card); cl.setContentsMargins(8, 8, 8, 8); cl.setSpacing(6)

        self.video = QVideoWidget()
        self.video.setFixedHeight(180)
        self.video.setStyleSheet("background:black;border-radius:8px;")
        cl.addWidget(self.video)

        self.player = QMediaPlayer()
        self.audio = QAudioOutput()
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.player.setSource(__import__("PyQt6.QtCore", fromlist=["QUrl"]).QUrl(url))

        ctrl = QHBoxLayout()
        self.play_btn = QPushButton("▶  Play")
        self.play_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.play_btn.setStyleSheet(f"""QPushButton{{background:{C['accent']};color:white;
            border:none;border-radius:8px;padding:6px 14px;font-size:12px;font-weight:bold;}}
            QPushButton:hover{{background:{C['accent_h']};}}""")
        self.play_btn.clicked.connect(self._toggle)
        ctrl.addWidget(self.play_btn); ctrl.addStretch()
        cl.addLayout(ctrl)

        if outgoing: lo.addStretch(); lo.addWidget(card)
        else: lo.addWidget(card); lo.addStretch()

    def _toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause(); self.play_btn.setText("▶  Play")
        else:
            self.player.play(); self.play_btn.setText("⏸  Pause")

# ── Main window ───────────────────────────────────────────
class VeloApp(QMainWindow):
    sig_msg = pyqtSignal(str, int)
    sig_group_msg = pyqtSignal(str)
    sig_group_closed = pyqtSignal(int)
    def __init__(self, token, user):
        super().__init__()
        self.token = token
        self.user = user
        self.recv_id = None
        self.friends = {}
        self.groups = {}
        self.current_group_id = None
        self.ws = None
        self.notifications_on = True
        self._workers = []
        self.setWindowTitle("Velo")
        self.last_status_label = None
        self.resize(1120, 720); self.setMinimumSize(840, 540)
        self.setStyleSheet(f"background:{C['bg']};")
        self._build_ui()
        self._load_friends()
        self._load_groups()
        self._refresh_badge()
        self._connect_ws()
        self.sig_msg.connect(self._on_incoming)
        self.sig_group_msg.connect(self._on_group_incoming)
        self.sig_group_closed.connect(self._on_group_closed)
        self.group_ws = None
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._periodic_refresh)
        self.refresh_timer.start(5000)
        self._typing_timer = QTimer(self)
        self._typing_timer.setSingleShot(True)
        self._typing_timer.timeout.connect(self._stop_typing)
        self._is_typing = False
        self.typing_bubble = None

    def _parse_attachment(self, content, outgoing):
        # content = "[FILE]type|url|name"
        payload = content[len("[FILE]"):]
        parts = payload.split("|", 2)
        if len(parts) != 3:
            return None
        ftype, url, name = parts
        info = {"type": ftype, "url": url, "name": name}
        return self._make_attachment(info, outgoing)

    def _make_attachment(self, info, outgoing):
        ftype = info.get("type", "file")
        url = info.get("url", "")
        name = info.get("name", "file")
        full_url = f"{BASE_URL}{url}"
        if ftype == "image":
            return ImageBubble(full_url, self.token, outgoing)
        elif ftype == "video":
            return VideoBubble(full_url, self.token, name, outgoing)
        else:
            return FileBubble(full_url, self.token, name, outgoing)

    def _attach_menu(self):
        if not self.recv_id and not self.current_group_id:
            return
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{background:{C['card']};color:{C['text']};border:1px solid {C['divider']};
                border-radius:8px;padding:4px;font-family:'Segoe UI';font-size:12px;}}
            QMenu::item {{padding:8px 20px;border-radius:6px;}}
            QMenu::item:selected {{background:{C['hover']};}}
        """)
        menu.addAction("🖼  Image", lambda: self._pick_attachment("image"))
        menu.addAction("🎬  Video", lambda: self._pick_attachment("video"))
        menu.addAction("📎  File", lambda: self._pick_attachment("file"))
        menu.exec(QCursor.pos())

    def _pick_attachment(self, kind):
        filters = {
            "image": "Images (*.png *.jpg *.jpeg *.webp *.gif)",
            "video": "Videos (*.mp4 *.webm *.mov *.avi *.mkv)",
            "file": "All files (*.*)",
        }
        path, _ = QFileDialog.getOpenFileName(self, "Choose file", "", filters[kind])
        if not path:
            return
        # Upload en arrière-plan
        self._async(api_upload, self._on_uploaded, self.token, path)

    def _on_uploaded(self, result):
        if not result:
            return
        msg = f"[FILE]{result['type']}|{result['url']}|{result['name']}"
        if self.current_group_id and self.group_ws:
            try:
                self.group_ws.send(msg)
                self.msg_vbox.insertWidget(self.msg_vbox.count() - 1, self._make_attachment(result, True))
                self._scroll_bottom()
            except Exception as ex:
                print(ex)
        elif self.recv_id and self.ws:
            try:
                self.ws.send(f"{self.recv_id}:{msg}")
                self.msg_vbox.insertWidget(self.msg_vbox.count() - 1, self._make_attachment(result, True))
                self._scroll_bottom()
            except Exception as ex:
                print(ex)

    def _show_typing(self):
        if self.typing_bubble:
            return  # déjà affichée
        self.typing_bubble = TypingBubble()
        self.msg_vbox.insertWidget(self.msg_vbox.count() - 1, self.typing_bubble)
        self._scroll_bottom()

    def _hide_typing(self):
        if self.typing_bubble:
            self.typing_bubble.stop()
            self.typing_bubble.deleteLater()
            self.typing_bubble = None

    def _on_typing(self):
        # Seulement en DM (pas en groupe)
        if not self.recv_id or not self.ws or self.current_group_id:
            return
        if not self._is_typing:
            self._is_typing = True
            try:
                self.ws.send(f"{self.recv_id}:[TYPING]")
            except Exception:
                pass
        # Relance le timer (2s sans frappe = stop)
        self._typing_timer.start(2000)

    def _stop_typing(self):
        if self._is_typing and self.recv_id and self.ws:
            self._is_typing = False
            try:
                self.ws.send(f"{self.recv_id}:[STOP_TYPING]")
            except Exception:
                pass

    def _set_msg_status(self, text, read=False):
        # Retire l'ancien label de statut
        if self.last_status_label:
            self.last_status_label.deleteLater()
            self.last_status_label = None
        lbl = QLabel(text)
        lbl.setFont(QFont("Segoe UI", 9))
        color = C["accent"] if read else C["text2"]
        lbl.setStyleSheet(f"color:{color};padding:0 20px 4px 0;background:transparent;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.msg_vbox.insertWidget(self.msg_vbox.count() - 1, lbl)
        self.last_status_label = lbl

    def _open_settings(self):
        d = SettingsDialog(self.token, self.user, self)
        d.profile_updated.connect(self._on_updated)
        d.notif_changed.connect(self._set_notifications)
        d.exec()

    def _set_notifications(self, on):
        self.notifications_on = on

    def _on_group_closed(self, gid):
        # Si on a changé de chat entre temps, on ignore
        if self.current_group_id != gid:
            return
        # Vérifie si on est encore membre (en async)
        self._async(api_get, lambda members: self._check_kicked(members, gid),
                    f"/groups/{gid}/members", self.token)

    def _check_kicked(self, members, gid):
        if self.current_group_id != gid:
            return
        if members is None:
            members = []
        my_ids = [m["user_id"] for m in members]
        if self.user["id"] not in my_ids:
            # On a été kické/banni
            self.current_group_id = None
            self.ch_name.setText("Select a chat")
            self.ch_sub.setText("")
            self.view_prof.setVisible(False)
            while self.msg_vbox.count() > 1:
                it = self.msg_vbox.takeAt(0)
                if it.widget(): it.widget().deleteLater()
            # Message d'info
            info = QLabel("You were removed from this group.")
            info.setStyleSheet(f"color:{C['text2']};padding:20px;")
            info.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.msg_vbox.insertWidget(0, info)
            self._load_groups()

    def _connect_group_ws(self, gid):
        if self.group_ws:
            try:
                self.group_ws.close()
            except Exception:
                pass
        self.group_ws = websocket.WebSocketApp(
            f"ws://localhost:8000/chat/group_ws/{gid}/{self.user['id']}",
            on_message=lambda ws, msg: self.sig_group_msg.emit(msg),
            on_close=lambda ws, code, reason: self.sig_group_closed.emit(gid))
        threading.Thread(target=self.group_ws.run_forever, daemon=True).start()

    def _on_group_incoming(self, message):
        if ":" not in message: return
        sender_name, content = message.split(":", 1)
        if sender_name == self.user["username"]:
            return
        if content.startswith("[FILE]"):
            w = self._parse_attachment(content, False)
            if w: self.msg_vbox.insertWidget(self.msg_vbox.count() - 1, w)
        else:
            self.msg_vbox.insertWidget(self.msg_vbox.count() - 1, Bubble(f"{sender_name}: {content}", False))
        self._scroll_bottom()

    def _select_group(self, gid):
        # Désélectionne amis et groupes
        for w in self.friends.values(): w.set_selected(False)
        for w in self.groups.values(): w.set_selected(False)
        if gid in self.groups: self.groups[gid].set_selected(True)
        self.current_group_id = gid
        self.recv_id = None  # on est en mode groupe
        self.view_prof.setVisible(True)
        self.ch_av.setVisible(True)
        self._set_can_send(True)
        # Vide les messages
        while self.msg_vbox.count() > 1:
            it = self.msg_vbox.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        # Charge infos + historique en async
        self._async(api_get, lambda g: self._fill_group_header(g), f"/groups/{gid}", self.token)
        self._async(api_get, lambda m: self._fill_group_history(m, gid), f"/groups/{gid}/history", self.token)
        self._connect_group_ws(gid)

    def _fill_group_header(self, g):
        if not g: return
        self.ch_av.refresh(g.get("name", "?"), g.get("avatar_url", ""))
        self.ch_name.setText(g.get("name", ""))
        lock = "🔒 Private group" if g.get("is_private") else "Public group"
        self.ch_sub.setText(lock)

    def _fill_group_history(self, msgs, gid):
        for i, m in enumerate(msgs):
            outgoing = m["sender_id"] == self.user["id"]
            content = m["content"]
            if content.startswith("[FILE]"):
                w = self._parse_attachment(content, outgoing)
                if w: self.msg_vbox.insertWidget(i, w)
            else:
                text = content if outgoing else f"{m['sender_name']}: {content}"
                self.msg_vbox.insertWidget(i, Bubble(text, outgoing))
        self._scroll_bottom()

    def _load_groups(self):
        self._async(api_get, self._fill_groups, "/groups/my", self.token)

    def _fill_groups(self, groups):
        if groups is None: return
        # Supprime les anciennes GroupRow
        for gid, row in list(self.groups.items()):
            row.deleteLater()
        self.groups.clear()
        pos = self.fvbox.count() - 1
        for g in groups:
            row = GroupRow(g)
            row.clicked.connect(self._select_group)
            self.groups[g["id"]] = row
            self.fvbox.insertWidget(pos, row);
            pos += 1

    def _create_group(self):
        d = CreateGroupDialog(self.token, self)
        d.created.connect(lambda g: self._load_all())
        d.exec()

    def _load_all(self):
        self._load_friends()
        self._load_groups()

    def _apply_can_send(self, st):
        is_friend = st and st.get("status") == "friends"
        self._set_can_send(is_friend)

    def _set_can_send(self, can):
        self.inp.setEnabled(can)
        if can:
            self.inp.setPlaceholderText("Message")
        else:
            self.inp.setPlaceholderText("🔒 Add as friend to send messages")

    def _async(self, fn, callback, *args):
        worker = ApiWorker(fn, *args)
        worker.done.connect(callback)
        worker.done.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        self._workers.append(worker)
        worker.start()

    def _periodic_refresh(self):
        self._async(api_get, self._apply_friends_refresh, "/friends/list", self.token)
        self._async(api_get, self._apply_badge, "/friends/requests", self.token)
        self._async(api_get, self._fill_groups, "/groups/my", self.token)

    def _apply_friends_refresh(self, friends):
        if friends is None: return
        new_ids = {u["id"] for u in friends}
        existing_ids = set(self.friends.keys())
        if new_ids != existing_ids:
            current = self.recv_id
            self._load_friends_from_data(friends)
            if current in self.friends:
                self.friends[current].set_selected(True)
                self.recv_id = current

    def _apply_badge(self, reqs):
        n = len(reqs) if reqs else 0
        if n > 0:
            self.req_btn.setStyleSheet(f"""QPushButton{{background:{C['accent']};color:white;
                border:none;border-radius:17px;font-size:15px;font-weight:bold;}}
                QPushButton:hover{{background:{C['accent_h']};}}""")
        else:
            self.req_btn.setStyleSheet(f"""QPushButton{{background:transparent;color:{C['text2']};
                border:none;border-radius:17px;font-size:17px;}}
                QPushButton:hover{{background:{C['hover']};color:{C['text']};}}""")

    def _build_ui(self):
        root = QWidget(); self.setCentralWidget(root)
        main = QHBoxLayout(root); main.setContentsMargins(0, 0, 0, 0); main.setSpacing(0)

        # ── Sidebar ──────────────────────────────────────
        sidebar = QWidget(); sidebar.setFixedWidth(320)
        sidebar.setStyleSheet(f"background:{C['sidebar']};")
        sb = QVBoxLayout(sidebar); sb.setContentsMargins(0, 0, 0, 0); sb.setSpacing(0)

        hdr = QWidget(); hdr.setFixedHeight(58)
        hdr.setStyleSheet(f"background:{C['sidebar']};border-bottom:1px solid {C['divider']};")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(14, 0, 12, 0)
        self.me_av = Avatar(self.user.get("username", "?"), 36, self.user.get("avatar_url", ""))
        self.me_av.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.me_av.mousePressEvent = lambda e: self._open_settings()
        nm = QLabel(self.user.get("username", "")); nm.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        nm.setStyleSheet(f"color:{C['text']};")
        hl.addWidget(self.me_av); hl.addSpacing(8); hl.addWidget(nm); hl.addStretch()

        def icon_btn(txt, cb):
            b = QPushButton(txt); b.setFixedSize(34, 34)
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.setStyleSheet(f"""QPushButton{{background:transparent;color:{C['text2']};
                border:none;border-radius:17px;font-size:17px;}}
                QPushButton:hover{{background:{C['hover']};color:{C['text']};}}""")
            b.clicked.connect(cb); return b

        self.req_btn = icon_btn("👥", self._open_requests)
        hl.addWidget(icon_btn("🔍", self._open_search))
        hl.addWidget(self.req_btn)
        hl.addWidget(icon_btn("⚙", self._open_settings))
        sb.addWidget(hdr)

        chats_hdr = QWidget()
        chl2 = QHBoxLayout(chats_hdr);
        chl2.setContentsMargins(14, 10, 10, 2)
        lbl = QLabel("CHATS")
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{C['text3']};letter-spacing:1px;")
        chl2.addWidget(lbl);
        chl2.addStretch()
        new_group_btn = QPushButton("+ New group")
        new_group_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        new_group_btn.setStyleSheet(f"""QPushButton{{background:transparent;color:{C['accent']};
                    border:none;font-size:11px;font-weight:bold;font-family:'Segoe UI';}}
                    QPushButton:hover{{color:{C['accent_h']};}}""")
        new_group_btn.clicked.connect(self._create_group)
        chl2.addWidget(new_group_btn)
        sb.addWidget(chats_hdr)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border:none;background:transparent;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.fbox = QWidget(); self.fbox.setStyleSheet("background:transparent;")
        self.fvbox = QVBoxLayout(self.fbox); self.fvbox.setContentsMargins(6, 2, 6, 4)
        self.fvbox.setSpacing(1); self.fvbox.addStretch()
        scroll.setWidget(self.fbox); sb.addWidget(scroll)
        main.addWidget(sidebar)

        sep = QFrame(); sep.setFixedWidth(1); sep.setStyleSheet(f"background:{C['divider']};")
        main.addWidget(sep)

        # ── Chat ──────────────────────────────────────────
        chat = QWidget(); chat.setStyleSheet(f"background:{C['bg']};")
        cl = QVBoxLayout(chat); cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(0)

        self.ch_hdr = QWidget(); self.ch_hdr.setFixedHeight(58)
        self.ch_hdr.setStyleSheet(f"background:{C['sidebar']};border-bottom:1px solid {C['divider']};")
        chl = QHBoxLayout(self.ch_hdr); chl.setContentsMargins(16, 0, 16, 0); chl.setSpacing(12)
        self.ch_av = Avatar("?", 38)
        self.ch_name = QLabel("Select a chat")
        self.ch_name.setFont(QFont("Segoe UI", 14, QFont.Weight.DemiBold))
        self.ch_name.setStyleSheet(f"color:{C['text']};")
        self.ch_sub = QLabel(""); self.ch_sub.setFont(QFont("Segoe UI", 11))
        self.ch_sub.setStyleSheet(f"color:{C['text2']};")
        ncol = QVBoxLayout(); ncol.setSpacing(1); ncol.addWidget(self.ch_name); ncol.addWidget(self.ch_sub)
        self.view_prof = btn("View profile", C["card"], C["text2"], font_size=12)
        self.view_prof.setVisible(False); self.view_prof.clicked.connect(self._view_profile)
        chl.addWidget(self.ch_av); chl.addLayout(ncol); chl.addStretch(); chl.addWidget(self.view_prof)
        cl.addWidget(self.ch_hdr)

        self.msg_scroll = QScrollArea(); self.msg_scroll.setWidgetResizable(True)
        self.msg_scroll.setStyleSheet(f"border:none;background:{C['bg']};")
        self.msg_box = QWidget(); self.msg_box.setStyleSheet(f"background:{C['bg']};")
        self.msg_vbox = QVBoxLayout(self.msg_box)
        self.msg_vbox.setContentsMargins(0, 12, 0, 8); self.msg_vbox.setSpacing(2)
        self.msg_vbox.addStretch()
        self.msg_scroll.setWidget(self.msg_box); cl.addWidget(self.msg_scroll)
        # Hide header avatar until a chat is open
        self.ch_av.setVisible(False)

        ibw = QWidget(); ibw.setFixedHeight(66)
        ibw.setStyleSheet(f"background:{C['sidebar']};border-top:1px solid {C['divider']};")
        ib = QHBoxLayout(ibw); ib.setContentsMargins(14, 10, 14, 10); ib.setSpacing(10)
        attach_btn = QPushButton("+")
        attach_btn.setFixedSize(40, 40)
        attach_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        attach_btn.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        attach_btn.setStyleSheet(f"""QPushButton{{background:{C['card']};color:{C['accent']};
                   border:none;border-radius:20px;padding:0px;text-align:center;}}
                   QPushButton:hover{{background:{C['hover']};}}""")
        attach_btn.clicked.connect(self._attach_menu)
        self.inp = QLineEdit(); self.inp.setPlaceholderText("Message")
        self.inp.setFixedHeight(42)
        self.inp.setStyleSheet(f"""QLineEdit{{background:{C['bg']};color:{C['text']};
            border:none;border-radius:21px;padding:0 18px;font-size:13px;font-family:'Segoe UI';}}""")
        self.inp.returnPressed.connect(self.send_message)
        self.inp.textChanged.connect(self._on_typing)
        sbtn = QPushButton("➤"); sbtn.setFixedSize(44, 44)
        sbtn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        sbtn.setStyleSheet(f"""QPushButton{{background:{C['accent']};color:white;
            border:none;border-radius:22px;font-size:17px;}}
            QPushButton:hover{{background:{C['accent_h']};}}""")
        sbtn.clicked.connect(self.send_message)
        ib.addWidget(attach_btn)
        ib.addWidget(self.inp); ib.addWidget(sbtn); cl.addWidget(ibw)
        main.addWidget(chat)

    # ── Friends ───────────────────────────────────────────
    def _load_friends(self):
        self._async(api_get, lambda f: self._load_friends_from_data(f) if f else None, "/friends/list", self.token)

    def _load_friends_from_data(self, friends):
        # Supprime uniquement les FriendRow existantes
        for uid, row in list(self.friends.items()):
            row.deleteLater()
        self.friends.clear()
        pos = self.fvbox.count() - 1
        for u in friends:
            row = FriendRow(u);
            row.clicked.connect(self._select)
            self.friends[u["id"]] = row
            self.fvbox.insertWidget(pos, row);
            pos += 1

    def _refresh_badge(self):
        reqs = api_get("/friends/requests", self.token) or []
        n = len(reqs)
        self.req_btn.setText(f"👥" if n == 0 else f"👥")
        if n > 0:
            self.req_btn.setStyleSheet(f"""QPushButton{{background:{C['accent']};color:white;
                border:none;border-radius:17px;font-size:15px;font-weight:bold;}}
                QPushButton:hover{{background:{C['accent_h']};}}""")
        else:
            self.req_btn.setStyleSheet(f"""QPushButton{{background:transparent;color:{C['text2']};
                border:none;border-radius:17px;font-size:17px;}}
                QPushButton:hover{{background:{C['hover']};color:{C['text']};}}""")

    def _select(self, uid):
        self.current_group_id = None
        self._hide_typing()
        for w in self.friends.values(): w.set_selected(False)
        if uid in self.friends: self.friends[uid].set_selected(True)
        self.recv_id = uid
        self._async(api_post, lambda r: None, "/chat/mark_read", self.token, {"other_user_id": uid})
        if uid in self.friends:
            self.friends[uid].clear_unread()
        self.view_prof.setVisible(True)
        self.ch_av.setVisible(True)
        # Vide les messages tout de suite
        while self.msg_vbox.count() > 1:
            it = self.msg_vbox.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        # Charge le profil et l'historique en arrière-plan
        self._async(api_get, lambda u: self._fill_header(u, uid), f"/auth/users/{uid}", self.token)
        self._async(api_get, lambda m: self._fill_history(m, uid), f"/chat/history/{self.user['id']}", self.token)

    def _fill_header(self, u, uid):
        if not u or uid != self.recv_id: return
        self.ch_av.refresh(u.get("username", "?"), u.get("avatar_url", ""))
        self.ch_name.setText(u.get("username", ""))
        if u.get("show_online", True):
            self.ch_sub.setText(format_last_seen(u.get("last_seen")))
        else:
            self.ch_sub.setText("@" + (u.get("slug") or u.get("username", "user").lower()))
        # Vérifie si on peut envoyer (profil privé + pas ami = bloqué)
        if u.get("is_private", False):
            self._async(api_get, lambda st: self._apply_can_send(st), f"/friends/status/{uid}", self.token)
        else:
            self._set_can_send(True)

    def _fill_history(self, msgs, uid):
        if msgs is None or uid != self.recv_id: return
        msgs = [m for m in msgs if {m["sender_id"], m["receiver_id"]} == {self.user["id"], uid}]
        for i, m in enumerate(msgs):
            content = m["content"]
            outgoing = m["sender_id"] == self.user["id"]
            if content.startswith("[GROUP_INVITE]"):
                gid = int(content.replace("[GROUP_INVITE]", ""))
                card = InviteCard(self.token, self.user, gid)
                card.joined.connect(self._load_groups)
                self.msg_vbox.insertWidget(i, card)
            elif content.startswith("[FILE]"):
                w = self._parse_attachment(content, outgoing)
                if w: self.msg_vbox.insertWidget(i, w)
            else:
                self.msg_vbox.insertWidget(i, Bubble(content, outgoing))
        self._scroll_bottom()

    def _load_history(self, uid):
        msgs = api_get(f"/chat/history/{self.user['id']}", self.token) or []
        msgs = [m for m in msgs if {m["sender_id"], m["receiver_id"]} == {self.user["id"], uid}]
        for i, m in enumerate(msgs):
            self.msg_vbox.insertWidget(i, Bubble(m["content"], m["sender_id"] == self.user["id"]))
        self._scroll_bottom()

    # ── WebSocket ─────────────────────────────────────────
    def _connect_ws(self):
        self.ws = websocket.WebSocketApp(
            f"ws://localhost:8000/chat/ws/{self.user['id']}",
            on_message=lambda ws, msg: self.sig_msg.emit(msg, 0))
        threading.Thread(target=self.ws.run_forever, daemon=True).start()

    def _on_incoming(self, raw, _):
        # Accusé de lecture
        if raw.startswith("[READ]"):
            reader_id = int(raw.replace("[READ]", ""))
            if reader_id == self.recv_id and self.last_status_label:
                self._set_msg_status("✓✓ Read", read=True)
            return
        if ":" not in raw:
            return
        sender_id_str, message = raw.split(":", 1)
        try:
            sender_id = int(sender_id_str)
        except ValueError:
            return

        # Indicateur "écrit..."
        if message == "[TYPING]":
            if sender_id == self.recv_id and self.current_group_id is None:
                self._show_typing()
            return
        if message == "[STOP_TYPING]":
            self._hide_typing()
            return

        # Invitation de groupe ?
        if message.startswith("[GROUP_INVITE]"):
            if sender_id == self.recv_id:
                gid = int(message.replace("[GROUP_INVITE]", ""))
                card = InviteCard(self.token, self.user, gid)
                card.joined.connect(self._load_groups)
                self.msg_vbox.insertWidget(self.msg_vbox.count() - 1, card)
                self._scroll_bottom()
            return

        # Message du chat actuellement ouvert ?
        if sender_id == self.recv_id and self.current_group_id is None:
            self._hide_typing()
            if message.startswith("[FILE]"):
                w = self._parse_attachment(message, False)
                if w: self.msg_vbox.insertWidget(self.msg_vbox.count() - 1, w)
            else:
                self.msg_vbox.insertWidget(self.msg_vbox.count() - 1, Bubble(message, False))
            self._scroll_bottom()
            if sender_id in self.friends:
                preview = "📎 Attachment" if message.startswith("[FILE]") else message
                self.friends[sender_id].set_preview(preview)
        else:
            # Message d'un autre chat → badge non-lu + notif
            if sender_id in self.friends:
                self.friends[sender_id].add_unread()
                self.friends[sender_id].set_preview(message)
            self._notify(sender_id, message)

    def _notify(self, sender_id, message):
        # Vérifie si les notifs sont activées
        if not getattr(self, "notifications_on", True):
            return
        # Récupère le nom de l'expéditeur
        sender_name = "New message"
        if sender_id in self.friends:
            sender_name = self.friends[sender_id].uname
        # Son
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass
        # Notification système
        try:
            from plyer import notification
            notification.notify(
                title=sender_name,
                message=message[:100],
                app_name="Velo",
                timeout=5,
            )
        except Exception as ex:
            print("notif error:", ex)

    def send_message(self):
        text = self.inp.text().strip()
        if not text: return
        # Mode groupe
        if self.current_group_id and self.group_ws:
            try:
                self.group_ws.send(text)
                self.msg_vbox.insertWidget(self.msg_vbox.count() - 1, Bubble(text, True))
                self.inp.clear();
                self._scroll_bottom()
            except Exception as ex:
                print("group send error:", ex)
            return
        # Mode ami (DM)
        if not self.recv_id or not self.ws: return
        try:
            self.ws.send(f"{self.recv_id}:{text}")
            self.msg_vbox.insertWidget(self.msg_vbox.count() - 1, Bubble(text, True))
            self.inp.clear()
            self._set_msg_status("✓ Delivered")
            self._scroll_bottom()
        except Exception as ex:
            print("send error:", ex)

    def _scroll_bottom(self):
        QTimer.singleShot(60, lambda: self.msg_scroll.verticalScrollBar().setValue(
            self.msg_scroll.verticalScrollBar().maximum()))

    # ── Dialogs ───────────────────────────────────────────
    def _open_settings(self):
        d = SettingsDialog(self.token, self.user, self)
        d.profile_updated.connect(self._on_updated); d.exec()
    def _on_updated(self, u):
        self.user = u
        self.me_av.refresh(u.get("username", "?"), u.get("avatar_url", ""))

    def _open_search(self):
        d = SearchDialog(self.token, self.user, self)
        d.open_profile.connect(lambda usr: self._show_profile(usr, d))
        d.finished.connect(lambda: self._load_groups())
        d.exec()
    def _show_profile(self, user, parent_dialog=None):
        p = ProfileDialog(self.token, self.user, user, self)
        p.action_done.connect(self._after_friend_action); p.exec()
    def _after_friend_action(self):
        self._load_friends(); self._refresh_badge()
    def _open_requests(self):
        d = RequestsDialog(self.token, self.user, self)
        d.changed.connect(self._after_friend_action); d.exec()
        self._refresh_badge()

    def _view_profile(self):
        # Si on est dans un groupe
        if self.current_group_id:
            g = api_get(f"/groups/{self.current_group_id}", self.token)
            if g:
                d = GroupProfileDialog(self.token, self.user, g, self)
                d.changed.connect(self._load_groups)
                d.left.connect(self._on_left_group)
                d.exec()
            return
        # Sinon profil d'ami
        if self.recv_id is None: return
        u = api_get(f"/auth/users/{self.recv_id}", self.token)
        if u: self._show_profile(u)

    def _on_left_group(self):
        self.current_group_id = None
        self.ch_name.setText("Select a chat")
        self.ch_sub.setText("")
        self.view_prof.setVisible(False)
        while self.msg_vbox.count() > 1:
            it = self.msg_vbox.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        self._load_groups()


if __name__ == "__main__":
    # Crisp HiDPI scaling (must be set before QApplication)
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("Velo")
    if os.path.exists(LOGO_PATH):
        from PyQt6.QtGui import QIcon
        app.setWindowIcon(QIcon(make_rounded_logo(LOGO_PATH, 64)))
    # Global scrollbar styling (sleeker, modern)
    app.setStyleSheet(f"""
        QScrollBar:vertical {{ background:transparent; width:8px; margin:2px; }}
        QScrollBar::handle:vertical {{ background:{C['card']}; border-radius:4px; min-height:30px; }}
        QScrollBar::handle:vertical:hover {{ background:{C['hover']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0px; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background:transparent; }}
        QToolTip {{ background:{C['card']}; color:{C['text']}; border:1px solid {C['divider']};
            border-radius:6px; padding:4px 8px; font-family:'Segoe UI'; }}
    """)
    login = LoginDialog()
    if login.exec() == QDialog.DialogCode.Accepted:
        win = VeloApp(login.token, login.user)
        win.show()
        sys.exit(app.exec())