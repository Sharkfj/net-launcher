"""Home: Ely.by login, pack overview, install/import, play with live loading progress."""

from __future__ import annotations

from netlauncher.i18n import t

import time
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import (QFileDialog, QInputDialog, QLabel, QLineEdit, QPushButton, QSizePolicy, QStackedWidget,
                               QWidget)

from netlauncher import localpacks, skin
from netlauncher.auth_ely import (Account, AuthUnavailable, BadCredentials, NeedLogin, TwoFactorRequired,
                                  ensure_valid, offline_account, valid_nick)
from netlauncher.author import new_pack_id
from netlauncher.catalog import Catalog, PackEntry, is_newer
from functools import partial
from netlauncher.catalog import resolve

resolve_catalog = partial(resolve, report_offline=True)
from netlauncher.importer import find_instances, import_instance, read_versions
from netlauncher import coop
from netlauncher.launch import GameProcess, LaunchSpec, LogProgress, Stage, apply_fullscreen, build_command, crash_info
from netlauncher.localpacks import LocalPack
from netlauncher.net import HashMismatch, HttpError, Offline
from netlauncher.pack import MrPack, add_manual, apply_update, load_state, plan_update
from netlauncher.settings import recommended_ram_mb
from netlauncher.ui import anim, jobs
from netlauncher.ui.pages import common
from netlauncher.ui.pages.common import hbox, label, plural, vbox
from netlauncher.ui.skinview import default_skin, face
from netlauncher.ui.theme import DISPLAY as DISPLAY_FAMILY, font, qcolor
from netlauncher.ui.widgets import AccentButton, GhostButton, GlassCard, SmoothBar, Toggle

LOADER_NAMES = {"neoforge": "NeoForge", "fabric": "Fabric", "forge": "Forge", "quilt": "Quilt", "vanilla": ""}
REGISTER_URL = "https://account.ely.by/register"
ELY_SKIN_UPLOAD = "https://ely.by/load"


def _error_text(e: BaseException) -> str:
    from netlauncher import integrity
    if isinstance(e, integrity.NeedsInternet):
        return t('Часть файлов сборки пропала или изменилась. Подключись к интернету, и лаунчер вернёт их.')
    if isinstance(e, integrity.NotRepaired):
        names = ", ".join(Path(p).name for p in (e.report.missing + e.report.changed)[:3])
        return t('Не получилось вернуть файлы сборки: {names}. Удали сборку во вкладке «Сборки» и поставь заново во вкладке «Официальные». Миры при удалении сохранятся.', names=names)
    if isinstance(e, (Offline, AuthUnavailable)):
        return t('Нет связи с сервером. Проверь интернет и попробуй ещё раз.')
    if isinstance(e, HashMismatch):
        return t('Файл {name} скачался с ошибкой. Попробуй ещё раз.', name=e.path.name)
    if isinstance(e, HttpError):
        return t('Сервер ответил ошибкой {status}. Попробуй позже.', status=e.status)
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
        lay.addWidget(label(t('Вход'), 22, 650, display=True))
        self.hint = label(t('Нужен аккаунт Ely.by: с ним работают скины и вход на сервер.'), 10.5, role="muted",
                          wrap=True)
        lay.addWidget(self.hint)
        lay.addSpacing(6)
        self.user = QLineEdit()
        self.user.setPlaceholderText(t('Логин или почта'))
        self.password = QLineEdit()
        self.password.setPlaceholderText(t('Пароль'))
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.totp = QLineEdit()
        self.totp.setPlaceholderText(t('Код из приложения'))
        self.totp.setMaxLength(8)
        self.totp.hide()
        for w in (self.user, self.password, self.totp):
            w.returnPressed.connect(self.submit)
            lay.addWidget(w)
        self.error = label("", 10, role="danger", wrap=True)
        lay.addWidget(self.error)
        self.button = AccentButton(t('Войти'))
        self.button.clicked.connect(self.submit)
        lay.addWidget(self.button)
        reg = GhostButton(t('Создать аккаунт на Ely.by'))
        reg.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(REGISTER_URL)))
        lay.addWidget(reg)
        self.guest_btn = GhostButton(t('Играть без входа'))
        self.guest_btn.clicked.connect(self._guest)
        lay.addWidget(self.guest_btn)
        lay.addSpacing(4)
        ms_row = hbox(None, (0, 0, 0, 0), 10)
        self.ms_button = GhostButton(t('Войти через Microsoft'))
        from netlauncher.auth_ms import MS_CLIENT_ID
        self.ms_button.setEnabled(bool(MS_CLIENT_ID))
        ms_row.addWidget(self.ms_button, 1)
        self.ms_note = label(t('В разработке'), 9.5, role="faint")
        self.ms_note.setVisible(not MS_CLIENT_ID)
        ms_row.addWidget(self.ms_note)
        lay.addLayout(ms_row)
        row.addWidget(card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(2)

    def _guest(self) -> None:
        name, ok = QInputDialog.getText(self, t('Играть без входа'), t('Ник для одиночной игры'))
        if not ok:
            return
        if not valid_nick(name):
            self.error.setText(t('Введи от 3 до 16 символов: латинские буквы, цифры или _.'))
            return
        self._done(offline_account(name))

    def set_message(self, text: str) -> None:
        self.error.setText(text)

    def submit(self) -> None:
        user, pw, code = self.user.text().strip(), self.password.text(), self.totp.text().strip()
        if not user or not pw:
            self.error.setText(t('Введи логин и пароль.'))
            return
        if self.totp.isVisible() and not code:
            self.error.setText(t('Введи код из приложения.'))
            return
        self.error.setText("")
        self.button.setEnabled(False)
        self.button.setText(t('Вхожу'))
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
            self.error.setText(t('На аккаунте включена двухфакторная защита. Введи код из приложения.'))
        elif isinstance(e, BadCredentials):
            self.error.setText(t('Неверный логин или пароль.') if not self.totp.isVisible()
                               else t('Неверный пароль или код.'))
        elif isinstance(e, AuthUnavailable):
            self.error.setText(t('Ely.by не отвечает. Проверь интернет и попробуй ещё раз.'))
        else:
            self.error.setText(_error_text(e))

    def _reset_button(self):
        self.button.setEnabled(True)
        self.button.setText(t('Войти'))


# ---------------------------------------------------------------- first run: theme
class WelcomePanel(QWidget):
    done = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = vbox(self, (8, 0, 8, 0), 12)
        lay.addStretch(1)
        self.title = label(t('Добро пожаловать'), 30, 650, display=True)
        lay.addWidget(self.title)
        lay.addWidget(label(t('Выбери язык. Поменять его можно в настройках.'), 11, role="muted"))
        lay.addSpacing(10)
        from netlauncher.i18n import LANGS, language
        lrow = hbox(None, (0, 0, 0, 0), 8)
        lrow.addWidget(label(t('Язык'), 10.5, 520))
        self.lang_chips = {}
        for key, text in LANGS:
            c = Chip(text, key == language())
            c.clicked.connect(lambda key=key: self.pick_language(key))
            lrow.addWidget(c)
            self.lang_chips[key] = c
        lrow.addStretch(1)
        lay.addLayout(lrow)
        lay.addSpacing(10)
        srow = hbox(None, (0, 0, 0, 0), 10)
        self.shortcut = Toggle()
        self.shortcut.setChecked(True)
        self.shortcut._set_knob(1.0)
        srow.addWidget(self.shortcut)
        srow.addWidget(label(t('Ярлык на рабочем столе'), 10.5, 520))
        srow.addStretch(1)
        lay.addLayout(srow)
        lay.addSpacing(14)
        self.next_btn = AccentButton(t('Дальше'))
        self.next_btn.clicked.connect(self.done.emit)
        lay.addWidget(self.next_btn, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addStretch(2)

    language_picked = Signal(str)

    def pick_language(self, lang: str):
        self.language_picked.emit(lang)
        return getattr(self, "_rebuilt", None)


# ---------------------------------------------------------------- no packs yet
class EmptyPanel(QWidget):
    install_entry = Signal(object)
    import_from = Signal(object)
    create = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = vbox(self, (8, 0, 8, 0), 10)
        lay.addWidget(label(t('Сборок пока нет'), 30, 650, display=True))
        lay.addWidget(label(t('Поставь сборку из списка, перенеси свою из PineconeMC или создай новую.'), 11,
                            role="muted"))
        lay.addSpacing(6)
        self.create_btn = GhostButton(t('Создать свою сборку'))
        self.create_btn.clicked.connect(self.create.emit)
        lay.addWidget(self.create_btn, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addSpacing(8)
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
            b = AccentButton(t('Установить'))
            b.clicked.connect(lambda _=False, e=e: self.install_entry.emit(e))
            self.catalog_buttons.append(b)
            self._rows.append(self._row(e.name, e.description or f"Minecraft {e.mc_version}", b))
        for inst in instances:
            b = GhostButton(t('Перенести «{name}»', name=inst.name))
            b.clicked.connect(lambda _=False, i=inst: self.import_from.emit(i))
            self.import_buttons.append(b)
            self._rows.append(self._row(f"PineconeMC: {inst.name}",
                                        t('Скопирую моды, настройки и миры. В PineconeMC всё останется как было.'), b))
        for w in self._rows:
            self.list.addWidget(w)
        anim.stagger(self._rows)
        self.note.setText("" if self._rows else
                          t('Список сборок не загрузился, а в PineconeMC сборок не нашлось. Проверь интернет.'))


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
        self.step.setText(t('Готовлю'))
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
        lay.addWidget(label(t('Один файл нужно скачать вручную'), 22, 650, display=True))
        self.text = label("", 11, role="muted", wrap=True)
        lay.addWidget(self.text)
        row = hbox()
        self.open_btn = AccentButton(t('Открыть страницу мода'))
        self.pick_btn = GhostButton(t('Выбрать скачанный файл'))
        row.addWidget(self.open_btn)
        row.addWidget(self.pick_btn)
        row.addStretch(1)
        lay.addLayout(row)
        self.drop = label(t('Или перетащи файл в это окно.'), 10, role="faint")
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
        self.text.setText(t('{name} нельзя скачать автоматически: автор запретил перезаливать мод. Скачай файл {name2} со страницы мода, лаунчер проверит его и положит на место.', name=m.name, name2=Path(m.path).name))
        self.open_btn.setEnabled(bool(m.page_url))

    def _open(self):
        if self.missing and self.missing[0].page_url:
            QDesktopServices.openUrl(QUrl(self.missing[0].page_url))

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(self, t('Файл мода'), str(Path.home() / "Downloads"), t('Моды (*.jar)'))
        if path:
            self.accept_file(Path(path))

    def accept_file(self, path: Path) -> None:
        try:
            m = add_manual(self.pack_index, self.game_dir, path)
        except HashMismatch:
            self.error.setText(t('Это другой файл или другая версия. Нужен именно {name}.', name=Path(self.missing[0].path).name))
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


# ---------------------------------------------------------------- create your own pack
class CreatePanel(QWidget):
    create = Signal(str, str, str, str)
    cancel = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from netlauncher.ui.widgets import CompactCombo
        from netlauncher import instances
        lay = vbox(self, (8, 0, 8, 0), 12)
        lay.addStretch(1)
        lay.addWidget(label(t('Новая сборка'), 26, 650, display=True))
        lay.addWidget(label(t('Выбери версию Minecraft и загрузчик модов. Моды добавишь потом в разделе «Моды».'),
                            11, role="muted", wrap=True))
        lay.addSpacing(8)
        self.name = QLineEdit()
        self.name.setPlaceholderText(t('Название'))
        self.name.setMaximumWidth(420)
        lay.addWidget(self.name)
        self.version = CompactCombo()
        self.version.setAccessibleName(t('Версия Minecraft'))
        self.version.setMinimumWidth(200)
        row = hbox(None, (0, 0, 0, 0), 10)
        row.addWidget(label(t('Версия Minecraft'), 10.5, 520))
        row.addWidget(self.version)
        row.addStretch(1)
        lay.addLayout(row)
        chips = hbox(None, (0, 0, 0, 0), 8)
        self.loader = "neoforge"
        self.loader_chips = {}
        for key, text in instances.LOADERS:
            c = Chip(t(text), key == self.loader)
            c.clicked.connect(lambda key=key: self.pick_loader(key))
            chips.addWidget(c)
            self.loader_chips[key] = c
        chips.addStretch(1)
        lay.addLayout(chips)
        self.loader_version = CompactCombo()
        self.loader_version.setAccessibleName(t('Версия загрузчика'))
        self.loader_version.setMinimumWidth(200)
        self.loader_line = QWidget()
        lr = hbox(self.loader_line, (0, 0, 0, 0), 10)
        lr.addWidget(label(t('Версия загрузчика'), 10.5, 520))
        lr.addWidget(self.loader_version)
        lr.addStretch(1)
        lay.addWidget(self.loader_line)
        fps_control = common.FpsControl()
        fps_control.setMaximumWidth(485)
        self.fps = fps_control.toggle
        lay.addWidget(fps_control)
        self.hint = label("", 10, role="muted", wrap=True)
        lay.addWidget(self.hint)
        brow = hbox(None, (0, 0, 0, 0), 8)
        self.create_btn = AccentButton(t('Создать'))
        back = GhostButton(t('Отмена'))
        self.create_btn.clicked.connect(self._create)
        back.clicked.connect(self.cancel.emit)
        brow.addWidget(self.create_btn)
        brow.addWidget(back)
        brow.addStretch(1)
        lay.addLayout(brow)
        lay.addStretch(2)
        self.version.currentIndexChanged.connect(lambda _i: self._load_loader_versions())
        self._seq = 0

    def open(self) -> None:
        from netlauncher import instances
        self.name.clear()
        self.fps.setChecked(False)
        self.hint.setText(t('Загружаю список версий'))
        self.create_btn.setEnabled(False)
        jobs.run(lambda progress: instances.minecraft_releases(), on_done=self._versions,
                 on_error=lambda e: self.hint.setText(_error_text(e)))

    def _versions(self, vs: list[str]) -> None:
        self.version.blockSignals(True)
        self.version.clear()
        self.version.addItems(vs)
        self.version.blockSignals(False)
        self.hint.setText("")
        self._load_loader_versions()

    def pick_loader(self, key: str) -> None:
        self.loader = key
        for k, c in self.loader_chips.items():
            c.active = k == key
            c.update()
        self.loader_line.setVisible(key != "vanilla")
        self._load_loader_versions()

    def _load_loader_versions(self) -> None:
        from netlauncher import instances
        mc = self.version.currentText()
        self.loader_version.clear()
        if self.loader == "vanilla":
            self.hint.setText("")
            self.create_btn.setEnabled(bool(mc))
            return
        if not mc:
            return
        self._seq += 1
        seq, loader = self._seq, self.loader
        self.create_btn.setEnabled(False)
        self.hint.setText(t('Загружаю версии загрузчика'))
        jobs.run(lambda progress: instances.loader_versions(loader, mc),
                 on_done=lambda vs: self._loader_versions(seq, loader, vs),
                 on_error=lambda e: self.hint.setText(_error_text(e)))

    def _loader_versions(self, seq: int, loader: str, vs: list[str]) -> None:
        if seq != self._seq:
            return
        names = dict(LOADER_NAMES)
        if not vs:
            self.hint.setText(t('Для этой версии Minecraft нет {x1}. Выбери другую версию или загрузчик.', x1=names.get(loader, loader)))
            self.create_btn.setEnabled(False)
            return
        self.loader_version.addItems(vs)
        self.hint.setText("")
        self.create_btn.setEnabled(True)

    def _create(self) -> None:
        mc = self.version.currentText()
        name = self.name.text().strip() or f"Minecraft {mc}"
        lv = "" if self.loader == "vanilla" else self.loader_version.currentText()
        self.create.emit(name, mc, self.loader, lv)


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


class PackSwitch(QPushButton):
    """Current pack name with a menu of installed packs, above the title."""

    picked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(font(10.5, 520))
        self.setFlat(True)
        self.setStyleSheet("QPushButton { color: #c3cee3; border: none; padding: 4px 0; text-align: left; }"
                           "QPushButton:hover { color: #e8eefb; }")
        self.packs: list[LocalPack] = []
        self.clicked.connect(self._open)

    def set_packs(self, packs: list[LocalPack], active: LocalPack) -> None:
        self.packs = packs
        self.setText(f"{active.name}  ▾" if len(packs) > 1 else active.name)
        self.setEnabled(len(packs) > 1)

    def _open(self) -> None:
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        for lp in self.packs:
            m.addAction(lp.name, lambda lp=lp: self.picked.emit(lp.id))
        m.exec(self.mapToGlobal(self.rect().bottomLeft()))


def title_font(text: str) -> QFont:
    f = font(40, 600, DISPLAY_FAMILY)
    f.setPixelSize(150 if len(text) <= 6 else 76)
    return f


class PackPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = hbox(self, (16, 0, 24, 0), 24)
        left = vbox(None, (0, 0, 0, 0), 0)
        left.addStretch(1)
        top_row = hbox(None, (0, 0, 0, 0), 12)
        self.switch = PackSwitch()
        top_row.addWidget(self.switch)
        self.new_btn = GhostButton(t('Новая сборка'))
        top_row.addWidget(self.new_btn)
        top_row.addStretch(1)
        left.addLayout(top_row)
        left.addSpacing(6)
        self.title = QLabel("")
        self.title.setFont(title_font(""))
        self.title.setWordWrap(True)
        self.title.setMaximumWidth(620)
        left.addWidget(self.title)
        left.addSpacing(14)
        self.desc = label("", 12, role="muted", wrap=True)
        self.desc.setMaximumWidth(560)
        left.addWidget(self.desc)
        left.addSpacing(4)
        self.meta = label("", 10, role="faint")
        left.addWidget(self.meta)
        left.addSpacing(22)
        buttons = hbox(None, (0, 0, 0, 0), 10)
        self.play_btn = AccentButton(t('Играть'), icon="play", big=True)
        self.continue_btn = GhostButton("")
        self.server_btn = GhostButton(t('Играть на сервере'))
        for b in (self.continue_btn, self.server_btn):
            b.setMinimumHeight(56)
        buttons.addWidget(self.play_btn)
        buttons.addWidget(self.continue_btn)
        buttons.addWidget(self.server_btn)
        buttons.addStretch(1)
        left.addLayout(buttons)
        left.addSpacing(16)
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
        left.addSpacing(12)

        self.crash_box = GlassCard()
        cb = vbox(self.crash_box, (20, 16, 20, 16), 6)
        self.crash_title = label(t('Игра закрылась с ошибкой'), 12.5, 650, role="danger")
        self.crash_text = label("", 10.5, role="muted", wrap=True)
        crow = hbox(None, (0, 6, 0, 0), 8)
        self.crash_open = GhostButton(t('Открыть отчёт'))
        self.crash_hide = GhostButton(t('Скрыть'))
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
        self.update_btn = AccentButton(t('Обновить'))
        ub.addWidget(self.update_label, 1)
        ub.addWidget(self.update_btn)
        self.update_box.setMaximumWidth(620)
        self.update_box.hide()
        left.addWidget(self.update_box)
        left.addSpacing(8)

        self.news_box = GlassCard()
        nb = vbox(self.news_box, (20, 16, 20, 18), 6)
        self.news_title = label("", 11, 600)
        self.news_text = label("", 10.5, role="muted", wrap=True)
        nb.addWidget(self.news_title)
        nb.addWidget(self.news_text)
        self.news_box.setMaximumWidth(620)
        self.news_box.hide()
        left.addWidget(self.news_box)
        left.addSpacing(30)
        root.addLayout(left, 3)

        right = vbox(None, (0, 0, 0, 30), 8)
        right.addStretch(1)
        self.skin_bar = GlassCard()
        self.skin_bar.setMaximumWidth(340)
        sb = vbox(self.skin_bar, (16, 12, 16, 14), 8)
        self.skin_hint = label(t('Это предпросмотр. Чтобы скин видели все, загрузи его на Ely.by.'), 10,
                               role="muted", wrap=True)
        sb.addWidget(self.skin_hint)
        srow = hbox(None, (0, 0, 0, 0), 10)
        srow.addWidget(label(t('Тонкие руки'), 10, 520))
        self.slim = Toggle()
        srow.addWidget(self.slim)
        srow.addStretch(1)
        sb.addLayout(srow)
        brow = hbox(None, (0, 0, 0, 0), 8)
        self.skin_upload = AccentButton(t('Загрузить на Ely.by'))
        self.skin_reload = GhostButton(t('Обновить'))
        self.skin_cancel = GhostButton(t('Отменить'))
        for b in (self.skin_upload, self.skin_reload, self.skin_cancel):
            brow.addWidget(b)
        sb.addLayout(brow)
        self.skin_bar.hide()
        right.addWidget(self.skin_bar, 0, Qt.AlignmentFlag.AlignRight)
        root.addLayout(right, 2)

    def set_title(self, text: str) -> None:
        self.title.setFont(title_font(text))
        self.title.setText(text)


# ---------------------------------------------------------------- page
class HomePage(QWidget):
    startup_done = False

    def __init__(self, ctx, window=None, parent=None):
        super().__init__(parent)
        self.ctx, self.window = ctx, window
        self.process_factory = GameProcess
        self.catalog: Catalog | None = None
        self.proc = None
        self.progress: LogProgress | None = None
        self._last_line_at = 0.0
        self._started_at = 0.0
        self._hidden_for_game = False
        self._crash_report: Path | None = None

        lay = vbox(self)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)
        self.welcome = WelcomePanel()
        self.login = LoginPanel(ctx)
        self.empty = EmptyPanel()
        self.panel = PackPanel()
        self.busy = ProgressPanel()
        self.manual = ManualPanel()
        self.creator = CreatePanel()
        self._modes = {"welcome": self.welcome, "login": self.login, "empty": self.empty, "pack": self.panel, "install": self.busy,
                       "manual": self.manual, "create": self.creator}
        for w in self._modes.values():
            self.stack.addWidget(w)

        self.login.logged_in.connect(self._on_login)
        self.welcome.done.connect(self._welcome_done)
        self.welcome.language_picked.connect(self._language_picked)
        self.empty.install_entry.connect(self.install_entry)
        self.empty.import_from.connect(self.import_instance)
        self.empty.create.connect(self.open_creator)
        self.manual.finished.connect(self.refresh)
        self.panel.new_btn.clicked.connect(self.open_creator)
        self.panel.switch.picked.connect(self.pick_pack)
        self.panel.play_btn.installEventFilter(self)
        self.creator.cancel.connect(self.refresh)
        self.creator.create.connect(self.create_pack)
        self.panel.play_btn.clicked.connect(self._play_clicked)
        self.panel.continue_btn.clicked.connect(self._continue)
        self.panel.server_btn.clicked.connect(self._server)
        self.panel.update_btn.clicked.connect(self._update)
        self.panel.crash_open.clicked.connect(self._open_report)
        self.panel.crash_hide.clicked.connect(self.panel.crash_box.hide)
        self.panel.slim.toggled.connect(self._slim_changed)
        self.panel.skin_upload.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(ELY_SKIN_UPLOAD)))
        self.panel.skin_reload.clicked.connect(self.reload_skin)
        self.panel.skin_cancel.clicked.connect(self.cancel_skin_preview)
        self._preview_png: bytes | None = None
        self.skin_account = None
        self.account_skin = None
        self._skin_request = 0

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

    def _language_picked(self, lang: str) -> None:
        from netlauncher import i18n
        self.ctx.settings.language = lang
        self.ctx.save()
        i18n.set_language(lang)
        if self.window is not None and hasattr(self.window, "rebuild"):
            self.welcome._rebuilt = self.window.rebuild()

    def _welcome_done(self) -> None:
        s = self.ctx.settings
        if not s.shortcut_asked:
            s.shortcut_asked = True
            if self.welcome.shortcut.isChecked():
                from netlauncher import shortcut
                try:
                    shortcut.create(shortcut.launch_command(), shortcut.icon_path())
                except Exception:  # noqa: BLE001
                    pass
        s.first_run_done = True
        self.ctx.save()
        self.refresh()

    def refresh(self) -> None:
        if not self.ctx.settings.first_run_done:
            self._set_scene(None)
            self._set_mode("welcome")
            return
        acc = self.ctx.accounts.load()
        if self.window is not None and hasattr(self.window, "set_account"):
            self.window.set_account(acc)
        if acc is None:
            self._set_scene(None)
            self._set_mode("login")
            return
        lp = self.current_pack()
        if lp is None:
            self._set_scene(None)
            self.empty.fill(self.catalog, find_instances(), set())
            self._set_mode("empty")
            return
        self._show_pack(lp)
        self._set_scene(lp, animate=getattr(self, "_switching", False))
        self._set_mode("pack")

    def _show_pack(self, lp: LocalPack) -> None:
        p = self.panel
        packs = localpacks.list_installed(self.ctx.lay)
        p.switch.set_packs(packs, lp)
        p.set_title(lp.name)
        p.desc.setText(lp.description)
        p.desc.setVisible(bool(lp.description))
        n = localpacks.mod_count(self.ctx.lay, lp.id)
        loader = LOADER_NAMES.get(lp.loader, lp.loader)
        meta = f"Minecraft {lp.mc_version}" + (t(' с {loader}', loader=loader) if loader else "")
        p.meta.setText(f"{meta}, {n} {plural(n, 'мод', 'мода', 'модов')}")
        world = localpacks.newest_world(self.ctx.lay, lp.id)
        p.continue_btn.setText(t('Продолжить «{world}»', world=world) if world else "")
        p.continue_btn.setVisible(bool(world))
        p.server_btn.setVisible(bool(lp.server) and not getattr(self.window, "offline", False) and not getattr(self.ctx.accounts.load(), "offline", False))
        entry = self.catalog.get(lp.id) if self.catalog else None
        outdated = self.play_action() == "update"
        if outdated:
            p.update_label.setText(t('Вышла версия {version}. Сейчас стоит {version2}.', version=entry.version, version2=lp.version))
            p.update_box.show()
        else:
            p.update_box.hide()
        # an outdated official pack is only updated, never started: the server expects the new version
        p.update_btn.hide()
        p.play_btn.setText(t('Обновить') if outdated else t('Играть'))
        p.play_btn.icon_name = None if outdated else "play"
        p.play_btn.updateGeometry()
        p.play_btn.update()
        if outdated:
            p.continue_btn.hide()
            p.server_btn.hide()
        if entry and entry.changelog:
            p.news_title.setText(t('Что нового в {version}', version=entry.version))
            p.news_text.setText(entry.changelog)
            p.news_box.show()
        else:
            p.news_box.hide()

    # ---------- scene ----------
    def scene_kind(self, lp: LocalPack | None) -> str:
        if lp is None:
            return "plain"
        if lp.official or (self.catalog is not None and self.catalog.get(lp.id) is not None):
            return "city"
        return "studio"

    def _set_scene(self, lp: LocalPack | None, animate: bool = False) -> None:
        if self.window is None or not hasattr(self.window, "scene"):
            return
        kind = self.scene_kind(lp) if self.ctx.settings.backgrounds else "plain"
        self.window.scene.set_scene(kind, animate=animate, force=animate)
        if kind == "studio" and hasattr(self.window.scene, "studio"):
            from netlauncher.ui.supporter import active
            styled = active(self.ctx)
            self.window.scene.studio.set_style(lp.backdrop if styled else "studio", lp.pose if styled else "idle")
            self.window.scene.update()

    def update_scene(self) -> None:
        self._set_scene(self.current_pack() if self.mode() == "pack" else None)

    def pick_pack(self, pack_id: str) -> None:
        if pack_id == self.ctx.settings.selected_pack:
            return
        self.ctx.settings.selected_pack = pack_id
        self.ctx.save()
        self._switching = True
        try:
            self.refresh()
        finally:
            self._switching = False
        p = self.panel
        anim.stagger([p.title, p.desc, p.meta, p.play_btn], step_ms=60)

    _pick_pack = pick_pack

    def eventFilter(self, obj: QObject, e: QEvent) -> bool:  # noqa: N802
        if obj is self.panel.play_btn and self.window is not None and hasattr(self.window, "skin"):
            if e.type() == QEvent.Type.Enter and self.window.skin.reaction == "idle":
                self.window.skin_react("ready")
            elif e.type() == QEvent.Type.Leave and self.window.skin.reaction == "ready":
                self.window.skin_react("idle")
        return super().eventFilter(obj, e)

    def play_action(self) -> str:
        """'update' when an installed official pack has a newer version in the catalog, else 'play'."""
        lp = self.current_pack()
        entry = self.catalog.get(lp.id) if (self.catalog and lp) else None
        return "update" if entry is not None and is_newer(entry.version, lp.version) else "play"

    def _play_clicked(self) -> None:
        if self.play_action() == "update":
            self._update()
            return
        if self.window is not None and hasattr(self.window, "skin_react"):
            self.window.skin_react("turn_head")
        self.play()

    def _on_login(self, acc: Account) -> None:
        self.refresh()
        self._load_skin(acc)

    def _load_skin(self, acc: Account | None) -> None:
        self._skin_request += 1
        request = self._skin_request
        identity = acc.uuid if acc else None
        if self.skin_account != identity:
            self.account_skin = None
            self.skin_account = identity
        if acc is None:
            return
        def loaded(value):
            current = self.ctx.accounts.load()
            if request == self._skin_request and current and current.uuid == identity:
                self._skin_loaded(value)
        jobs.run(lambda progress: skin.fetch(self.ctx.http, acc.name, self.ctx.lay.cache),
                 on_done=loaded, on_error=lambda e: None)

    # ---------- skin change ----------
    def pick_skin(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, t('Файл скина'), str(Path.home()), t('Скины (*.png)'))
        if path:
            self.preview_skin(Path(path))

    def preview_skin(self, path: Path) -> None:
        p = self.panel
        p.skin_bar.show()
        try:
            data = Path(path).read_bytes()
            skin.check_skin(data)
        except (OSError, ValueError) as e:
            p.skin_hint.setText(t(str(e)) if isinstance(e, ValueError) else t('Не получилось открыть файл.'))
            return
        self._preview_png = data
        p.skin_hint.setText(t('Это предпросмотр. Чтобы скин видели все, загрузи его на Ely.by.'))
        self._scene_skin(skin.Skin(data, p.slim.isChecked()))

    def _slim_changed(self, on: bool) -> None:
        if self._preview_png is not None:
            self._scene_skin(skin.Skin(self._preview_png, on))

    def cancel_skin_preview(self) -> None:
        self._preview_png = None
        self.panel.skin_bar.hide()
        self._load_skin(self.ctx.accounts.load())

    def reload_skin(self) -> None:
        acc = self.ctx.accounts.load()
        if acc is None:
            return
        self.panel.skin_hint.setText(t('Загружаю скин с Ely.by'))
        self._skin_request += 1
        request = self._skin_request
        def current():
            account = self.ctx.accounts.load()
            return request == self._skin_request and account and account.uuid == acc.uuid
        jobs.run(lambda progress: skin.fetch(self.ctx.http, acc.name, self.ctx.lay.cache, force=True),
                 on_done=lambda value: self._skin_reloaded(value) if current() else None,
                 on_error=lambda e: self.panel.skin_hint.setText(_error_text(e)) if current() else None)

    def _skin_reloaded(self, sk) -> None:
        self._preview_png = None
        if sk is None:
            self.panel.skin_hint.setText(t('На Ely.by у аккаунта нет скина.'))
            return
        self.panel.skin_bar.hide()
        self._skin_loaded(sk)

    def _skin_loaded(self, sk) -> None:
        self.account_skin = sk
        page = getattr(self.window, "_pages", {}).get("profile")
        if page and hasattr(page, "show_account_skin"):
            page.show_account_skin(default_skin(), self.skin_account)
        self._scene_skin(default_skin())
        if self.window is not None and hasattr(self.window, "set_face"):
            self.window.set_face(face(default_skin().png))

    def _scene_skin(self, sk) -> None:
        if self.window is not None and hasattr(self.window, "skin"):
            self.window.skin.set_skin(sk)

    def _load_catalog(self) -> None:
        self.startup_done = False
        jobs.run(lambda progress: resolve_catalog(self.ctx.http), on_done=self._catalog_loaded,
                 on_error=lambda e: self._catalog_loaded(None, offline=isinstance(e, Offline)))

    def _catalog_loaded(self, cat: Catalog | None, offline: bool = False) -> None:
        self.catalog = cat
        self.ctx.catalog = cat
        if self.window and hasattr(self.window, "set_offline"):
            self.window.set_offline(offline)
        self.startup_done = True
        if self.window is not None and hasattr(self.window, "offer_update"):
            self.window.offer_update(cat)
            if self.window.current_page() == "official":
                self.window.page("official").refresh_cards()
        if self.mode() in ("pack", "empty"):
            self.refresh()

    # ---------- install / update / import ----------
    def install_entry(self, entry: PackEntry) -> None:
        self.busy.start(t('Установка {name}', name=entry.name))
        self._set_mode("install")
        jobs.run(self._install_job, entry, on_done=self._installed, on_error=self._install_failed,
                 on_progress=self.busy.progress)

    def _install_job(self, entry: PackEntry, progress):
        lay = self.ctx.lay
        gd = localpacks.game_dir(lay, entry.id)
        progress(t('Скачиваю описание сборки'), 0, 0)
        mp_path = self.ctx.http.download(entry.mrpack_url, lay.cache / "packs" / f"{entry.id}-{entry.version}.mrpack",
                                         sha1=entry.mrpack_sha1 or None)
        pack = MrPack.open(mp_path)
        state = load_state(gd)
        if state is not None:
            from netlauncher import worlds
            progress(t('Сохраняю копии миров'), 0, 0)
            worlds.backup_all(lay, entry.id, gd)
        plan = plan_update(pack, gd, state)
        apply_update(plan, pack, gd, self.ctx.http, lay.cache, lay.snapshots / entry.id,
                     lambda name, cur, mx: progress(t('Скачиваю {name}', name=name), cur, mx))
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
        name, ok = QInputDialog.getText(self, t('Название сборки'), t('Как назвать сборку в лаунчере?'), text=default)
        if not ok or not name.strip():
            return
        self.busy.start(t('Перенос {x1}', x1=name.strip()))
        self._set_mode("install")
        jobs.run(self._import_job, inst, name.strip(), on_done=lambda r: self.refresh(),
                 on_error=self._install_failed, on_progress=self.busy.progress)

    def _import_job(self, inst: Path, name: str, progress):
        lay = self.ctx.lay
        mc, loader, lv = read_versions(inst)
        existing = {p.id for p in localpacks.list_installed(lay)}
        pid = new_pack_id(name, existing)
        gd = localpacks.game_dir(lay, pid)
        import_instance(inst, gd, lambda item, cur, mx: progress(t('Копирую {item}', item=item), cur, mx))
        localpacks.save(lay, LocalPack(pid, name, "0.0", mc, loader, lv))
        self.ctx.installer.ensure(mc, loader, lv, lambda s, c, m: progress(f"Minecraft: {s}", c, m))
        self.ctx.settings.selected_pack = pid
        self.ctx.save()
        return pid

    # ---------- own packs ----------
    def open_creator(self) -> None:
        self.creator.open()
        self._set_mode("create")

    def create_pack(self, name: str, mc: str, loader: str, lv: str) -> None:
        from netlauncher import instances
        use_fps = self.creator.fps.isChecked()
        self.busy.start(t('Создаю {name}', name=name))
        self._set_mode("install")

        def job(progress):
            lp = instances.create(self.ctx.lay, name, mc, loader, lv)
            self.ctx.installer.ensure(mc, loader, lv, lambda s, c, m: progress(f"Minecraft: {s}", c, m))
            if use_fps:
                from netlauncher import fps
                fps.configure(self.ctx, lp, True, progress)
            return lp

        def done(lp):
            self.ctx.settings.selected_pack = lp.id
            self.ctx.save()
            self.refresh()

        jobs.run(job, on_done=done, on_error=self._install_failed, on_progress=self.busy.progress)

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
        if self.play_action() == "update":
            self._update()
            return
        self.panel.crash_box.hide()
        self._set_playing(True)
        self.panel.status.setText(t('Проверяю вход и файлы игры'))
        self.panel.percent.setText("")
        self.panel.bar.set_fraction(0.01)

        locked = localpacks.locked(lp, self.ctx.settings, self.catalog)
        entry = self.catalog.get(lp.id) if self.catalog else None
        mrpack_url = entry.mrpack_url if entry and entry.version == lp.version else ""
        has_catalog = self.catalog is not None

        def verify(progress):
            from netlauncher import integrity
            progress(t('Проверяю файлы сборки'), 0, 0)
            gd = localpacks.game_dir(self.ctx.lay, lp.id)
            report = integrity.check(gd, load_state(gd))
            if report.ok:
                return
            progress(t('Возвращаю файлы сборки'), 0, 0)
            try:
                left = integrity.repair(report, self.ctx.lay, lp, self.ctx.http,
                                        lambda name, c, m: progress(t('Скачиваю {name}', name=name), c, m),
                                        mrpack_url=mrpack_url)
            except Offline as e:
                raise integrity.NeedsInternet() from e
            except integrity.NoPackFile as e:
                if not has_catalog:
                    raise integrity.NeedsInternet() from e
                raise integrity.NotRepaired(report) from e
            if left.missing or left.changed:
                raise integrity.NotRepaired(left)

        disconnected = bool(getattr(self.window, "offline", False))

        def prepare(progress):
            if locked:
                verify(progress)
            acc = ensure_valid(self.ctx.auth, self.ctx.accounts, disconnected=disconnected)
            game = self.ctx.installer.ensure(lp.mc_version, lp.loader, lp.loader_version,
                                             lambda s, c, m: progress(f"Minecraft: {s}", c, m))
            if acc.offline and server:
                raise ValueError(t('Для игры на сервере нужен вход через Ely.by и интернет.'))
            authlib = None if acc.offline else self.ctx.installer.ensure_authlib()
            return acc, game, authlib

        jobs.run(prepare, on_done=lambda r: self._launch(lp, r, world, server), on_error=self._prepare_failed,
                 on_progress=lambda s, c, m: self.panel.status.setText(s))

    def _prepare_failed(self, e: BaseException) -> None:
        self._set_playing(False)
        self.panel.bar.set_fraction(0)
        if isinstance(e, NeedLogin):
            self.login.set_message(t('Сессия Ely.by истекла. Войди ещё раз.'))
            self.refresh()
            return
        self.panel.status.setText(_error_text(e))

    def _launch(self, lp: LocalPack, prepared, world, server) -> None:
        acc, game, authlib = prepared
        if self.window and hasattr(self.window, "set_offline") and not getattr(self.ctx.accounts.load(), "offline", False):
            self.window.set_offline(acc.offline)
        s = self.ctx.settings
        gd = localpacks.game_dir(self.ctx.lay, lp.id)
        ram = s.max_ram_mb or recommended_ram_mb(localpacks.total_ram_mb())
        spec = LaunchSpec(game, self.ctx.lay.minecraft, gd, acc, ram, s.fullscreen, s.width, s.height, authlib,
                          world=world, server=server, fps=lp.fps)
        try:
            apply_fullscreen(gd, s.fullscreen)
            cmd = build_command(spec)
            self.proc = self.process_factory(gd)
            self._started_at = time.time()
            self._session_log = coop.SessionLog(self.proc.log_path)
            self._hosting = lp if not server and not getattr(acc, "offline", False) and (gd / coop.OPT_IN).is_file() else None
            self._announced = set()
            self.proc.start(cmd, gd)
            if self.window is not None and hasattr(self.window, "set_game_running"):
                self.window.set_game_running(True)
        except Exception as e:  # noqa: BLE001
            self.proc = None
            self._prepare_failed(e)
            return
        self.progress = LogProgress()
        self._last_line_at = time.time()
        self._hidden_for_game = False
        self.panel.status.setText(t('Запускаю игру'))
        if self.window is not None:
            self.window.game_status = ("playing", lp.name, server or "")
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
        lines = self._session_log.lines()
        if lines:
            self._last_line_at = time.time()
        for line in lines:
            if self._hosting and (domain := coop.assigned_domain(line)) and domain not in self._announced:
                self._announced.add(domain)
                self._invite_to_world(self._hosting, domain)
            ev = self.progress.feed(line)
            if ev:
                self._show_stage(*ev)

    def _invite_to_world(self, pack, domain):
        if not self.window or not self.ctx.friends_url():
            return
        gd = localpacks.game_dir(self.ctx.lay, pack.id)
        if not (gd / coop.OPT_IN).is_file():
            return
        identity = coop.source_id(self.ctx.lay, pack)
        self.window.game_status = ("playing", pack.name, domain)
        self.window.game_pack = {"pack_id": identity, "pack_version": pack.version}
        client = self.ctx.friends()
        jobs.run(lambda progress: coop.invite_friends(client, pack.name, identity, pack.version, domain),
                 on_error=lambda exc: self.window.toast(str(exc)))

    def _show_stage(self, stage: Stage, frac: float) -> None:
        self.panel.status.setText(t(stage.value))
        self.panel.bar.set_fraction(frac)
        self.panel.percent.setText(f"{round(frac * 100)} %")
        if stage in (Stage.MENU, Stage.WORLD) and not self._hidden_for_game and self.window is not None:
            self._hidden_for_game = True
            self.window.hide_to_tray()

    def _finished(self, code: int) -> None:
        self.timer.stop()
        self.proc = None
        if self.window is not None and hasattr(self.window, "set_game_running"):
            self.window.set_game_running(False)
        if self.window is not None:
            self.window.game_status = ("launcher", "", "")
            self.window.game_pack = {}
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
                parts.append(t('Возможная причина: {suspects}', suspects=info.suspects))
            self.panel.crash_text.setText("\n".join(x for x in parts if x))
            self._crash_report = info.report
            self.panel.crash_open.show()
        else:
            self.panel.crash_text.setText(t('Код выхода {code}. Отчёта о вылете нет, подробности в logs/latest.log.', code=code))
            self._crash_report = None
            self.panel.crash_open.hide()
        self.panel.status.setText("")
        self.panel.crash_box.show()
        anim.fade_slide_in(self.panel.crash_box, dx=0, dy=8, ms=240)

    def _open_report(self) -> None:
        if self._crash_report:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._crash_report)))
