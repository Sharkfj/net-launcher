"""Friends: requests, online status, invites, play together."""

from __future__ import annotations

import time

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QLineEdit, QMenu, QScrollArea, QWidget

from netlauncher import localpacks, skin
from netlauncher.friends import NotConfigured
from netlauncher.net import HttpError
from netlauncher.ui import anim, jobs
from netlauncher.ui.pages.common import hbox, label, plural, vbox
from netlauncher.ui.pages.home import _error_text
from netlauncher.ui.skinview import face
from netlauncher.ui.widgets import AccentButton, Avatar, GhostButton, GlassCard

POLL_MS = 15000


def _ago(ts: float) -> str:
    d = max(0, time.time() - ts)
    if d < 3600:
        m = max(1, int(d // 60))
        return f"{m} мин назад"
    if d < 86400:
        return f"{int(d // 3600)} ч назад"
    n = int(d // 86400)
    return f"{n} {plural(n, 'день', 'дня', 'дней')} назад"


def status_text(f: dict) -> str:
    if not f.get("online"):
        return "Не в сети" + (f", был {_ago(f['last_seen'])}" if f.get("last_seen") else "")
    if f.get("status") == "playing":
        text = f"Играет в {f.get('pack') or 'Minecraft'}"
        return text + (f" на {f['server']}" if f.get("server") else "")
    return "В сети, в лаунчере"


class FriendRow(GlassCard):
    join = Signal(dict)
    invite = Signal(str)
    remove = Signal(str)

    def __init__(self, f: dict, parent=None):
        super().__init__(parent, radius=14)
        self.f, self.name = f, f["name"]
        row = hbox(self, (14, 10, 12, 10), 12)
        self.avatar = Avatar(38)
        self.avatar.set_name(self.name)
        row.addWidget(self.avatar)
        col = vbox(None, (0, 0, 0, 0), 1)
        col.addWidget(label(self.name, 11, 580))
        self.status = label(status_text(f), 9.5, role="muted" if f.get("online") else "faint")
        col.addWidget(self.status)
        row.addLayout(col, 1)
        self.join_btn = AccentButton("Играть вместе")
        self.join_btn.clicked.connect(lambda: self.join.emit(self.f))
        self.join_btn.setVisible(bool(f.get("online") and f.get("status") == "playing" and f.get("server")))
        row.addWidget(self.join_btn)
        self.invite_btn = GhostButton("Пригласить")
        self.invite_btn.clicked.connect(lambda: self.invite.emit(self.name))
        row.addWidget(self.invite_btn)
        more = GhostButton("Ещё")
        more.clicked.connect(lambda: self._menu(more))
        row.addWidget(more)

    def _menu(self, btn):
        m = QMenu(self)
        m.addAction("Удалить из друзей", lambda: self.remove.emit(self.name))
        m.exec(btn.mapToGlobal(btn.rect().bottomLeft()))


class RequestRow(GlassCard):
    def __init__(self, name: str, parent=None):
        super().__init__(parent, radius=14)
        self.name = name
        row = hbox(self, (16, 10, 12, 10), 10)
        row.addWidget(label(f"{name} хочет добавить тебя в друзья", 10.5, 520), 1)
        self.accept_btn = AccentButton("Принять")
        self.decline_btn = GhostButton("Отклонить")
        row.addWidget(self.accept_btn)
        row.addWidget(self.decline_btn)


class InviteRow(GlassCard):
    def __init__(self, inv: dict, parent=None):
        super().__init__(parent, radius=14)
        self.inv = inv
        row = hbox(self, (16, 10, 12, 10), 10)
        self.text = label(f"{inv['from']} зовёт играть в {inv.get('pack') or 'Minecraft'}", 10.5, 560)
        row.addWidget(self.text, 1)
        self.play_btn = AccentButton("Играть")
        self.later_btn = GhostButton("Позже")
        row.addWidget(self.play_btn)
        row.addWidget(self.later_btn)


class FriendsPage(QWidget):
    def __init__(self, ctx, window=None, parent=None):
        super().__init__(parent)
        self.ctx, self.window = ctx, window
        self.rows: list[FriendRow] = []
        self.request_rows: list[RequestRow] = []
        self.invite_rows: list[InviteRow] = []
        self._client = None
        self._client_url = None
        outer = vbox(self, (8, 4, 0, 0), 12)
        outer.addWidget(label("Друзья", 22, 650, display=True))
        self.subtitle = label("", 10.5, role="muted")
        outer.addWidget(self.subtitle)
        self.notice = label("", 10.5, role="muted", wrap=True)
        outer.addWidget(self.notice)
        add = hbox(None, (0, 0, 0, 0), 8)
        self.add_name = QLineEdit()
        self.add_name.setPlaceholderText("Ник на Ely.by")
        self.add_name.setMinimumWidth(280)
        self.add_name.returnPressed.connect(self.add_friend)
        self.add_btn = AccentButton("Добавить в друзья")
        self.add_btn.clicked.connect(self.add_friend)
        add.addWidget(self.add_name)
        add.addWidget(self.add_btn)
        add.addStretch(1)
        self.add_row = QWidget()
        self.add_row.setLayout(add)
        outer.addWidget(self.add_row)
        inner = QWidget()
        self.list = vbox(inner, (0, 0, 6, 0), 8)
        self.outgoing = label("", 9.5, role="faint", wrap=True)
        self.list.addWidget(self.outgoing)
        self.list.addStretch(1)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(inner)
        sa.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(sa, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self._faces: dict[str, object] = {}
        self._update_notice()

    # ---------- client ----------
    def client(self):
        url = self.ctx.friends_url()
        if self._client is None or self._client_url != url:
            self._client, self._client_url = self.ctx.friends(), url
        return self._client

    def _update_notice(self) -> bool:
        configured = bool(self.ctx.friends_url())
        self.add_row.setVisible(configured)
        if not configured:
            self.notice.setText("Сервер друзей не подключён. Его адрес задаёт автор сборки в каталоге; "
                                "если тебе дали адрес, впиши его в настройках, раздел «Лаунчер».")
        elif self.ctx.accounts.load() is None:
            self.notice.setText("Войди через Ely.by на главной, чтобы видеть друзей.")
            return False
        else:
            self.notice.setText("")
        return configured

    def on_shown(self) -> None:
        self.tick()

    def tick(self) -> None:
        if not self._update_notice():
            return
        status, pack, server = getattr(self.window, "game_status", ("launcher", "", ""))
        cl = self.client()
        jobs.run(lambda progress: cl.presence(status, pack, server), on_done=self._show, on_error=self._failed)

    def _run(self, fn) -> None:
        jobs.run(lambda progress: fn(self.client()), on_done=self._show, on_error=self._failed)

    def _failed(self, e: BaseException) -> None:
        if isinstance(e, NotConfigured):
            self._update_notice()
        elif isinstance(e, HttpError) and e.status == 401:
            self.notice.setText("Ely.by не подтвердил вход. Выйди из аккаунта и войди снова.")
        else:
            self.notice.setText("Сервер друзей не отвечает: " + _error_text(e))

    # ---------- view ----------
    def _clear(self, rows: list) -> None:
        for r in rows:
            r.setParent(None)
            r.deleteLater()
        rows.clear()

    def _show(self, st: dict) -> None:
        if not isinstance(st, dict):
            return
        self.notice.setText("")
        friends = st.get("friends") or []
        online = sum(1 for f in friends if f.get("online"))
        self.subtitle.setText(f"{online} в сети" if friends else "Пока никого. Добавь друга по нику на Ely.by.")
        for rows in (self.invite_rows, self.request_rows, self.rows):
            self._clear(rows)
        pos = 0
        for inv in st.get("invites") or []:
            r = InviteRow(inv)
            r.play_btn.clicked.connect(lambda _=False, inv=inv: self._play(inv.get("pack", ""), inv.get("server", ""),
                                                                            inv["from"]))
            r.later_btn.clicked.connect(lambda _=False, n=inv["from"]: self._run(lambda c: c.dismiss(n)))
            self.list.insertWidget(pos, r)
            pos += 1
            self.invite_rows.append(r)
        for name in st.get("incoming") or []:
            r = RequestRow(name)
            r.accept_btn.clicked.connect(lambda _=False, n=name: self._run(lambda c: c.accept(n)))
            r.decline_btn.clicked.connect(lambda _=False, n=name: self._run(lambda c: c.decline(n)))
            self.list.insertWidget(pos, r)
            pos += 1
            self.request_rows.append(r)
        for f in sorted(friends, key=lambda f: (not f.get("online"), f["name"].lower())):
            r = FriendRow(f)
            r.join.connect(lambda f: self._play(f.get("pack", ""), f.get("server", "")))
            r.invite.connect(self._invite)
            r.remove.connect(lambda n: self._run(lambda c: c.remove(n)))
            self.list.insertWidget(pos, r)
            pos += 1
            self.rows.append(r)
            self._face(r)
        out = st.get("outgoing") or []
        self.outgoing.setText("Ждут ответа: " + ", ".join(out) if out else "")
        self.outgoing.setVisible(bool(out))

    def _face(self, row: FriendRow) -> None:
        name = row.name
        if name in self._faces:
            row.avatar.set_face(self._faces[name])
            return

        def done(sk):
            if sk is None:
                return
            self._faces[name] = face(sk.png)
            import shiboken6
            if shiboken6.isValid(row):
                row.avatar.set_face(self._faces[name])

        jobs.run(lambda progress: skin.fetch(self.ctx.http, name, self.ctx.lay.cache), on_done=done,
                 on_error=lambda e: None)

    # ---------- actions ----------
    def add_friend(self) -> None:
        name = self.add_name.text().strip()
        if not name:
            return
        self.add_name.clear()
        self.notice.setText(f"Заявка отправлена: {name}")
        self._run(lambda c: c.request(name))

    def _invite(self, name: str) -> None:
        from netlauncher.ui.pages import common
        lp = common.current_pack(self.ctx)
        pack = lp.name if lp else ""
        server = lp.server if lp else ""
        self.notice.setText(f"Приглашение отправлено: {name}")
        self._run(lambda c: c.invite(name, pack, server))

    def _play(self, pack: str, server: str, dismiss_from: str | None = None) -> None:
        packs = localpacks.list_installed(self.ctx.lay)
        match = next((p for p in packs if p.name == pack), None)
        if pack and match is None:
            self.notice.setText(f"Сначала установи сборку «{pack}» на главной.")
            return
        if match is not None:
            self.ctx.settings.selected_pack = match.id
            self.ctx.save()
        if dismiss_from:
            self._run(lambda c: c.dismiss(dismiss_from))
        if self.window is not None:
            home = self.window.page("home")
            if hasattr(home, "refresh"):
                home.refresh()
            self.window.open_page("home")
            home.play(server=server or None)
