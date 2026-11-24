"""Account, supporter appearance and player comments."""
from __future__ import annotations

import uuid
from datetime import datetime

import shiboken6
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QGridLayout, QLineEdit, QScrollArea, QWidget

from netlauncher import localpacks, skin
from netlauncher.i18n import t
from netlauncher.net import HttpError
from netlauncher.ui import jobs, supporter, profile_style
from netlauncher.ui.pages.common import confirm, hbox, human_date, label, vbox
from netlauncher.ui.pages.home import ELY_SKIN_UPLOAD
from netlauncher.ui.skinview import SkinRenderer, face
from netlauncher.ui.widgets import AccentButton, Avatar, CompactCombo, GhostButton, GlassCard


class ProfilePage(QWidget):
    def __init__(self, ctx, window):
        super().__init__()
        self.ctx, self.window = ctx, window
        self.target = None
        self.own = True
        inner = QWidget()
        layout = vbox(inner, (10, 4, 18, 16), 12)
        layout.addWidget(label(t("Профиль"), 22, 650, display=True))
        header = hbox(spacing=14)
        self.avatar = Avatar(64)
        header.addWidget(self.avatar)
        identity = vbox(spacing=2)
        self.nickname = profile_style.PlayerName()
        self.developer = profile_style.DeveloperBadge()
        name_row = hbox(spacing=5)
        name_row.addWidget(self.nickname)
        name_row.addWidget(self.developer)
        name_row.addStretch(1)
        self.kind = label("", 10, role="muted")
        identity.addLayout(name_row)
        identity.addWidget(self.kind)
        header.addLayout(identity, 1)
        layout.addLayout(header)
        account_actions = hbox(spacing=8)
        self.skin_btn = GhostButton(t("Сменить скин"))
        self.skin_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(ELY_SKIN_UPLOAD)))
        account_actions.addWidget(self.skin_btn)
        self.preview = GhostButton(t("Примерить скин"))
        self.preview.clicked.connect(self.preview_skin)
        account_actions.addWidget(self.preview)
        self.account_btn = GhostButton("")
        self.account_btn.clicked.connect(self.account_action)
        account_actions.addWidget(self.account_btn)
        account_actions.addStretch(1)
        layout.addLayout(account_actions)
        self.support = supporter.RedeemCard(ctx, window)
        layout.addWidget(self.support)
        self.appearance = GlassCard()
        style = vbox(self.appearance, (20, 14, 20, 16), 8)
        style.addWidget(label(t("Украшения"), 13, 620))
        personal = QGridLayout()
        personal.setHorizontalSpacing(12)
        personal.setVerticalSpacing(8)
        self.style_boxes = {}
        captions = {"font": t("Шрифт ника"), "color": t("Цвет ника"), "motion": t("Анимация ника"), "frame": t("Рамка аватара")}
        for field, options in profile_style.OPTIONS.items():
            box = CompactCombo()
            box.setAccessibleName(captions[field])
            for value, title in options.items():
                box.addItem(t(title), value)
            group = vbox(spacing=4)
            group.addWidget(label(captions[field], 10, role="muted"))
            group.addWidget(box)
            row, column = divmod(len(self.style_boxes), 2)
            personal.addLayout(group, row, column)
            self.style_boxes[field] = box
            box.currentIndexChanged.connect(self.preview_appearance)
        style.addLayout(personal)
        self.save_appearance = AccentButton(t("Сохранить украшения"))
        self.save_appearance.clicked.connect(self.save_cosmetics)
        self.style_note = label("", 10, role="muted", wrap=True)
        actions = hbox(spacing=12)
        actions.addWidget(self.save_appearance)
        actions.addWidget(self.style_note, 1)
        style.addLayout(actions)
        self.edited = False
        self.saving = set()
        style.addSpacing(8)
        style.addWidget(label(t("Оформление сборки"), 12, 620))
        self.pack_controls = QWidget()
        pack_layout = vbox(self.pack_controls, spacing=8)
        self.pack_note = label(t("Фон и позу можно выбрать для своей сборки."), 10, role="muted")
        style.addWidget(self.pack_note)
        style.addWidget(self.pack_controls)
        choices = hbox()
        self.pack, self.backdrop, self.pose = CompactCombo(), CompactCombo(), CompactCombo()
        for box, caption in [(self.pack, t("Сборка")), (self.backdrop, t("Фон")), (self.pose, t("Поза"))]:
            group = vbox(spacing=3)
            box.setAccessibleName(caption)
            group.addWidget(label(caption, 9.5, role="muted"))
            group.addWidget(box)
            choices.addLayout(group, 1)
        supporter.style_choices(self.backdrop, self.pose)
        self.pack.currentIndexChanged.connect(self.load_style)
        pack_layout.addLayout(choices)
        self.apply = GhostButton(t("Сохранить оформление сборки"))
        self.apply.clicked.connect(self.apply_style)
        pack_layout.addWidget(self.apply, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.appearance)
        self.comments = Comments(ctx)
        self.comments.profile_loaded.connect(self.remote_profile)
        layout.addWidget(self.comments)
        layout.addStretch(1)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(inner)
        self.skin_column = QWidget()
        model = vbox(self.skin_column, (0, 12, 12, 12), 2)
        self.skin_model = SkinRenderer()
        window.scene.profile_studio.skin = self.skin_model
        model.addStretch(1)
        self.skin_status = label("", 10, role="muted", wrap=True)
        self.skin_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        model.addWidget(self.skin_status)
        columns = hbox(self, spacing=12)
        columns.addWidget(self.scroll, 3)
        columns.addWidget(self.skin_column, 2)
        self.skin_request = 0

    def on_shown(self):
        acc = self.ctx.accounts.load()
        self.own = not self.target or bool(acc and self.target.casefold() == acc.name.casefold())
        name = (acc.name if acc else "") if self.own else self.target
        self.nickname.setText(name or t("Гость"))
        online_account = bool(acc and not acc.offline)
        self.kind.setText(t("Локальный профиль") if self.own and acc and acc.offline
                          else t("Аккаунт Microsoft") if self.own and acc and acc.provider == "microsoft"
                          else t("Аккаунт Ely.by") if name else t("Вход в лаунчер"))
        self.avatar.set_name(name)
        self.avatar.set_face(self.window.rail.avatar.face_image() if self.own else None)
        self.edited = False
        self.nickname.set_appearance(None)
        self.developer.setVisible(self.own and online_account and profile_style.is_developer(acc.uuid))
        self.avatar.set_supporter(False)
        self.style_note.clear()
        self.skin_btn.setVisible(self.own and online_account and acc.provider == "ely")
        selected = localpacks.get(self.ctx.lay, self.ctx.settings.selected_pack) if self.ctx.settings.selected_pack else None
        self.preview.setVisible(bool(self.own and acc and selected))
        self.account_btn.setVisible(self.own)
        self.account_btn.setText(t("Выйти из аккаунта") if acc else t("Войти"))
        self.skin_column.setVisible(bool(name))
        self.skin_request += 1
        request = self.skin_request
        self.support.setVisible(self.own)
        self.appearance.setVisible(self.own)
        if self.own:
            self.pack.blockSignals(True)
            self.pack.clear()
            for pack in localpacks.list_installed(self.ctx.lay):
                if not pack.official and not (self.ctx.catalog and self.ctx.catalog.get(pack.id)):
                    self.pack.addItem(pack.name, pack.id)
            if not self.pack.count():
                self.pack.addItem(t("Нет своих сборок"), None)
            self.pack.setCurrentIndex(max(0, self.pack.findData(self.ctx.settings.selected_pack)))
            self.pack.blockSignals(False)
            self.load_style()
            self.load_cosmetics(supporter.saved_style(self.ctx))
            self.refresh_entitlement()
            self.support.refresh_status()
        if self.own and acc:
            home = self.window.page("home")
            if home.skin_account != acc.uuid:
                home._load_skin(acc)
            self.show_account_skin(home.account_skin, acc.uuid)
        else:
            self.skin_model.set_skin(None)
            self.window.scene.profile_studio.skin = self.skin_model if name else None
            self.window.scene.update()
            self.skin_status.setText(t("Загружаем скин…") if name else "")

        if not self.own:
            def got_skin(value):
                if shiboken6.isValid(self) and request == self.skin_request:
                    self.skin_model.set_skin(value)
                    self.window.scene.update()
                    self.avatar.set_face(face(self.skin_model.skin_png))
                    self.skin_status.setText("" if value else t("Скин недоступен. Показана стандартная модель."))
            jobs.run(lambda progress: skin.fetch(self.ctx.http, name, self.ctx.lay.cache),
                     on_done=got_skin, on_error=lambda _: got_skin(None))
        self.comments.open(name, self.own, self.avatar)
        self.scroll.verticalScrollBar().setValue(0)

    def refresh_entitlement(self):
        if self.own:
            enabled = supporter.active(self.ctx)
            self.save_appearance.setEnabled(enabled and supporter._identity(self.ctx) not in self.saving)
            if not self.edited:
                self.paint_style(supporter.saved_style(self.ctx), enabled)
            if not enabled:
                self.style_note.setText(t("Можно примерить. Для сохранения активируй ключ."))
            elif self.style_note.text() == t("Можно примерить. Для сохранения активируй ключ."):
                self.style_note.clear()
            self.support.refresh()
            uuid = supporter._identity(self.ctx)
            cached = self.ctx.settings.profile_cosmetics.get(uuid, {})
            if isinstance(cached, dict) and cached.get("pending"):
                self.sync_cosmetics(uuid, profile_style.clean(cached))
            self.pack_controls.setVisible(bool(self.pack.currentData()))
            self.pack_note.setVisible(not self.pack.currentData())
            for control in (self.pack, self.backdrop, self.pose, self.apply):
                control.setEnabled(enabled and bool(self.pack.currentData()))

    def load_cosmetics(self, style):
        for key, box in self.style_boxes.items():
            box.blockSignals(True)
            box.setCurrentIndex(box.findData(style[key]))
            box.blockSignals(False)

    def paint_style(self, style, enabled):
        self.nickname.set_appearance(style if enabled else None)
        self.avatar.set_supporter(enabled, style["frame"])

    def preview_appearance(self):
        self.edited = True
        self.paint_style({k: box.currentData() for k, box in self.style_boxes.items()}, True)
        if supporter.active(self.ctx):
            self.style_note.setText(t("Примерка. Сохрани, чтобы применить."))

    def remote_profile(self, result):
        style = profile_style.clean(result.get("appearance"))
        if not self.own:
            self.developer.setVisible(profile_style.is_developer(result["owner"]))
            self.paint_style(style, bool(result.get("supporter")))
        elif result.get("supporter") and result.get("appearance") and not self.edited:
            uuid = supporter._identity(self.ctx)
            if str(result["owner"]).replace("-", "").lower() != uuid:
                return
            cached = self.ctx.settings.profile_cosmetics.get(uuid, {})
            if isinstance(cached, dict) and not cached.get("pending"):
                if cached != style:
                    self.ctx.settings.profile_cosmetics[uuid] = style
                    self.ctx.save()
                self.load_cosmetics(style)
                self.paint_style(style, True)
                self.window.rail.avatar.set_supporter(True, style["frame"])

    def save_cosmetics(self):
        if not self.own or not supporter.active(self.ctx):
            return
        uuid = supporter._identity(self.ctx)
        if uuid in self.saving:
            return
        style = {k: box.currentData() for k, box in self.style_boxes.items()}
        self.ctx.settings.profile_cosmetics[uuid] = dict(style, pending=True)
        self.ctx.save()
        self.edited = False
        self.window.rail.avatar.set_supporter(True, style["frame"])
        self.style_note.setText(t("Сохранено на этом ПК."))
        self.sync_cosmetics(uuid, style)

    def sync_cosmetics(self, uuid, style):
        if uuid in self.saving or not supporter.online_active(self.ctx) or not self.ctx.friends_url():
            return
        self.saving.add(uuid)
        self.save_appearance.setEnabled(False)
        acc, client = self.ctx.accounts.load(), self.ctx.friends()
        def finished(ok):
            self.saving.discard(uuid)
            if supporter._identity(self.ctx) != uuid or self.ctx.friends_url().rstrip("/") != client.base:
                return
            if ok:
                self.ctx.settings.profile_cosmetics[uuid] = style
                self.ctx.save()
            if self.own:
                self.save_appearance.setEnabled(supporter.active(self.ctx))
                if not self.edited:
                    self.style_note.setText(t("Сохранено в профиле.") if ok else
                                            t("Сохранено на этом ПК. Для синхронизации нажми «Сохранить украшения» ещё раз."))
        jobs.run(lambda progress: client.profile(acc.name, "appearance", owner=acc.uuid,
                                                appearance=style),
                 on_done=lambda _: finished(True), on_error=lambda _: finished(False))

    def show_account_skin(self, value, account_id):
        acc = self.ctx.accounts.load()
        if self.own and acc and acc.uuid == account_id:
            self.skin_model.set_skin(value)
            self.window.scene.profile_studio.skin = self.skin_model
            self.window.scene.update()
            self.skin_status.clear()
            self.avatar.set_face(face(self.skin_model.skin_png))

    def show_own_face(self, image):
        if self.own:
            self.avatar.set_face(image)

    def load_style(self):
        key = self.pack.currentData()
        pack = localpacks.get(self.ctx.lay, key) if key else None
        self.backdrop.setCurrentIndex(max(0, self.backdrop.findData(pack.backdrop if pack else "studio")))
        self.pose.setCurrentIndex(max(0, self.pose.findData(pack.pose if pack else "idle")))

    def apply_style(self):
        if supporter.save_style(self.ctx, self.window, self.pack.currentData(), self.backdrop.currentData(), self.pose.currentData()):
            self.window.toast(t("Оформление сохранено."))

    def preview_skin(self):
        self.window.open_page("home")
        self.window.page("home").pick_skin()

    def account_action(self):
        if self.ctx.accounts.load():
            self.window.page("settings").logout()
        else:
            self.window.open_page("home")


class Comments(GlassCard):
    profile_loaded = Signal(dict)

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.generation = 0
        self.owner = None
        self.last_id = 0
        layout = vbox(self, (20, 14, 20, 16), 8)
        header = hbox()
        header.addWidget(label(t("Комментарии"), 13, 620), 1)
        self.permission = label(t("Кто может писать"), 10, role="muted")
        header.addWidget(self.permission)
        self.policy = CompactCombo()
        self.policy.setAccessibleName(self.permission.text())
        for caption, value in [(t("Друзья"), "friends"), (t("Все игроки"), "all"), (t("Никто"), "closed")]:
            self.policy.addItem(caption, value)
        self.policy.activated.connect(lambda: self.mutate("policy", policy=self.policy.currentData()))
        header.addWidget(self.policy)
        layout.addLayout(header)
        self.status = label("", 10, role="muted", wrap=True)
        layout.addWidget(self.status)
        self.retry = GhostButton(t("Повторить"))
        self.retry.clicked.connect(lambda: self.load())
        layout.addWidget(self.retry, 0, Qt.AlignmentFlag.AlignLeft)
        self.form = QWidget()
        composer = hbox(self.form)
        self.input = QLineEdit()
        self.input.setPlaceholderText(t("Оставить комментарий"))
        self.input.setMaxLength(500)
        self.send = AccentButton(t("Отправить"))
        self.send.setEnabled(False)
        self.input.textChanged.connect(lambda s: self.send.setEnabled(bool(s.strip())))
        self.input.returnPressed.connect(self.post)
        self.send.clicked.connect(self.post)
        composer.addWidget(self.input, 1)
        composer.addWidget(self.send)
        layout.addWidget(self.form)
        self.rows = vbox()
        layout.addLayout(self.rows)
        self.older = GhostButton(t("Показать ещё"))
        self.older.clicked.connect(lambda: self.load(self.last_id))
        layout.addWidget(self.older, 0, Qt.AlignmentFlag.AlignLeft)

    def clear_rows(self):
        while self.rows.count():
            widget = self.rows.takeAt(0).widget()
            widget.hide()
            widget.deleteLater()

    def open(self, name, own, avatar):
        self.generation += 1
        self.name, self.avatar, self.owner = name, avatar, None
        self.clear_rows()
        self.last_id = 0
        self.input.clear()
        self.form.hide()
        self.retry.hide()
        self.older.hide()
        self.policy.setVisible(own)
        self.permission.setVisible(own)
        self.policy.setEnabled(False)
        acc = self.ctx.accounts.load()
        if not name or not acc or acc.offline:
            self.status.setText(t("Комментарии доступны после входа через Ely.by."))
            return
        if not self.ctx.friends_url():
            self.status.setText(t("Сервер друзей не подключён."))
            return
        self.client = self.ctx.friends()
        self.load()

    def run(self, action, done, **data):
        generation, name, client = self.generation, self.name, self.client
        def current():
            if not shiboken6.isValid(self) or generation != self.generation:
                return False
            acc = self.ctx.accounts.load()
            return bool(acc and not acc.offline and acc.uuid == client.identity and
                        self.ctx.friends_url().rstrip("/") == client.base)
        def failed(err):
            if current():
                self.controls_enabled(True)
                if action == "policy":
                    self.policy.setCurrentIndex(self.policy.findData(self.saved_policy))
                self.status.setText(t("Действие недоступно для этого профиля.") if isinstance(err, HttpError) and err.status == 403
                                    else t("Комментарии недоступны. Проверь подключение и версию сервера друзей."))
                self.retry.show()
        jobs.run(lambda progress: client.profile(name, action, **data),
                 on_done=lambda result: done(result) if current() else None, on_error=failed)

    def controls_enabled(self, enabled):
        self.form.setEnabled(enabled)
        self.older.setEnabled(enabled)
        self.policy.setEnabled(enabled and self.owner is not None)
        for i in range(self.rows.count()):
            self.rows.itemAt(i).widget().setEnabled(enabled)

    def load(self, before=0):
        self.retry.hide()
        self.controls_enabled(False)
        self.status.setText(t("Загрузка…"))
        def loaded(result):
            self.owner, self.saved_policy = result["owner"], result["policy"]
            self.policy.setCurrentIndex(self.policy.findData(self.saved_policy))
            self.form.setVisible(bool(result["can_post"]))
            if not before:
                self.profile_loaded.emit(result)
            if not before:
                self.clear_rows()
                self.last_id = 0
            for comment in result["comments"]:
                self.add_row(comment)
                self.last_id = comment["id"]
            self.older.setVisible(bool(result["more"]))
            self.controls_enabled(True)
            if not result["can_post"]:
                self.status.setText(t("Комментарии закрыты.") if self.saved_policy == "closed"
                                    else t("Оставлять комментарии могут только друзья игрока."))
            else:
                self.status.setText("" if self.last_id else t("Комментариев пока нет."))
        self.run("read", loaded, before=before)

    def add_row(self, comment):
        row = QWidget()
        content = vbox(row, (2, 5, 2, 5), 3)
        header = hbox()
        header.addWidget(label(comment["author"], 10, 620))
        header.addWidget(label(human_date(datetime.fromtimestamp(comment["created"])), 9, role="muted"))
        header.addStretch(1)
        if comment["can_delete"]:
            remove = GhostButton(t("Удалить"))
            remove.clicked.connect(lambda: self.remove(comment["id"]))
            header.addWidget(remove)
        content.addLayout(header)
        body = label("", 10.5, wrap=True)
        body.setTextFormat(Qt.TextFormat.PlainText)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setText(comment["body"])
        content.addWidget(body)
        self.rows.addWidget(row)

    def remove(self, comment_id):
        if confirm(self, t("Удалить комментарий"), t("Удалить этот комментарий из профиля?"), t("Удалить")):
            self.mutate("delete", id=comment_id)

    def post(self):
        text = self.input.text().strip()
        if text and self.form.isEnabled() and self.form.isVisible():
            self.mutate("post", text=text, nonce=uuid.uuid4().hex)

    def mutate(self, action, **data):
        if self.owner is None:
            return
        self.controls_enabled(False)
        def saved(_):
            if action == "post":
                self.input.clear()
            self.load()
        self.run(action, saved, owner=self.owner, **data)
