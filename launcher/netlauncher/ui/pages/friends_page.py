"""Friends: requests, online status, invites, play together."""

from __future__ import annotations

from netlauncher.i18n import t

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QLineEdit, QMenu, QScrollArea, QStackedWidget, QWidget

from netlauncher import coop, localpacks, skin
from netlauncher.friends import NotConfigured
from netlauncher.net import HttpError
from netlauncher.ui import anim, jobs, profile_style
from netlauncher.ui.pages.common import hbox, label, plural, vbox
from netlauncher.ui.pages.home import _error_text
from netlauncher.ui.supporter import display_name, remember
from netlauncher.ui.skinview import face
from netlauncher.ui.widgets import AccentButton, Avatar, GhostButton, GlassCard

POLL_MS = 15000


def _ago(ts: float) -> str:
    d = max(0, time.time() - ts)
    if d < 3600:
        m = max(1, int(d // 60))
        return t('{m} мин назад', m=m)
    if d < 86400:
        return t('{x0} ч назад', x0=int(d // 3600))
    n = int(d // 86400)
    return t('{n} {x2} назад', n=n, x2=plural(n, 'день', 'дня', 'дней'))


def status_text(f: dict) -> str:
    if not f.get("online"):
        return t('Не в сети, был {ago}', ago=_ago(f['last_seen'])) if f.get("last_seen") else t('Не в сети')
    if f.get("status") == "playing":
        text = t('Играет в {x1}', x1=f.get('pack') or 'Minecraft')
        return text + (t(' на {x1}', x1=f['server']) if f.get("server") else "")
    return t('В сети, в лаунчере')


class FriendRow(GlassCard):
    profile = Signal(str)
    join = Signal(dict)
    chat = Signal(str)
    invite = Signal(str)
    remove = Signal(str)

    def __init__(self, f: dict, parent=None):
        super().__init__(parent, radius=14)
        self.f, self.name = f, f["name"]
        row = hbox(self, (14, 10, 12, 10), 12)
        self.avatar = Avatar(38)
        self.avatar.set_name(self.name)
        self.avatar.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.avatar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.avatar.setAccessibleName(t("Профиль игрока {name}", name=self.name))
        self.avatar.setToolTip(self.avatar.accessibleName())
        self.avatar.clicked.connect(lambda: self.profile.emit(self.name))
        style = profile_style.clean(f.get("appearance") if f.get("supporter") else None)
        self.avatar.set_supporter(f.get("supporter", False), style["frame"])
        row.addWidget(self.avatar)
        col = vbox(None, (0, 0, 0, 0), 1)
        name_label = profile_style.PlayerName(11)
        name_label.setText(display_name(self.name, f.get("supporter")))
        name_label.set_appearance(style if f.get("supporter") else dict(style, font="sans"))
        if f.get("supporter"):
            name_label.setToolTip(t("Поддержка автора"))
        name_row = hbox(spacing=4)
        name_row.addWidget(name_label)
        if profile_style.is_developer(f.get("profile_uuid")):
            badge = profile_style.DeveloperBadge()
            name_row.addWidget(badge)
            badge.show()
        name_row.addStretch(1)
        col.addLayout(name_row)
        self.status = label(status_text(f), 9.5, role="muted" if f.get("online") else "faint")
        col.addWidget(self.status)
        row.addLayout(col, 1)
        write = GhostButton(t("Написать"))
        write.clicked.connect(lambda:self.chat.emit(self.name))
        row.addWidget(write)
        self.join_btn = AccentButton(t('Играть вместе'))
        self.join_btn.clicked.connect(lambda: self.join.emit(self.f))
        self.join_btn.setVisible(bool(f.get("online") and f.get("status") == "playing" and f.get("server")))
        row.addWidget(self.join_btn)
        self.invite_btn = GhostButton(t('Пригласить'))
        self.invite_btn.clicked.connect(lambda: self.invite.emit(self.name))
        row.addWidget(self.invite_btn)
        more = GhostButton(t('Ещё'))
        more.clicked.connect(lambda: self._menu(more))
        row.addWidget(more)

    def _menu(self, btn):
        m = QMenu(self)
        m.addAction(t("Профиль"), lambda: self.profile.emit(self.name))
        m.addAction(t('Удалить из друзей'), lambda: self.remove.emit(self.name))
        m.exec(btn.mapToGlobal(btn.rect().bottomLeft()))


class RequestRow(GlassCard):
    def __init__(self, name: str, parent=None):
        super().__init__(parent, radius=14)
        self.name = name
        row = hbox(self, (16, 10, 12, 10), 10)
        row.addWidget(label(t('{name} хочет добавить тебя в друзья', name=name), 10.5, 520), 1)
        self.accept_btn = AccentButton(t('Принять'))
        self.decline_btn = GhostButton(t('Отклонить'))
        row.addWidget(self.accept_btn)
        row.addWidget(self.decline_btn)


class InviteRow(GlassCard):
    def __init__(self, inv: dict, parent=None):
        super().__init__(parent, radius=14)
        self.inv = inv
        row = hbox(self, (16, 10, 12, 10), 10)
        self.text = label(t('{x0} зовёт играть в {x2}', x0=inv['from'], x2=inv.get('pack') or 'Minecraft'), 10.5, 560)
        row.addWidget(self.text, 1)
        self.play_btn = AccentButton(t('Присоединиться'))
        self.later_btn = GhostButton(t('Позже'))
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
        self.views = QStackedWidget()
        vbox(self).addWidget(self.views)
        directory = QWidget()
        self.views.addWidget(directory)
        outer = vbox(directory, (8, 4, 0, 0), 12)
        outer.addWidget(label(t('Друзья'), 22, 650, display=True))
        self.subtitle = label("", 10.5, role="muted")
        outer.addWidget(self.subtitle)
        self.notice = label("", 10.5, role="muted", wrap=True)
        outer.addWidget(self.notice)
        add = hbox(None, (0, 0, 0, 0), 8)
        self.add_name = QLineEdit()
        self.add_name.setPlaceholderText(t('Ник на Ely.by'))
        self.add_name.setMinimumWidth(280)
        self.add_name.returnPressed.connect(self.add_friend)
        self.add_btn = AccentButton(t('Добавить в друзья'))
        self.add_btn.clicked.connect(self.add_friend)
        add.addWidget(self.add_name)
        add.addWidget(self.add_btn)
        self.chat_btn = GhostButton(t("Чаты"))
        self.chat_btn.clicked.connect(lambda:self.chats.open())
        add.addWidget(self.chat_btn)
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
        from netlauncher.ui.pages.chat import Chats
        self.chats = Chats(self)
        self._update_notice()

    # ---------- client ----------
    def client(self):
        url = self.ctx.friends_url()
        acc = self.ctx.accounts.load()
        key = (url, acc.uuid if acc and not getattr(acc,"offline",False) else "")
        if self._client is None or self._client_url != key:
            if self._client is not None:
                self.chats.reset()
                self._clear(self.rows)
                self._clear(self.request_rows)
                self._clear(self.invite_rows)
                self.outgoing.clear()
                self.subtitle.clear()
            self._client, self._client_url = self.ctx.friends(), key
        return self._client

    def _update_notice(self) -> bool:
        configured = bool(self.ctx.friends_url())
        acc = self.ctx.accounts.load()
        self.add_row.setVisible(bool(configured and acc and not acc.offline and acc.provider == "ely"))
        if not configured:
            self.notice.setText(t('Сервер друзей не подключён. Его адрес задаёт автор сборки в каталоге; если тебе дали адрес, впиши его в настройках, раздел «Лаунчер».'))
        elif acc and (acc.offline or acc.provider != "ely"):
            self.notice.setText(t("Друзья работают после входа через Ely.by."))
            return False
        elif acc is None:
            self.notice.setText(t('Войди через Ely.by на главной, чтобы видеть друзей.'))
            return False
        else:
            self.notice.setText("")
        return configured

    def on_shown(self) -> None:
        self.tick()

    def tick(self) -> None:
        self.client()
        if not self._update_notice():
            return
        status, pack, server = getattr(self.window, "game_status", ("launcher", "", ""))
        identity = getattr(self.window, "game_pack", {})
        self._run(lambda c: c.presence(status, pack, server, **identity))

    def _run(self, fn, on_done=None) -> None:
        cl = self.client()
        import shiboken6
        def current():
            return shiboken6.isValid(self) and cl is self.client()
        def completed(state):
            if current():
                self._show(state)
                if on_done:
                    on_done()

        jobs.run(lambda progress: fn(cl), on_done=completed,
                 on_error=lambda e:self._failed(e) if current() else None)

    def _failed(self, e: BaseException) -> None:
        if isinstance(e, NotConfigured):
            self._update_notice()
        elif isinstance(e, HttpError) and e.status == 401:
            self.notice.setText(t('Ely.by не подтвердил вход. Выйди из аккаунта и войди снова.'))
        else:
            self.notice.setText(t('Сервер друзей не отвечает: {error}', error=_error_text(e)))

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
        remember(self.ctx, self.window, st)
        friends = st.get("friends") or []
        self.chats.start(self.client(), st.get("me",""), [f["name"] for f in friends])
        online = sum(1 for f in friends if f.get("online"))
        if self.window is not None and hasattr(self.window, "nav_button"):
            self.window.nav_button("friends").set_badge(str(online) if online else "")
        if self.window is not None and hasattr(self.window, "set_online_faces"):
            self.window.set_online_faces([(f["name"], self._faces.get(f["name"])) for f in friends if f.get("online")])
        self.subtitle.setText(t('{online} в сети', online=online) if friends else t('Пока никого. Добавь друга по нику на Ely.by.'))
        for rows in (self.invite_rows, self.request_rows, self.rows):
            self._clear(rows)
        pos = 0
        for inv in st.get("invites") or []:
            r = InviteRow(inv)
            r.play_btn.clicked.connect(lambda _=False, inv=inv: self._play(inv.get("pack", ""), inv.get("server", ""),
                                                                            inv["from"], inv.get("pack_id", ""), inv.get("pack_version", "")))
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
            r.join.connect(lambda f: self._play(f.get("pack", ""), f.get("server", ""),
                                                pack_id=f.get("pack_id", ""), version=f.get("pack_version", "")))
            r.chat.connect(self.chats.direct)
            if hasattr(self.window, "open_profile"):
                r.profile.connect(self.window.open_profile)
            r.invite.connect(self._invite)
            r.remove.connect(lambda n: self._run(lambda c: c.remove(n)))
            self.list.insertWidget(pos, r)
            pos += 1
            self.rows.append(r)
            self._face(r)
        out = st.get("outgoing") or []
        self.outgoing.setText(t('Ждут ответа: {names}', names=", ".join(out)) if out else "")
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
        self.notice.setText("")
        if self.window is not None and hasattr(self.window, "toast"):
            self.window.toast(t('Заявка отправлена: {name}', name=name))
        self._run(lambda c: c.request(name))

    def _invite(self, name: str) -> None:
        from netlauncher.ui.pages import common
        lp = common.current_pack(self.ctx)
        pack = lp.name if lp else ""
        server = lp.server if lp else ""
        if self.window is not None and hasattr(self.window, "toast"):
            self.window.toast(t('Приглашение отправлено: {name}', name=name))
        identity = {}
        status, playing, addr = getattr(self.window, "game_status", ("launcher", "", ""))
        if status == "playing" and addr:
            pack, server = playing, addr
            identity = getattr(self.window, "game_pack", {})
        self._run(lambda c: c.invite(name, pack, server, **identity))

    def _play(self, pack: str, server: str, dismiss_from: str | None = None, pack_id="", version="") -> None:
        match = coop.invited_pack(self.ctx.lay, pack, pack_id, version)
        if pack_id and version and match is None:
            self.notice.setText(t('Установи сборку «{pack}» версии {version}, чтобы присоединиться.',
                                  pack=pack, version=version))
            return
        if pack and match is None:
            self.notice.setText(t('Сначала установи сборку «{pack}» на главной.', pack=pack))
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
