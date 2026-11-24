"""Account-bound supporter controls for Settings, Official and personal packs."""

import hashlib
import hmac
import json
import re

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit

from netlauncher import localpacks
from netlauncher.i18n import t
from netlauncher.net import HttpError
from netlauncher.ui import jobs, profile_style
from netlauncher.ui.pages.common import hbox, label, vbox
from netlauncher.ui.widgets import AccentButton, GhostButton, GlassCard


def display_name(name, supporter):
    return f"{name}  ✦" if supporter else name


def _identity(ctx):
    account = ctx.accounts.load()
    if account and not account.offline and account.provider == "ely":
        return account.uuid.replace("-", "").lower()
    return ""


def online_active(ctx):
    uuid = _identity(ctx)
    cached = ctx.settings.supporter_accounts.get(uuid)
    return bool(uuid and cached and (not ctx.friends_url() or cached == ctx.friends_url()))


def author_digest(ctx):
    """The local author installation is provisioned separately from the public launcher."""
    uuid = _identity(ctx)
    if not profile_style.is_developer(uuid):
        return ""
    try:
        grant = json.loads((ctx.lay.root / "author-cosmetics.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(grant, dict) or grant.get("uuid") != uuid:
        return ""
    value = grant.get("digest")
    return value if isinstance(value, str) and re.fullmatch("[a-f0-9]{64}", value) else ""


def active(ctx):
    if online_active(ctx):
        return True
    digest = author_digest(ctx)
    return bool(digest and hmac.compare_digest(ctx.settings.author_cosmetic_receipt, digest))


def saved_style(ctx):
    return profile_style.clean(ctx.settings.profile_cosmetics.get(_identity(ctx)))


def update_window(ctx, window):
    if window and hasattr(window, "rail"):
        window.rail.avatar.set_supporter(active(ctx), saved_style(ctx)["frame"])
        home = window.page("home")
        if hasattr(home, "update_scene"):
            home.update_scene()
        profile = getattr(window, "_pages", {}).get("profile")
        if profile and profile.isVisible():
            profile.refresh_entitlement()


def remember(ctx, window, state):
    uuid = _identity(ctx)
    if not uuid or uuid != str(state.get("profile_uuid", "")).replace("-", "").lower():
        return
    known = ctx.settings.supporter_accounts
    service = ctx.friends_url()
    if not service:
        return
    was_active = active(ctx)
    if state.get("supporter") and known.get(uuid) != service:
        known[uuid] = service
        ctx.save()
    elif not state.get("supporter") and known.get(uuid) == service:
        known.pop(uuid)
        ctx.save()
    if was_active != active(ctx):
        update_window(ctx, window)


def _connected(ctx, window):
    return bool(_identity(ctx) and ctx.friends_url() and not getattr(window, "offline", False))


class RedeemCard(GlassCard):
    def __init__(self, ctx, window):
        super().__init__(radius=16)
        self.ctx, self.window = ctx, window
        self.pending = None
        col = vbox(self, (22, 18, 22, 20), 8)
        head = hbox()
        head.addWidget(label(t("Поддержка автора"), 13, 620), 1)
        self.link = GhostButton(t("Поддержать"))
        self.link.clicked.connect(lambda: QDesktopServices.openUrl(self.link_url()))
        head.addWidget(self.link)
        col.addLayout(head)
        self.status = label("", 10, role="muted", wrap=True)
        col.addWidget(self.status)
        row = hbox()
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("XXXX-XXXX-XXXX-XXXX")
        self.entry.setAccessibleName(t("Ключ поддержки"))
        self.entry.setMaxLength(96)
        self.entry.setMaximumWidth(260)
        self.submit = AccentButton(t("Активировать ключ"))
        self.submit.clicked.connect(self.redeem)
        self.entry.returnPressed.connect(self.redeem)
        row.addWidget(self.entry)
        row.addWidget(self.submit)
        row.addStretch(1)
        col.addLayout(row)
        self.refresh()

    def link_url(self):
        return QUrl(getattr(self.ctx.catalog, "support_url", ""))

    def refresh(self):
        url = self.link_url()
        self.link.setVisible(url.scheme() == "https" and bool(url.host()))
        online = online_active(self.ctx)
        local = bool(author_digest(self.ctx))
        enabled = active(self.ctx)
        if online:
            message = t("Украшения открыты для {name}.", name=self.ctx.accounts.load().name)
        elif enabled:
            message = (t("Украшения открыты на этом ПК. Для синхронизации введи ключ ещё раз.")
                       if self.ctx.friends_url() else t("Украшения открыты на этом ПК."))
        elif local:
            message = t("Введи ключ украшений. На этом ПК он работает без подключения к серверу друзей.")
        elif _identity(self.ctx):
            message = t("Для активации ключа нужен сервер друзей.") if not self.ctx.friends_url() else t("Введи ключ украшений от автора.")
        else:
            message = t("Для активации ключа войди через Ely.by.")
        self.status.setText(message)
        self.submit.setText(t("Привязать к серверу") if enabled and not online else t("Активировать ключ"))
        can_redeem = bool(_identity(self.ctx) and self.ctx.friends_url()) or (local and not enabled)
        for widget in (self.entry, self.submit):
            widget.setVisible(not online and (not enabled or can_redeem))
            widget.setEnabled(can_redeem and self.pending is None)

    def refresh_status(self):
        self.refresh()
        identity = (_identity(self.ctx), self.ctx.friends_url())
        if _connected(self.ctx, self.window):
            client = self.ctx.friends()

            def checked(state):
                if self.pending is None and identity == (_identity(self.ctx), self.ctx.friends_url()):
                    remember(self.ctx, self.window, state)
                    self.refresh()

            jobs.run(lambda progress: client.state(), on_done=checked)

    def redeem(self):
        if not self.submit.isEnabled():
            return
        key = re.sub(r"[\s-]+", "", self.entry.text()).upper()
        if not re.fullmatch("[A-HJ-NP-Z2-9]{16}", key):
            self.status.setText(t("В ключе должно быть 16 символов."))
            return
        digest = author_digest(self.ctx)
        if digest and not _connected(self.ctx, self.window) and not active(self.ctx) and hmac.compare_digest(hashlib.sha256(key.encode()).hexdigest(), digest):
            self.ctx.settings.author_cosmetic_receipt = digest
            self.ctx.save()
            self.entry.clear()
            update_window(self.ctx, self.window)
            self.refresh()
            return
        if not self.ctx.friends_url():
            self.status.setText(t("Этот ключ не подходит для локальной активации."))
            return
        client = self.ctx.friends()
        identity = (_identity(self.ctx), self.ctx.friends_url())
        self.pending = identity
        self.refresh()
        self.status.setText(t("Проверяем ключ…"))

        def done(state):
            self.pending = None
            if identity == (_identity(self.ctx), self.ctx.friends_url()):
                remember(self.ctx, self.window, state)
                self.entry.clear()
            self.refresh()

        def failed(err):
            self.pending = None
            self.refresh()
            if identity != (_identity(self.ctx), self.ctx.friends_url()):
                return
            status = err.status if isinstance(err, HttpError) else None
            if status in (400, 409):
                self.status.setText(t("Ключ неверен или уже использован."))
            elif status in (401, 403):
                self.status.setText(t("Сервер отклонил активацию. Проверь аккаунт Ely.by."))
            elif status in (404, 405):
                self.status.setText(t("Сервер друзей не поддерживает активацию ключей."))
            else:
                self.status.setText(t("Не удалось связаться с сервером друзей."))

        def redeem_online(progress):
            try:
                return client.redeem_key(key)
            except HttpError as err:
                if err.status == 409 and "already a supporter" in err.body:
                    return client.state()
                raise

        jobs.run(redeem_online, on_done=done, on_error=failed)


class IssueCard(GlassCard):
    def __init__(self, ctx, window):
        super().__init__(radius=16)
        self.ctx, self.window = ctx, window
        col = vbox(self, (22, 18, 22, 20), 8)
        col.addWidget(label(t("Ключи поддержки"), 13, 620))
        col.addWidget(label(t("Каждый ключ открывает украшения одному аккаунту Ely.by."), 10, role="muted", wrap=True))
        row = hbox()
        self.issue = AccentButton(t("Создать ключ"))
        self.issue.clicked.connect(self.create)
        row.addWidget(self.issue)
        self.key = QLineEdit()
        self.key.setReadOnly(True)
        self.key.setAccessibleName(t("Ключ поддержки"))
        self.key.setMaximumWidth(220)
        row.addWidget(self.key)
        self.copy = GhostButton(t("Скопировать"))
        self.copy.clicked.connect(lambda: QApplication.clipboard().setText(self.key.text()))
        row.addWidget(self.copy)
        row.addStretch(1)
        col.addLayout(row)
        self.error = label("", 10, role="muted")
        col.addWidget(self.error)
        self.identity = None
        self.hide()

    def refresh(self):
        self.hide()
        identity = (_identity(self.ctx), self.ctx.friends_url())
        if self.identity != identity:
            self.key.clear()
            self.error.clear()
        self.identity = identity
        self.key.setVisible(bool(self.key.text()))
        self.copy.setVisible(bool(self.key.text()))
        if _connected(self.ctx, self.window):
            client = self.ctx.friends()

            def checked(state):
                if identity == (_identity(self.ctx), self.ctx.friends_url()):
                    remember(self.ctx, self.window, state)
                    self.setVisible(bool(state.get("can_issue_keys")))

            jobs.run(lambda progress: client.state(), on_done=checked)

    def create(self):
        self.issue.setEnabled(False)
        identity = self.identity
        client = self.ctx.friends()

        def done(result):
            self.issue.setEnabled(True)
            if identity == (_identity(self.ctx), self.ctx.friends_url()):
                self.key.setText(result["key"])
                self.key.show()
                self.copy.show()
                self.error.clear()

        def failed(err):
            self.issue.setEnabled(True)
            self.error.setText(t("Не удалось создать ключ. Проверь вход и доступ автора."))

        jobs.run(lambda progress: client.issue_key(), on_done=done, on_error=failed)


def style_choices(backdrop, pose):
    for text, value in [(t("Студия"), "studio"), (t("Полярное сияние"), "aurora"), (t("Депо"), "depot")]:
        backdrop.addItem(text, value)
    for text, value in [(t("Обычная"), "idle"), (t("Приветствие"), "wave"), (t("Шаг вперёд"), "stride")]:
        pose.addItem(text, value)


def save_style(ctx, window, pack_id, backdrop, pose):
    pack = localpacks.get(ctx.lay, pack_id) if pack_id else None
    if not pack or pack.official or (ctx.catalog and ctx.catalog.get(pack_id)) or not active(ctx):
        return False
    pack.backdrop, pack.pose = backdrop, pose
    localpacks.save(ctx.lay, pack)
    if window:
        window.page("home").update_scene()
    return True


def edit_style(ctx, window, pack_id, parent):
    pack = localpacks.get(ctx.lay, pack_id)
    if not pack or pack.official or not active(ctx):
        return
    dialog = QDialog(parent)
    dialog.setWindowTitle(t("Оформление сборки"))
    form = QFormLayout(dialog)
    backdrop, pose = QComboBox(), QComboBox()
    style_choices(backdrop, pose)
    backdrop.setCurrentIndex(max(0, backdrop.findData(pack.backdrop)))
    pose.setCurrentIndex(max(0, pose.findData(pack.pose)))
    form.addRow(t("Фон"), backdrop)
    form.addRow(t("Поза"), pose)
    buttons = QDialogButtonBox()
    buttons.addButton(t("Сохранить"), QDialogButtonBox.ButtonRole.AcceptRole)
    buttons.addButton(t("Отмена"), QDialogButtonBox.ButtonRole.RejectRole)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    form.addRow(buttons)
    if dialog.exec():
        save_style(ctx, window, pack_id, backdrop.currentData(), pose.currentData())
