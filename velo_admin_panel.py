# -*- coding: utf-8 -*-
"""
Velo Admin Panel — outil d'administration séparé pour Velo.
Réservé aux comptes superuser (is_superuser=True).

Fonctions :
  - Connexion admin (login Velo, vérifie is_superuser)
  - Bascule Users / Groups
  - Liste + recherche (par id ou nom)
  - Users  : Bannir (blacklist IP + suppression) ou Supprimer
  - Groups : Supprimer un groupe

Lancement : py velo_admin_panel.py
"""

import sys
import requests

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QFrame, QMessageBox, QDialog, QStackedWidget,
    QInputDialog, QComboBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

# ── Configuration ─────────────────────────────────────────
BASE_URL = "https://velo-n1cd.onrender.com"

# ── Palette ───────────────────────────────────────────────
C = {
    "bg": "#0e1621", "panel": "#17212b", "card": "#222e3b", "card_h": "#283544",
    "hover": "#202b36", "divider": "#0b131c", "accent": "#5288c1", "accent_h": "#5e93cc",
    "text": "#ffffff", "text2": "#8295a6", "text3": "#5a6b7a",
    "green": "#54c75e", "red": "#e15c5c", "orange": "#e8a14b",
}


def H(token):
    return {"Authorization": f"Bearer {token}"}


# ── Worker réseau asynchrone ──────────────────────────────
class Worker(QThread):
    done = pyqtSignal(object, object)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn(), None)
        except Exception as e:
            self.done.emit(None, str(e))


def field():
    return f"""QLineEdit {{background:{C['card']};color:{C['text']};border:none;
        border-radius:10px;padding:0 14px;font-size:13px;font-family:'Segoe UI';}}
        QLineEdit:focus {{background:{C['card_h']};}}"""


def make_btn(text, bg, fg="white", font_size=13, bold=True, hover=None):
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    weight = "bold" if bold else "normal"
    hv = hover or bg
    b.setStyleSheet(f"""QPushButton {{background:{bg};color:{fg};border:none;
        border-radius:10px;font-size:{font_size}px;font-weight:{weight};
        font-family:'Segoe UI';padding:11px 16px;}}
        QPushButton:hover {{background:{hv};}}
        QPushButton:disabled {{background:{C['card']};color:{C['text3']};}}""")
    return b


# ── Écran de connexion ────────────────────────────────────
class AdminLogin(QDialog):
    """Connexion admin par mot de passe.

    Le mot de passe est comparé côté serveur à la variable d'environnement
    ADMIN_PASSWORD (réglée sur Render, comme l'accès à la base). En cas de
    succès, l'API renvoie un token JWT d'un compte superuser utilisé ensuite
    pour tous les appels /admin.
    """
    def __init__(self):
        super().__init__()
        self.token = None
        self.user = None
        self.setWindowTitle("Velo Admin — Login")
        self.setFixedSize(400, 380)
        self.setStyleSheet(f"background:{C['bg']};")
        self._build()

    def _build(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(36, 36, 36, 36)
        lo.addStretch()

        title = QLabel("Velo Admin")
        title.setFont(QFont("Segoe UI", 25, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color:{C['text']};")
        lo.addWidget(title)

        sub = QLabel("Administration panel")
        sub.setFont(QFont("Segoe UI", 11))
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color:{C['text2']};")
        lo.addWidget(sub)
        lo.addSpacing(26)

        self.pw_input = QLineEdit()
        self.pw_input.setPlaceholderText("Admin password")
        self.pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw_input.setFixedHeight(46)
        self.pw_input.setStyleSheet(field())
        self.pw_input.returnPressed.connect(self._login)
        lo.addWidget(self.pw_input)
        lo.addSpacing(8)

        self.err = QLabel("")
        self.err.setFont(QFont("Segoe UI", 10))
        self.err.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.err.setStyleSheet(f"color:{C['red']};")
        self.err.setWordWrap(True)
        lo.addWidget(self.err)
        lo.addSpacing(6)

        self.login_btn = make_btn("Log in", C["accent"], font_size=14, hover=C["accent_h"])
        self.login_btn.clicked.connect(self._login)
        lo.addWidget(self.login_btn)
        lo.addStretch()

    # ── Actions ───────────────────────────────────────────
    def _login(self):
        password = self.pw_input.text()
        if not password:
            self.err.setText("Enter the admin password.")
            return
        self.err.setText("Signing in…")
        self.login_btn.setEnabled(False)

        def do():
            r = requests.post(f"{BASE_URL}/admin/login",
                              json={"password": password}, timeout=15)
            if r.status_code == 401:
                raise Exception("Incorrect password.")
            if r.status_code != 200:
                raise Exception("Login failed.")
            data = r.json()
            return data["access_token"], data["user"]

        self._w = Worker(do)
        self._w.done.connect(self._on_login)
        self._w.start()

    def _on_login(self, result, error):
        self.login_btn.setEnabled(True)
        if error:
            self.err.setText(error)
            return
        token, user = result
        if not user.get("is_superuser"):
            self.err.setText("This account is not an administrator.")
            return
        self.token = token
        self.user = user
        self.accept()


# ── Carte cliquable (user ou group) ───────────────────────
class Card(QFrame):
    clicked = pyqtSignal(object)

    def __init__(self, data, kind):
        super().__init__()
        self.data = data
        self.kind = kind
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(62)
        lo = QHBoxLayout(self)
        lo.setContentsMargins(14, 0, 14, 0)
        lo.setSpacing(12)

        idl = QLabel(f"#{data['id']}")
        idl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        idl.setStyleSheet(f"color:{C['accent']};background:transparent;")
        idl.setFixedWidth(46)
        lo.addWidget(idl)

        col = QVBoxLayout()
        col.setSpacing(1)
        col.setContentsMargins(0, 0, 0, 0)
        if kind == "user":
            primary = data["username"] + ("  ★" if data.get("is_superuser") else "")
            secondary = data.get("phone", "") or "—"
        else:
            lock = "🔒 " if data.get("is_private") else ""
            primary = lock + data["name"]
            secondary = f"{data.get('members', 0)} member(s)"
        self.name = QLabel(primary)
        self.name.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        star = data.get("is_superuser") if kind == "user" else False
        self.name.setStyleSheet(f"color:{C['orange'] if star else C['text']};background:transparent;")
        col.addWidget(self.name)
        self.sub = QLabel(secondary)
        self.sub.setFont(QFont("Segoe UI", 10))
        self.sub.setStyleSheet(f"color:{C['text2']};background:transparent;")
        col.addWidget(self.sub)
        lo.addLayout(col)
        lo.addStretch()

        if kind == "user":
            ip = QLabel(data.get("ip") or "—")
            ip.setFont(QFont("Consolas", 10))
            ip.setStyleSheet(f"color:{C['text3']};background:transparent;")
            lo.addWidget(ip)
        self._refresh()

    def _refresh(self):
        bg = C["card_h"] if self._selected else C["card"]
        border = C["accent"] if self._selected else "transparent"
        self.setStyleSheet(f"""Card {{background:{bg};border-radius:11px;
            border:1.5px solid {border};}}""")

    def set_selected(self, v):
        self._selected = v
        self._refresh()

    def enterEvent(self, e):
        if not self._selected:
            self.setStyleSheet(f"""Card {{background:{C['card_h']};border-radius:11px;
                border:1.5px solid transparent;}}""")

    def leaveEvent(self, e):
        self._refresh()

    def mousePressEvent(self, e):
        self.clicked.emit(self.data)


# ── Fenêtre principale ────────────────────────────────────
class AdminPanel(QWidget):
    def __init__(self, token, user):
        super().__init__()
        self.token = token
        self.user = user
        self.mode = "user"
        self.items = []
        self.cards = []
        self.selected = None
        self.setWindowTitle("Velo Admin Panel")
        self.resize(940, 660)
        self.setStyleSheet(f"background:{C['bg']};")
        self._build()
        self._load()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Colonne gauche ──
        left = QWidget()
        left.setStyleSheet(f"background:{C['panel']};")
        left.setFixedWidth(470)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(18, 18, 18, 18)
        ll.setSpacing(12)

        # Bandeau outils (Stats + Banned IPs)
        tools_row = QHBoxLayout()
        tools_row.setSpacing(8)
        stats_btn = make_btn("📊 Stats", C["card"], C["text"], font_size=12, hover=C["card_h"])
        stats_btn.clicked.connect(self._show_stats)
        tools_row.addWidget(stats_btn)
        bans_btn = make_btn("🚫 Banned IPs", C["card"], C["text"], font_size=12, hover=C["card_h"])
        bans_btn.clicked.connect(self._show_banned_ips)
        tools_row.addWidget(bans_btn)
        ll.addLayout(tools_row)

        tools_row2 = QHBoxLayout()
        tools_row2.setSpacing(8)
        reports_btn = make_btn("🚩 Reports", C["card"], C["text"], font_size=12, hover=C["card_h"])
        reports_btn.clicked.connect(self._show_reports)
        tools_row2.addWidget(reports_btn)
        searchmsg_btn = make_btn("🔎 Search messages", C["card"], C["text"], font_size=12, hover=C["card_h"])
        searchmsg_btn.clicked.connect(self._show_search_messages)
        tools_row2.addWidget(searchmsg_btn)
        ll.addLayout(tools_row2)

        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(8)
        self.users_tab = QPushButton("Users")
        self.groups_tab = QPushButton("Groups")
        for b in (self.users_tab, self.groups_tab):
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(40)
        self.users_tab.setChecked(True)
        self.users_tab.clicked.connect(lambda: self._switch_mode("user"))
        self.groups_tab.clicked.connect(lambda: self._switch_mode("group"))
        toggle_row.addWidget(self.users_tab)
        toggle_row.addWidget(self.groups_tab)
        ll.addLayout(toggle_row)
        self._refresh_tabs()

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by id or name…")
        self.search.setFixedHeight(42)
        self.search.setStyleSheet(field())
        self.search.returnPressed.connect(self._load)
        search_row.addWidget(self.search)
        sb = make_btn("Search", C["accent"], font_size=12, hover=C["accent_h"])
        sb.clicked.connect(self._load)
        search_row.addWidget(sb)
        ll.addLayout(search_row)

        self.count_label = QLabel("")
        self.count_label.setFont(QFont("Segoe UI", 10))
        self.count_label.setStyleSheet(f"color:{C['text2']};")
        ll.addWidget(self.count_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(f"""
            QScrollArea {{border:none;background:transparent;}}
            QScrollBar:vertical {{background:transparent;width:8px;margin:0;}}
            QScrollBar::handle:vertical {{background:{C['card_h']};border-radius:4px;min-height:30px;}}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{height:0;}}
        """)
        self.scroll.verticalScrollBar().setSingleStep(20)
        self.list_container = QWidget()
        self.list_container.setStyleSheet("background:transparent;")
        self.list_vbox = QVBoxLayout(self.list_container)
        self.list_vbox.setContentsMargins(0, 0, 6, 0)
        self.list_vbox.setSpacing(8)
        self.list_vbox.addStretch()
        self.scroll.setWidget(self.list_container)
        ll.addWidget(self.scroll)
        root.addWidget(left)

        # ── Colonne droite ──
        right = QWidget()
        right.setStyleSheet(f"background:{C['bg']};")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(30, 30, 30, 30)
        rl.setSpacing(16)

        self.detail_stack = QStackedWidget()
        rl.addWidget(self.detail_stack)

        empty = QWidget()
        el = QVBoxLayout(empty)
        el.addStretch()
        ei = QLabel("Select an item")
        ei.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        ei.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ei.setStyleSheet(f"color:{C['text3']};")
        el.addWidget(ei)
        es = QLabel("Click an entry on the left to view details and actions.")
        es.setFont(QFont("Segoe UI", 11))
        es.setAlignment(Qt.AlignmentFlag.AlignCenter)
        es.setStyleSheet(f"color:{C['text3']};")
        el.addWidget(es)
        el.addStretch()
        self.detail_stack.addWidget(empty)

        detail = QWidget()
        dl = QVBoxLayout(detail)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(14)
        self.d_title = QLabel("")
        self.d_title.setFont(QFont("Segoe UI", 23, QFont.Weight.Bold))
        self.d_title.setStyleSheet(f"color:{C['text']};")
        self.d_title.setWordWrap(True)
        dl.addWidget(self.d_title)

        self.info_card = QWidget()
        self.info_card.setStyleSheet(f"background:{C['card']};border-radius:12px;")
        self.ic = QVBoxLayout(self.info_card)
        self.ic.setContentsMargins(18, 16, 18, 16)
        self.ic.setSpacing(11)
        dl.addWidget(self.info_card)
        dl.addStretch()

        self.actions_label = QLabel("ACTIONS")
        self.actions_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.actions_label.setStyleSheet(f"color:{C['text2']};letter-spacing:1px;")
        dl.addWidget(self.actions_label)

        self.delete_btn = make_btn("Delete", C["card"], C["orange"], hover=C["card_h"])
        self.delete_btn.clicked.connect(self._delete)
        dl.addWidget(self.delete_btn)

        self.messages_btn = make_btn("View recent messages", C["card"], C["text"], hover=C["card_h"])
        self.messages_btn.clicked.connect(self._show_user_messages)
        dl.addWidget(self.messages_btn)

        self.promote_btn = make_btn("Promote to admin", C["card"], C["accent"], hover=C["card_h"])
        self.promote_btn.clicked.connect(self._toggle_admin)
        dl.addWidget(self.promote_btn)

        self.warn_btn = make_btn("⚠ Add warning", C["card"], C["orange"], hover=C["card_h"])
        self.warn_btn.clicked.connect(self._add_warning)
        dl.addWidget(self.warn_btn)

        self.note_btn = make_btn("📝 Add admin note", C["card"], C["text2"], hover=C["card_h"])
        self.note_btn.clicked.connect(self._add_note)
        dl.addWidget(self.note_btn)

        self.ban_btn = make_btn("Ban (blacklist IP + delete)", C["red"], hover="#c94f4f")
        self.ban_btn.clicked.connect(self._ban)
        dl.addWidget(self.ban_btn)

        self.detail_stack.addWidget(detail)
        root.addWidget(right, 1)

    def _refresh_tabs(self):
        for b, active in ((self.users_tab, self.mode == "user"),
                          (self.groups_tab, self.mode == "group")):
            if active:
                b.setStyleSheet(f"""QPushButton {{background:{C['accent']};color:white;
                    border:none;border-radius:10px;font-size:13px;font-weight:bold;
                    font-family:'Segoe UI';}}""")
            else:
                b.setStyleSheet(f"""QPushButton {{background:{C['card']};color:{C['text2']};
                    border:none;border-radius:10px;font-size:13px;font-weight:bold;
                    font-family:'Segoe UI';}}
                    QPushButton:hover {{background:{C['card_h']};}}""")

    def _switch_mode(self, mode):
        self.mode = mode
        self.users_tab.setChecked(mode == "user")
        self.groups_tab.setChecked(mode == "group")
        self._refresh_tabs()
        self.search.clear()
        self.detail_stack.setCurrentIndex(0)
        self.selected = None
        self._load()

    def _load(self):
        q = self.search.text().strip()
        self.count_label.setText("Loading…")
        endpoint = "/admin/users" if self.mode == "user" else "/admin/groups"

        def do():
            r = requests.get(f"{BASE_URL}{endpoint}", params={"q": q},
                             headers=H(self.token), timeout=20)
            if r.status_code != 200:
                raise Exception(f"Error {r.status_code}: {r.text[:80]}")
            return r.json()

        self._w = Worker(do)
        self._w.done.connect(self._on_loaded)
        self._w.start()

    def _on_loaded(self, result, error):
        for c in self.cards:
            c.setParent(None)
        self.cards = []
        if error:
            self.count_label.setText(error)
            return
        self.items = result
        for d in result:
            card = Card(d, self.mode)
            card.clicked.connect(self._on_select)
            self.list_vbox.insertWidget(self.list_vbox.count() - 1, card)
            self.cards.append(card)
        label = "account(s)" if self.mode == "user" else "group(s)"
        self.count_label.setText(f"{len(result)} {label}")

    def _on_select(self, data):
        self.selected = data
        for c in self.cards:
            c.set_selected(c.data["id"] == data["id"])
        # Nettoie l'ancienne section membres (si on venait d'un groupe)
        self._clear_members_section()
        while self.ic.count():
            item = self.ic.takeAt(0)
            if item.layout():
                self._clear_layout(item.layout())
        # Détecte le type depuis les données (users ont 'username', groupes ont 'name')
        is_user = "username" in data
        if is_user:
            self.d_title.setText(data["username"] + ("  ★" if data.get("is_superuser") else ""))
            self._info("User ID", f"#{data['id']}")
            self._info("Phone", data.get("phone", "—"))
            self._info("IP address", data.get("ip") or "—")
            created = data.get("created_at", "")
            self._info("Created", created.split("T")[0] if created else "—")
            self._info("Role", "Administrator ★" if data.get("is_superuser") else "User")
            is_admin = data.get("is_superuser", False)
            self.delete_btn.setText("Delete account")
            self.ban_btn.setVisible(True)
            self.messages_btn.setVisible(True)
            self.promote_btn.setVisible(True)
            self.promote_btn.setText("Demote to user" if is_admin else "Promote to admin")
            self.warn_btn.setVisible(True)
            self.note_btn.setVisible(True)
            self.delete_btn.setEnabled(not is_admin)
            self.ban_btn.setEnabled(not is_admin)
            # Charge les comptes avec la même IP
            self._load_alt_accounts(data["id"])
            # Charge warnings + notes
            self._load_warnings_notes(data["id"])
        else:
            lock = "🔒 " if data.get("is_private") else ""
            self.d_title.setText(lock + data["name"])
            self._info("Group ID", f"#{data['id']}")
            self._info("Name", data.get("name", "—"))
            self._info("Privacy", "Private" if data.get("is_private") else "Public")
            self._info("Members", str(data.get("members", 0)))
            self.delete_btn.setText("Delete group")
            self.ban_btn.setVisible(False)
            self.messages_btn.setVisible(False)
            self.promote_btn.setVisible(False)
            self.warn_btn.setVisible(False)
            self.note_btn.setVisible(False)
            self.delete_btn.setEnabled(True)
            # Charge la liste des membres cliquables
            self._load_group_members(data["id"])
        self.detail_stack.setCurrentIndex(1)

    def _load_group_members(self, group_id):
        # Nettoie l'ancienne liste de membres si présente
        self._clear_members_section()

        def do():
            r = requests.get(f"{BASE_URL}/admin/group_members",
                             params={"group_id": group_id},
                             headers=H(self.token), timeout=20)
            if r.status_code != 200:
                raise Exception(f"Error {r.status_code}")
            return r.json()

        self._mw = Worker(do)
        self._mw.done.connect(self._on_members_loaded)
        self._mw.start()

    def _clear_members_section(self):
        # Retire le bloc membres précédent (label + cartes)
        if hasattr(self, "_member_widgets"):
            for w in self._member_widgets:
                w.setParent(None)
        self._member_widgets = []

    def _on_members_loaded(self, result, error):
        if error or not result:
            return
        if not hasattr(self, "_member_widgets"):
            self._member_widgets = []
        # Insère un label "MEMBERS" + les cartes, avant le stretch de la page détail
        detail_layout = self.detail_stack.widget(1).layout()
        # Position d'insertion : juste après la info_card (index 2, avant le stretch)
        lbl = QLabel(f"MEMBERS ({len(result)})")
        lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{C['text2']};letter-spacing:1px;")
        detail_layout.insertWidget(2, lbl)
        self._member_widgets.append(lbl)
        # Zone scrollable pour les membres
        mscroll = QScrollArea()
        mscroll.setWidgetResizable(True)
        mscroll.setFixedHeight(min(220, 50 * len(result) + 10))
        mscroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        mscroll.setStyleSheet(f"""
            QScrollArea {{border:none;background:transparent;}}
            QScrollBar:vertical {{background:transparent;width:8px;}}
            QScrollBar::handle:vertical {{background:{C['card_h']};border-radius:4px;}}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{height:0;}}
        """)
        cont = QWidget()
        cont.setStyleSheet("background:transparent;")
        cv = QVBoxLayout(cont)
        cv.setContentsMargins(0, 0, 6, 0)
        cv.setSpacing(6)
        for u in result:
            row = self._member_row(u)
            cv.addWidget(row)
        cv.addStretch()
        mscroll.setWidget(cont)
        detail_layout.insertWidget(3, mscroll)
        self._member_widgets.append(mscroll)

    def _member_row(self, user):
        row = QFrame()
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setFixedHeight(44)
        row.setStyleSheet(f"""QFrame {{background:{C['card']};border-radius:9px;}}
            QFrame:hover {{background:{C['card_h']};}}""")
        lo = QHBoxLayout(row)
        lo.setContentsMargins(12, 0, 12, 0)
        lo.setSpacing(10)
        name = QLabel(user["username"] + ("  ★" if user.get("is_superuser") else ""))
        name.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        star = user.get("is_superuser")
        name.setStyleSheet(f"color:{C['orange'] if star else C['text']};background:transparent;")
        lo.addWidget(name)
        lo.addStretch()
        role = QLabel(user.get("role", "member"))
        role.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        rc = C["orange"] if user.get("role") == "owner" else (
            C["accent"] if user.get("role") == "admin" else C["text3"])
        role.setStyleSheet(f"color:{rc};background:transparent;")
        lo.addWidget(role)
        # Clic → ouvre la vue user de ce membre
        row.mousePressEvent = lambda e, u=user: self._open_member(u)
        return row

    def _open_member(self, user):
        # Affiche ce membre comme un user (le type est détecté par _on_select)
        self._on_select(user)

    def _clear_layout(self, layout):
        while layout.count():
            it = layout.takeAt(0)
            if it.widget():
                it.widget().setParent(None)
            elif it.layout():
                self._clear_layout(it.layout())

    def _info(self, label, value):
        row = QHBoxLayout()
        row.setSpacing(10)
        l = QLabel(label)
        l.setFont(QFont("Segoe UI", 11))
        l.setStyleSheet(f"color:{C['text2']};background:transparent;")
        l.setFixedWidth(110)
        row.addWidget(l)
        v = QLabel(value)
        v.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        v.setStyleSheet(f"color:{C['text']};background:transparent;")
        v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        v.setWordWrap(True)
        row.addWidget(v)
        row.addStretch()
        self.ic.addLayout(row)

    def _delete(self):
        d = self.selected
        if not d:
            return
        is_user = "username" in d
        if is_user:
            msg = (f"Permanently delete account #{d['id']} ({d['username']})?\n\n"
                   "This does NOT ban their IP.")
            path = "/admin/delete_user"
            payload = {"user_id": d["id"]}
        else:
            msg = (f"Permanently delete group #{d['id']} ({d['name']})?\n\n"
                   "All its messages and members will be removed.")
            path = "/admin/delete_group"
            payload = {"group_id": d["id"]}
        if QMessageBox.question(self, "Confirm delete", msg,
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) \
                != QMessageBox.StandardButton.Yes:
            return
        self._do_action(path, payload, "deleted")

    def _ban(self):
        d = self.selected
        if not d or "username" not in d:
            return
        msg = (f"Ban {d['username']} (#{d['id']})?\n\n"
               f"This will blacklist their IP ({d.get('ip') or 'unknown'}) "
               "and permanently delete the account.")
        if QMessageBox.question(self, "Confirm ban", msg,
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) \
                != QMessageBox.StandardButton.Yes:
            return
        self._do_action("/admin/ban_user", {"user_id": d["id"]}, "banned")

    def _do_action(self, path, payload, word):
        def do():
            r = requests.post(f"{BASE_URL}{path}", json=payload,
                              headers=H(self.token), timeout=20)
            if r.status_code != 200:
                raise Exception(f"Error {r.status_code}: {r.text[:120]}")
            return r.json()

        self._w = Worker(do)
        self._w.done.connect(lambda res, err: self._on_action_done(res, err, word))
        self._w.start()

    def _on_action_done(self, result, error, word):
        if error:
            QMessageBox.warning(self, "Action failed", error)
            return
        QMessageBox.information(self, "Done", f"Successfully {word}.")
        self.detail_stack.setCurrentIndex(0)
        self.selected = None
        self._load()

    # ── Statistiques ──
    def _show_stats(self):
        def do():
            r = requests.get(f"{BASE_URL}/admin/stats", headers=H(self.token), timeout=20)
            if r.status_code != 200:
                raise Exception(f"Error {r.status_code}")
            return r.json()
        self._sw = Worker(do)
        self._sw.done.connect(self._on_stats)
        self._sw.start()

    def _on_stats(self, result, error):
        if error:
            QMessageBox.warning(self, "Stats", error)
            return
        s = result
        dlg = QDialog(self)
        dlg.setWindowTitle("Statistics")
        dlg.setFixedSize(320, 300)
        dlg.setStyleSheet(f"background:{C['bg']};")
        lo = QVBoxLayout(dlg)
        lo.setContentsMargins(24, 24, 24, 24)
        lo.setSpacing(10)
        title = QLabel("📊 Statistics")
        title.setFont(QFont("Segoe UI", 17, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{C['text']};")
        lo.addWidget(title)
        lo.addSpacing(6)
        rows = [("Users", s["users"]), ("Groups", s["groups"]),
                ("Direct messages", s["dm_messages"]),
                ("Group messages", s["group_messages"]),
                ("Banned IPs", s["banned_ips"])]
        for label, val in rows:
            row = QHBoxLayout()
            l = QLabel(label)
            l.setFont(QFont("Segoe UI", 12))
            l.setStyleSheet(f"color:{C['text2']};")
            row.addWidget(l)
            row.addStretch()
            v = QLabel(str(val))
            v.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
            v.setStyleSheet(f"color:{C['accent']};")
            row.addWidget(v)
            lo.addLayout(row)
        lo.addStretch()
        dlg.exec()

    # ── IP bannies ──
    def _show_banned_ips(self):
        def do():
            r = requests.get(f"{BASE_URL}/admin/banned_ips", headers=H(self.token), timeout=20)
            if r.status_code != 200:
                raise Exception(f"Error {r.status_code}")
            return r.json()
        self._bw = Worker(do)
        self._bw.done.connect(self._on_banned_ips)
        self._bw.start()

    def _on_banned_ips(self, result, error):
        if error:
            QMessageBox.warning(self, "Banned IPs", error)
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Banned IPs")
        dlg.setFixedSize(420, 460)
        dlg.setStyleSheet(f"background:{C['bg']};")
        lo = QVBoxLayout(dlg)
        lo.setContentsMargins(20, 20, 20, 20)
        lo.setSpacing(10)
        title = QLabel(f"🚫 Banned IPs ({len(result)})")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{C['text']};")
        lo.addWidget(title)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border:none;background:transparent;")
        cont = QWidget(); cont.setStyleSheet("background:transparent;")
        cv = QVBoxLayout(cont); cv.setSpacing(6); cv.setContentsMargins(0, 0, 6, 0)
        if not result:
            empty = QLabel("No banned IPs.")
            empty.setStyleSheet(f"color:{C['text3']};")
            cv.addWidget(empty)
        for b in result:
            row = QFrame()
            row.setStyleSheet(f"background:{C['card']};border-radius:9px;")
            row.setFixedHeight(54)
            rl = QHBoxLayout(row); rl.setContentsMargins(12, 0, 10, 0)
            col = QVBoxLayout(); col.setSpacing(1)
            ip = QLabel(b["ip"])
            ip.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
            ip.setStyleSheet(f"color:{C['text']};background:transparent;")
            col.addWidget(ip)
            if b.get("reason"):
                rs = QLabel(b["reason"])
                rs.setFont(QFont("Segoe UI", 9))
                rs.setStyleSheet(f"color:{C['text3']};background:transparent;")
                col.addWidget(rs)
            rl.addLayout(col)
            rl.addStretch()
            unban = make_btn("Unban", C["accent"], font_size=11, hover=C["accent_h"])
            unban.clicked.connect(lambda _, ip=b["ip"], d=dlg: self._unban_ip(ip, d))
            rl.addWidget(unban)
            cv.addWidget(row)
        cv.addStretch()
        scroll.setWidget(cont)
        lo.addWidget(scroll)
        dlg.exec()

    def _unban_ip(self, ip, dlg):
        def do():
            r = requests.post(f"{BASE_URL}/admin/unban_ip", json={"ip": ip},
                              headers=H(self.token), timeout=20)
            if r.status_code != 200:
                raise Exception(f"Error {r.status_code}")
            return r.json()
        self._uw = Worker(do)
        self._uw.done.connect(lambda res, err: self._on_unban(res, err, dlg))
        self._uw.start()

    def _on_unban(self, result, error, dlg):
        if error:
            QMessageBox.warning(self, "Unban", error)
            return
        dlg.accept()
        QMessageBox.information(self, "Done", "IP unbanned.")
        self._show_banned_ips()  # rafraîchit la liste

    # ── Alt accounts (même IP) ──
    def _load_alt_accounts(self, user_id):
        def do():
            r = requests.get(f"{BASE_URL}/admin/alt_accounts",
                             params={"user_id": user_id},
                             headers=H(self.token), timeout=20)
            if r.status_code != 200:
                raise Exception(f"Error {r.status_code}")
            return r.json()
        self._aw = Worker(do)
        self._aw.done.connect(self._on_alt_accounts)
        self._aw.start()

    def _on_alt_accounts(self, result, error):
        if error or not result:
            return
        detail_layout = self.detail_stack.widget(1).layout()
        lbl = QLabel(f"⚠ POSSIBLE ALT ACCOUNTS ({len(result)})")
        lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{C['orange']};letter-spacing:1px;")
        detail_layout.insertWidget(2, lbl)
        self._member_widgets.append(lbl)
        cont = QWidget(); cont.setStyleSheet("background:transparent;")
        cv = QVBoxLayout(cont); cv.setContentsMargins(0, 0, 0, 0); cv.setSpacing(6)
        for u in result:
            row = self._member_row(u)
            cv.addWidget(row)
        detail_layout.insertWidget(3, cont)
        self._member_widgets.append(cont)

    # ── Promote / Demote ──
    def _toggle_admin(self):
        d = self.selected
        if not d or "username" not in d:
            return
        make = not d.get("is_superuser", False)
        word = "promote to admin" if make else "demote to user"
        if QMessageBox.question(self, "Confirm", f"Are you sure you want to {word} {d['username']}?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) \
                != QMessageBox.StandardButton.Yes:
            return
        def do():
            r = requests.post(f"{BASE_URL}/admin/set_admin",
                              json={"user_id": d["id"], "make_admin": make},
                              headers=H(self.token), timeout=20)
            if r.status_code != 200:
                raise Exception(f"Error {r.status_code}")
            return r.json()
        self._pw = Worker(do)
        self._pw.done.connect(self._on_toggle_admin)
        self._pw.start()

    def _on_toggle_admin(self, result, error):
        if error:
            QMessageBox.warning(self, "Admin", error)
            return
        QMessageBox.information(self, "Done", "Role updated.")
        self._load()
        self.detail_stack.setCurrentIndex(0)

    # ── Voir les messages d'un user ──
    def _show_user_messages(self):
        d = self.selected
        if not d or "username" not in d:
            return
        uid = d["id"]
        def do():
            r = requests.get(f"{BASE_URL}/admin/user_messages",
                             params={"user_id": uid},
                             headers=H(self.token), timeout=20)
            if r.status_code != 200:
                raise Exception(f"Error {r.status_code}")
            return r.json()
        self._mw2 = Worker(do)
        self._mw2.done.connect(lambda res, err: self._on_user_messages(res, err, d))
        self._mw2.start()

    def _on_user_messages(self, result, error, user):
        if error:
            QMessageBox.warning(self, "Messages", error)
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Messages — {user['username']}")
        dlg.setFixedSize(480, 520)
        dlg.setStyleSheet(f"background:{C['bg']};")
        lo = QVBoxLayout(dlg)
        lo.setContentsMargins(20, 20, 20, 20); lo.setSpacing(10)
        title = QLabel(f"Last messages — {user['username']}")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{C['text']};")
        lo.addWidget(title)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border:none;background:transparent;")
        cont = QWidget(); cont.setStyleSheet("background:transparent;")
        cv = QVBoxLayout(cont); cv.setSpacing(6); cv.setContentsMargins(0, 0, 6, 0)
        if not result:
            empty = QLabel("No messages.")
            empty.setStyleSheet(f"color:{C['text3']};")
            cv.addWidget(empty)
        for m in result:
            row = QFrame()
            row.setStyleSheet(f"background:{C['card']};border-radius:9px;")
            rl = QVBoxLayout(row); rl.setContentsMargins(12, 8, 12, 8); rl.setSpacing(3)
            head = QHBoxLayout()
            badge = QLabel(m["type"])
            badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            bc = C["accent"] if m["type"] == "DM" else C["orange"]
            badge.setStyleSheet(f"color:white;background:{bc};border-radius:5px;padding:1px 7px;")
            head.addWidget(badge)
            head.addStretch()
            at = QLabel((m.get("at") or "").replace("T", " ")[:16])
            at.setFont(QFont("Segoe UI", 8))
            at.setStyleSheet(f"color:{C['text3']};background:transparent;")
            head.addWidget(at)
            rl.addLayout(head)
            content = QLabel(m["content"])
            content.setWordWrap(True)
            content.setFont(QFont("Segoe UI", 11))
            content.setStyleSheet(f"color:{C['text']};background:transparent;")
            rl.addWidget(content)
            cv.addWidget(row)
        cv.addStretch()
        scroll.setWidget(cont)
        lo.addWidget(scroll)
        dlg.exec()


    # ── Recherche dans tous les messages ──
    def _show_search_messages(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Search messages")
        dlg.setFixedSize(560, 560)
        dlg.setStyleSheet(f"background:{C['bg']};")
        lo = QVBoxLayout(dlg)
        lo.setContentsMargins(20, 20, 20, 20)
        lo.setSpacing(10)
        title = QLabel("🔎 Search all messages")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{C['text']};")
        lo.addWidget(title)
        srow = QHBoxLayout()
        inp = QLineEdit()
        inp.setPlaceholderText("Keyword (min 2 chars)…")
        inp.setFixedHeight(42)
        inp.setStyleSheet(field())
        srow.addWidget(inp)
        go = make_btn("Search", C["accent"], font_size=12, hover=C["accent_h"])
        srow.addWidget(go)
        lo.addLayout(srow)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border:none;background:transparent;")
        cont = QWidget(); cont.setStyleSheet("background:transparent;")
        cv = QVBoxLayout(cont); cv.setSpacing(6); cv.setContentsMargins(0, 0, 6, 0)
        cv.addStretch()
        scroll.setWidget(cont)
        lo.addWidget(scroll)

        def run_search():
            q = inp.text().strip()
            if len(q) < 2:
                return
            def do():
                r = requests.get(f"{BASE_URL}/admin/search_messages",
                                 params={"q": q}, headers=H(self.token), timeout=20)
                if r.status_code != 200:
                    raise Exception(f"Error {r.status_code}")
                return r.json()
            self._smw = Worker(do)
            self._smw.done.connect(lambda res, err: fill(res, err))
            self._smw.start()

        def fill(result, error):
            # Vide
            while cv.count() > 1:
                it = cv.takeAt(0)
                if it.widget():
                    it.widget().setParent(None)
            if error:
                return
            for m in result:
                row = QFrame()
                row.setStyleSheet(f"background:{C['card']};border-radius:9px;")
                rl = QVBoxLayout(row); rl.setContentsMargins(12, 8, 12, 8); rl.setSpacing(3)
                head = QHBoxLayout()
                badge = QLabel(m["type"])
                badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                bc = C["accent"] if m["type"] == "DM" else C["orange"]
                badge.setStyleSheet(f"color:white;background:{bc};border-radius:5px;padding:1px 7px;")
                head.addWidget(badge)
                sender = QLabel(f"by {m['sender']}")
                sender.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                sender.setStyleSheet(f"color:{C['text2']};background:transparent;")
                head.addWidget(sender)
                head.addStretch()
                at = QLabel((m.get("at") or "").replace("T", " ")[:16])
                at.setFont(QFont("Segoe UI", 8))
                at.setStyleSheet(f"color:{C['text3']};background:transparent;")
                head.addWidget(at)
                rl.addLayout(head)
                content = QLabel(m["content"])
                content.setWordWrap(True)
                content.setFont(QFont("Segoe UI", 11))
                content.setStyleSheet(f"color:{C['text']};background:transparent;")
                rl.addWidget(content)
                del_btn = make_btn("Delete this message", C["bg"], C["red"], font_size=10, hover=C["hover"])
                del_btn.clicked.connect(
                    lambda _, mid=m["msg_id"], k=m["kind"], rw=row: self._delete_one_message(mid, k, rw))
                rl.addWidget(del_btn)
                cv.insertWidget(cv.count() - 1, row)

        go.clicked.connect(run_search)
        inp.returnPressed.connect(run_search)
        dlg.exec()

    def _delete_one_message(self, msg_id, kind, row_widget):
        def do():
            r = requests.post(f"{BASE_URL}/admin/delete_message",
                              json={"msg_id": msg_id, "kind": kind},
                              headers=H(self.token), timeout=20)
            if r.status_code != 200:
                raise Exception(f"Error {r.status_code}")
            return r.json()
        self._dmw = Worker(do)
        self._dmw.done.connect(lambda res, err: row_widget.setParent(None) if not err else
                               QMessageBox.warning(self, "Delete", err))
        self._dmw.start()

    # ── Reports (signalements) ──
    def _show_reports(self):
        def do():
            r = requests.get(f"{BASE_URL}/admin/reports", headers=H(self.token), timeout=20)
            if r.status_code != 200:
                raise Exception(f"Error {r.status_code}")
            return r.json()
        self._rw = Worker(do)
        self._rw.done.connect(self._on_reports)
        self._rw.start()

    def _on_reports(self, result, error):
        if error:
            QMessageBox.warning(self, "Reports", error)
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Reports")
        dlg.setFixedSize(520, 560)
        dlg.setStyleSheet(f"background:{C['bg']};")
        lo = QVBoxLayout(dlg)
        lo.setContentsMargins(20, 20, 20, 20); lo.setSpacing(10)
        pending = [r for r in result if r["status"] == "pending"]
        title = QLabel(f"🚩 Reports ({len(pending)} pending)")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{C['text']};")
        lo.addWidget(title)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border:none;background:transparent;")
        cont = QWidget(); cont.setStyleSheet("background:transparent;")
        cv = QVBoxLayout(cont); cv.setSpacing(6); cv.setContentsMargins(0, 0, 6, 0)
        if not result:
            empty = QLabel("No reports.")
            empty.setStyleSheet(f"color:{C['text3']};")
            cv.addWidget(empty)
        for r in result:
            row = QFrame()
            done = r["status"] == "resolved"
            row.setStyleSheet(f"background:{C['card']};border-radius:9px;"
                              + (f"" if not done else ""))
            rl = QVBoxLayout(row); rl.setContentsMargins(12, 8, 12, 8); rl.setSpacing(4)
            head = QHBoxLayout()
            who = QLabel(f"{r['reporter']}  →  {r['reported']}")
            who.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            who.setStyleSheet(f"color:{C['text'] if not done else C['text3']};background:transparent;")
            head.addWidget(who)
            head.addStretch()
            st = QLabel("✓ resolved" if done else "pending")
            st.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            st.setStyleSheet(f"color:{C['green'] if done else C['orange']};background:transparent;")
            head.addWidget(st)
            rl.addLayout(head)
            reason = QLabel(r["reason"])
            reason.setWordWrap(True)
            reason.setFont(QFont("Segoe UI", 10))
            reason.setStyleSheet(f"color:{C['text2']};background:transparent;")
            rl.addWidget(reason)
            if not done:
                resolve = make_btn("Mark resolved", C["bg"], C["green"], font_size=10, hover=C["hover"])
                resolve.clicked.connect(
                    lambda _, rid=r["id"], d=dlg: self._resolve_report(rid, d))
                rl.addWidget(resolve)
            cv.addWidget(row)
        cv.addStretch()
        scroll.setWidget(cont)
        lo.addWidget(scroll)
        dlg.exec()

    def _resolve_report(self, report_id, dlg):
        def do():
            r = requests.post(f"{BASE_URL}/admin/resolve_report",
                              json={"report_id": report_id},
                              headers=H(self.token), timeout=20)
            if r.status_code != 200:
                raise Exception(f"Error {r.status_code}")
            return r.json()
        self._rrw = Worker(do)
        self._rrw.done.connect(lambda res, err: (dlg.accept(), self._show_reports()) if not err
                               else QMessageBox.warning(self, "Resolve", err))
        self._rrw.start()

    # ── Warnings + Notes (fiche user) ──
    def _add_warning(self):
        d = self.selected
        if not d or "username" not in d:
            return
        reason, ok = QInputDialog.getText(self, "Add warning",
            f"Warning reason for {d['username']}:")
        if not ok or not reason.strip():
            return
        # Demande la gravité
        sev, ok2 = QInputDialog.getItem(self, "Severity", "Severity level:",
            ["warning", "severe"], 0, False)
        if not ok2:
            return
        def do():
            r = requests.post(f"{BASE_URL}/admin/add_warning",
                              json={"user_id": d["id"], "reason": reason.strip(), "severity": sev},
                              headers=H(self.token), timeout=20)
            if r.status_code != 200:
                raise Exception(f"Error {r.status_code}")
            return r.json()
        self._ww = Worker(do)
        self._ww.done.connect(lambda res, err: self._after_warn_note(err, d["id"]))
        self._ww.start()

    def _add_note(self):
        d = self.selected
        if not d or "username" not in d:
            return
        note, ok = QInputDialog.getText(self, "Add admin note",
            f"Private note about {d['username']}:")
        if not ok or not note.strip():
            return
        def do():
            r = requests.post(f"{BASE_URL}/admin/add_note",
                              json={"user_id": d["id"], "note": note.strip()},
                              headers=H(self.token), timeout=20)
            if r.status_code != 200:
                raise Exception(f"Error {r.status_code}")
            return r.json()
        self._nw = Worker(do)
        self._nw.done.connect(lambda res, err: self._after_warn_note(err, d["id"]))
        self._nw.start()

    def _after_warn_note(self, error, user_id):
        if error:
            QMessageBox.warning(self, "Error", error)
            return
        # Recharge les sections warnings/notes
        self._load_warnings_notes(user_id)

    def _load_warnings_notes(self, user_id):
        def do():
            w = requests.get(f"{BASE_URL}/admin/warnings", params={"user_id": user_id},
                             headers=H(self.token), timeout=20)
            n = requests.get(f"{BASE_URL}/admin/notes", params={"user_id": user_id},
                             headers=H(self.token), timeout=20)
            return (w.json() if w.status_code == 200 else [],
                    n.json() if n.status_code == 200 else [])
        self._wnw = Worker(do)
        self._wnw.done.connect(self._on_warnings_notes)
        self._wnw.start()

    def _on_warnings_notes(self, result, error):
        if error or not result:
            return
        warnings, notes = result
        detail_layout = self.detail_stack.widget(1).layout()
        # Warnings
        if warnings:
            lbl = QLabel(f"⚠ WARNINGS ({len(warnings)})")
            lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            lbl.setStyleSheet(f"color:{C['orange']};letter-spacing:1px;")
            detail_layout.insertWidget(2, lbl)
            self._member_widgets.append(lbl)
            for w in warnings:
                row = self._warn_note_row(w["reason"],
                    f"{w['severity']} · {(w.get('at') or '')[:10]}",
                    C["orange"] if w["severity"] == "severe" else C["text2"], None)
                detail_layout.insertWidget(3, row)
                self._member_widgets.append(row)
        # Notes
        if notes:
            lbl2 = QLabel(f"📝 ADMIN NOTES ({len(notes)})")
            lbl2.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            lbl2.setStyleSheet(f"color:{C['text2']};letter-spacing:1px;")
            detail_layout.insertWidget(detail_layout.count() - 5, lbl2)
            self._member_widgets.append(lbl2)
            for n in notes:
                row = self._warn_note_row(n["note"], (n.get("at") or "")[:10], C["text3"], None)
                detail_layout.insertWidget(detail_layout.count() - 5, row)
                self._member_widgets.append(row)

    def _warn_note_row(self, text, meta, color, on_delete):
        row = QFrame()
        row.setStyleSheet(f"background:{C['card']};border-radius:9px;")
        rl = QVBoxLayout(row); rl.setContentsMargins(12, 7, 12, 7); rl.setSpacing(2)
        t = QLabel(text)
        t.setWordWrap(True)
        t.setFont(QFont("Segoe UI", 10))
        t.setStyleSheet(f"color:{C['text']};background:transparent;")
        rl.addWidget(t)
        m = QLabel(meta)
        m.setFont(QFont("Segoe UI", 8))
        m.setStyleSheet(f"color:{color};background:transparent;")
        rl.addWidget(m)
        return row


def main():
    app = QApplication(sys.argv)
    login = AdminLogin()
    if login.exec() != QDialog.DialogCode.Accepted:
        sys.exit(0)
    panel = AdminPanel(login.token, login.user)
    panel.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()