"""Home: Ely.by login, pack overview, install/import, play with live loading progress."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPainter, QPainterPath
from PySide6.QtWidgets import (QFileDialog, QInputDialog, QLineEdit, QSizePolicy, QStackedWidget, QWidget)

from netlauncher import localpacks, skin
from netlauncher.auth_ely import (Account, AuthUnavailable, BadCredentials, NeedLogin, TwoFactorRequired,
                                  ensure_valid)
from netlauncher.author import new_pack_id
from netlauncher.catalog import Catalog, PackEntry, is_newer
from netlauncher.catalog import resolve as resolve_catalog
from netlauncher.importer import find_instances, import_instance, read_versions
from netlauncher.launch import GameProcess, LaunchSpec, LogProgress, Stage, apply_fullscreen, build_command, crash_info
from netlauncher.localpacks import LocalPack
from netlauncher.net import HashMismatch, HttpError, Offline
from netlauncher.pack import MrPack, add_manual, apply_update, load_state, plan_update
from netlauncher.settings import recommended_ram_mb
from netlauncher.ui import anim, jobs
from netlauncher.ui.pages import common
from netlauncher.ui.pages.common import hbox, label, plural, vbox
from netlauncher.ui.skinview import SkinView3D, face
from netlauncher.ui.theme import qcolor
from netlauncher.ui.widgets import AccentButton, GhostButton, GlassCard, SmoothBar, Toggle

LOADER_NAMES = {"neoforge": "NeoForge", "fabric": "Fabric", "forge": "Forge", "quilt": "Quilt", "vanilla": ""}
REGISTER_URL = "https://account.ely.by/register"
ELY_SKIN_UPLOAD = "https://ely.by/load"


def _error_text(e: BaseException) -> str:
    if isinstance(e, (Offline, AuthUnavailable)):
        return "Нет связи с сервером. Проверь интернет и попробуй ещё раз."
    if isinstance(e, HashMismatch):
        return f"Файл {e.path.name} скачался с ошибкой. Попробуй ещё раз."
    if isinstance(e, HttpError):
        return f"Сервер ответил ошибкой {e.status}. Попробуй позже."
    return str(e) or e.__class__.__name__


# ---------------------------------------------------------------- login
class LoginPanel(QWidget):
    logged_in = Signal(object)

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        outer = vbox(self)
        outer.addStretch(1)
        row = hbox()
        row.addStretch(1)
        card = GlassCard(radius=20)
        card.setFixedWidth(400)
        lay = vbox(card, (32, 30, 32, 28), 12)
        lay.addWidget(label("Вход", 22, 650, display=True))
        self.hint = label("Нужен аккаунт Ely.by: с ним работают скины и вход на сервер.", 10.5, role="muted",
                          wrap=True)
        lay.addWidget(self.hint)
        lay.addSpacing(6)
        self.user = QLineEdit()
        self.user.setPlaceholderText("Логин или почта")
        self.password = QLineEdit()
        self.password.setPlaceholderText("Пароль")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.totp = QLineEdit()
        self.totp.setPlaceholderText("Код из приложения")
        self.totp.setMaxLength(8)
        self.totp.hide()
        for w in (self.user, self.password, self.totp):
            w.returnPressed.connect(self.submit)
            lay.addWidget(w)
        self.error = label("", 10, role="danger", wrap=True)
        lay.addWidget(self.error)
        self.button = AccentButton("Войти")
        self.button.clicked.connect(self.submit)
        lay.addWidget(self.button)
        reg = GhostButton("Создать аккаунт на Ely.by")
        reg.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(REGISTER_URL)))
        lay.addWidget(reg)
        row.addWidget(card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(2)

    def set_message(self, text: str) -> None:
        self.error.setText(text)

    def submit(self) -> None:
        user, pw, code = self.user.text().strip(), self.password.text(), self.totp.text().strip()
        if not user or not pw:
            self.error.setText("Введи логин и пароль.")
            return
        if self.totp.isVisible() and not code:
            self.error.setText("Введи код из приложения.")
            return
        self.error.setText("")
        self.button.setEnabled(False)
        self.button.setText("Вхожу")
        jobs.run(lambda progress: self.ctx.auth.login(user, pw, code or None),
                 on_done=self._done, on_error=self._failed)

    def _done(self, acc: Account) -> None:
        self._reset_button()
        self.ctx.accounts.save(acc)
        self.password.clear()
        self.totp.clear()
        self.totp.hide()
        self.logged_in.emit(acc)

    def _failed(self, e: BaseException) -> None:
        self._reset_button()
        if isinstance(e, TwoFactorRequired):
            self.totp.show()
            self.totp.setFocus()
            self.error.setText("На аккаунте включена двухфакторная защита. Введи код из приложения.")
        elif isinstance(e, BadCredentials):
            self.error.setText("Неверный логин или пароль." if not self.totp.isVisible()
                               else "Неверный пароль или код.")
        elif isinstance(e, AuthUnavailable):
            self.error.setText("Ely.by не отвечает. Проверь интернет и попробуй ещё раз.")
        else:
            self.error.setText(_error_text(e))

    def _reset_button(self):
        self.button.setEnabled(True)
        self.button.setText("Войти")


# ---------------------------------------------------------------- first run: theme
class ThemeCard(QWidget):
    clicked = Signal(str)

    def __init__(self, key: str, title: str, text: str, parent=None):
        super().__init__(parent)
        self.key, self.title, self.text = key, title, text
        self.selected = False
        self.setFixedSize(260, 230)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e):  # noqa: N802
        self.clicked.emit(self.key)

    def paintEvent(self, e):  # noqa: N802
        from PySide6.QtGui import QColor, QLinearGradient, QPen, QRadialGradient
        from netlauncher.ui.theme import font
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(qcolor("accent") if self.selected else qcolor("border"), 2 if self.selected else 1))
        p.setBrush(qcolor("card"))
        p.drawRoundedRect(r, 16, 16)
        prev = QRectF(16, 16, r.width() - 30, 130)
        p.save()
        clip = QPainterPath()
        clip.addRoundedRect(prev, 10, 10)
        p.setClipPath(clip)
        if self.key == "glass":
            p.fillRect(prev, QColor("#20304F"))
            for cx, cy, rad, col in ((50, 40, 60, "#E0773A"), (170, 120, 70, "#3FA36B"), (200, 30, 50, "#8E5BD8")):
                g = QRadialGradient(prev.x() + cx, prev.y() + cy, rad)
                g.setColorAt(0, QColor(col))
                g.setColorAt(1, QColor(0, 0, 0, 0))
                p.fillRect(prev, g)
            p.fillRect(prev.adjusted(18, 16, -18, -16), qcolor("window"))
        else:
            g = QLinearGradient(prev.topLeft(), prev.bottomLeft())
            g.setColorAt(0, QColor("#0F1A2E"))
            g.setColorAt(1, QColor("#0A101D"))
            p.fillRect(prev, g)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qcolor("accent"))
        p.drawRoundedRect(QRectF(prev.x() + 34, prev.bottom() - 40, 70, 18), 6, 6)
        p.setBrush(QColor(255, 255, 255, 40))
        p.drawRoundedRect(QRectF(prev.x() + 34, prev.y() + 30, 110, 12), 4, 4)
        p.restore()
        p.setPen(qcolor("text"))
        p.setFont(font(12, 620))
        p.drawText(QRectF(18, 156, r.width() - 30, 24), Qt.AlignmentFlag.AlignLeft, self.title)
        p.setPen(qcolor("muted"))
        p.setFont(font(9.5))
        p.drawText(QRectF(18, 182, r.width() - 30, 40), Qt.TextFlag.TextWordWrap, self.text)


class WelcomePanel(QWidget):
    done = Signal(str)
    picked = Signal(str)

    def __init__(self, current: str = "glass", parent=None):
        super().__init__(parent)
        lay = vbox(self, (8, 0, 8, 0), 12)
        lay.addStretch(1)
        lay.addWidget(label("Добро пожаловать", 30, 650, display=True))
        lay.addWidget(label("Выбери, как будет выглядеть лаунчер. Поменять можно в настройках.", 11, role="muted"))
        lay.addSpacing(14)
        row = hbox(None, (0, 0, 0, 0), 16)
        self.cards = [ThemeCard("glass", "Стекло", "Окно прозрачное, за ним размытый рабочий стол."),
                      ThemeCard("solid", "Сплошная", "Тёмно-синее окно без прозрачности.")]
        for c in self.cards:
            c.clicked.connect(self.pick)
            row.addWidget(c)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addSpacing(14)
        self.next_btn = AccentButton("Дальше")
        self.next_btn.clicked.connect(lambda: self.done.emit(self.choice))
        lay.addWidget(self.next_btn, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addStretch(2)
        self.choice = current
        self._mark()

    def pick(self, key: str) -> None:
        self.choice = key
        self._mark()
        self.picked.emit(key)

    def _mark(self):
        for c in self.cards:
            c.selected = c.key == self.choice
            c.update()


# ---------------------------------------------------------------- no packs yet
class EmptyPanel(QWidget):
    install_entry = Signal(object)
    import_from = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = vbox(self, (8, 0, 8, 0), 10)
        lay.addWidget(label("Сборок пока нет", 30, 650, display=True))
        lay.addWidget(label("Поставь сборку из списка или перенеси свою из PineconeMC.", 11, role="muted"))
        lay.addSpacing(14)
        self.list = vbox(None, (0, 0, 0, 0), 10)
        lay.addLayout(self.list)
        self.note = label("", 10, role="faint", wrap=True)
        lay.addWidget(self.note)
        lay.addStretch(1)
        self.catalog_buttons: list = []
        self.import_buttons: list = []
        self._rows: list[QWidget] = []

    def _row(self, title: str, text: str, button) -> QWidget:
        card = GlassCard()
        row = hbox(card, (20, 14, 14, 14), 14)
        col = vbox(None, (0, 0, 0, 0), 2)
        col.addWidget(label(title, 12.5, 600))
        if text:
            col.addWidget(label(text, 10, role="muted", wrap=True))
        row.addLayout(col, 1)
        row.addWidget(button)
        return card

    def fill(self, catalog: Catalog | None, instances: list[Path], installed: set[str]) -> None:
        for w in self._rows:
            w.setParent(None)
            w.deleteLater()
        self._rows, self.catalog_buttons, self.import_buttons = [], [], []
        for e in (catalog.packs if catalog else []):
            if e.id in installed:
                continue
            b = AccentButton("Установить")
            b.clicked.connect(lambda _=False, e=e: self.install_entry.emit(e))
            self.catalog_buttons.append(b)
            self._rows.append(self._row(e.name, e.description or f"Minecraft {e.mc_version}", b))
        for inst in instances:
            b = GhostButton(f"Перенести «{inst.name}»")
            b.clicked.connect(lambda _=False, i=inst: self.import_from.emit(i))
            self.import_buttons.append(b)
            self._rows.append(self._row(f"PineconeMC: {inst.name}",
                                        "Скопирую моды, настройки и миры. В PineconeMC всё останется как было.", b))
        for w in self._rows:
            self.list.addWidget(w)
        anim.stagger(self._rows)
        self.note.setText("" if self._rows else
                          "Список сборок не загрузился, а в PineconeMC сборок не нашлось. Проверь интернет.")


# ---------------------------------------------------------------- long operations
class ProgressPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = vbox(self, (8, 0, 8, 0), 12)
        lay.addStretch(1)
        self.title = label("", 26, 650, display=True)
        self.step = label("", 11, role="muted")
        self.bar = SmoothBar(height=8)
        self.percent = label("", 10, role="faint")
        for w in (self.title, self.step, self.bar, self.percent):
            lay.addWidget(w)
        lay.addStretch(2)

    def start(self, title: str) -> None:
        self.title.setText(title)
        self.step.setText("Готовлю")
        self.bar.set_fraction(0)
        self.percent.setText("")

    def progress(self, text: str, cur: int, mx: int) -> None:
        self.step.setText(text)
        if mx > 0:
            self.bar.set_fraction(cur / mx)
            self.percent.setText(f"{round(100 * cur / mx)} %")


class ManualPanel(QWidget):
    finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        lay = vbox(self, (8, 0, 8, 0), 12)
        lay.addStretch(1)
        lay.addWidget(label("Один файл нужно скачать вручную", 22, 650, display=True))
        self.text = label("", 11, role="muted", wrap=True)
        lay.addWidget(self.text)
        row = hbox()
        self.open_btn = AccentButton("Открыть страницу мода")
        self.pick_btn = GhostButton("Выбрать скачанный файл")
        row.addWidget(self.open_btn)
        row.addWidget(self.pick_btn)
        row.addStretch(1)
        lay.addLayout(row)
        self.drop = label("Или перетащи файл в это окно.", 10, role="faint")
        lay.addWidget(self.drop)
        self.error = label("", 10, role="danger", wrap=True)
        lay.addWidget(self.error)
        lay.addStretch(2)
        self.open_btn.clicked.connect(self._open)
        self.pick_btn.clicked.connect(self._pick)
        self.pack_index = None
        self.game_dir: Path | None = None
        self.missing: list = []

    def show_missing(self, pack_index, game_dir: Path, missing: list) -> None:
        self.pack_index, self.game_dir, self.missing = pack_index, game_dir, list(missing)
        self._refresh()

    def _refresh(self):
        if not self.missing:
            self.finished.emit()
            return
        m = self.missing[0]
        self.text.setText(f"{m.name} нельзя скачать автоматически: автор запретил перезаливать мод. "
                          f"Скачай файл {Path(m.path).name} со страницы мода, лаунчер проверит его и положит на место.")
        self.open_btn.setEnabled(bool(m.page_url))

    def _open(self):
        if self.missing and self.missing[0].page_url:
            QDesktopServices.openUrl(QUrl(self.missing[0].page_url))

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(self, "Файл мода", str(Path.home() / "Downloads"), "Моды (*.jar)")
        if path:
            self.accept_file(Path(path))

    def accept_file(self, path: Path) -> None:
        try:
            m = add_manual(self.pack_index, self.game_dir, path)
        except HashMismatch:
            self.error.setText("Это другой файл или другая версия. Нужен именно " +
                               Path(self.missing[0].path).name + ".")
            return
        self.error.setText("")
        self.missing = [x for x in self.missing if x.sha1 != m.sha1]
        self._refresh()

    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):  # noqa: N802
        for url in e.mimeData().urls():
            if url.isLocalFile():
                self.accept_file(Path(url.toLocalFile()))


# ---------------------------------------------------------------- pack overview
class Chip(QWidget):
    clicked = Signal()

    def __init__(self, text: str, active: bool, parent=None):
        super().__init__(parent)
        self.text, self.active = text, active
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lab = label(text, 10, 560)
        self.setFixedHeight(30)
        self.setMinimumWidth(self.lab.sizeHint().width() + 28)

    def mousePressEvent(self, e):  # noqa: N802
        self.clicked.emit()

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(qcolor("accent") if self.active else qcolor("border"))
        p.setBrush(qcolor("rgba(76,154,255,0.16)") if self.active else qcolor("card"))
        p.drawRoundedRect(r, 15, 15)
        p.setPen(qcolor("text") if self.active else qcolor("muted"))
        p.setFont(self.lab.font())
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text)


class PackPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = hbox(self, (8, 0, 0, 0), 24)
        left = vbox(None, (0, 0, 0, 0), 0)
        self.chips_row = hbox(None, (0, 0, 0, 0), 8)
        left.addLayout(self.chips_row)
        left.addSpacing(28)
        self.title = label("", 44, 700, display=True)
        self.title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        left.addWidget(self.title)
        left.addSpacing(6)
        self.desc = label("", 12, role="muted", wrap=True)
        self.desc.setMaximumWidth(520)
        left.addWidget(self.desc)
        left.addSpacing(4)
        self.meta = label("", 10, role="faint")
        left.addWidget(self.meta)
        left.addSpacing(26)
        buttons = hbox(None, (0, 0, 0, 0), 10)
        self.play_btn = AccentButton("Играть", icon="play", big=True)
        self.continue_btn = GhostButton("")
        self.server_btn = GhostButton("Играть на сервере")
        for b in (self.continue_btn, self.server_btn):
            b.setMinimumHeight(56)
        buttons.addWidget(self.play_btn)
        buttons.addWidget(self.continue_btn)
        buttons.addWidget(self.server_btn)
        buttons.addStretch(1)
        left.addLayout(buttons)
        left.addSpacing(18)
        status_row = hbox(None, (0, 0, 0, 0), 12)
        self.status = label("", 10.5, role="muted")
        self.percent = label("", 10, role="faint")
        status_row.addWidget(self.status)
        status_row.addStretch(1)
        status_row.addWidget(self.percent)
        left.addLayout(status_row)
        left.addSpacing(6)
        self.bar = SmoothBar(height=4)
        self.bar.setMaximumWidth(560)
        self.bar.hide()
        left.addWidget(self.bar)
        left.addSpacing(18)

        self.crash_box = GlassCard()
        cb = vbox(self.crash_box, (20, 16, 20, 16), 6)
        self.crash_title = label("Игра закрылась с ошибкой", 12.5, 650, role="danger")
        self.crash_text = label("", 10.5, role="muted", wrap=True)
        crow = hbox(None, (0, 6, 0, 0), 8)
        self.crash_open = GhostButton("Открыть отчёт")
        self.crash_hide = GhostButton("Скрыть")
        crow.addWidget(self.crash_open)
        crow.addWidget(self.crash_hide)
        crow.addStretch(1)
        cb.addWidget(self.crash_title)
        cb.addWidget(self.crash_text)
        cb.addLayout(crow)
        self.crash_box.setMaximumWidth(620)
        self.crash_box.hide()
        left.addWidget(self.crash_box)

        self.update_box = GlassCard()
        ub = hbox(self.update_box, (20, 14, 14, 14), 12)
        self.update_label = label("", 11, 560)
        self.update_btn = AccentButton("Обновить")
        ub.addWidget(self.update_label, 1)
        ub.addWidget(self.update_btn)
        self.update_box.setMaximumWidth(620)
        self.update_box.hide()
        left.addWidget(self.update_box)
        left.addSpacing(10)

        self.news_box = GlassCard()
        nb = vbox(self.news_box, (20, 16, 20, 18), 6)
        self.news_title = label("", 11, 600)
        self.news_text = label("", 10.5, role="muted", wrap=True)
        nb.addWidget(self.news_title)
        nb.addWidget(self.news_text)
        self.news_box.setMaximumWidth(620)
        self.news_box.hide()
        left.addWidget(self.news_box)
        left.addStretch(1)
        root.addLayout(left, 3)
        self.model_slot = vbox(None, (0, 0, 0, 0), 0)
        self.model = SkinView3D()
        self.model.setToolTip("Покрути мышью")
        self.model_slot.addWidget(self.model, 1)
        skin_row = hbox(None, (0, 0, 0, 0), 8)
        skin_row.addStretch(1)
        self.skin_btn = GhostButton("Сменить скин")
        skin_row.addWidget(self.skin_btn)
        skin_row.addStretch(1)
        self.model_slot.addLayout(skin_row)
        self.skin_bar = GlassCard()
        sb = vbox(self.skin_bar, (16, 12, 16, 14), 8)
        self.skin_hint = label("Это предпросмотр. Чтобы скин видели все, загрузи его на Ely.by.", 10,
                               role="muted", wrap=True)
        sb.addWidget(self.skin_hint)
        srow = hbox(None, (0, 0, 0, 0), 10)
        srow.addWidget(label("Тонкие руки", 10, 520))
        self.slim = Toggle()
        srow.addWidget(self.slim)
        srow.addStretch(1)
        sb.addLayout(srow)
        brow = hbox(None, (0, 0, 0, 0), 8)
        self.skin_upload = AccentButton("Загрузить на Ely.by")
        self.skin_reload = GhostButton("Обновить")
        self.skin_cancel = GhostButton("Отменить")
        for b in (self.skin_upload, self.skin_reload, self.skin_cancel):
            brow.addWidget(b)
        sb.addLayout(brow)
        self.skin_bar.hide()
        self.model_slot.addWidget(self.skin_bar)
        root.addLayout(self.model_slot, 2)
        self._chips: list[Chip] = []

    def set_chips(self, packs: list[LocalPack], active: str, on_pick) -> None:
        for c in self._chips:
            c.setParent(None)
            c.deleteLater()
        self._chips = []
        if len(packs) < 2:
            return
        for lp in packs:
            c = Chip(lp.name, lp.id == active)
            c.clicked.connect(lambda lp=lp: on_pick(lp.id))
            self.chips_row.addWidget(c)
            self._chips.append(c)
        self.chips_row.addStretch(1)


# ---------------------------------------------------------------- page
class HomePage(QWidget):
    def __init__(self, ctx, window=None, parent=None):
        super().__init__(parent)
        self.ctx, self.window = ctx, window
        self.process_factory = GameProcess
        self.catalog: Catalog | None = None
        self.proc = None
        self.progress: LogProgress | None = None
        self._log_offset = 0
        self._last_line_at = 0.0
        self._started_at = 0.0
        self._hidden_for_game = False
        self._crash_report: Path | None = None

        lay = vbox(self)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)
        self.welcome = WelcomePanel(ctx.settings.theme)
        self.login = LoginPanel(ctx)
        self.empty = EmptyPanel()
        self.panel = PackPanel()
        self.busy = ProgressPanel()
        self.manual = ManualPanel()
        self._modes = {"welcome": self.welcome, "login": self.login, "empty": self.empty, "pack": self.panel, "install": self.busy,
                       "manual": self.manual}
        for w in self._modes.values():
            self.stack.addWidget(w)

        self.login.logged_in.connect(self._on_login)
        self.welcome.picked.connect(self._preview_theme)
        self.welcome.done.connect(self._welcome_done)
        self.empty.install_entry.connect(self.install_entry)
        self.empty.import_from.connect(self.import_instance)
        self.manual.finished.connect(self.refresh)
        self.panel.play_btn.clicked.connect(lambda: self.play())
        self.panel.continue_btn.clicked.connect(self._continue)
        self.panel.server_btn.clicked.connect(self._server)
        self.panel.update_btn.clicked.connect(self._update)
        self.panel.crash_open.clicked.connect(self._open_report)
        self.panel.crash_hide.clicked.connect(self.panel.crash_box.hide)
        self.panel.skin_btn.clicked.connect(self.pick_skin)
        self.panel.slim.toggled.connect(self._slim_changed)
        self.panel.skin_upload.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(ELY_SKIN_UPLOAD)))
        self.panel.skin_reload.clicked.connect(self.reload_skin)
        self.panel.skin_cancel.clicked.connect(self.cancel_skin_preview)
        self._preview_png: bytes | None = None

        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self._poll)
        self.refresh()
        self._load_catalog()
        self._load_skin(self.ctx.accounts.load())

    # ---------- state ----------
    def mode(self) -> str:
        cur = self.stack.currentWidget()
        return next(k for k, w in self._modes.items() if w is cur)

    def _set_mode(self, mode: str) -> None:
        w = self._modes[mode]
        if self.stack.currentWidget() is not w:
            self.stack.setCurrentWidget(w)
            anim.fade_slide_in(w, dx=0, dy=10, ms=260)

    def current_pack(self) -> LocalPack | None:
        return common.current_pack(self.ctx)

    def _preview_theme(self, theme: str) -> None:
        if self.window is not None and hasattr(self.window, "set_theme"):
            self.window.set_theme(theme)

    def _welcome_done(self, theme: str) -> None:
        self.ctx.settings.theme = theme
        self.ctx.settings.first_run_done = True
        self.ctx.save()
        self._preview_theme(theme)
        self.refresh()

    def refresh(self) -> None:
        if not self.ctx.settings.first_run_done:
            self._set_mode("welcome")
            return
        acc = self.ctx.accounts.load()
        if self.window is not None and hasattr(self.window, "set_account"):
            self.window.set_account(acc)
        if acc is None:
            self._set_mode("login")
            return
        lp = self.current_pack()
        if lp is None:
            self.empty.fill(self.catalog, find_instances(), set())
            self._set_mode("empty")
            return
        self._show_pack(lp)
        self._set_mode("pack")

    def _show_pack(self, lp: LocalPack) -> None:
        p = self.panel
        packs = localpacks.list_installed(self.ctx.lay)
        p.set_chips(packs, lp.id, self._pick_pack)
        p.title.setText(lp.name)
        p.desc.setText(lp.description)
        p.desc.setVisible(bool(lp.description))
        n = localpacks.mod_count(self.ctx.lay, lp.id)
        loader = LOADER_NAMES.get(lp.loader, lp.loader)
        meta = f"Minecraft {lp.mc_version}" + (f" с {loader}" if loader else "")
        p.meta.setText(f"{meta}, {n} {plural(n, 'мод', 'мода', 'модов')}")
        world = localpacks.newest_world(self.ctx.lay, lp.id)
        p.continue_btn.setText(f"Продолжить «{world}»" if world else "")
        p.continue_btn.setVisible(bool(world))
        p.server_btn.setVisible(bool(lp.server))
        entry = self.catalog.get(lp.id) if self.catalog else None
        if entry and is_newer(entry.version, lp.version):
            p.update_label.setText(f"Вышла версия {entry.version}. Сейчас стоит {lp.version}.")
            p.update_box.show()
        else:
            p.update_box.hide()
        if entry and entry.changelog:
            p.news_title.setText(f"Что нового в {entry.version}")
            p.news_text.setText(entry.changelog)
            p.news_box.show()
        else:
            p.news_box.hide()

    def _pick_pack(self, pack_id: str) -> None:
        self.ctx.settings.selected_pack = pack_id
        self.ctx.save()
        self.refresh()

    def _on_login(self, acc: Account) -> None:
        self.refresh()
        self._load_skin(acc)

    def _load_skin(self, acc: Account | None) -> None:
        if acc is None:
            return
        jobs.run(lambda progress: skin.fetch(self.ctx.http, acc.name, self.ctx.lay.cache),
                 on_done=self._skin_loaded, on_error=lambda e: None)

    # ---------- skin change ----------
    def pick_skin(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Файл скина", str(Path.home()), "Скины (*.png)")
        if path:
            self.preview_skin(Path(path))

    def preview_skin(self, path: Path) -> None:
        p = self.panel
        p.skin_bar.show()
        try:
            data = Path(path).read_bytes()
            skin.check_skin(data)
        except (OSError, ValueError) as e:
            p.skin_hint.setText(str(e) if isinstance(e, ValueError) else "Не получилось открыть файл.")
            return
        self._preview_png = data
        p.skin_hint.setText("Это предпросмотр. Чтобы скин видели все, загрузи его на Ely.by.")
        p.model.set_skin(skin.Skin(data, p.slim.isChecked()), entrance=False)

    def _slim_changed(self, on: bool) -> None:
        if self._preview_png is not None:
            self.panel.model.set_skin(skin.Skin(self._preview_png, on), entrance=False)

    def cancel_skin_preview(self) -> None:
        self._preview_png = None
        self.panel.skin_bar.hide()
        self._load_skin(self.ctx.accounts.load())

    def reload_skin(self) -> None:
        acc = self.ctx.accounts.load()
        if acc is None:
            return
        self.panel.skin_hint.setText("Загружаю скин с Ely.by")
        jobs.run(lambda progress: skin.fetch(self.ctx.http, acc.name, self.ctx.lay.cache, force=True),
                 on_done=self._skin_reloaded, on_error=lambda e: self.panel.skin_hint.setText(_error_text(e)))

    def _skin_reloaded(self, sk) -> None:
        self._preview_png = None
        if sk is None:
            self.panel.skin_hint.setText("На Ely.by у аккаунта нет скина.")
            return
        self.panel.skin_bar.hide()
        self._skin_loaded(sk)

    def _skin_loaded(self, sk) -> None:
        if sk is None:
            return
        if self._preview_png is None:
            self.panel.model.set_skin(sk)
        if self.window is not None and hasattr(self.window, "set_face"):
            self.window.set_face(face(sk.png))

    def _load_catalog(self) -> None:
        jobs.run(lambda progress: resolve_catalog(self.ctx.http), on_done=self._catalog_loaded,
                 on_error=lambda e: None)

    def _catalog_loaded(self, cat: Catalog | None) -> None:
        self.catalog = cat
        if self.mode() in ("pack", "empty"):
            self.refresh()

    # ---------- install / update / import ----------
    def install_entry(self, entry: PackEntry) -> None:
        self.busy.start(f"Установка {entry.name}")
        self._set_mode("install")
        jobs.run(self._install_job, entry, on_done=self._installed, on_error=self._install_failed,
                 on_progress=self.busy.progress)

    def _install_job(self, entry: PackEntry, progress):
        lay = self.ctx.lay
        gd = localpacks.game_dir(lay, entry.id)
        progress("Скачиваю описание сборки", 0, 0)
        mp_path = self.ctx.http.download(entry.mrpack_url, lay.cache / "packs" / f"{entry.id}-{entry.version}.mrpack",
                                         sha1=entry.mrpack_sha1 or None)
        pack = MrPack.open(mp_path)
        plan = plan_update(pack, gd, load_state(gd))
        apply_update(plan, pack, gd, self.ctx.http, lay.cache, lay.snapshots / entry.id,
                     lambda name, cur, mx: progress(f"Скачиваю {name}", cur, mx))
        localpacks.save(lay, localpacks.from_entry(entry))
        self.ctx.installer.ensure(entry.mc_version, entry.loader, entry.loader_version,
                                  lambda s, c, m: progress(f"Minecraft: {s}", c, m))
        self.ctx.settings.selected_pack = entry.id
        self.ctx.save()
        return pack.index, gd, plan.manual_missing

    def _installed(self, result) -> None:
        index, gd, missing = result
        if missing:
            self.manual.show_missing(index, gd, missing)
            self._set_mode("manual")
        else:
            self.refresh()

    def _install_failed(self, e: BaseException) -> None:
        self.refresh()
        if self.mode() == "pack":
            self.panel.status.setText(_error_text(e))
        else:
            self.empty.note.setText(_error_text(e))

    def _update(self) -> None:
        lp = self.current_pack()
        entry = self.catalog.get(lp.id) if (self.catalog and lp) else None
        if entry:
            self.install_entry(entry)

    def import_instance(self, inst: Path) -> None:
        default = ".NET" if inst.name[:1].isdigit() else inst.name
        name, ok = QInputDialog.getText(self, "Название сборки", "Как назвать сборку в лаунчере?", text=default)
        if not ok or not name.strip():
            return
        self.busy.start(f"Перенос {name.strip()}")
        self._set_mode("install")
        jobs.run(self._import_job, inst, name.strip(), on_done=lambda r: self.refresh(),
                 on_error=self._install_failed, on_progress=self.busy.progress)

    def _import_job(self, inst: Path, name: str, progress):
        lay = self.ctx.lay
        mc, loader, lv = read_versions(inst)
        existing = {p.id for p in localpacks.list_installed(lay)}
        pid = new_pack_id(name, existing)
        gd = localpacks.game_dir(lay, pid)
        import_instance(inst, gd, lambda item, cur, mx: progress(f"Копирую {item}", cur, mx))
        localpacks.save(lay, LocalPack(pid, name, "0.0", mc, loader, lv))
        self.ctx.installer.ensure(mc, loader, lv, lambda s, c, m: progress(f"Minecraft: {s}", c, m))
        self.ctx.settings.selected_pack = pid
        self.ctx.save()
        return pid

    # ---------- play ----------
    def _continue(self) -> None:
        lp = self.current_pack()
        if lp:
            self.play(world=localpacks.newest_world(self.ctx.lay, lp.id))

    def _server(self) -> None:
        lp = self.current_pack()
        if lp and lp.server:
            self.play(server=lp.server)

    def _set_playing(self, on: bool) -> None:
        self.panel.bar.setVisible(on)
        for b in (self.panel.play_btn, self.panel.continue_btn, self.panel.server_btn, self.panel.update_btn):
            b.setEnabled(not on)

    def play(self, world: str | None = None, server: str | None = None) -> None:
        lp = self.current_pack()
        if lp is None or self.proc is not None:
            return
        self.panel.crash_box.hide()
        self._set_playing(True)
        self.panel.status.setText("Проверяю вход и файлы игры")
        self.panel.percent.setText("")
        self.panel.bar.set_fraction(0.01)

        def prepare(progress):
            acc = ensure_valid(self.ctx.auth, self.ctx.accounts)
            game = self.ctx.installer.ensure(lp.mc_version, lp.loader, lp.loader_version,
                                             lambda s, c, m: progress(f"Minecraft: {s}", c, m))
            authlib = self.ctx.installer.ensure_authlib()
            return acc, game, authlib

        jobs.run(prepare, on_done=lambda r: self._launch(lp, r, world, server), on_error=self._prepare_failed,
                 on_progress=lambda s, c, m: self.panel.status.setText(s))

    def _prepare_failed(self, e: BaseException) -> None:
        self._set_playing(False)
        self.panel.bar.set_fraction(0)
        if isinstance(e, NeedLogin):
            self.login.set_message("Сессия Ely.by истекла. Войди ещё раз.")
            self.refresh()
            return
        self.panel.status.setText(_error_text(e))

    def _launch(self, lp: LocalPack, prepared, world, server) -> None:
        acc, game, authlib = prepared
        s = self.ctx.settings
        gd = localpacks.game_dir(self.ctx.lay, lp.id)
        ram = s.max_ram_mb or recommended_ram_mb(localpacks.total_ram_mb())
        spec = LaunchSpec(game, self.ctx.lay.minecraft, gd, acc, ram, s.fullscreen, s.width, s.height, authlib,
                          world=world, server=server)
        try:
            apply_fullscreen(gd, s.fullscreen)
            cmd = build_command(spec)
            self.proc = self.process_factory(gd)
            self._started_at = time.time()
            self.proc.start(cmd, gd)
        except Exception as e:  # noqa: BLE001
            self.proc = None
            self._prepare_failed(e)
            return
        self.progress = LogProgress()
        self._log_offset = 0
        self._last_line_at = time.time()
        self._hidden_for_game = False
        self.panel.status.setText("Запускаю игру")
        self.timer.start()

    def _poll(self) -> None:
        if self.proc is None:
            self.timer.stop()
            return
        self._read_log()
        if self.progress:
            ev = self.progress.idle(time.time() - self._last_line_at)
            if ev:
                self._show_stage(*ev)
        code = self.proc.poll()
        if code is not None:
            self._read_log()
            self._finished(code)

    def _read_log(self) -> None:
        path = self.proc.log_path
        try:
            st = path.stat()
        except OSError:
            return
        if st.st_mtime < self._started_at - 2:
            return  # still the previous session's log
        if st.st_size < self._log_offset:
            self._log_offset = 0
        if st.st_size == self._log_offset:
            return
        with open(path, "rb") as f:
            f.seek(self._log_offset)
            chunk = f.read()
        last_nl = chunk.rfind(b"\n")
        if last_nl < 0:
            return
        self._log_offset += last_nl + 1
        self._last_line_at = time.time()
        for line in chunk[: last_nl + 1].decode("utf-8", "replace").splitlines():
            ev = self.progress.feed(line)
            if ev:
                self._show_stage(*ev)

    def _show_stage(self, stage: Stage, frac: float) -> None:
        self.panel.status.setText(stage.value)
        self.panel.bar.set_fraction(frac)
        self.panel.percent.setText(f"{round(frac * 100)} %")
        if stage in (Stage.MENU, Stage.WORLD) and not self._hidden_for_game and self.window is not None:
            self._hidden_for_game = True
            self.window.hide_to_tray()

    def _finished(self, code: int) -> None:
        self.timer.stop()
        self.proc = None
        self._set_playing(False)
        self.panel.bar.set_fraction(0)
        self.panel.percent.setText("")
        if self.window is not None and self._hidden_for_game:
            self.window.restore_from_tray()
        self.refresh()
        if code == 0:
            self.panel.status.setText("")
            return
        lp = self.current_pack()
        info = crash_info(localpacks.game_dir(self.ctx.lay, lp.id), self._started_at - 5) if lp else None
        if info:
            parts = [info.description, info.cause]
            if info.suspects:
                parts.append(f"Возможная причина: {info.suspects}")
            self.panel.crash_text.setText("\n".join(x for x in parts if x))
            self._crash_report = info.report
            self.panel.crash_open.show()
        else:
            self.panel.crash_text.setText(f"Код выхода {code}. Отчёта о вылете нет, подробности в logs/latest.log.")
            self._crash_report = None
            self.panel.crash_open.hide()
        self.panel.status.setText("")
        self.panel.crash_box.show()
        anim.fade_slide_in(self.panel.crash_box, dx=0, dy=8, ms=240)

    def _open_report(self) -> None:
        if self._crash_report:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._crash_report)))
