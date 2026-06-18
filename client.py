import sys
import os
import json
import requests
import websocket
import threading
import html as _html

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QHBoxLayout, QScrollArea, QTextEdit,
    QFileDialog, QFrame, QSizePolicy, QStackedWidget, QMenu,
    QGridLayout, QComboBox, QInputDialog, QMessageBox, QSlider, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import (
    Qt, QTimer, pyqtSignal, QRect, QThread, QObject,
    QByteArray, QBuffer, QSize, QPropertyAnimation, QEasingCurve
)
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QPen, QPixmap,
    QLinearGradient, QPainterPath, QCursor, QMovie, QImage, QIcon
)
from datetime import datetime, timezone
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from call_engine import CallEngine
from countries import make_country_combo

def list_audio_devices():
    try:
        import sounddevice as sd
        inputs, outputs = [], []
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0:
                inputs.append((i, d["name"]))
            if d["max_output_channels"] > 0:
                outputs.append((i, d["name"]))
        return inputs, outputs
    except Exception as e:
        print("audio list error:", e)
        return [], []

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

def format_msg_time(dt=None):
    """Formate l'heure selon la préférence 12h/24h."""
    if dt is None:
        dt = datetime.now()
    if APPEARANCE.get("time_format", "24h") == "12h":
        return dt.strftime("%I:%M %p").lstrip("0")
    return dt.strftime("%H:%M")

def render_mentions(text, my_username=None):
    """Transforme @mentions en HTML coloré. Échappe le reste du texte."""
    # Échappe le HTML pour la sécurité
    escaped = _html.escape(text)
    # Repère les @mentions (lettres, chiffres, _ après @)
    import re
    def repl(m):
        name = m.group(1)
        # Couleur plus vive si c'est MOI qui suis mentionné
        is_me = my_username and name.lower() == my_username.lower()
        color = C["accent"] if not is_me else C["orange"]
        weight = "bold" if is_me else "600"
        return f'<span style="color:{color};font-weight:{weight};">@{name}</span>'
    return re.sub(r'@(\w+)', repl, escaped)


def format_date_label(iso_str):
    """Renvoie 'Today', 'Yesterday' ou une date pour les séparateurs."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", ""))
    except Exception:
        return None
    today = datetime.now().date()
    d = dt.date()
    delta = (today - d).days
    if delta == 0: return "Today"
    if delta == 1: return "Yesterday"
    if delta < 7:
        return dt.strftime("%A")  # nom du jour
    return dt.strftime("%d %B %Y")


def make_date_separator(text):
    """Petite étiquette de date centrée entre les messages."""
    wrap = QWidget()
    wl = QHBoxLayout(wrap); wl.setContentsMargins(0, 10, 0, 10)
    wl.addStretch()
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
    lbl.setStyleSheet(f"""color:{C['text2']};background:{C['card']};
        border-radius:10px;padding:3px 12px;""")
    wl.addWidget(lbl)
    wl.addStretch()
    return wrap


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

# ── Thèmes ────────────────────────────────────────────────
THEMES = {
    "standard": {
        "bg": "#0e1621", "sidebar": "#17212b", "panel": "#1c2733", "card": "#232e3c",
        "msg_in": "#182533", "msg_out": "#2b5278", "hover": "#202b36", "selected": "#2b5278",
        "divider": "#101a24", "accent": "#5288c1", "accent_h": "#5e93cc",
        "text": "#ffffff", "text2": "#7d8e9e", "text3": "#5a6b7a",
        "green": "#54c75e", "red": "#e15c5c", "orange": "#e8a14b",
    },
    "dark": {
        "bg": "#0b0d10", "sidebar": "#121519", "panel": "#171b20", "card": "#1d2228",
        "msg_in": "#1a1f25", "msg_out": "#2f4156", "hover": "#1c2127", "selected": "#2f4156",
        "divider": "#0a0c0e", "accent": "#4a8fd4", "accent_h": "#589ade",
        "text": "#f2f4f6", "text2": "#828c96", "text3": "#5b636c",
        "green": "#4fc25a", "red": "#e05a5a", "orange": "#e09a45",
    },
    "light": {
        "bg": "#ffffff", "sidebar": "#f3f5f7", "panel": "#eaedf0", "card": "#e6e9ec",
        "msg_in": "#eef1f4", "msg_out": "#cfe3fb", "hover": "#e2e6ea", "selected": "#cfe3fb",
        "divider": "#dde1e5", "accent": "#3d7fc4", "accent_h": "#4a8cd0",
        "text": "#15191e", "text2": "#5e6b78", "text3": "#9aa3ad",
        "green": "#2faa42", "red": "#d44545", "orange": "#d88a2e",
    },
    "lightgray": {
        "bg": "#e9ebee", "sidebar": "#dfe2e6", "panel": "#d5d9de", "card": "#cfd4d9",
        "msg_in": "#d8dce1", "msg_out": "#bcd4f0", "hover": "#d2d6db", "selected": "#bcd4f0",
        "divider": "#c8ccd1", "accent": "#3d7fc4", "accent_h": "#4a8cd0",
        "text": "#1a1e23", "text2": "#5a626b", "text3": "#8a929b",
        "green": "#2faa42", "red": "#d44545", "orange": "#d88a2e",
    },
}


def _detect_system_language():
    """Détecte la langue Windows, retombe sur 'en' si non supportée."""
    supported = {"en", "fr", "de", "es", "ru"}
    try:
        import locale
        # Essaie d'abord getlocale (moderne), puis fallback
        loc = None
        try:
            loc = locale.getlocale()[0]
        except Exception:
            pass
        if not loc:
            try:
                loc = locale.getdefaultlocale()[0]
            except Exception:
                pass
        if loc:
            code = loc.split("_")[0].lower()[:2]
            if code in supported:
                return code
    except Exception:
        pass
    return "en"


def _load_appearance():
    """Charge les préférences d'apparence (thème, police, etc.)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "appearance.json")
    # Au premier lancement, la langue par défaut = langue du système
    defaults = {"theme": "standard", "font_size": 12, "group_spacing": 2,
                "animate_gifs": True, "time_format": "24h",
                "language": _detect_system_language()}
    try:
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
                defaults.update(data)
    except Exception:
        pass
    return defaults


def _save_appearance(prefs):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "appearance.json")
    try:
        with open(path, "w") as f:
            json.dump(prefs, f)
    except Exception as e:
        print("appearance save error:", e)


# Préférences chargées au démarrage
APPEARANCE = _load_appearance()

# Système de traduction (i18n)
from translations import t as tr, set_language
set_language(APPEARANCE.get("language", "en"))

# ── Palette (remplie depuis le thème choisi) ──────────────
C = dict(THEMES.get(APPEARANCE.get("theme", "standard"), THEMES["standard"]))

AVATAR_PALETTE = [
    "#e17076","#7bc862","#65aadd","#ee7aae",
    "#aa65dd","#6ec9cb","#faa774","#5288c1",
]

BASE_URL = "https://velo-n1cd.onrender.com"
WS_URL = "wss://velo-n1cd.onrender.com"
from dotenv import load_dotenv
load_dotenv()  # charge le fichier .env (à côté de client.py)

KLIPY_API_KEY = os.getenv("KLIPY_API_KEY", "")
KLIPY_BASE = "https://api.klipy.com/api/v1"
H = lambda token: {"Authorization": f"Bearer {token}"}
LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")

# Flag global pour relancer le login après déconnexion
_RELOGIN = False

# ── Stockage sécurisé du token (Windows Credential Manager via keyring) ──
import keyring

KEYRING_SERVICE = "VeloMessaging"
KEYRING_KEY = "auth_token"

def save_token(token):
    """Sauvegarde le token dans le gestionnaire sécurisé de l'OS."""
    try:
        keyring.set_password(KEYRING_SERVICE, KEYRING_KEY, token)
    except Exception as ex:
        print("token save error:", ex)

def load_saved_token():
    """Récupère le token sauvegardé, ou None."""
    try:
        return keyring.get_password(KEYRING_SERVICE, KEYRING_KEY)
    except Exception as ex:
        print("token load error:", ex)
        return None

def clear_token():
    """Supprime le token sauvegardé (au logout)."""
    try:
        keyring.delete_password(KEYRING_SERVICE, KEYRING_KEY)
    except Exception:
        pass  # pas grave si déjà absent


# ── Avatar ────────────────────────────────────────────────
def avatar_color(name):
    return AVATAR_PALETTE[sum(ord(c) for c in name) % len(AVATAR_PALETTE)]


_AVATAR_CACHE = {}

def make_avatar(name, size, image_path=""):
    # Cache : évite de redessiner le même avatar plusieurs fois
    # Pour les images, on inclut la date de modif pour rafraîchir si le fichier change
    mtime = ""
    if image_path and os.path.exists(image_path):
        try:
            mtime = str(os.path.getmtime(image_path))
        except Exception:
            mtime = ""
    cache_key = (name, size, image_path, mtime)
    cached = _AVATAR_CACHE.get(cache_key)
    if cached is not None:
        return cached

    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    path = QPainterPath(); path.addEllipse(0, 0, size, size)
    p.setClipPath(path)
    if image_path and os.path.exists(image_path):
        src = QPixmap(image_path)
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
    # Limite la taille du cache (évite la fuite mémoire)
    if len(_AVATAR_CACHE) > 200:
        _AVATAR_CACHE.clear()
    _AVATAR_CACHE[cache_key] = px
    return px


def _squircle_path(size, n=5.0):
    """iOS-style squircle (superellipse) path filling a size×size box."""
    import math
    path = QPainterPath()
    cx = cy = size / 2.0
    a = b = size / 2.0
    steps = 180
    pts = []
    for i in range(steps + 1):
        t = (i / steps) * 2 * math.pi
        ct = math.cos(t); st = math.sin(t)
        # superellipse parametric form
        x = cx + a * (abs(ct) ** (2.0 / n)) * (1 if ct >= 0 else -1)
        y = cy + b * (abs(st) ** (2.0 / n)) * (1 if st >= 0 else -1)
        pts.append((x, y))
    path.moveTo(pts[0][0], pts[0][1])
    for x, y in pts[1:]:
        path.lineTo(x, y)
    path.closeSubpath()
    return path


def make_rounded_logo(path, size, radius_ratio=0.30):
    """Affiche le logo (déjà un squircle détouré) à la taille voulue."""
    out = QPixmap(size, size); out.fill(Qt.GlobalColor.transparent)
    if path and os.path.exists(path):
        src = QPixmap(path)
        scaled = src.scaled(size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        p = QPainter(out)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        ox = (size - scaled.width()) // 2
        oy = (size - scaled.height()) // 2
        p.drawPixmap(ox, oy, scaled)
        p.end()
    return out


class Avatar(QLabel):
    def __init__(self, name, size=42, image_path="", parent=None, online=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._online = online  # None = pas d'indicateur, True/False = point vert/gris
        self.refresh(name, image_path)
    def refresh(self, name, image_path=""):
        base = make_avatar(name, self.width(), image_path)
        if self._online is not None:
            # Copie pour ne pas corrompre le pixmap en cache
            px = base.copy()
            p = QPainter(px)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            s = self.width()
            dot = max(10, s // 4)
            p.setPen(Qt.PenStyle.NoPen)
            ring = dot + 4
            p.setBrush(QColor(C["sidebar"]))
            p.drawEllipse(s - ring, s - ring, ring, ring)
            p.setBrush(QColor(C["green"] if self._online else C["text3"]))
            p.drawEllipse(s - ring + 2, s - ring + 2, dot, dot)
            p.end()
            self.setPixmap(px)
        else:
            self.setPixmap(base)
    def set_online(self, online):
        self._online = online
        # Re-render en gardant le nom/image actuels n'est pas trivial ici,
        # donc on laisse refresh être rappelé par l'appelant si besoin.


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

def klipy_search(query, page=1, per_page=24):
    try:
        if query.strip():
            url = f"{KLIPY_BASE}/{KLIPY_API_KEY}/gifs/search"
            params = {"q": query, "page": page, "per_page": per_page}
        else:
            url = f"{KLIPY_BASE}/{KLIPY_API_KEY}/gifs/trending"
            params = {"page": page, "per_page": per_page}
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        items = data.get("data", {}).get("data", [])
        results = []
        for it in items:
            f = it.get("file", {})
            md = f.get("md", {}).get("gif", {})
            sm = f.get("sm", {}).get("gif", {})
            hd = f.get("hd", {}).get("gif", {})
            preview = md.get("url") or sm.get("url") or hd.get("url")
            full = hd.get("url") or md.get("url") or preview
            if preview and full:
                results.append({"preview": preview, "url": full})
        return results
    except Exception as ex:
        print("klipy error:", ex)
        return []


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
    edit_requested = pyqtSignal(int, str)   # (message_id, current_text)
    delete_requested = pyqtSignal(int)      # (message_id)

    def __init__(self, text, outgoing, msg_id=None, edited=False, parent=None,
                 sender_name=None, sender_avatar=None, time_str=None, indent=False):
        super().__init__(parent)
        self.msg_id = msg_id
        self.outgoing = outgoing
        self._raw_text = text
        self._sender_name = sender_name
        self._edited = edited
        self._time_str = time_str or ""

        lo = QHBoxLayout(self); lo.setContentsMargins(12, 2, 12, 2); lo.setSpacing(8)
        lo.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Avatar (groupes, messages entrants uniquement)
        avw = None
        if sender_name and not outgoing:
            av = Avatar(sender_name, 34, sender_avatar or "")
            av.setFixedSize(34, 34)
            avw = QWidget(); avw.setFixedSize(34, 34)
            avl = QVBoxLayout(avw); avl.setContentsMargins(0, 0, 0, 0)
            avl.addWidget(av)
        elif indent and not outgoing:
            # Espace réservé pour aligner les messages groupés (même expéditeur)
            avw = QWidget(); avw.setFixedSize(34, 1)

        # Bulle : conteneur vertical compact
        bubble = QWidget()
        bubble.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        bg = C["msg_out"] if outgoing else C["msg_in"]
        br = "14px 14px 4px 14px" if outgoing else "14px 14px 14px 4px"
        bubble.setStyleSheet(f"background:{bg};border-radius:{br};")
        bubble.setMaximumWidth(540)

        inner = QVBoxLayout(bubble); inner.setContentsMargins(13, 7, 13, 5); inner.setSpacing(2)

        # Nom de l'expéditeur (groupes entrants)
        if sender_name and not outgoing:
            nm = QLabel(sender_name)
            nm.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            nm.setStyleSheet(f"color:{avatar_color(sender_name)};background:transparent;")
            inner.addWidget(nm)

        # Texte du message
        self.lbl = QLabel(); self.lbl.setWordWrap(True)
        self.lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl.setFont(QFont("Segoe UI", APPEARANCE.get("font_size", 12)))
        self.lbl.setStyleSheet(f"color:{C['text']};background:transparent;")
        self.lbl.setMaximumWidth(510)
        self.lbl.setText(render_mentions(text, getattr(self, "_my_username", None)))
        self.lbl.setTextFormat(Qt.TextFormat.RichText)
        inner.addWidget(self.lbl)

        # Pied : "(edited)" à gauche + heure à droite, même couleur discrète
        foot = QHBoxLayout(); foot.setContentsMargins(0, 0, 0, 0); foot.setSpacing(8)
        meta_color = "#cfe0f0" if outgoing else C["text3"]
        self.edited_lbl = QLabel("edited" if edited else "")
        self.edited_lbl.setFont(QFont("Segoe UI", 8))
        self.edited_lbl.setStyleSheet(f"color:{meta_color};background:transparent;")
        foot.addWidget(self.edited_lbl)
        foot.addStretch()
        if time_str:
            tm = QLabel(time_str)
            tm.setFont(QFont("Segoe UI", 8))
            tm.setStyleSheet(f"color:{meta_color};background:transparent;")
            foot.addWidget(tm)
        inner.addLayout(foot)

        # Clic droit pour modifier/supprimer (seulement ses propres messages)
        if outgoing and msg_id is not None:
            self.lbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.lbl.customContextMenuRequested.connect(self._menu)

        # Disposition gauche/droite
        if outgoing:
            lo.addStretch()
            lo.addWidget(bubble)
        else:
            if avw: lo.addWidget(avw)
            lo.addWidget(bubble)
            lo.addStretch()

    def _set_text(self, text, edited):
        self._raw_text = text
        self.lbl.setText(text)
        if edited:
            self.edited_lbl.setText("edited")

    def mark_edited(self, new_text):
        self._raw_text = new_text
        self.lbl.setText(new_text)
        self.edited_lbl.setText("edited")

    def _menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{background:{C['card']};color:{C['text']};border:1px solid {C['divider']};
                border-radius:8px;padding:4px;font-family:'Segoe UI';font-size:12px;}}
            QMenu::item {{padding:8px 18px;border-radius:6px;}}
            QMenu::item:selected {{background:{C['hover']};}}
        """)
        menu.addAction("✏  Edit", lambda: self.edit_requested.emit(self.msg_id, self._raw_text))
        menu.addAction("🗑  Delete", lambda: self.delete_requested.emit(self.msg_id))
        menu.exec(self.lbl.mapToGlobal(pos))


# ── Contact / friend row ──────────────────────────────────
class FriendRow(QWidget):
    clicked = pyqtSignal(int)
    hide_requested = pyqtSignal(int)
    def __init__(self, user, parent=None):
        super().__init__(parent)
        self._my_username = None
        self.uid = user["id"]; self.uname = user.get("username", "?")
        self._sel = False
        self.setFixedHeight(64)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lo = QHBoxLayout(self); lo.setContentsMargins(10, 7, 10, 7); lo.setSpacing(11)
        # Détermine le statut en ligne depuis last_seen (si visible)
        online = None
        if user.get("show_online", True):
            online = format_last_seen(user.get("last_seen")) == "online"
        self.av = Avatar(self.uname, 46, user.get("avatar_url", ""), online=online)
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
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            self._show_menu(e)
            return
        self.clicked.emit(self.uid)

    def _show_menu(self, e):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{background:{C['card']};color:{C['text']};border:1px solid {C['divider']};
                border-radius:8px;padding:4px;font-family:'Segoe UI';font-size:12px;}}
            QMenu::item {{padding:8px 18px;border-radius:6px;}}
            QMenu::item:selected {{background:{C['hover']};}}
        """)
        menu.addAction("🗙  Remove from list", lambda: self.hide_requested.emit(self.uid))
        menu.exec(self.mapToGlobal(e.pos()))

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
        sep = QFrame(); sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{C['divider']};border:none;"); lo.addWidget(sep)
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

        # Bouton "Signaler" (sauf sur son propre profil)
        if self.user["id"] != self.me["id"]:
            lo.addSpacing(6)
            report = QPushButton("🚩 " + tr("report_user"))
            report.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            report.setFixedHeight(38)
            report.setStyleSheet(f"""QPushButton{{background:transparent;color:{C['text3']};
                border:none;font-size:12px;font-family:'Segoe UI';}}
                QPushButton:hover{{color:{C['red']};}}""")
            report.clicked.connect(self._report)
            lo.addWidget(report)

    def _report(self):
        reason, ok = QInputDialog.getText(self, tr("report_user"),
            tr("report_reason"))
        if not ok or not reason.strip():
            return
        res = api_post("/admin/report", self.token,
                       {"reported_user_id": self.user["id"], "reason": reason.strip()})
        if res is not None:
            QMessageBox.information(self, tr("report_user"), tr("report_sent"))
        else:
            QMessageBox.warning(self, tr("report_user"), "Failed.")

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
            lbl = QLabel(tr("request_sent"))
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
        t = QLabel(tr("friend_requests"))
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
            empty = QLabel(tr("no_pending_requests"))
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
        t = QLabel(tr("find_people"))
        t.setFont(QFont("Segoe UI", 17, QFont.Weight.Bold))
        t.setStyleSheet(f"color:{C['text']};"); lo.addWidget(t)
        self.inp = QLineEdit(); self.inp.setPlaceholderText(tr("search_by_username"))
        self.inp.setFixedHeight(42); self.inp.setStyleSheet(field())
        self.inp.textChanged.connect(self._on_type); lo.addWidget(self.inp)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("border:none;background:transparent;")
        self.box = QWidget(); self.box.setStyleSheet("background:transparent;")
        self.vbox = QVBoxLayout(self.box); self.vbox.setSpacing(4); self.vbox.addStretch()
        self.scroll.setWidget(self.box); lo.addWidget(self.scroll)
        # Debounce : attend 350ms après la dernière frappe avant de chercher
        self._search_timer = QTimer(self); self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._search)
        self._workers = []
        self._search_seq = 0   # pour ignorer les réponses obsolètes

    def _on_type(self):
        self._search_timer.start(350)

    def _search(self):
        q = self.inp.text().strip()
        while self.vbox.count() > 1:
            it = self.vbox.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        if len(q) < 1: return
        self._search_seq += 1
        seq = self._search_seq
        # Recherche utilisateurs (async)
        wu = ApiWorker(api_get, f"/friends/search?q={q}", self.token)
        wu.done.connect(lambda users, s=seq: self._show_users(users, s))
        wu.done.connect(lambda *_: self._workers.remove(wu) if wu in self._workers else None)
        self._workers.append(wu); wu.start()
        # Recherche groupes publics (async)
        wg = ApiWorker(api_get, f"/groups/search/public?q={q}", self.token)
        wg.done.connect(lambda groups, s=seq: self._show_groups(groups, s))
        wg.done.connect(lambda *_: self._workers.remove(wg) if wg in self._workers else None)
        self._workers.append(wg); wg.start()

    def _show_users(self, users, seq):
        if seq != self._search_seq: return  # réponse obsolète, ignore
        for u in (users or []):
            row = FriendRow(u)
            row.clicked.connect(lambda _, usr=u: self._open(usr))
            self.vbox.insertWidget(self.vbox.count() - 1, row)

    def _show_groups(self, groups, seq):
        if seq != self._search_seq: return
        for g in (groups or []):
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
        sub = QLabel(tr("public_group"));
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


# ── Login (téléphone + code à 6 chiffres) ─────────────────
class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Velo")
        self.setFixedSize(420, 520)
        self.setStyleSheet(f"background:{C['bg']};")
        self.token = None; self.user = None
        self.phone = ""
        self._resend_left = 0
        self._resend_timer = QTimer(self)
        self._resend_timer.timeout.connect(self._tick_resend)
        self._build()

    def _build(self):
        self.stack = QStackedWidget(self)
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.stack)
        self.stack.addWidget(self._phone_page())
        self.stack.addWidget(self._code_page())
        self.stack.setCurrentIndex(0)

    def _logo(self, size=96):
        icon = QLabel()
        if os.path.exists(LOGO_PATH):
            icon.setPixmap(make_rounded_logo(LOGO_PATH, size + 8))
        else:
            icon.setText("✈"); icon.setFont(QFont("Segoe UI Emoji", 46))
            icon.setStyleSheet(f"color:{C['accent']};")
        icon.setFixedSize(size, size)
        icon.setScaledContents(True)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return icon

    # Page 1 : saisie du numéro
    def _phone_page(self):
        page = QWidget()
        lo = QVBoxLayout(page); lo.setContentsMargins(48, 46, 48, 40); lo.setSpacing(0)
        lo.addStretch()
        lo.addWidget(self._logo(), alignment=Qt.AlignmentFlag.AlignHCenter)
        lo.addSpacing(26)
        t = QLabel("Velo"); t.setFont(QFont("Segoe UI", 27, QFont.Weight.Bold))
        t.setAlignment(Qt.AlignmentFlag.AlignCenter); t.setStyleSheet(f"color:{C['text']};")
        lo.addWidget(t)
        lo.addSpacing(4)
        sub = QLabel(tr("phone_login_hint")); sub.setFont(QFont("Segoe UI", 12))
        sub.setWordWrap(True)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color:{C['text2']};"); lo.addWidget(sub)
        lo.addSpacing(28)
        # Ligne : sélecteur de pays (drapeau + indicatif, recherchable) + numéro local
        row = QHBoxLayout(); row.setSpacing(8)
        self.country_combo = make_country_combo("FR")
        self.country_combo.setFixedHeight(46)
        self.country_combo.setFixedWidth(104)
        self.country_combo.setStyleSheet(f"""
            QComboBox {{background:{C['panel']};color:{C['text']};
                border:1.5px solid {C['card']};border-radius:12px;padding:0 10px;
                font-size:13px;font-family:'Segoe UI';}}
            QComboBox:focus {{border:1.5px solid {C['accent']};}}
            QComboBox::drop-down {{border:none;width:18px;}}
            QComboBox QAbstractItemView {{background:{C['panel']};color:{C['text']};
                selection-background-color:{C['accent']};border:1px solid {C['card']};
                padding:4px;outline:none;}}""")
        row.addWidget(self.country_combo)
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText(tr("phone_number"))
        self.phone_input.setFixedHeight(46)
        self.phone_input.setStyleSheet(field(12))
        self.phone_input.returnPressed.connect(self._send_code)
        row.addWidget(self.phone_input, 1)
        lo.addLayout(row)
        lo.addSpacing(8)
        self.phone_err = QLabel(""); self.phone_err.setFont(QFont("Segoe UI", 11))
        self.phone_err.setWordWrap(True)
        self.phone_err.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.phone_err.setStyleSheet(f"color:{C['red']};"); lo.addWidget(self.phone_err)
        lo.addSpacing(6)
        self.send_btn = btn(tr("send_code"), C["accent"], bold=True, font_size=14)
        self.send_btn.setFixedHeight(48); self.send_btn.clicked.connect(self._send_code)
        lo.addWidget(self.send_btn)
        lo.addStretch()
        return page

    # Page 2 : saisie du code
    def _code_page(self):
        page = QWidget()
        lo = QVBoxLayout(page); lo.setContentsMargins(48, 46, 48, 40); lo.setSpacing(0)
        lo.addStretch()
        lo.addWidget(self._logo(72), alignment=Qt.AlignmentFlag.AlignHCenter)
        lo.addSpacing(22)
        t = QLabel(tr("enter_code")); t.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        t.setAlignment(Qt.AlignmentFlag.AlignCenter); t.setStyleSheet(f"color:{C['text']};")
        lo.addWidget(t)
        lo.addSpacing(6)
        self.code_info = QLabel(""); self.code_info.setFont(QFont("Segoe UI", 11))
        self.code_info.setWordWrap(True)
        self.code_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code_info.setStyleSheet(f"color:{C['text2']};"); lo.addWidget(self.code_info)
        lo.addSpacing(20)
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("• • • • • •")
        self.code_input.setMaxLength(6)
        self.code_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code_input.setFixedHeight(54)
        self.code_input.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        self.code_input.setStyleSheet(field(12))
        self.code_input.returnPressed.connect(self._verify)
        lo.addWidget(self.code_input)
        # Indice de code en mode dev (tant qu'il n'y a pas de vrai SMS)
        self.dev_hint = QLabel(""); self.dev_hint.setFont(QFont("Segoe UI", 10))
        self.dev_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dev_hint.setStyleSheet(f"color:{C['text3']};"); lo.addWidget(self.dev_hint)
        lo.addSpacing(4)
        self.code_err = QLabel(""); self.code_err.setFont(QFont("Segoe UI", 11))
        self.code_err.setWordWrap(True)
        self.code_err.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code_err.setStyleSheet(f"color:{C['red']};"); lo.addWidget(self.code_err)
        lo.addSpacing(6)
        self.verify_btn = btn(tr("verify"), C["accent"], bold=True, font_size=14)
        self.verify_btn.setFixedHeight(48); self.verify_btn.clicked.connect(self._verify)
        lo.addWidget(self.verify_btn)
        lo.addSpacing(10)
        row = QHBoxLayout()
        self.resend_btn = QPushButton(tr("resend_code"))
        self.change_btn = QPushButton(tr("change_number"))
        for b in (self.resend_btn, self.change_btn):
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.setFixedHeight(36)
            b.setStyleSheet(f"""QPushButton{{background:transparent;color:{C['accent']};
                border:none;font-size:12px;font-weight:600;font-family:'Segoe UI';}}
                QPushButton:hover{{color:{C['text']};}}
                QPushButton:disabled{{color:{C['text3']};}}""")
        self.resend_btn.clicked.connect(self._resend)
        self.change_btn.clicked.connect(self._change_number)
        row.addWidget(self.change_btn); row.addStretch(); row.addWidget(self.resend_btn)
        lo.addLayout(row)
        lo.addStretch()
        return page

    # ── Actions ───────────────────────────────────────────
    def _request_code(self, error_label):
        """Demande/renvoie un code pour self.phone. Retourne True si OK."""
        try:
            r = requests.post(f"{BASE_URL}/auth/request_code", json={"phone": self.phone})
        except Exception:
            error_label.setText(tr("server_unreachable")); return False
        if r.status_code == 200:
            dev = r.json().get("dev_code")
            self.dev_hint.setText(f"Dev code: {dev}" if dev else "")
            return True
        if r.status_code == 403:
            error_label.setText("Access denied.")
        else:
            error_label.setText(tr("invalid_phone"))
        return False

    def _send_code(self):
        self.phone_err.setText("")
        dial = (self.country_combo.currentData() or {}).get("dial", "")
        # Retire le 0 national de tête (convention internationale : 06… -> +33 6…)
        local = "".join(ch for ch in self.phone_input.text() if ch.isdigit()).lstrip("0")
        if not local:
            self.phone_err.setText(tr("invalid_phone")); return
        # Numéro complet = indicatif du pays + numéro local saisi
        self.phone = dial + local
        if not self._request_code(self.phone_err):
            return
        self.code_info.setText(tr("code_sent_to", phone=self.phone))
        self.code_input.clear(); self.code_err.setText("")
        self.stack.setCurrentIndex(1)
        self.code_input.setFocus()
        self._start_resend_cooldown()

    def _verify(self):
        self.code_err.setText("")
        code = self.code_input.text().strip()
        if len(code) < 4:
            self.code_err.setText(tr("invalid_code")); return
        try:
            r = requests.post(f"{BASE_URL}/auth/verify_code",
                              json={"phone": self.phone, "code": code})
        except Exception:
            self.code_err.setText(tr("server_unreachable")); return
        if r.status_code == 200:
            self._resend_timer.stop()
            self.token = r.json()["access_token"]
            save_token(self.token)  # mémorise pour les prochaines ouvertures
            self.user = api_get("/auth/me", self.token)
            self.accept()
        else:
            self.code_err.setText(tr("invalid_code"))

    def _resend(self):
        if self._resend_left > 0:
            return
        self.code_err.setText("")
        if self._request_code(self.code_err):
            self._start_resend_cooldown()

    def _change_number(self):
        self._resend_timer.stop()
        self.stack.setCurrentIndex(0)
        self.phone_input.setFocus()

    def _start_resend_cooldown(self):
        self._resend_left = 30
        self._update_resend_btn()
        self._resend_timer.start(1000)

    def _tick_resend(self):
        self._resend_left -= 1
        if self._resend_left <= 0:
            self._resend_timer.stop()
        self._update_resend_btn()

    def _update_resend_btn(self):
        if self._resend_left > 0:
            self.resend_btn.setText(tr("resend_in", s=self._resend_left))
            self.resend_btn.setEnabled(False)
        else:
            self.resend_btn.setText(tr("resend_code"))
            self.resend_btn.setEnabled(True)

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
        t = QLabel(tr("create_a_group"))
        t.setFont(QFont("Segoe UI", 17, QFont.Weight.Bold))
        t.setStyleSheet(f"color:{C['text']};"); lo.addWidget(t)
        self.name = QLineEdit(); self.name.setPlaceholderText(tr("group_name"))
        self.name.setFixedHeight(44); self.name.setStyleSheet(field()); lo.addWidget(self.name)
        self.bio = QLineEdit(); self.bio.setPlaceholderText(tr("description_optional"))
        self.bio.setFixedHeight(44); self.bio.setStyleSheet(field()); lo.addWidget(self.bio)
        # Toggle privé
        row = QWidget()
        rl = QHBoxLayout(row); rl.setContentsMargins(0, 4, 0, 4)
        col = QVBoxLayout(); col.setSpacing(1)
        lab = QLabel(tr("private_group"))
        lab.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        lab.setStyleSheet(f"color:{C['text']};")
        desc = QLabel(tr("private_desc"))
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
    hide_requested = pyqtSignal(int)
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
        self._default_preview = f"{lock}Group"
        self._upd()
    def set_preview(self, t):
        self.preview.setText(t[:38] + ("…" if len(t) > 38 else ""))
    def set_selected(self, v): self._sel = v; self._upd()
    def _upd(self):
        self.setStyleSheet(f"background:{C['selected'] if self._sel else 'transparent'};border-radius:10px;")
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            self._show_menu(e)
            return
        self.clicked.emit(self.gid)
    def _show_menu(self, e):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{background:{C['card']};color:{C['text']};border:1px solid {C['divider']};
                border-radius:8px;padding:4px;font-family:'Segoe UI';font-size:12px;}}
            QMenu::item {{padding:8px 18px;border-radius:6px;}}
            QMenu::item:selected {{background:{C['hover']};}}
        """)
        menu.addAction("🗙  Remove from list", lambda: self.hide_requested.emit(self.gid))
        menu.exec(self.mapToGlobal(e.pos()))
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
        t = QLabel(tr("invite_a_friend"))
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
        sep = QFrame(); sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{C['divider']};border:none;"); lo.addWidget(sep)
        mt = QLabel(tr("members"))
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
        self.lbl = QLabel(tr("loading_image"))
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
        sub = QLabel(tr("click_download")); sub.setFont(QFont("Segoe UI", 9))
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

class ConvSettingsDialog(QDialog):
    def __init__(self, token, other_user_id, other_name, parent=None):
        super().__init__(parent)
        self.token = token
        self.other_user_id = other_user_id
        self.setWindowTitle("Conversation settings")
        self.setFixedSize(380, 240)
        self.setStyleSheet(f"background:{C['bg']};")
        self._build(other_name)
    def _build(self, other_name):
        lo = QVBoxLayout(self); lo.setContentsMargins(28, 24, 28, 24); lo.setSpacing(14)
        t = QLabel(tr("conversation_settings"))
        t.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        t.setStyleSheet(f"color:{C['text']};"); lo.addWidget(t)
        sub = QLabel(f"with {other_name}")
        sub.setFont(QFont("Segoe UI", 11))
        sub.setStyleSheet(f"color:{C['text2']};"); lo.addWidget(sub)
        # Toggle éphémère
        row = QWidget()
        rl = QHBoxLayout(row); rl.setContentsMargins(0, 8, 0, 0)
        col = QVBoxLayout(); col.setSpacing(2)
        lab = QLabel(tr("delete_after_reading"))
        lab.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        lab.setStyleSheet(f"color:{C['text']};")
        desc = QLabel(tr("vanish_desc"))
        desc.setFont(QFont("Segoe UI", 10))
        desc.setStyleSheet(f"color:{C['text2']};")
        col.addWidget(lab); col.addWidget(desc)
        rl.addLayout(col); rl.addStretch()
        self.toggle = Toggle(False)
        rl.addWidget(self.toggle)
        lo.addWidget(row)
        self.status = QLabel(""); self.status.setFont(QFont("Segoe UI", 10))
        self.status.setStyleSheet(f"color:{C['green']};")
        lo.addWidget(self.status)
        lo.addStretch()
        # Charge l'état actuel
        cur = api_get(f"/conversation/settings/{self.other_user_id}", self.token) or {}
        self.toggle.setChecked(cur.get("ephemeral", False))
        # Connecte le changement
        self.toggle.toggled.connect(self._save)
    def _save(self, checked):
        api_post("/conversation/settings", self.token,
                 {"other_user_id": self.other_user_id, "ephemeral": checked})
        self.status.setText("✓ Saved")
        QTimer.singleShot(1200, lambda: self.status.setText(""))

class EmojiPicker(QDialog):
    emoji_picked = pyqtSignal(str)
    EMOJIS = [
        "😀","😃","😄","😁","😆","😅","😂","🤣","😊","😇",
        "🙂","🙃","😉","😌","😍","🥰","😘","😗","😙","😚",
        "😋","😛","😝","😜","🤪","🤨","🧐","🤓","😎","🥸",
        "🤩","🥳","😏","😒","😞","😔","😟","😕","🙁","☹️",
        "😣","😖","😫","😩","🥺","😢","😭","😤","😠","😡",
        "🤬","🤯","😳","🥵","🥶","😱","😨","😰","😥","😓",
        "🤗","🤔","🤭","🤫","🤥","😶","😐","😑","😬","🙄",
        "😯","😦","😧","😮","😲","🥱","😴","🤤","😪","😵",
        "🤐","🥴","🤢","🤮","🤧","😷","🤒","🤕","🤑","🤠",
        "👍","👎","👌","✌️","🤞","🤟","🤘","👈","👉","👆",
        "👇","☝️","✋","🤚","🖐️","🖖","👋","🤙","💪","🙏",
        "❤️","🧡","💛","💚","💙","💜","🖤","🤍","🤎","💔",
        "💕","💞","💓","💗","💖","💘","💝","🔥","⭐","✨",
        "🎉","🎊","🎈","🎁","🏆","🥇","💯","✅","❌","❓",
    ]
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(360, 300)
        self._build()

    def paintEvent(self, e):
        # Dessine un fond arrondi anti-aliasé (coins lisses)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C["card"]))
        from PyQt6.QtCore import QRectF
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 18, 18)
        p.end()

    def _build(self):
        lo = QVBoxLayout(self); lo.setContentsMargins(12, 12, 12, 12); lo.setSpacing(8)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border:none;background:transparent;")
        grid_w = QWidget(); grid_w.setStyleSheet("background:transparent;")
        grid = QGridLayout(grid_w); grid.setSpacing(2)
        cols = 8
        for i, emo in enumerate(self.EMOJIS):
            b = QPushButton(emo)
            b.setFixedSize(38, 38)
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.setStyleSheet(f"""QPushButton{{background:transparent;border:none;
                font-size:20px;border-radius:8px;}}
                QPushButton:hover{{background:{C['hover']};}}""")
            b.clicked.connect(lambda _, e=emo: self._pick(e))
            grid.addWidget(b, i // cols, i % cols)
        scroll.setWidget(grid_w); lo.addWidget(scroll)
    def _pick(self, emo):
        self.emoji_picked.emit(emo)
        self.close()

class GifPicker(QDialog):
    gif_picked = pyqtSignal(str)  # émet l'URL du GIF choisi
    def __init__(self, token, parent=None):
        super().__init__(parent)
        self.token = token
        self.setWindowFlags(Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(440, 480)
        self._workers = []
        self._build()
        self._search("")  # trending au départ

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C["card"]))
        from PyQt6.QtCore import QRectF
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 18, 18)
        p.end()

    def _build(self):
        lo = QVBoxLayout(self); lo.setContentsMargins(16, 16, 16, 16); lo.setSpacing(10)
        # Barre de recherche + onglet favoris
        top = QHBoxLayout()
        self.inp = QLineEdit(); self.inp.setPlaceholderText(tr("search_gifs"))
        self.inp.setFixedHeight(40); self.inp.setStyleSheet(field())
        self.inp.textChanged.connect(self._on_type)
        top.addWidget(self.inp)
        self.fav_btn = QPushButton("⭐")
        self.fav_btn.setFixedSize(40, 40)
        self.fav_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.fav_btn.setStyleSheet(f"""QPushButton{{background:{C['panel']};border:none;
            border-radius:10px;font-size:18px;}}
            QPushButton:hover{{background:{C['hover']};}}""")
        self.fav_btn.clicked.connect(self._show_favorites)
        top.addWidget(self.fav_btn)
        lo.addLayout(top)
        # Zone de résultats (grille scrollable)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("border:none;background:transparent;")
        self.grid_w = QWidget(); self.grid_w.setStyleSheet("background:transparent;")
        self.grid = QGridLayout(self.grid_w); self.grid.setSpacing(6)
        self.scroll.setWidget(self.grid_w); lo.addWidget(self.scroll)
        # Timer de debounce pour la recherche
        self._search_timer = QTimer(self); self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(lambda: self._search(self.inp.text()))
    def _on_type(self):
        self._search_timer.start(500)
    def _clear_grid(self):
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget(): it.widget().deleteLater()
    def _search(self, query):
        self._clear_grid()
        loading = QLabel(tr("loading")); loading.setStyleSheet(f"color:{C['text2']};")
        self.grid.addWidget(loading, 0, 0)
        w = ApiWorker(klipy_search, query)
        w.done.connect(self._show_results)
        w.done.connect(lambda: self._workers.remove(w) if w in self._workers else None)
        self._workers.append(w); w.start()
    def _show_results(self, results):
        self._clear_grid()
        if not results:
            empty = QLabel(tr("no_gifs")); empty.setStyleSheet(f"color:{C['text2']};")
            self.grid.addWidget(empty, 0, 0); return
        cols = 2
        for i, g in enumerate(results):
            cell = self._gif_cell(g)
            self.grid.addWidget(cell, i // cols, i % cols)
    def _gif_cell(self, g):
        cell = QWidget(); cell.setFixedSize(190, 150)
        cell.setStyleSheet(f"background:{C['card']};border-radius:10px;")
        cl = QVBoxLayout(cell); cl.setContentsMargins(4, 4, 4, 4)
        gif = AnimatedGif(g["preview"], max_width=180)
        gif.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        gif.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gif.mousePressEvent = lambda e, url=g["url"]: self._pick(url)
        cl.addWidget(gif)
        return cell
    def _pick(self, url):
        self.gif_picked.emit(url)
        self.close()
    def _show_favorites(self):
        favs = self._load_favs()
        self._clear_grid()
        if not favs:
            empty = QLabel(tr("no_favorites"))
            empty.setStyleSheet(f"color:{C['text2']};"); empty.setWordWrap(True)
            self.grid.addWidget(empty, 0, 0); return
        cols = 2
        for i, url in enumerate(favs):
            cell = self._gif_cell({"preview": url, "url": url})
            self.grid.addWidget(cell, i // cols, i % cols)
    def _load_favs(self):
        try:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gif_favorites.json")
            if os.path.exists(path):
                with open(path) as f: return json.load(f)
        except Exception: pass
        return []

class GifDownloader(QThread):
    loaded = pyqtSignal(object)

    def __init__(self, url):
        super().__init__();
        self.url = url

    def run(self):
        try:
            r = requests.get(self.url, timeout=20)
            self.loaded.emit(r.content if r.status_code == 200 else None)
        except Exception:
            self.loaded.emit(None)

class AnimatedGif(QLabel):
    """Affiche un GIF animé depuis une URL, chargé en arrière-plan."""
    def __init__(self, url, max_width=200, parent=None):
        super().__init__(parent)
        self.url = url
        self.max_width = max_width
        self._buffer = None
        self._movie = None
        self.setStyleSheet("background:transparent;")
        self.setText("…")
        self._loader = GifDownloader(url)
        self._loader.loaded.connect(self._play)
        self._loader.start()
    def _play(self, data):
        if not data:
            self.setText("⚠")
            return
        self._bytes = QByteArray(data)
        self._buffer = QBuffer(self._bytes)
        self._buffer.open(QBuffer.OpenModeFlag.ReadOnly)
        self._movie = QMovie()
        self._movie.setDevice(self._buffer)
        self._movie.setCacheMode(QMovie.CacheMode.CacheAll)
        # Lit la taille réelle via la première frame, AVANT de lancer
        self._movie.jumpToFrame(0)
        orig = self._movie.currentImage().size()
        if orig.width() > 0:
            ratio = min(1.0, self.max_width / orig.width())
            scaled_size = QSize(int(orig.width() * ratio), int(orig.height() * ratio))
            self._movie.setScaledSize(scaled_size)
            self.setFixedSize(scaled_size)
        self.setMovie(self._movie)
        if APPEARANCE.get("animate_gifs", True):
            self._movie.start()
        else:
            # GIF figé sur la première image
            self._movie.jumpToFrame(0)


class GifDownloader(QThread):
    loaded = pyqtSignal(object)
    def __init__(self, url):
        super().__init__(); self.url = url
    def run(self):
        try:
            r = requests.get(self.url, timeout=20)
            self.loaded.emit(r.content if r.status_code == 200 else None)
        except Exception:
            self.loaded.emit(None)

class CallDialog(QDialog):
    remote_frame = pyqtSignal(object)  # signal thread-safe pour la vidéo reçue
    video_stopped = pyqtSignal()
    def __init__(self, name, avatar_url, incoming=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Call")
        self.setFixedSize(520, 560)
        self.setStyleSheet(f"background:{C['bg']};")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.name = name; self.avatar_url = avatar_url
        self._build(name, avatar_url, incoming)
        self.remote_frame.connect(self._show_remote_frame)
        self.video_stopped.connect(self._hide_remote_video)
    def _build(self, name, avatar_url, incoming):
        lo = QVBoxLayout(self); lo.setContentsMargins(0, 20, 0, 24); lo.setSpacing(0)
        # Zone vidéo (cachée au départ)
        self.video_label = QLabel()
        self.video_label.setFixedSize(520, 300)
        self.video_label.setStyleSheet("background:#000;")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setVisible(False)
        lo.addWidget(self.video_label)
        # Bloc avatar + nom (visible si pas de vidéo)
        self.info_block = QWidget()
        ib = QVBoxLayout(self.info_block); ib.setSpacing(0)
        ib.addStretch()
        av = Avatar(name, 110, avatar_url)
        avw = QHBoxLayout(); avw.addStretch(); avw.addWidget(av); avw.addStretch()
        ib.addLayout(avw)
        ib.addSpacing(16)
        nm = QLabel(name); nm.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        nm.setAlignment(Qt.AlignmentFlag.AlignCenter); nm.setStyleSheet(f"color:{C['text']};")
        ib.addWidget(nm)
        self.status = QLabel("Incoming call…" if incoming else "Calling…")
        self.status.setFont(QFont("Segoe UI", 13))
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setStyleSheet(f"color:{C['text2']};margin-top:6px;")
        ib.addWidget(self.status)
        ib.addStretch()
        lo.addWidget(self.info_block)
        # Barre de boutons
        btns = QHBoxLayout(); btns.setSpacing(16); btns.addStretch()
        if incoming:
            self.accept_btn = QPushButton("✓")
            self.accept_btn.setFixedSize(58, 58)
            self.accept_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.accept_btn.setStyleSheet(f"""QPushButton{{background:{C['green']};color:white;
                border:none;border-radius:29px;font-size:24px;}}
                QPushButton:hover{{background:#48b352;}}""")
            btns.addWidget(self.accept_btn)
        # Bouton caméra
        self.cam_btn = QPushButton("📷")
        self.cam_btn.setFixedSize(52, 52)
        self.cam_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.cam_btn.setStyleSheet(self._tool_style())
        self.cam_btn.setVisible(not incoming)
        btns.addWidget(self.cam_btn)
        # Bouton écran
        self.screen_btn = QPushButton("🖥")
        self.screen_btn.setFixedSize(52, 52)
        self.screen_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.screen_btn.setStyleSheet(self._tool_style())
        self.screen_btn.setVisible(not incoming)
        btns.addWidget(self.screen_btn)
        # Raccrocher
        self.hangup_btn = QPushButton("✕")
        self.hangup_btn.setFixedSize(58, 58)
        self.hangup_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.hangup_btn.setStyleSheet(f"""QPushButton{{background:{C['red']};color:white;
            border:none;border-radius:29px;font-size:24px;}}
            QPushButton:hover{{background:#d04545;}}""")
        btns.addWidget(self.hangup_btn)
        btns.addStretch()
        lo.addSpacing(16); lo.addLayout(btns)

    def _hide_remote_video(self):
        self.video_label.clear()
        self.video_label.setVisible(False)
        self.info_block.setVisible(True)
    def _tool_style(self):
        return f"""QPushButton{{background:{C['card']};color:{C['text']};
            border:none;border-radius:26px;font-size:20px;}}
            QPushButton:hover{{background:{C['hover']};}}"""
    def set_status(self, text):
        self.status.setText(text)
    def show_call_controls(self):
        # Affiche les boutons cam/écran une fois connecté
        self.cam_btn.setVisible(True)
        self.screen_btn.setVisible(True)
    def _show_remote_frame(self, img):
        # img = ndarray RGB
        h, w, ch = img.shape
        bytes_per_line = ch * w
        qimg = QImage(img.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg).scaled(
            self.video_label.width(), self.video_label.height(),
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.video_label.setPixmap(pix)
        if not self.video_label.isVisible():
            self.video_label.setVisible(True)
            self.info_block.setVisible(False)

# ── Full-page Settings (Discord-style with categories) ────
class SettingsPage(QWidget):
    profile_updated = pyqtSignal(dict)
    notif_changed = pyqtSignal(bool)
    closed = pyqtSignal()
    logout_requested = pyqtSignal()
    account_deleted = pyqtSignal()

    def __init__(self, token, user, parent=None):
        super().__init__(parent)
        self.app = parent
        self.token = token
        self.user = user
        self.avatar_path = ""
        self.setStyleSheet(f"background:{C['bg']};")
        self._cat_buttons = {}
        self._build()

    # ── Styles helpers ────────────────────────────────────
    def _combo_style(self):
        return f"""
            QComboBox {{background:{C['panel']};color:{C['text']};border:1.5px solid {C['card']};
                border-radius:8px;padding:9px 12px;font-size:12px;font-family:'Segoe UI';}}
            QComboBox:hover {{border-color:{C['accent']};}}
            QComboBox::drop-down {{border:none;width:24px;}}
            QComboBox QAbstractItemView {{background:{C['card']};color:{C['text']};
                selection-background-color:{C['accent']};border:none;outline:none;}}
        """

    def _section_label(self, text):
        l = QLabel(text)
        l.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        l.setStyleSheet(f"color:{C['text3']};letter-spacing:1px;margin-top:6px;")
        return l

    def _small_label(self, text):
        l = QLabel(text)
        l.setStyleSheet(f"color:{C['text2']};font-size:11px;font-family:'Segoe UI';")
        return l

    def _toggle_row(self, label_text, desc_text, checked):
        row = QWidget()
        rl = QHBoxLayout(row); rl.setContentsMargins(0, 6, 0, 6)
        cc = QVBoxLayout(); cc.setSpacing(2)
        lab = QLabel(label_text)
        lab.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        lab.setStyleSheet(f"color:{C['text']};")
        desc = QLabel(desc_text)
        desc.setFont(QFont("Segoe UI", 10))
        desc.setStyleSheet(f"color:{C['text2']};")
        cc.addWidget(lab); cc.addWidget(desc)
        rl.addLayout(cc); rl.addStretch()
        tog = Toggle(checked)
        rl.addWidget(tog, alignment=Qt.AlignmentFlag.AlignVCenter)
        return row, tog

    # ── Build ─────────────────────────────────────────────
    def _build(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        # Top bar
        topbar = QWidget(); topbar.setFixedHeight(58)
        topbar.setStyleSheet(f"background:{C['sidebar']};")
        tl = QHBoxLayout(topbar); tl.setContentsMargins(12, 0, 16, 0); tl.setSpacing(10)
        back = QPushButton("←"); back.setFixedSize(36, 36)
        back.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        back.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        back.setStyleSheet(f"""QPushButton{{background:transparent;color:{C['text']};
            border:none;border-radius:18px;}}
            QPushButton:hover{{background:{C['hover']};}}""")
        back.clicked.connect(self.closed.emit)
        title = QLabel(tr("settings"))
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{C['text']};")
        tl.addWidget(back); tl.addWidget(title); tl.addStretch()
        outer.addWidget(topbar)

        # Body: category sidebar + content stack
        body = QHBoxLayout(); body.setContentsMargins(0, 0, 0, 0); body.setSpacing(0)
        outer.addLayout(body)

        # Category sidebar
        cat_side = QWidget(); cat_side.setFixedWidth(210)
        cat_side.setStyleSheet(f"background:{C['sidebar']};")
        cs = QVBoxLayout(cat_side); cs.setContentsMargins(12, 16, 12, 16); cs.setSpacing(3)
        body.addWidget(cat_side)

        # Content stack
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background:transparent;")
        body.addWidget(self.stack, 1)

        # Build category pages
        categories = [
            (tr("account"), "👤", self._page_account),
            (tr("account_standing"), "🛡", self._page_standing),
            (tr("privacy"), "🔒", self._page_privacy),
            (tr("notifications"), "🔔", self._page_notifications),
            (tr("voice_video"), "🎙", self._page_voice),
            (tr("appearance"), "🎨", self._page_appearance),
            (tr("language_time"), "🌐", self._page_language_time),
            (tr("about"), "ℹ", self._page_about),
        ]
        for i, (name, icon, builder) in enumerate(categories):
            page = builder()
            wrapped = self._wrap_scroll(page)
            self.stack.addWidget(wrapped)
            b = QPushButton(f"  {icon}   {name}")
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.setFixedHeight(40)
            b.setCheckable(True)
            b.setStyleSheet(self._cat_style())
            b.clicked.connect(lambda _, idx=i: self._select_cat(idx))
            cs.addWidget(b)
            self._cat_buttons[i] = b

        cs.addStretch()
        # Logout at the bottom of the sidebar
        logout = QPushButton(f"  ⏻   {tr('log_out')}")
        logout.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        logout.setFixedHeight(40)
        logout.setStyleSheet(f"""QPushButton{{background:transparent;color:{C['red']};
            border:none;border-radius:8px;text-align:left;padding-left:6px;
            font-size:13px;font-weight:bold;font-family:'Segoe UI';}}
            QPushButton:hover{{background:{C['hover']};}}""")
        logout.clicked.connect(self.logout_requested.emit)
        cs.addWidget(logout)

        self._select_cat(0)

    def _cat_style(self):
        return f"""QPushButton{{background:transparent;color:{C['text2']};
            border:none;border-radius:8px;text-align:left;padding-left:6px;
            font-size:13px;font-weight:600;font-family:'Segoe UI';}}
            QPushButton:hover{{background:{C['hover']};color:{C['text']};}}
            QPushButton:checked{{background:{C['card']};color:{C['text']};}}"""

    def _select_cat(self, idx):
        for i, b in self._cat_buttons.items():
            b.setChecked(i == idx)
        self.stack.setCurrentIndex(idx)

    def _wrap_scroll(self, inner_widget):
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border:none;background:transparent;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget(); host.setStyleSheet("background:transparent;")
        wrap = QHBoxLayout(host); wrap.setContentsMargins(0, 0, 0, 0)
        wrap.addStretch()
        col = QWidget(); col.setFixedWidth(540); col.setStyleSheet("background:transparent;")
        cl = QVBoxLayout(col); cl.setContentsMargins(40, 28, 40, 28); cl.setSpacing(14)
        cl.addWidget(inner_widget)
        cl.addStretch()
        wrap.addWidget(col); wrap.addStretch()
        scroll.setWidget(host)
        return scroll

    def _page_title(self, text):
        t = QLabel(text)
        t.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        t.setStyleSheet(f"color:{C['text']};")
        return t

    # ── Page: Account ─────────────────────────────────────
    def _page_account(self):
        page = QWidget(); lo = QVBoxLayout(page); lo.setContentsMargins(0, 0, 0, 0); lo.setSpacing(12)
        lo.addWidget(self._page_title(tr("my_account")))

        # Avatar
        self.av_w = Avatar(self.user.get("username", "?"), 92, self.user.get("avatar_url", ""))
        self.av_w.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.av_w.mousePressEvent = lambda e: self._pick()
        ch = QLabel(tr("tap_to_change")); ch.setFont(QFont("Segoe UI", 10))
        ch.setStyleSheet(f"color:{C['text2']};")
        lo.addWidget(self.av_w, alignment=Qt.AlignmentFlag.AlignCenter)
        lo.addWidget(ch, alignment=Qt.AlignmentFlag.AlignCenter)

        lo.addWidget(self._small_label(tr("username")))
        self.un = QLineEdit(self.user.get("username", "")); self.un.setFixedHeight(44)
        self.un.setStyleSheet(field()); lo.addWidget(self.un)
        lo.addWidget(self._small_label(tr("bio")))
        self.bio = QTextEdit(); self.bio.setFixedHeight(80)
        self.bio.setPlainText(self.user.get("bio", "")); self.bio.setStyleSheet(field())
        lo.addWidget(self.bio)

        self.acc_status = QLabel(""); self.acc_status.setFont(QFont("Segoe UI", 11))
        self.acc_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lo.addWidget(self.acc_status)
        save = btn(tr("save_profile"), C["accent"], bold=True, font_size=13)
        save.setFixedHeight(46); save.clicked.connect(self._save_profile); lo.addWidget(save)

        # Phone (lecture seule : identifiant de connexion)
        sep = QFrame(); sep.setFixedHeight(1); sep.setStyleSheet(f"background:{C['divider']};border:none;")
        lo.addSpacing(6); lo.addWidget(sep); lo.addSpacing(6)
        lo.addWidget(self._section_label(tr("phone_caps")))
        phone_field = QLineEdit(self.user.get("phone", "")); phone_field.setReadOnly(True)
        phone_field.setFixedHeight(42); phone_field.setStyleSheet(field())
        lo.addWidget(phone_field)

        # Danger zone
        sep3 = QFrame(); sep3.setFixedHeight(1); sep3.setStyleSheet(f"background:{C['divider']};border:none;")
        lo.addSpacing(6); lo.addWidget(sep3); lo.addSpacing(6)
        dz = QLabel(tr("danger_zone"))
        dz.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        dz.setStyleSheet(f"color:{C['red']};letter-spacing:1px;")
        lo.addWidget(dz)
        # Supprimer tous ses messages
        nuke_btn = QPushButton(tr("delete_all_messages"))
        nuke_btn.setFixedHeight(44)
        nuke_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        nuke_btn.setStyleSheet(f"""QPushButton{{background:transparent;color:{C['orange']};
            border:1.5px solid {C['orange']};border-radius:10px;font-size:13px;
            font-weight:bold;font-family:'Segoe UI';}}
            QPushButton:hover{{background:{C['orange']};color:white;}}""")
        nuke_btn.clicked.connect(self._nuke_messages)
        lo.addWidget(nuke_btn)
        # Supprimer le compte
        del_btn = QPushButton(tr("delete_account"))
        del_btn.setFixedHeight(44)
        del_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        del_btn.setStyleSheet(f"""QPushButton{{background:transparent;color:{C['red']};
            border:1.5px solid {C['red']};border-radius:10px;font-size:13px;
            font-weight:bold;font-family:'Segoe UI';}}
            QPushButton:hover{{background:{C['red']};color:white;}}""")
        del_btn.clicked.connect(self._delete_account)
        lo.addWidget(del_btn)
        return page

    # ── Page: Privacy ─────────────────────────────────────
    def _page_privacy(self):
        page = QWidget(); lo = QVBoxLayout(page); lo.setContentsMargins(0, 0, 0, 0); lo.setSpacing(12)
        lo.addWidget(self._page_title(tr("privacy")))
        priv_row, self.priv_toggle = self._toggle_row(
            tr("private_profile"), tr("private_profile_desc"),
            self.user.get("is_private", False))
        lo.addWidget(priv_row)
        online_row, self.online_toggle = self._toggle_row(
            tr("show_online"), tr("show_online_desc"),
            self.user.get("show_online", True))
        lo.addWidget(online_row)
        self.priv_status = QLabel(""); self.priv_status.setFont(QFont("Segoe UI", 11))
        self.priv_status.setAlignment(Qt.AlignmentFlag.AlignCenter); lo.addWidget(self.priv_status)
        save = btn(tr("save_privacy"), C["accent"], bold=True, font_size=13)
        save.setFixedHeight(46); save.clicked.connect(self._save_privacy); lo.addWidget(save)
        return page

    # ── Page: Notifications ───────────────────────────────
    def _page_notifications(self):
        page = QWidget(); lo = QVBoxLayout(page); lo.setContentsMargins(0, 0, 0, 0); lo.setSpacing(12)
        lo.addWidget(self._page_title(tr("notifications")))
        notif_row, self.notif_toggle = self._toggle_row(
            tr("enable_notifications"), tr("enable_notifications_desc"),
            getattr(self.app, "notifications_on", True) if self.app else True)
        lo.addWidget(notif_row)
        self.notif_toggle.toggled.connect(self.notif_changed.emit)
        return page

    # ── Page: Voice & Video ───────────────────────────────
    def _page_voice(self):
        page = QWidget(); lo = QVBoxLayout(page); lo.setContentsMargins(0, 0, 0, 0); lo.setSpacing(12)
        lo.addWidget(self._page_title(tr("voice_video")))
        inputs, outputs = list_audio_devices()
        lo.addWidget(self._small_label(tr("microphone")))
        self.mic_combo = QComboBox(); self.mic_combo.setStyleSheet(self._combo_style())
        for idx, name in inputs:
            self.mic_combo.addItem(name, idx)
        lo.addWidget(self.mic_combo)
        lo.addWidget(self._small_label(tr("speaker")))
        self.spk_combo = QComboBox(); self.spk_combo.setStyleSheet(self._combo_style())
        for idx, name in outputs:
            self.spk_combo.addItem(name, idx)
        lo.addWidget(self.spk_combo)
        cfg = self.app._load_audio_config() if self.app else {"mic": None, "speaker": None}
        if cfg.get("mic") is not None:
            i = self.mic_combo.findData(cfg["mic"])
            if i >= 0: self.mic_combo.setCurrentIndex(i)
        if cfg.get("speaker") is not None:
            i = self.spk_combo.findData(cfg["speaker"])
            if i >= 0: self.spk_combo.setCurrentIndex(i)
        self.voice_status = QLabel(""); self.voice_status.setFont(QFont("Segoe UI", 11))
        self.voice_status.setAlignment(Qt.AlignmentFlag.AlignCenter); lo.addWidget(self.voice_status)
        save = btn(tr("save_audio"), C["accent"], bold=True, font_size=13)
        save.setFixedHeight(46); save.clicked.connect(self._save_voice); lo.addWidget(save)
        return page

    # ── Page: Appearance ──────────────────────────────────
    def _page_appearance(self):
        page = QWidget(); lo = QVBoxLayout(page); lo.setContentsMargins(0, 0, 0, 0); lo.setSpacing(14)
        lo.addWidget(self._page_title(tr("appearance")))
        prefs = _load_appearance()

        # Thème
        lo.addWidget(self._section_label(tr("theme")))
        self.theme_combo = QComboBox(); self.theme_combo.setStyleSheet(self._combo_style())
        theme_names = [("standard", "Standard (blue)"), ("dark", "Dark"),
                       ("light", "Light"), ("lightgray", "Light gray")]
        for key, label in theme_names:
            self.theme_combo.addItem(label, key)
        i = self.theme_combo.findData(prefs.get("theme", "standard"))
        if i >= 0: self.theme_combo.setCurrentIndex(i)
        lo.addWidget(self.theme_combo)
        hint = QLabel(tr("theme_hint"))
        hint.setStyleSheet(f"color:{C['text3']};font-size:10px;font-family:'Segoe UI';")
        lo.addWidget(hint)

        # Taille du texte
        sep1 = QFrame(); sep1.setFixedHeight(1); sep1.setStyleSheet(f"background:{C['divider']};border:none;")
        lo.addSpacing(4); lo.addWidget(sep1); lo.addSpacing(4)
        self.fontsize_label = QLabel(tr("text_size", v=prefs.get('font_size', 12)))
        self.fontsize_label.setStyleSheet(f"color:{C['text']};font-size:12px;font-weight:600;font-family:'Segoe UI';")
        lo.addWidget(self.fontsize_label)
        self.fontsize_slider = QSlider(Qt.Orientation.Horizontal)
        self.fontsize_slider.setMinimum(9); self.fontsize_slider.setMaximum(20)
        self.fontsize_slider.setValue(prefs.get("font_size", 12))
        self.fontsize_slider.setFixedHeight(24)
        self.fontsize_slider.setStyleSheet(self._slider_style())
        self.fontsize_slider.valueChanged.connect(
            lambda v: self.fontsize_label.setText(tr("text_size", v=v)))
        lo.addWidget(self.fontsize_slider)

        # Espace entre messages
        self.spacing_label = QLabel(tr("space_messages", v=prefs.get('group_spacing', 2)))
        self.spacing_label.setStyleSheet(f"color:{C['text']};font-size:12px;font-weight:600;font-family:'Segoe UI';")
        lo.addWidget(self.spacing_label)
        self.spacing_slider = QSlider(Qt.Orientation.Horizontal)
        self.spacing_slider.setMinimum(0); self.spacing_slider.setMaximum(16)
        self.spacing_slider.setValue(prefs.get("group_spacing", 2))
        self.spacing_slider.setFixedHeight(24)
        self.spacing_slider.setStyleSheet(self._slider_style())
        self.spacing_slider.valueChanged.connect(
            lambda v: self.spacing_label.setText(tr("space_messages", v=v)))
        lo.addWidget(self.spacing_slider)

        # Animer les GIFs
        sep3 = QFrame(); sep3.setFixedHeight(1); sep3.setStyleSheet(f"background:{C['divider']};border:none;")
        lo.addSpacing(4); lo.addWidget(sep3); lo.addSpacing(4)
        gif_row, self.gif_toggle = self._toggle_row(
            tr("animate_gifs"), tr("animate_gifs_desc"),
            prefs.get("animate_gifs", True))
        lo.addWidget(gif_row)

        # Bouton sauvegarder
        self.appearance_status = QLabel(""); self.appearance_status.setFont(QFont("Segoe UI", 11))
        self.appearance_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lo.addWidget(self.appearance_status)
        save = btn(tr("save_appearance"), C["accent"], bold=True, font_size=13)
        save.setFixedHeight(46); save.clicked.connect(self._save_appearance_prefs)
        lo.addWidget(save)
        return page

    # ── Page: Language & Time ─────────────────────────────
    def _page_language_time(self):
        page = QWidget(); lo = QVBoxLayout(page); lo.setContentsMargins(0, 0, 0, 0); lo.setSpacing(14)
        lo.addWidget(self._page_title(tr("language_time")))
        prefs = _load_appearance()

        # Langue
        lo.addWidget(self._section_label(tr("language")))
        self.lang_combo = QComboBox(); self.lang_combo.setStyleSheet(self._combo_style())
        languages = [("en", "English"), ("fr", "Français"), ("de", "Deutsch"),
                     ("es", "Español"), ("ru", "Русский")]
        for key, label in languages:
            self.lang_combo.addItem(label, key)
        li = self.lang_combo.findData(prefs.get("language", "en"))
        if li >= 0: self.lang_combo.setCurrentIndex(li)
        lo.addWidget(self.lang_combo)

        # Format de l'heure
        sep = QFrame(); sep.setFixedHeight(1); sep.setStyleSheet(f"background:{C['divider']};border:none;")
        lo.addSpacing(4); lo.addWidget(sep); lo.addSpacing(4)
        lo.addWidget(self._section_label(tr("time_format")))
        self.time_combo = QComboBox(); self.time_combo.setStyleSheet(self._combo_style())
        self.time_combo.addItem(tr("time_24h"), "24h")
        self.time_combo.addItem(tr("time_12h"), "12h")
        ti = self.time_combo.findData(prefs.get("time_format", "24h"))
        if ti >= 0: self.time_combo.setCurrentIndex(ti)
        lo.addWidget(self.time_combo)

        # Bouton sauvegarder
        self.langtime_status = QLabel(""); self.langtime_status.setFont(QFont("Segoe UI", 11))
        self.langtime_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lo.addWidget(self.langtime_status)
        save = btn(tr("save"), C["accent"], bold=True, font_size=13)
        save.setFixedHeight(46); save.clicked.connect(self._save_langtime_prefs)
        lo.addWidget(save)
        return page

    def _save_langtime_prefs(self):
        prefs = _load_appearance()
        prefs["language"] = self.lang_combo.currentData()
        prefs["time_format"] = self.time_combo.currentData()
        _save_appearance(prefs)
        global APPEARANCE
        APPEARANCE = prefs
        self.langtime_status.setStyleSheet(f"color:{C['green']};")
        self.langtime_status.setText(tr("saved_restarting"))
        QTimer.singleShot(500, self._restart_app)

    def _slider_style(self):
        return f"""
            QSlider {{min-height:22px;}}
            QSlider::groove:horizontal {{height:6px;background:{C['panel']};border-radius:3px;margin:0px;}}
            QSlider::handle:horizontal {{background:{C['accent']};width:16px;height:16px;
                margin:-6px 0;border-radius:8px;}}
            QSlider::handle:horizontal:hover {{background:{C['accent_h']};}}
            QSlider::sub-page:horizontal {{background:{C['accent']};border-radius:3px;}}
        """

    def _save_appearance_prefs(self):
        prefs = _load_appearance()
        prefs["theme"] = self.theme_combo.currentData()
        prefs["font_size"] = self.fontsize_slider.value()
        prefs["group_spacing"] = self.spacing_slider.value()
        prefs["animate_gifs"] = self.gif_toggle.isChecked()
        _save_appearance(prefs)
        global APPEARANCE
        APPEARANCE = prefs
        self.appearance_status.setStyleSheet(f"color:{C['green']};")
        self.appearance_status.setText(tr("saved_restarting"))
        # Redémarre l'app automatiquement pour appliquer le thème
        QTimer.singleShot(500, self._restart_app)

    def _restart_app(self):
        import sys
        # Ferme proprement les connexions de l'app principale
        try:
            if self.app:
                if getattr(self.app, "ws", None): self.app.ws.close()
                if getattr(self.app, "group_ws", None): self.app.group_ws.close()
        except Exception:
            pass
        # Relance le process Python avec les mêmes arguments
        python = sys.executable
        os.execl(python, python, *sys.argv)

    # ── Page: Account Standing ────────────────────────────
    def _page_standing(self):
        page = QWidget(); lo = QVBoxLayout(page); lo.setContentsMargins(0, 0, 0, 0); lo.setSpacing(14)
        lo.addWidget(self._page_title(tr("account_standing")))

        # Carte de statut (remplie après chargement)
        self.standing_card = QWidget()
        self.standing_card.setStyleSheet(f"background:{C['card']};border-radius:14px;")
        sc = QVBoxLayout(self.standing_card)
        sc.setContentsMargins(20, 20, 20, 20); sc.setSpacing(10)
        self.standing_icon = QLabel("⏳")
        self.standing_icon.setFont(QFont("Segoe UI", 34))
        self.standing_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sc.addWidget(self.standing_icon)
        self.standing_status = QLabel(tr("loading"))
        self.standing_status.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.standing_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.standing_status.setStyleSheet(f"color:{C['text']};")
        sc.addWidget(self.standing_status)
        self.standing_desc = QLabel("")
        self.standing_desc.setFont(QFont("Segoe UI", 11))
        self.standing_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.standing_desc.setWordWrap(True)
        self.standing_desc.setStyleSheet(f"color:{C['text2']};")
        sc.addWidget(self.standing_desc)
        lo.addWidget(self.standing_card)

        # Section des avertissements
        self.standing_warnings_label = QLabel("")
        self.standing_warnings_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.standing_warnings_label.setStyleSheet(f"color:{C['text2']};letter-spacing:1px;")
        lo.addWidget(self.standing_warnings_label)

        self.standing_warnings_box = QVBoxLayout()
        self.standing_warnings_box.setSpacing(8)
        lo.addLayout(self.standing_warnings_box)
        lo.addStretch()

        # Charge le standing depuis le serveur
        self._load_standing()
        return page

    def _load_standing(self):
        def do():
            return api_get("/auth/my_standing", self.token)
        self._standing_worker = ApiWorker(do)
        self._standing_worker.done.connect(self._on_standing_loaded)
        self._standing_worker.start()

    def _on_standing_loaded(self, data):
        # Vide la liste (utile en cas de rechargement après une erreur)
        while self.standing_warnings_box.count():
            it = self.standing_warnings_box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if not data:
            # État d'erreur : serveur injoignable
            self.standing_icon.setText("📡")
            self.standing_status.setText(tr("standing_error"))
            self.standing_status.setStyleSheet(f"color:{C['red']};")
            self.standing_desc.setText(tr("standing_error_desc"))
            self.standing_warnings_label.setText("")
            retry = QPushButton(tr("retry"))
            retry.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            retry.setFixedHeight(38)
            retry.setStyleSheet(f"""QPushButton{{background:{C['accent']};color:white;
                border:none;border-radius:10px;font-size:13px;font-weight:bold;
                font-family:'Segoe UI';}}""")
            retry.clicked.connect(self._retry_standing)
            self.standing_warnings_box.addWidget(retry)
            return
        status = data.get("status", "good")
        total = data.get("total", 0)
        warnings = data.get("warnings", [])
        # Configure la carte selon le statut
        if status == "good":
            self.standing_icon.setText("✅")
            self.standing_status.setText(tr("standing_good"))
            self.standing_status.setStyleSheet(f"color:{C['green']};")
            self.standing_desc.setText(tr("standing_good_desc"))
        elif status == "warning":
            self.standing_icon.setText("⚠️")
            self.standing_status.setText(tr("standing_warning"))
            self.standing_status.setStyleSheet(f"color:{C['orange']};")
            self.standing_desc.setText(tr("standing_warning_desc"))
        else:  # limited
            self.standing_icon.setText("🛑")
            self.standing_status.setText(tr("standing_limited"))
            self.standing_status.setStyleSheet(f"color:{C['red']};")
            self.standing_desc.setText(tr("standing_limited_desc"))
        # Liste des avertissements
        if warnings:
            self.standing_warnings_label.setText(tr("your_warnings", n=total))
            for w in warnings:
                self.standing_warnings_box.addWidget(self._standing_warning_row(w))
        else:
            self.standing_warnings_label.setText("")

    def _retry_standing(self):
        # Remet la carte en état de chargement puis relance la requête
        self.standing_icon.setText("⏳")
        self.standing_status.setText(tr("loading"))
        self.standing_status.setStyleSheet(f"color:{C['text']};")
        self.standing_desc.setText("")
        self._load_standing()

    def _standing_warning_row(self, w):
        row = QWidget()
        row.setStyleSheet(f"background:{C['card']};border-radius:10px;")
        rl = QVBoxLayout(row); rl.setContentsMargins(14, 10, 14, 10); rl.setSpacing(3)
        head = QHBoxLayout()
        sev = w.get("severity", "warning")
        badge = QLabel(tr("severe") if sev == "severe" else tr("warning_label"))
        badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        bc = C["red"] if sev == "severe" else C["orange"]
        badge.setStyleSheet(f"color:white;background:{bc};border-radius:5px;padding:2px 8px;")
        head.addWidget(badge)
        head.addStretch()
        at = QLabel((w.get("at") or "")[:10])
        at.setFont(QFont("Segoe UI", 9))
        at.setStyleSheet(f"color:{C['text3']};background:transparent;")
        head.addWidget(at)
        rl.addLayout(head)
        reason = QLabel(w.get("reason", ""))
        reason.setWordWrap(True)
        reason.setFont(QFont("Segoe UI", 11))
        reason.setStyleSheet(f"color:{C['text']};background:transparent;")
        rl.addWidget(reason)
        return row

    # ── Page: About ───────────────────────────────────────
    def _page_about(self):
        page = QWidget(); lo = QVBoxLayout(page); lo.setContentsMargins(0, 0, 0, 0); lo.setSpacing(12)
        lo.addWidget(self._page_title(tr("about")))
        if os.path.exists(LOGO_PATH):
            logo = QLabel(); logo.setPixmap(make_rounded_logo(LOGO_PATH, 80))
            logo.setFixedSize(80, 80); logo.setScaledContents(True)
            lo.addWidget(logo, alignment=Qt.AlignmentFlag.AlignCenter)
        name = QLabel("Velo"); name.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        name.setAlignment(Qt.AlignmentFlag.AlignCenter); name.setStyleSheet(f"color:{C['text']};")
        lo.addWidget(name)
        ver = QLabel("Version 1.0  •  Fast and secure messaging")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet(f"color:{C['text2']};font-size:11px;font-family:'Segoe UI';")
        lo.addWidget(ver)
        return page

    # ── Avatar pick ───────────────────────────────────────
    def _pick(self):
        p, _ = QFileDialog.getOpenFileName(self, "Choose image", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if p:
            self.avatar_path = p
            self.av_w.refresh(self.user.get("username", "?"), p)

    # ── Actions ───────────────────────────────────────────
    def _save_profile(self):
        payload = {
            "username": self.un.text().strip(),
            "bio": self.bio.toPlainText().strip(),
        }
        if self.avatar_path: payload["avatar_url"] = self.avatar_path
        try:
            r = requests.patch(f"{BASE_URL}/auth/me", json=payload, headers=H(self.token))
            if r.status_code == 200:
                updated = r.json()
                if self.avatar_path: updated["avatar_url"] = self.avatar_path
                self.profile_updated.emit(updated)
                self.acc_status.setStyleSheet(f"color:{C['green']};")
                self.acc_status.setText("✓ Profile updated")
            else:
                self.acc_status.setStyleSheet(f"color:{C['red']};")
                self.acc_status.setText("Update failed.")
        except Exception:
            self.acc_status.setStyleSheet(f"color:{C['red']};")
            self.acc_status.setText("Cannot reach server.")

    def _save_privacy(self):
        payload = {
            "is_private": self.priv_toggle.isChecked(),
            "show_online": self.online_toggle.isChecked(),
        }
        try:
            r = requests.patch(f"{BASE_URL}/auth/me", json=payload, headers=H(self.token))
            if r.status_code == 200:
                self.profile_updated.emit(r.json())
                self.priv_status.setStyleSheet(f"color:{C['green']};")
                self.priv_status.setText("✓ Privacy updated")
            else:
                self.priv_status.setStyleSheet(f"color:{C['red']};")
                self.priv_status.setText("Update failed.")
        except Exception:
            self.priv_status.setStyleSheet(f"color:{C['red']};")
            self.priv_status.setText("Cannot reach server.")

    def _save_voice(self):
        if self.app:
            self.app._save_audio_config(self.mic_combo.currentData(), self.spk_combo.currentData())
            self.voice_status.setStyleSheet(f"color:{C['green']};")
            self.voice_status.setText("✓ Audio devices saved")

    def _confirm_with_code(self, title, purpose):
        """Demande un code de confirmation au serveur puis le fait saisir.
        Retourne le code saisi (str) ou None si annulé / erreur."""
        try:
            r = requests.post(f"{BASE_URL}/auth/request_action_code",
                              json={"purpose": purpose}, headers=H(self.token))
        except Exception:
            QMessageBox.warning(self, title, tr("server_unreachable"))
            return None
        if r.status_code != 200:
            QMessageBox.warning(self, title, tr("server_unreachable"))
            return None
        # Indice du code en mode dev (pas de vrai SMS pour l'instant)
        dev = r.json().get("dev_code")
        prompt = tr("confirm_code_prompt")
        if dev:
            prompt += f"\n\nDev code: {dev}"
        code, ok = QInputDialog.getText(self, title, prompt)
        if not ok or not code.strip():
            return None
        return code.strip()

    def _delete_account(self):
        confirm = QMessageBox.question(self, tr("delete_account"),
            "This is permanent. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm != QMessageBox.StandardButton.Yes:
            return
        code = self._confirm_with_code(tr("delete_account"), "delete_account")
        if code is None:
            return
        try:
            r = requests.post(f"{BASE_URL}/auth/delete_account",
                              json={"code": code}, headers=H(self.token))
            if r.status_code == 200:
                self.account_deleted.emit()
            elif r.status_code == 401:
                QMessageBox.warning(self, tr("delete_account"), tr("invalid_code"))
            else:
                QMessageBox.warning(self, tr("delete_account"), "Failed to delete account.")
        except Exception:
            QMessageBox.warning(self, tr("delete_account"), tr("server_unreachable"))

    def _nuke_messages(self):
        #confirmation dabord
        confirm = QMessageBox.question(self, tr("delete_all_messages"),
            "This will permanently delete ALL messages you've sent "
            "(direct messages and group messages). This cannot be undone.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm != QMessageBox.StandardButton.Yes:
            return
        # Confirmation par code SMS
        code = self._confirm_with_code(tr("delete_all_messages"), "nuke_messages")
        if code is None:
            return
        try:
            r = requests.post(f"{BASE_URL}/chat/nuke_messages",
                              json={"code": code}, headers=H(self.token))
            if r.status_code == 200:
                n = r.json().get("deleted", 0)
                QMessageBox.information(self, tr("delete_all_messages"),
                    f"✓ {n} message(s) deleted.")
            elif r.status_code == 401:
                QMessageBox.warning(self, tr("delete_all_messages"), tr("invalid_code"))
            else:
                QMessageBox.warning(self, tr("delete_all_messages"), "Failed.")
        except Exception:
            QMessageBox.warning(self, tr("delete_all_messages"), tr("server_unreachable"))


# ── Main window ───────────────────────────────────────────
class SplashScreen(QWidget):
    """Écran de chargement façon Discord pendant le démarrage de l'app."""
    def __init__(self):
        super().__init__()
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setFixedSize(360, 360)
        self.setStyleSheet(f"background:{C['bg']};")
        lo = QVBoxLayout(self)
        lo.setContentsMargins(40, 40, 40, 40); lo.setSpacing(0)
        lo.addStretch()
        icon = QLabel()
        if os.path.exists(LOGO_PATH):
            icon.setPixmap(make_rounded_logo(LOGO_PATH, 120))
            icon.setFixedSize(120, 120); icon.setScaledContents(True)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lo.addWidget(icon, alignment=Qt.AlignmentFlag.AlignHCenter)
        lo.addSpacing(28)
        name = QLabel("Velo")
        name.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet(f"color:{C['text']};")
        lo.addWidget(name)
        lo.addSpacing(8)
        self.status = QLabel(tr("connecting"))
        self.status.setFont(QFont("Segoe UI", 12))
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setStyleSheet(f"color:{C['text2']};")
        lo.addWidget(self.status)
        lo.addStretch()
        self._dots = 0
        self._dot_timer = QTimer(self)
        self._dot_timer.timeout.connect(self._tick)
        self._dot_timer.start(400)
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2,
                  (screen.height() - self.height()) // 2)

    def _tick(self):
        self._dots = (self._dots + 1) % 4
        self.status.setText("Connecting" + "." * self._dots)

    def set_status(self, text):
        self.status.setText(text)

    def stop(self):
        self._dot_timer.stop()
        self.close()

class MentionPopup(QListWidget):
    """Liste d'autocomplétion pour les @mentions."""
    picked = pyqtSignal(str)  # username choisi
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup)
        self.setStyleSheet(f"""
            QListWidget {{background:{C['card']};border:1px solid {C['divider']};
                border-radius:10px;padding:4px;outline:none;
                font-family:'Segoe UI';font-size:13px;color:{C['text']};}}
            QListWidget::item {{padding:7px 12px;border-radius:6px;}}
            QListWidget::item:selected {{background:{C['accent']};color:white;}}
            QListWidget::item:hover {{background:{C['hover']};}}
        """)
        self.itemClicked.connect(lambda it: self.picked.emit(it.data(Qt.ItemDataRole.UserRole)))

    def set_members(self, members):
        """members = liste de dicts {username, ...}"""
        self.clear()
        for m in members[:8]:  # max 8 suggestions
            uname = m.get("username", "?")
            it = QListWidgetItem(f"@{uname}")
            it.setData(Qt.ItemDataRole.UserRole, uname)
            self.addItem(it)
        if self.count() > 0:
            self.setCurrentRow(0)

class VeloApp(QMainWindow):
    sig_msg = pyqtSignal(str, int)
    sig_group_msg = pyqtSignal(str)
    sig_group_closed = pyqtSignal(int)
    sig_call_incoming = pyqtSignal(int)
    sig_call_connected = pyqtSignal()
    sig_call_ended = pyqtSignal()
    sig_call_unavailable = pyqtSignal()
    sig_msg_edited = pyqtSignal(int, str)    # (message_id, new_text)
    sig_msg_deleted = pyqtSignal(int)        # (message_id)
    def __init__(self, token, user, splash=None):
        super().__init__()
        self.token = token
        self.user = user
        self._splash = splash
        self._loaded_flags = {"friends": False, "groups": False}
        self.recv_id = None
        self.friends = {}
        self.groups = {}
        self.current_group_id = None
        self.ws = None
        self._bubbles = {}   # msg_id -> Bubble (pour edit/delete)
        _audio_cfg = self._load_audio_config()
        self.call_engine = CallEngine(
            WS_URL,
            self.user["id"],
            mic_index=_audio_cfg.get("mic"),
            speaker_index=_audio_cfg.get("speaker"),
        )
        self.call_engine.on_incoming = lambda from_id: self.sig_call_incoming.emit(from_id)
        self.call_engine.on_connected = lambda: self.sig_call_connected.emit()
        self.call_engine.on_ended = lambda: self.sig_call_ended.emit()
        self.call_engine.on_unavailable = lambda: self.sig_call_unavailable.emit()
        self.call_engine.start()
        self.active_call_dialog = None
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
        self.sig_call_incoming.connect(self._on_call_incoming)
        self.sig_call_connected.connect(self._on_call_connected)
        self.sig_call_ended.connect(self._on_call_ended)
        self.sig_call_unavailable.connect(self._on_call_unavailable)
        self.sig_msg_edited.connect(self._apply_edit)
        self.sig_msg_deleted.connect(self._apply_delete)
        self.group_ws = None
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._periodic_refresh)
        self.refresh_timer.start(10000)
        # Sécurité : ferme le splash après 8s max même si le réseau traîne
        if self._splash is not None:
            QTimer.singleShot(8000, self._force_close_splash)
        self._typing_timer = QTimer(self)
        self._typing_timer.setSingleShot(True)
        self._typing_timer.timeout.connect(self._stop_typing)
        self._is_typing = False
        self.typing_bubble = None
        self.mention_popup = MentionPopup(self)
        self.mention_popup.picked.connect(self._insert_mention)

    def _get_mention_candidates(self):
        """Renvoie la liste des personnes mentionnables selon le contexte."""
        # En groupe : les membres du groupe
        if self.current_group_id:
            members = getattr(self, "_current_group_members", None)
            if members:
                return members
            return []
        # En DM : la personne à qui on parle
        if self.recv_id and self.recv_id in self.friends:
            row = self.friends[self.recv_id]
            uname = getattr(row, "uname", None)
            if uname:
                return [{"username": uname}]
        return []

    def _check_mention_trigger(self, text):
        # Cherche un @mot juste avant le curseur
        cursor_pos = self.inp.cursorPosition()
        before = text[:cursor_pos]
        import re
        m = re.search(r'@(\w*)$', before)
        if not m:
            self.mention_popup.hide()
            return
        query = m.group(1).lower()
        # Filtre les candidats
        candidates = self._get_mention_candidates()
        filtered = [c for c in candidates
                    if c.get("username", "").lower().startswith(query)]
        if not filtered:
            self.mention_popup.hide()
            return
        self.mention_popup.set_members(filtered)
        # Positionne le popup au-dessus du champ
        pos = self.inp.mapToGlobal(self.inp.rect().topLeft())
        h = min(self.mention_popup.sizeHintForRow(0) * len(filtered) + 10, 250)
        self.mention_popup.setFixedHeight(h)
        self.mention_popup.setFixedWidth(220)
        self.mention_popup.move(pos.x(), pos.y() - h - 6)
        self.mention_popup.show()

    def _insert_mention(self, username):
        # Remplace le @mot en cours par @username complet
        text = self.inp.text()
        cursor_pos = self.inp.cursorPosition()
        before = text[:cursor_pos]
        after = text[cursor_pos:]
        import re
        new_before = re.sub(r'@(\w*)$', f'@{username} ', before)
        self.inp.setText(new_before + after)
        self.inp.setCursorPosition(len(new_before))
        self.mention_popup.hide()
        self.inp.setFocus()

    def _toggle_camera(self):
        if getattr(self, "_video_mode", None) == "camera":
            # Couper la caméra
            self.call_engine.stop_video()
            self._video_mode = None
            self.active_call_dialog.cam_btn.setStyleSheet(self.active_call_dialog._tool_style())
        else:
            self.call_engine.start_camera()
            self._video_mode = "camera"
            # Bouton actif (bleu)
            self.active_call_dialog.cam_btn.setStyleSheet(f"""QPushButton{{background:{C['accent']};
                color:white;border:none;border-radius:26px;font-size:20px;}}""")
            # Désactive le style écran
            self.active_call_dialog.screen_btn.setStyleSheet(self.active_call_dialog._tool_style())

    def _toggle_screen(self):
        if getattr(self, "_video_mode", None) == "screen":
            self.call_engine.stop_video()
            self._video_mode = None
            self.active_call_dialog.screen_btn.setStyleSheet(self.active_call_dialog._tool_style())
        else:
            self.call_engine.start_screen()
            self._video_mode = "screen"
            self.active_call_dialog.screen_btn.setStyleSheet(f"""QPushButton{{background:{C['accent']};
                color:white;border:none;border-radius:26px;font-size:20px;}}""")
            self.active_call_dialog.cam_btn.setStyleSheet(self.active_call_dialog._tool_style())

    def _load_audio_config(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio_config.json")
        try:
            if os.path.exists(path):
                with open(path) as f:
                    return json.load(f)
        except Exception:
            pass
        return {"mic": None, "speaker": None}

    def _save_audio_config(self, mic_idx, speaker_idx):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio_config.json")
        try:
            with open(path, "w") as f:
                json.dump({"mic": mic_idx, "speaker": speaker_idx}, f)
        except Exception as e:
            print("audio config save error:", e)
        self.call_engine.mic_index = mic_idx
        self.call_engine.speaker_index = speaker_idx

    def _start_call(self):
        if not self.recv_id:
            return
        name = self.friends[self.recv_id].uname if self.recv_id in self.friends else "User"
        avatar = ""
        self.active_call_dialog = CallDialog(name, avatar, incoming=False, parent=self)
        self.active_call_dialog.hangup_btn.clicked.connect(self._hangup_call)
        self.active_call_dialog.cam_btn.clicked.connect(self._toggle_camera)
        self.active_call_dialog.screen_btn.clicked.connect(self._toggle_screen)
        self.call_engine.on_remote_video = lambda img: self.active_call_dialog.remote_frame.emit(img)
        self.call_engine.on_video_stopped = lambda: self.active_call_dialog.video_stopped.emit()
        self.call_engine.call(self.recv_id)
        self.active_call_dialog.show()
        self._video_mode = None

    def _on_call_incoming(self, from_id):
        name = "User"
        if from_id in self.friends:
            name = self.friends[from_id].uname
        self.active_call_dialog = CallDialog(name, "", incoming=True, parent=self)
        self.active_call_dialog.accept_btn.clicked.connect(self._accept_call)
        self.active_call_dialog.hangup_btn.clicked.connect(self._decline_call)
        self.active_call_dialog.cam_btn.clicked.connect(self._toggle_camera)
        self.active_call_dialog.screen_btn.clicked.connect(self._toggle_screen)
        self.call_engine.on_remote_video = lambda img: self.active_call_dialog.remote_frame.emit(img)
        self.call_engine.on_video_stopped = lambda: self.active_call_dialog.video_stopped.emit()
        self.active_call_dialog.show()
        self._video_mode = None
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass

    def _accept_call(self):
        self.call_engine.accept()
        if self.active_call_dialog:
            self.active_call_dialog.set_status("Connected")
            self.active_call_dialog.accept_btn.setVisible(False)
            self.active_call_dialog.show_call_controls()

    def _decline_call(self):
        self.call_engine.decline()
        self._close_call_dialog()

    def _hangup_call(self):
        self.call_engine.hangup()
        self._close_call_dialog()

    def _on_call_connected(self):
        if self.active_call_dialog:
            self.active_call_dialog.set_status("Connected")
            self.active_call_dialog.show_call_controls()

    def _on_call_ended(self):
        self._close_call_dialog()

    def _on_call_unavailable(self):
        if self.active_call_dialog:
            self.active_call_dialog.set_status("User unavailable")
            QTimer.singleShot(1500, self._close_call_dialog)

    def _close_call_dialog(self):
        if self.active_call_dialog:
            self.active_call_dialog.close()
            self.active_call_dialog = None

    def _open_gif(self):
        if not self.recv_id and not self.current_group_id:
            return
        d = GifPicker(self.token, self)
        d.gif_picked.connect(self._send_gif)
        anchor = self.inp.mapToGlobal(self.inp.rect().bottomRight())
        d.move(anchor.x() - d.width() + 40, anchor.y() - d.height() - 50)
        d.show()

    def _send_gif(self, url):
        # On envoie le GIF comme une pièce jointe de type image
        info = {"type": "image", "url": url, "name": "gif"}
        msg = f"[FILE]image|{url}|gif"
        if self.current_group_id and self.group_ws:
            try:
                self.group_ws.send(msg)
                self.msg_vbox.insertWidget(self.msg_vbox.count() - 1, self._make_attachment(info, True))
                self._scroll_bottom()
            except Exception as ex:
                print(ex)
        elif self.recv_id and self.ws:
            try:
                self.ws.send(f"{self.recv_id}:{msg}")
                self.msg_vbox.insertWidget(self.msg_vbox.count() - 1, self._make_attachment(info, True))
                self._scroll_bottom()
            except Exception as ex:
                print(ex)

    def _open_emoji(self):
        d = EmojiPicker(self)
        d.emoji_picked.connect(self._insert_emoji)
        # Ancre le panneau en bas à droite de la zone de saisie (sort vers le haut)
        anchor = self.inp.mapToGlobal(self.inp.rect().bottomRight())
        d.move(anchor.x() - d.width() + 40, anchor.y() - d.height() - 50)
        d.show()

    def _insert_emoji(self, emo):
        # Insère l'emoji à la position du curseur dans le champ
        self.inp.setText(self.inp.text() + emo)
        self.inp.setFocus()

    def _clear_ephemeral(self, uid):
        if uid is None:
            return
        self._async(api_post, lambda r: None,
                    f"/conversation/clear_read/{uid}", self.token, {})

    def _open_conv_settings(self):
        if not self.recv_id:
            return
        other_name = self.friends[self.recv_id].uname if self.recv_id in self.friends else "user"
        d = ConvSettingsDialog(self.token, self.recv_id, other_name, self)
        d.exec()

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
        full_url = url if url.startswith("http") else f"{BASE_URL}{url}"
        # GIF animé (URL externe se terminant par .gif)
        if full_url.lower().endswith(".gif"):
            return self._make_gif_bubble(full_url, outgoing)
        if ftype == "image":
            return ImageBubble(full_url, self.token, outgoing)
        elif ftype == "video":
            return VideoBubble(full_url, self.token, name, outgoing)
        else:
            return FileBubble(full_url, self.token, name, outgoing)

    def _make_gif_bubble(self, url, outgoing):
        wrap = QWidget()
        lo = QHBoxLayout(wrap);
        lo.setContentsMargins(16, 3, 16, 3)
        gif = AnimatedGif(url, max_width=220)
        gif.setStyleSheet(f"background:{C['msg_out'] if outgoing else C['msg_in']};border-radius:12px;padding:4px;")
        if outgoing:
            lo.addStretch();
            lo.addWidget(gif)
        else:
            lo.addWidget(gif);
            lo.addStretch()
        return wrap

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
        menu.addAction("😀  Emoji", self._open_emoji)
        menu.addAction("🎞  GIF", self._open_gif)
        menu.addSeparator()
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
        # Si la requête a échoué (None) ou renvoie vide (latence/timeout Render),
        # on NE kick PAS — sinon faux positif.
        if not members:
            return
        my_ids = [m["user_id"] for m in members]
        if self.user["id"] not in my_ids:
            # On a été kické/banni
            self.current_group_id = None
            self.ch_name.setText(tr("select_a_chat"))
            self.ch_sub.setText("")
            self.view_prof.setVisible(False)
            while self.msg_vbox.count() > 1:
                it = self.msg_vbox.takeAt(0)
                if it.widget(): it.widget().deleteLater()
            # Message d'info
            info = QLabel(tr("removed_from_group"))
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
        new_ws = websocket.WebSocketApp(
            f"{WS_URL}/chat/group_ws/{gid}/{self.user['id']}",
            on_message=lambda ws, msg: self.sig_group_msg.emit(msg),
            on_close=lambda ws, code, reason: self._handle_group_close(ws, gid))
        self.group_ws = new_ws
        threading.Thread(target=new_ws.run_forever, daemon=True).start()

    def _handle_group_close(self, ws, gid):
        # Si ce n'est plus le WebSocket actif, fermeture volontaire → ignorer
        if ws is not self.group_ws:
            return
        self.sig_group_closed.emit(gid)

    def _on_group_incoming(self, message):
        if ":" not in message: return
        header, content = message.split(":", 1)
        # Signaux edit/delete de groupe (header == "__SIGNAL__")
        if header == "__SIGNAL__":
            if content.startswith("[EDIT]"):
                payload = content[len("[EDIT]"):]
                parts = payload.split("|", 1)
                if len(parts) == 2:
                    try:
                        mid = int(parts[0])
                        self.sig_msg_edited.emit(mid, parts[1])
                    except ValueError:
                        pass
            elif content.startswith("[DELETE]"):
                try:
                    mid = int(content[len("[DELETE]"):])
                    self.sig_msg_deleted.emit(mid)
                except ValueError:
                    pass
            return
        # Format normal : "sender_name|msg_id"
        msg_id = None
        sender_name = header
        if "|" in header:
            sender_name, id_str = header.rsplit("|", 1)
            try:
                msg_id = int(id_str)
            except ValueError:
                msg_id = None
        # Mon propre message renvoyé → on attribue juste l'id à la bulle en attente
        if sender_name == self.user["username"]:
            if msg_id is not None:
                self._assign_group_sent_id(msg_id, self.current_group_id)
            return
        # Message d'un autre membre
        if content.startswith("[FILE]"):
            w = self._parse_attachment(content, False)
            if w:
                self.msg_vbox.insertWidget(self.msg_vbox.count() - 1, w)
                self._fade_in(w)
            preview = "📎 Attachment"
        else:
            b = self._make_group_bubble(content, False,
                                        self.current_group_id, msg_id=msg_id,
                                        raw_content=content, sender_name=sender_name)
            self.msg_vbox.insertWidget(self.msg_vbox.count() - 1, b)
            self._fade_in(b)
            preview = f"{sender_name}: {content}"
        # Met à jour l'aperçu du groupe dans la liste
        if self.current_group_id in self.groups:
            self.groups[self.current_group_id].set_preview(preview)
        self._scroll_bottom()

    def _assign_group_sent_id(self, new_id, gid):
        b = getattr(self, "_pending_group_bubble", None)
        if b is None:
            return
        b.msg_id = new_id
        b._raw_content = getattr(b, "_raw_content", b._raw_text)
        self._bubbles[new_id] = b
        b.lbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        try:
            b.lbl.customContextMenuRequested.disconnect()
        except Exception:
            pass
        b.lbl.customContextMenuRequested.connect(b._menu)
        b.edit_requested.connect(lambda mid, _t, g=gid: self._on_group_edit_requested(mid, g))
        b.delete_requested.connect(lambda mid, g=gid: self._on_group_delete_requested(mid, g))
        self._pending_group_bubble = None

    def _select_group(self, gid):
        if self.recv_id:
            self._clear_ephemeral(self.recv_id)
        self._show_chat_area()
        # Si le groupe était masqué, on le ré-affiche
        if gid in self._load_hidden_groups():
            self._unhide_group(gid)
        # Désélectionne amis et groupes
        for w in self.friends.values(): w.set_selected(False)
        for w in self.groups.values(): w.set_selected(False)
        if gid in self.groups: self.groups[gid].set_selected(True)
        self.current_group_id = gid
        self.recv_id = None  # on est en mode groupe
        self.view_prof.setText(tr("group_settings"))
        self.view_prof.setVisible(True)
        self.conv_settings_btn.setVisible(False)
        self.call_btn.setVisible(False)
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
        lock = "🔒 " + tr("private_group") if g.get("is_private") else tr("public_group")
        self.ch_sub.setText(lock)

    def _fill_group_history(self, msgs, gid):
        self._bubbles.clear()
        prev_sender = None
        for i, m in enumerate(msgs):
            outgoing = m["sender_id"] == self.user["id"]
            content = m["content"]
            if content.startswith("[FILE]"):
                w = self._parse_attachment(content, outgoing)
                if w: self.msg_vbox.insertWidget(i, w)
                prev_sender = None  # une pièce jointe casse le regroupement
            else:
                # Regroupement : masque avatar+nom si même expéditeur que le précédent
                same_as_prev = (m["sender_id"] == prev_sender)
                sender = None if (outgoing or same_as_prev) else m.get("sender_name", "?")
                # indent : réserve l'espace avatar pour aligner les messages groupés
                indent = (not outgoing) and same_as_prev
                b = self._make_group_bubble(content, outgoing, gid,
                                            msg_id=m.get("id"), edited=m.get("edited", False),
                                            raw_content=content, sender_name=sender, indent=indent)
                self.msg_vbox.insertWidget(i, b)
                prev_sender = m["sender_id"]
        self._scroll_bottom()

    def _make_group_bubble(self, text, outgoing, gid, msg_id=None, edited=False,
                           raw_content="", sender_name=None, indent=False):
        import datetime
        now = format_msg_time()
        b = Bubble(text, outgoing, msg_id=msg_id, edited=edited,
                   sender_name=sender_name, time_str=now, indent=indent)
        b._raw_content = raw_content  # contenu sans le préfixe "nom:"
        if msg_id is not None:
            self._bubbles[msg_id] = b
            if outgoing:
                b.edit_requested.connect(lambda mid, _t, g=gid: self._on_group_edit_requested(mid, g))
                b.delete_requested.connect(lambda mid, g=gid: self._on_group_delete_requested(mid, g))
        return b

    def _on_group_edit_requested(self, msg_id, gid):
        current = ""
        if msg_id in self._bubbles:
            current = getattr(self._bubbles[msg_id], "_raw_content", "")
        new_text, ok = QInputDialog.getText(self, "Edit message", "New text:", text=current)
        if ok and new_text.strip() and new_text != current:
            self._async(api_post, lambda r: None, f"/groups/{gid}/edit_message", self.token,
                        {"message_id": msg_id, "new_content": new_text.strip()})
            if msg_id in self._bubbles:
                self._bubbles[msg_id].mark_edited(new_text.strip())
            # Diffuse aux autres via le WS de groupe
            if self.group_ws:
                try:
                    self.group_ws.send(f"[EDIT]{msg_id}|{new_text.strip()}")
                except Exception:
                    pass

    def _on_group_delete_requested(self, msg_id, gid):
        self._async(api_post, lambda r: None, f"/groups/{gid}/delete_message", self.token,
                    {"message_id": msg_id})
        self._apply_delete(msg_id)
        if self.group_ws:
            try:
                self.group_ws.send(f"[DELETE]{msg_id}")
            except Exception:
                pass

    def _load_groups(self):
        self._async(api_get, self._fill_groups, "/groups/my", self.token)

    def _fill_groups(self, groups):
        if groups is None:
            # Échec réseau : on marque quand même pour ne pas bloquer le splash
            self._loaded_flags["groups"] = True
            self._maybe_close_splash()
            return
        # Supprime les anciennes GroupRow
        for gid, row in list(self.groups.items()):
            row.deleteLater()
        self.groups.clear()
        hidden = self._load_hidden_groups()
        pos = self.fvbox.count() - 1
        for g in groups:
            row = GroupRow(g)
            row.clicked.connect(self._select_group)
            row.hide_requested.connect(self._hide_group)
            self.groups[g["id"]] = row
            self.fvbox.insertWidget(pos, row)
            if g["id"] in hidden:
                row.setVisible(False)
            pos += 1
        self._loaded_flags["groups"] = True
        self._maybe_close_splash()

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
            self.inp.setPlaceholderText(tr("message"))
        else:
            self.inp.setPlaceholderText("🔒 Add as friend to send messages")

    def _async(self, fn, callback, *args):
        worker = ApiWorker(fn, *args)
        worker.done.connect(callback)
        worker.done.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        self._workers.append(worker)
        worker.start()

    def _periodic_refresh(self):
        # Évite de surcharger : ne rafraîchit pas si la fenêtre est en arrière-plan
        if not self.isActiveWindow():
            return
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
        # Stacked: page 0 = main app, page 1 = settings
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        root = QWidget()
        main = QHBoxLayout(root); main.setContentsMargins(0, 0, 0, 0); main.setSpacing(0)

        # ── Sidebar ──────────────────────────────────────
        sidebar = QWidget(); sidebar.setFixedWidth(320)
        sidebar.setStyleSheet(f"background:{C['sidebar']};")
        sb = QVBoxLayout(sidebar); sb.setContentsMargins(0, 0, 0, 0); sb.setSpacing(0)

        hdr = QWidget(); hdr.setFixedHeight(58)
        hdr.setStyleSheet(f"background:{C['sidebar']};")
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
        lbl = QLabel(tr("chats"))
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{C['text3']};letter-spacing:1px;")
        chl2.addWidget(lbl);
        chl2.addStretch()
        new_group_btn = QPushButton(tr("new_group"))
        new_group_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        new_group_btn.setStyleSheet(f"""QPushButton{{background:transparent;color:{C['accent']};
                    border:none;font-size:11px;font-weight:bold;font-family:'Segoe UI';}}
                    QPushButton:hover{{color:{C['accent_h']};}}""")
        new_group_btn.clicked.connect(self._create_group)
        chl2.addWidget(new_group_btn)
        sb.addWidget(chats_hdr)

        # Barre de recherche locale (filtre amis + retrouve les masqués)
        search_wrap = QWidget()
        swl = QHBoxLayout(search_wrap); swl.setContentsMargins(10, 2, 10, 6); swl.setSpacing(0)
        self.sidebar_search = QLineEdit()
        self.sidebar_search.setPlaceholderText("🔍  " + tr("search_conversations"))
        self.sidebar_search.setFixedHeight(36)
        self.sidebar_search.setStyleSheet(f"""QLineEdit{{background:{C['card']};color:{C['text']};
            border:none;border-radius:9px;padding:0 12px;font-size:12px;font-family:'Segoe UI';}}""")
        self.sidebar_search.textChanged.connect(self._filter_sidebar)
        swl.addWidget(self.sidebar_search)
        sb.addWidget(search_wrap)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border:none;background:transparent;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.fbox = QWidget(); self.fbox.setStyleSheet("background:transparent;")
        self.fvbox = QVBoxLayout(self.fbox); self.fvbox.setContentsMargins(6, 2, 6, 4)
        self.fvbox.setSpacing(1); self.fvbox.addStretch()
        scroll.setWidget(self.fbox); sb.addWidget(scroll)
        main.addWidget(sidebar)

        # ── Chat ──────────────────────────────────────────
        chat = QWidget(); chat.setStyleSheet(f"background:{C['bg']};")
        cl = QVBoxLayout(chat); cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(0)

        self.ch_hdr = QWidget(); self.ch_hdr.setFixedHeight(58)
        self.ch_hdr.setStyleSheet(f"background:{C['sidebar']};")
        chl = QHBoxLayout(self.ch_hdr); chl.setContentsMargins(16, 0, 16, 0); chl.setSpacing(12)
        self.ch_av = Avatar("?", 38)
        self.ch_name = QLabel(tr("select_a_chat"))
        self.ch_name.setFont(QFont("Segoe UI", 14, QFont.Weight.DemiBold))
        self.ch_name.setStyleSheet(f"color:{C['text']};")
        self.ch_sub = QLabel(""); self.ch_sub.setFont(QFont("Segoe UI", 11))
        self.ch_sub.setStyleSheet(f"color:{C['text2']};")
        ncol = QVBoxLayout(); ncol.setSpacing(1); ncol.addWidget(self.ch_name); ncol.addWidget(self.ch_sub)
        self.call_btn = QPushButton("📞")
        self.call_btn.setFixedSize(36, 36)
        self.call_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.call_btn.setStyleSheet(f"""QPushButton{{background:transparent;color:{C['text2']};
                   border:none;border-radius:18px;font-size:16px;}}
                   QPushButton:hover{{background:{C['hover']};color:{C['green']};}}""")
        self.call_btn.setVisible(False)
        self.call_btn.clicked.connect(self._start_call)
        self.conv_settings_btn = QPushButton("⚙")
        self.conv_settings_btn.setFixedSize(36, 36)
        self.conv_settings_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.conv_settings_btn.setStyleSheet(f"""QPushButton{{background:transparent;color:{C['text2']};
                   border:none;border-radius:18px;font-size:16px;}}
                   QPushButton:hover{{background:{C['hover']};color:{C['text']};}}""")
        self.conv_settings_btn.setVisible(False)
        self.conv_settings_btn.clicked.connect(self._open_conv_settings)
        self.view_prof = btn(tr("view_profile"), C["card"], C["text2"], font_size=12)
        self.view_prof.setVisible(False);
        self.view_prof.clicked.connect(self._view_profile)
        chl.addWidget(self.ch_av);
        chl.addLayout(ncol);
        chl.addStretch()
        chl.addWidget(self.call_btn);
        chl.addWidget(self.conv_settings_btn);
        chl.addWidget(self.view_prof)
        cl.addWidget(self.ch_hdr)

        self.msg_scroll = QScrollArea(); self.msg_scroll.setWidgetResizable(True)
        self.msg_scroll.setStyleSheet(f"border:none;background:{C['bg']};")
        self.msg_box = QWidget(); self.msg_box.setStyleSheet(f"background:{C['bg']};")
        self.msg_vbox = QVBoxLayout(self.msg_box)
        self.msg_vbox.setContentsMargins(0, 12, 0, 8)
        self.msg_vbox.setSpacing(APPEARANCE.get("group_spacing", 2))
        self.msg_vbox.addStretch()
        self.msg_scroll.setWidget(self.msg_box); cl.addWidget(self.msg_scroll)

        # Bouton flottant "descendre en bas" (apparaît quand on remonte)
        self.scroll_btn = QPushButton("⬇", self.msg_scroll)
        self.scroll_btn.setFixedSize(40, 40)
        self.scroll_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.scroll_btn.setStyleSheet(f"""QPushButton{{background:{C['card']};color:{C['text']};
            border:none;border-radius:20px;font-size:16px;}}
            QPushButton:hover{{background:{C['accent']};color:white;}}""")
        self.scroll_btn.clicked.connect(lambda: self._scroll_bottom())
        self.scroll_btn.setVisible(False)
        self.msg_scroll.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)

        # État vide : placeholder accueillant quand aucune conversation n'est ouverte
        self.empty_state = QWidget()
        self.empty_state.setStyleSheet(f"background:{C['bg']};")
        es = QVBoxLayout(self.empty_state)
        es.setContentsMargins(40, 40, 40, 40); es.setSpacing(14)
        es.addStretch()
        es_logo = QLabel()
        if os.path.exists(LOGO_PATH):
            es_logo.setPixmap(make_rounded_logo(LOGO_PATH, 96))
            es_logo.setFixedSize(96, 96); es_logo.setScaledContents(True)
        es_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        es.addWidget(es_logo, alignment=Qt.AlignmentFlag.AlignHCenter)
        es_t = QLabel(tr("welcome_title"))
        es_t.setFont(QFont("Segoe UI", 19, QFont.Weight.Bold))
        es_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        es_t.setStyleSheet(f"color:{C['text']};")
        es.addWidget(es_t)
        es_sub = QLabel(tr("welcome_sub"))
        es_sub.setFont(QFont("Segoe UI", 12))
        es_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        es_sub.setStyleSheet(f"color:{C['text2']};")
        es.addWidget(es_sub)
        es.addStretch()
        cl.addWidget(self.empty_state)
        # Au démarrage, on montre l'état vide et on cache la zone de messages
        self.msg_scroll.setVisible(False)
        # Hide header avatar until a chat is open
        self.ch_av.setVisible(False)

        ibw = QWidget(); ibw.setFixedHeight(70)
        ibw.setStyleSheet(f"background:{C['sidebar']};")
        ib = QHBoxLayout(ibw); ib.setContentsMargins(14, 12, 14, 12); ib.setSpacing(8)
        attach_btn = QPushButton("＋")
        attach_btn.setFixedSize(42, 42)
        attach_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        attach_btn.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        attach_btn.setStyleSheet(f"""QPushButton{{background:{C['card']};color:{C['accent']};
                   border:none;border-radius:21px;padding:0px;}}
                   QPushButton:hover{{background:{C['hover']};}}""")
        attach_btn.clicked.connect(self._attach_menu)
        # Conteneur arrondi qui regroupe le champ + bouton emoji
        field_wrap = QWidget()
        field_wrap.setStyleSheet(f"background:{C['bg']};border-radius:21px;")
        field_wrap.setFixedHeight(44)
        fw = QHBoxLayout(field_wrap); fw.setContentsMargins(6, 0, 6, 0); fw.setSpacing(4)
        self.inp = QLineEdit(); self.inp.setPlaceholderText(tr("message"))
        self.inp.setStyleSheet(f"""QLineEdit{{background:transparent;color:{C['text']};
            border:none;padding:0 12px;font-size:13px;font-family:'Segoe UI';}}""")
        self.inp.returnPressed.connect(self.send_message)
        self.inp.textChanged.connect(self._on_typing)
        self.inp.textChanged.connect(self._check_mention_trigger)
        emoji_btn = QPushButton("😊"); emoji_btn.setFixedSize(34, 34)
        emoji_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        emoji_btn.setStyleSheet(f"""QPushButton{{background:transparent;border:none;
            border-radius:17px;font-size:16px;}}
            QPushButton:hover{{background:{C['hover']};}}""")
        emoji_btn.clicked.connect(self._open_emoji)
        gif_btn = QPushButton("GIF"); gif_btn.setFixedSize(38, 34)
        gif_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        gif_btn.setStyleSheet(f"""QPushButton{{background:transparent;color:{C['text2']};
            border:none;border-radius:8px;font-size:11px;font-weight:bold;}}
            QPushButton:hover{{background:{C['hover']};color:{C['text']};}}""")
        gif_btn.clicked.connect(self._open_gif)
        fw.addWidget(self.inp); fw.addWidget(emoji_btn); fw.addWidget(gif_btn)
        sbtn = QPushButton("➤"); sbtn.setFixedSize(44, 44)
        sbtn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        sbtn.setStyleSheet(f"""QPushButton{{background:{C['accent']};color:white;
            border:none;border-radius:22px;font-size:17px;}}
            QPushButton:hover{{background:{C['accent_h']};}}""")
        sbtn.clicked.connect(self.send_message)
        ib.addWidget(attach_btn)
        ib.addWidget(field_wrap); ib.addWidget(sbtn); cl.addWidget(ibw)
        main.addWidget(chat)

        # Add main app as page 0; settings page built lazily
        self.stack.addWidget(root)
        self.settings_page = None

    # ── Friends ───────────────────────────────────────────
    def _load_friends(self):
        self._async(api_get, lambda f: self._load_friends_from_data(f) if f else None, "/friends/list", self.token)

    def _filter_sidebar(self, text):
        q = text.strip().lower()
        hidden = self._load_hidden()
        for uid, row in self.friends.items():
            if not q:
                # Champ vide : on respecte le masquage
                row.setVisible(uid not in hidden)
            else:
                # Recherche : montre tout ce qui correspond (même masqué)
                name = row.uname.lower()
                match = q in name
                row.setVisible(match)
        # Filtre aussi les groupes par leur nom
        for gid, row in self.groups.items():
            if not q:
                row.setVisible(True)
            else:
                gname = getattr(row, "gname", "").lower()
                row.setVisible(q in gname)

    def _hidden_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "hidden_convs.json")

    def _load_hidden(self):
        try:
            p = self._hidden_path()
            if os.path.exists(p):
                with open(p) as f:
                    return set(json.load(f))
        except Exception:
            pass
        return set()

    def _save_hidden(self, hidden_set):
        try:
            with open(self._hidden_path(), "w") as f:
                json.dump(list(hidden_set), f)
        except Exception as ex:
            print("hidden save error:", ex)

    def _hide_conversation(self, uid):
        hidden = self._load_hidden()
        hidden.add(uid)
        self._save_hidden(hidden)
        # Retire la ligne de la liste
        if uid in self.friends:
            self.friends[uid].setVisible(False)

    def _unhide_conversation(self, uid):
        hidden = self._load_hidden()
        hidden.discard(uid)
        self._save_hidden(hidden)
        if uid in self.friends:
            self.friends[uid].setVisible(True)

    # ── Masquage des groupes ──────────────────────────────
    def _hidden_groups_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "hidden_groups.json")

    def _load_hidden_groups(self):
        try:
            p = self._hidden_groups_path()
            if os.path.exists(p):
                with open(p) as f:
                    return set(json.load(f))
        except Exception:
            pass
        return set()

    def _save_hidden_groups(self, hidden_set):
        try:
            with open(self._hidden_groups_path(), "w") as f:
                json.dump(list(hidden_set), f)
        except Exception as ex:
            print("hidden groups save error:", ex)

    def _hide_group(self, gid):
        hidden = self._load_hidden_groups()
        hidden.add(gid)
        self._save_hidden_groups(hidden)
        if gid in self.groups:
            self.groups[gid].setVisible(False)

    def _unhide_group(self, gid):
        hidden = self._load_hidden_groups()
        hidden.discard(gid)
        self._save_hidden_groups(hidden)
        if gid in self.groups:
            self.groups[gid].setVisible(True)

    def _load_friends_from_data(self, friends):
        # Supprime uniquement les FriendRow existantes
        for uid, row in list(self.friends.items()):
            row.deleteLater()
        self.friends.clear()
        hidden = self._load_hidden()
        pos = self.fvbox.count() - 1
        for u in friends:
            row = FriendRow(u)
            row.clicked.connect(self._select)
            row.hide_requested.connect(self._hide_conversation)
            self.friends[u["id"]] = row
            self.fvbox.insertWidget(pos, row)
            if u["id"] in hidden:
                row.setVisible(False)
            pos += 1
        self._loaded_flags["friends"] = True
        self._maybe_close_splash()

    def _maybe_close_splash(self):
        # Ferme le splash quand amis ET groupes sont chargés
        if self._splash is None:
            return
        if self._loaded_flags.get("friends") and self._loaded_flags.get("groups"):
            sp = self._splash
            self._splash = None
            sp.stop()

    def _force_close_splash(self):
        if self._splash is not None:
            sp = self._splash
            self._splash = None
            sp.stop()

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

    def _show_chat_area(self):
        # Bascule de l'état vide vers la zone de messages
        if hasattr(self, "empty_state"):
            self.empty_state.setVisible(False)
        self.msg_scroll.setVisible(True)

    def _select(self, uid):
        prev = self.recv_id
        if prev and prev != uid:
            self._clear_ephemeral(prev)
        self._show_chat_area()
        self.current_group_id = None
        # Ferme proprement le WS de groupe (pour ne pas déclencher de faux kick)
        if self.group_ws:
            old = self.group_ws
            self.group_ws = None
            try: old.close()
            except Exception: pass
        self._hide_typing()
        for w in self.friends.values(): w.set_selected(False)
        if uid in self.friends: self.friends[uid].set_selected(True)
        self.recv_id = uid
        # Si la conv était masquée, on la ré-affiche (on l'ouvre donc on la veut visible)
        hidden = self._load_hidden()
        if uid in hidden:
            self._unhide_conversation(uid)
        self._async(api_post, lambda r: None, "/chat/mark_read", self.token, {"other_user_id": uid})
        if uid in self.friends:
            self.friends[uid].clear_unread()
        self.view_prof.setText(tr("view_profile"))
        self.view_prof.setVisible(True)
        self.conv_settings_btn.setVisible(True)
        self.call_btn.setVisible(True)
        self.ch_av.setVisible(True)
        # Vide les messages tout de suite
        while self.msg_vbox.count() > 1:
            it = self.msg_vbox.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        # Charge le profil et l'historique en arrière-plan
        self._async(api_get, lambda u: self._fill_header(u, uid), f"/auth/users/{uid}", self.token)
        self._async(api_get, lambda m: self._fill_history(m, uid), f"/chat/conversation/{uid}", self.token)

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

    def _make_bubble(self, content, outgoing, msg_id=None, edited=False):
        import datetime
        now = format_msg_time()
        b = Bubble(content, outgoing, msg_id=msg_id, edited=edited, time_str=now)
        if msg_id is not None:
            self._bubbles[msg_id] = b
            if outgoing:
                b.edit_requested.connect(self._on_edit_requested)
                b.delete_requested.connect(self._on_delete_requested)
        return b

    def _assign_sent_id(self, new_id):
        b = getattr(self, "_pending_sent_bubble", None)
        if b is None:
            return
        b.msg_id = new_id
        self._bubbles[new_id] = b
        # Active le clic-droit edit/delete maintenant qu'on a l'id
        b.lbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        try:
            b.lbl.customContextMenuRequested.disconnect()
        except Exception:
            pass
        b.lbl.customContextMenuRequested.connect(b._menu)
        b.edit_requested.connect(self._on_edit_requested)
        b.delete_requested.connect(self._on_delete_requested)
        self._pending_sent_bubble = None

    def _on_edit_requested(self, msg_id, current_text):
        new_text, ok = QInputDialog.getText(self, "Edit message", "New text:", text=current_text)
        if ok and new_text.strip() and new_text != current_text:
            self._async(api_post, lambda r: None, "/chat/edit_message", self.token,
                        {"message_id": msg_id, "new_content": new_text.strip()})
            # Applique localement tout de suite
            if msg_id in self._bubbles:
                self._bubbles[msg_id].mark_edited(new_text.strip())

    def _on_delete_requested(self, msg_id):
        self._async(api_post, lambda r: None, "/chat/delete_message", self.token,
                    {"message_id": msg_id})
        self._apply_delete(msg_id)

    def _apply_edit(self, msg_id, new_text):
        if msg_id in self._bubbles:
            self._bubbles[msg_id].mark_edited(new_text)

    def _apply_delete(self, msg_id):
        if msg_id in self._bubbles:
            w = self._bubbles[msg_id]
            w.deleteLater()
            del self._bubbles[msg_id]

    def _fill_history(self, msgs, uid):
        if msgs is None or uid != self.recv_id: return
        self._bubbles.clear()
        pos = 0  # position d'insertion (avant le stretch final)
        prev_date = None
        for m in msgs:
            content = m["content"]
            outgoing = m["sender_id"] == self.user["id"]
            # Séparateur de date si le jour change
            created = m.get("created_at")
            if created:
                dlabel = format_date_label(created)
                if dlabel and dlabel != prev_date:
                    self.msg_vbox.insertWidget(pos, make_date_separator(dlabel))
                    pos += 1
                    prev_date = dlabel
            if content.startswith("[GROUP_INVITE]"):
                gid = int(content.replace("[GROUP_INVITE]", ""))
                card = InviteCard(self.token, self.user, gid)
                card.joined.connect(self._load_groups)
                self.msg_vbox.insertWidget(pos, card)
            elif content.startswith("[FILE]"):
                w = self._parse_attachment(content, outgoing)
                if w: self.msg_vbox.insertWidget(pos, w)
            else:
                self.msg_vbox.insertWidget(pos, self._make_bubble(
                    content, outgoing, msg_id=m.get("id"), edited=m.get("edited", False)))
            pos += 1
        self._scroll_bottom()

    #websocket
    def _connect_ws(self):
        def on_error(ws, error):
            print("WS ERROR:", error)

        def on_close(ws, code, reason):
            print(f"WS CLOSED: code={code}, reason={reason}")

        def on_open(ws):
            print("WS CONNECTED ✓")

        self.ws = websocket.WebSocketApp(
            f"{WS_URL}/chat/ws/{self.user['id']}",
            on_message=lambda ws, msg: self.sig_msg.emit(msg, 0),
            on_error=on_error,
            on_close=on_close,
            on_open=on_open)
        threading.Thread(target=self.ws.run_forever, daemon=True).start()

    def _on_incoming(self, raw, _):
        # Accusé de lecture
        if raw.startswith("[READ]"):
            reader_id = int(raw.replace("[READ]", ""))
            if reader_id == self.recv_id and self.last_status_label:
                self._set_msg_status("✓✓ Read", read=True)
            return
        # Message modifié
        if raw.startswith("[EDIT]"):
            payload = raw[len("[EDIT]"):]
            parts = payload.split("|", 1)
            if len(parts) == 2:
                try:
                    mid = int(parts[0])
                    self.sig_msg_edited.emit(mid, parts[1])
                except ValueError:
                    pass
            return
        # Message supprimé
        if raw.startswith("[DELETE]"):
            try:
                mid = int(raw[len("[DELETE]"):])
                self.sig_msg_deleted.emit(mid)
            except ValueError:
                pass
            return
        # ID du message qu'on vient d'envoyer (pour edit/delete immédiat)
        if raw.startswith("[NEWID]"):
            payload = raw[len("[NEWID]"):]
            parts = payload.split("|", 1)
            if len(parts) == 2:
                try:
                    new_id = int(parts[0])
                    self._assign_sent_id(new_id)
                except ValueError:
                    pass
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
                if w:
                    self.msg_vbox.insertWidget(self.msg_vbox.count() - 1, w)
                    self._fade_in(w)
            else:
                b = self._make_bubble(message, False)
                self.msg_vbox.insertWidget(self.msg_vbox.count() - 1, b)
                self._fade_in(b)
            self._scroll_bottom()
            if sender_id in self.friends:
                preview = "📎 Attachment" if message.startswith("[FILE]") else message
                self.friends[sender_id].set_preview(preview)
        else:
            # Message d'un autre chat → badge non-lu + notif
            if sender_id in self.friends:
                # Si la conv était masquée, on la ré-affiche
                if not self.friends[sender_id].isVisible():
                    self._unhide_conversation(sender_id)
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
                bubble = self._make_group_bubble(text, True, self.current_group_id,
                                                 msg_id=None, raw_content=text)
                self._pending_group_bubble = bubble  # pour recevoir son id
                self.msg_vbox.insertWidget(self.msg_vbox.count() - 1, bubble)
                self._fade_in(bubble)
                self.inp.clear()
                self._scroll_bottom()
                # Met à jour l'aperçu du groupe dans la liste
                if self.current_group_id in self.groups:
                    self.groups[self.current_group_id].set_preview(f"You: {text}")
            except Exception as ex:
                print("group send error:", ex)
            return
        # Mode ami (DM)
        if not self.recv_id or not self.ws: return
        try:
            self.ws.send(f"{self.recv_id}:{text}")
            bubble = self._make_bubble(text, True, msg_id=None)
            self._pending_sent_bubble = bubble  # pour recevoir son id via [NEWID]
            self.msg_vbox.insertWidget(self.msg_vbox.count() - 1, bubble)
            self._fade_in(bubble)
            self.inp.clear()
            self._set_msg_status("✓ Delivered")
            self._scroll_bottom()
            # Met à jour l'aperçu DM dans la liste
            if self.recv_id in self.friends:
                self.friends[self.recv_id].set_preview(f"You: {text}")
        except Exception as ex:
            print("send error:", ex)

    def _fade_in(self, widget, duration=180):
        # Petit fondu d'apparition pour les nouveaux messages
        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        eff = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        # Garde une référence pour éviter le garbage collection
        if not hasattr(self, "_fade_anims"):
            self._fade_anims = []
        self._fade_anims.append(anim)
        if len(self._fade_anims) > 30:
            self._fade_anims = self._fade_anims[-15:]

    def _on_scroll_changed(self, value):
        bar = self.msg_scroll.verticalScrollBar()
        # Affiche le bouton si on est remonté de plus de 200px du bas
        far_from_bottom = (bar.maximum() - value) > 200
        self.scroll_btn.setVisible(far_from_bottom)
        self._reposition_scroll_btn()

    def _reposition_scroll_btn(self):
        # Coin bas-droit de la zone de messages
        if hasattr(self, "scroll_btn"):
            m = 16
            x = self.msg_scroll.width() - self.scroll_btn.width() - m
            y = self.msg_scroll.height() - self.scroll_btn.height() - m
            self.scroll_btn.move(x, y)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._reposition_scroll_btn()

    def _scroll_bottom(self, animate=True):
        def do_scroll():
            bar = self.msg_scroll.verticalScrollBar()
            target = bar.maximum()
            if not animate or abs(target - bar.value()) < 4:
                bar.setValue(target)
                return
            # Animation douce vers le bas
            anim = QPropertyAnimation(bar, b"value", self)
            anim.setDuration(220)
            anim.setStartValue(bar.value())
            anim.setEndValue(target)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.start()
            self._scroll_anim = anim  # garde une référence pour éviter le GC
        QTimer.singleShot(60, do_scroll)

    # ── Dialogs ───────────────────────────────────────────
    def _open_settings(self):
        # Build the settings page fresh each time (reflects current data)
        if self.settings_page is not None:
            self.stack.removeWidget(self.settings_page)
            self.settings_page.deleteLater()
        self.settings_page = SettingsPage(self.token, self.user, self)
        self.settings_page.profile_updated.connect(self._on_updated)
        self.settings_page.notif_changed.connect(self._set_notifications)
        self.settings_page.closed.connect(self._close_settings)
        self.settings_page.logout_requested.connect(self._logout)
        self.settings_page.account_deleted.connect(self._on_account_deleted)
        self.stack.addWidget(self.settings_page)
        self.stack.setCurrentWidget(self.settings_page)

    def _on_account_deleted(self):
        # Compte supprimé → efface le token et retourne au login
        clear_token()
        QMessageBox.information(self, "Account deleted", "Your account has been deleted.")
        self._logout()

    def _close_settings(self):
        self.stack.setCurrentIndex(0)

    def _logout(self):
        # Oublie le token sauvegardé (plus d'auto-login)
        clear_token()
        # Ferme proprement et relance l'écran de login
        try:
            if self.ws: self.ws.close()
        except Exception:
            pass
        try:
            if getattr(self, "group_ws", None): self.group_ws.close()
        except Exception:
            pass
        global _RELOGIN
        _RELOGIN = True
        self.close()
        QApplication.instance().quit()

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
            gid = self.current_group_id
            self._async(api_get, lambda g: self._open_group_profile(g) if g else None,
                        f"/groups/{gid}", self.token)
            return
        # Sinon profil d'ami
        if self.recv_id is None: return
        self._async(api_get, lambda u: self._show_profile(u) if u else None,
                    f"/auth/users/{self.recv_id}", self.token)

    def _open_group_profile(self, g):
        d = GroupProfileDialog(self.token, self.user, g, self)
        d.changed.connect(self._load_groups)
        d.left.connect(self._on_left_group)
        d.exec()

    def _on_left_group(self):
        self.current_group_id = None
        self.ch_name.setText(tr("select_a_chat"))
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
    # Boucle login → app → (logout) → login
    # Au tout premier passage, on tente une connexion auto avec le token sauvegardé.
    _try_auto = True
    while True:
        _RELOGIN = False
        token = None
        user = None
        if _try_auto:
            _try_auto = False
            saved = load_saved_token()
            if saved:
                me = api_get("/auth/me", saved)
                if me:  # token encore valide
                    token = saved
                    user = me
        # Si pas d'auto-login réussi, on affiche l'écran de connexion
        if token is None:
            login = LoginDialog()
            if login.exec() != QDialog.DialogCode.Accepted:
                break
            token = login.token
            user = login.user
        # Écran de chargement pendant la construction de l'app
        splash = SplashScreen()
        splash.show()
        app.processEvents()  # affiche le splash immédiatement
        win = VeloApp(token, user, splash=splash)
        win.show()
        # Le splash se ferme tout seul quand les données sont chargées
        app.exec()
        if not _RELOGIN:
            break
    sys.exit(0)

