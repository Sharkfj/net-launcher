"""Settings: game memory and window, launcher options, pack author tools, about."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QComboBox, QLineEdit, QPlainTextEdit, QScrollArea, QSlider, QSpinBox, QWidget

from netlauncher import __version__, author, localpacks
from netlauncher.catalog import PackEntry
from netlauncher.curseforge import CurseForge
from netlauncher.pack import MrPack
from netlauncher.settings import recommended_ram_mb
from netlauncher.ui import anim, jobs
from netlauncher.ui.pages import common
from netlauncher.ui.pages.common import hbox, label, vbox
from netlauncher.ui.pages.home import _error_text
from netlauncher.ui.widgets import AccentButton, GhostButton, GlassCard, Toggle


def _section(title: str) -> tuple[GlassCard, object]:
    card = GlassCard(radius=16)
    lay = vbox(card, (22, 18, 22, 20), 12)
    lay.addWidget(label(title, 13, 620))
    return card, lay


def _line(text: str, widget: QWidget, hint: str = "") -> QWidget:
    w = QWidget()
    row = hbox(w, (0, 0, 0, 0), 12)
    col = vbox(None, (0, 0, 0, 0), 1)
    col.addWidget(label(text, 10.5, 520))
    if hint:
        col.addWidget(label(hint, 9.5, role="faint", wrap=True))
    row.addLayout(col, 1)
    row.addWidget(widget)
    return w


def gb_text(mb: int) -> str:
    return f"{mb / 1024:g} ГБ".replace(".", ",")


def next_version(v: str) -> str:
    parts = (v or "0.0").split(".")
    try:
        parts[-1] = str(int(parts[-1]) + 1)
    except ValueError:
        parts.append("1")
    return ".".join(parts)


class SettingsPage(QWidget):
    def __init__(self, ctx, window=None, parent=None):
        super().__init__(parent)
        self.ctx, self.window = ctx, window
        s = ctx.settings
        outer = vbox(self, (8, 4, 0, 0), 12)
        outer.addWidget(label("Настройки", 22, 650, display=True))
        inner = QWidget()
        lay = vbox(inner, (0, 0, 8, 12), 14)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(inner)
        sa.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(sa, 1)

        # --- game
        game, g = _section("Игра")
        total = localpacks.total_ram_mb()
        rec = recommended_ram_mb(total)
        self.ram = QSlider(Qt.Orientation.Horizontal)
        self.ram.setRange(2048, max(2048, min(16384, total - 1024)))
        self.ram.setSingleStep(512)
        self.ram.setPageStep(1024)
        self.ram.setFixedWidth(260)
        self.ram_label = label("", 10.5, 560)
        ram_box = QWidget()
        rb = hbox(ram_box, (0, 0, 0, 0), 12)
        rb.addWidget(self.ram)
        rb.addWidget(self.ram_label)
        g.addWidget(_line("Память для игры", ram_box, f"Рекомендуется {gb_text(rec)} из {round(total / 1024)} ГБ."))
        self.ram.setValue(s.max_ram_mb or rec)
        self._ram_text(self.ram.value())
        self.ram.valueChanged.connect(self._ram_changed)
        self.fullscreen = Toggle()
        self.fullscreen.setChecked(s.fullscreen)
        self.fullscreen._set_knob(1.0 if s.fullscreen else 0.0)
        self.fullscreen.toggled.connect(self._fullscreen)
        g.addWidget(_line("Полноэкранный режим", self.fullscreen))
        self.res_box = QWidget()
        rr = hbox(self.res_box, (0, 0, 0, 0), 8)
        self.width_box, self.height_box = QSpinBox(), QSpinBox()
        for sb, v in ((self.width_box, s.width), (self.height_box, s.height)):
            sb.setRange(640, 7680)
            sb.setValue(v)
            sb.valueChanged.connect(self._resolution)
            rr.addWidget(sb)
        self.res_line = _line("Размер окна игры", self.res_box)
        self.res_line.setVisible(not s.fullscreen)
        g.addWidget(self.res_line)
        lay.addWidget(game)

        # --- launcher
        launcher, lc = _section("Лаунчер")
        self.animations = Toggle()
        self.animations.setChecked(s.animations)
        self.animations._set_knob(1.0 if s.animations else 0.0)
        self.animations.toggled.connect(self._animations)
        lc.addWidget(_line("Анимации", self.animations, "Плавные переходы и движения фигуры."))
        from netlauncher.ui.pages.home import Chip
        theme_box = QWidget()
        tb = hbox(theme_box, (0, 0, 0, 0), 8)
        self.theme_chips = {}
        for key, text in (("glass", "Стекло"), ("solid", "Сплошная")):
            c = Chip(text, s.theme == key)
            c.clicked.connect(lambda key=key: self.set_theme(key))
            tb.addWidget(c)
            self.theme_chips[key] = c
        lc.addWidget(_line("Тема", theme_box, "Стекло: прозрачное окно с размытием. Сплошная: без прозрачности."))
        self.cf_key = QLineEdit(s.curseforge_key)
        self.cf_key.setPlaceholderText("Ключ CurseForge API")
        self.cf_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.cf_key.setMinimumWidth(340)
        self.cf_key.editingFinished.connect(self._save_cf)
        lc.addWidget(_line("CurseForge", self.cf_key,
                           "Нужен для поиска модов на CurseForge. Бесплатный ключ выдают на console.curseforge.com."))
        btns = hbox(None, (0, 4, 0, 0), 8)
        open_dir = GhostButton("Открыть папку игры")
        open_dir.clicked.connect(self._open_game_dir)
        logout = GhostButton("Выйти из аккаунта", danger=True)
        logout.clicked.connect(self._logout)
        btns.addWidget(open_dir)
        btns.addWidget(logout)
        btns.addStretch(1)
        lc.addLayout(btns)
        lay.addWidget(launcher)

        # --- author
        auth_card, ac = _section("Автор сборки")
        self.author_toggle = Toggle()
        self.author_toggle.setChecked(s.author_mode)
        self.author_toggle._set_knob(1.0 if s.author_mode else 0.0)
        self.author_toggle.toggled.connect(self._author_mode)
        ac.addWidget(_line("Публиковать сборки", self.author_toggle,
                           "Сборки и обновления уходят на GitHub, игроки получают их при следующем запуске."))
        self.author_box = QWidget()
        ab = vbox(self.author_box, (0, 6, 0, 0), 10)
        self.repo = QLineEdit(s.github_repo)
        self.repo.setPlaceholderText("пользователь/репозиторий")
        self.token = QLineEdit(s.github_token)
        self.token.setPlaceholderText("Токен GitHub с доступом к репозиторию")
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.repo.editingFinished.connect(self._save_github)
        self.token.editingFinished.connect(self._save_github)
        ab.addWidget(_line("Репозиторий", self.repo))
        ab.addWidget(_line("Токен", self.token))
        self.author_pack = QComboBox()
        self.author_pack.currentIndexChanged.connect(self._pack_picked)
        ab.addWidget(_line("Сборка", self.author_pack, "Новая сборка появится в каталоге после первой публикации."))
        self.pack_desc = QLineEdit()
        self.pack_desc.setPlaceholderText("Одно предложение о сборке")
        self.pack_server = QLineEdit()
        self.pack_server.setPlaceholderText("play.example.net:25565")
        self.pack_version = QLineEdit()
        self.pack_version.setFixedWidth(120)
        ab.addWidget(_line("Описание", self.pack_desc))
        ab.addWidget(_line("Адрес сервера", self.pack_server, "Если указать, у игроков появится «Играть на сервере»."))
        ab.addWidget(_line("Версия", self.pack_version))
        for f in (self.repo, self.token, self.pack_desc, self.pack_server):
            f.setMinimumWidth(340)
        self.author_pack.setMinimumWidth(200)
        self.changelog = QPlainTextEdit()
        self.changelog.setPlaceholderText("Что изменилось в этой версии")
        self.changelog.setFixedHeight(90)
        ab.addWidget(self.changelog)
        arow = hbox(None, (0, 0, 0, 0), 8)
        self.build_btn = GhostButton("Собрать")
        self.publish_btn = AccentButton("Опубликовать")
        self.publish_btn.setEnabled(False)
        self.build_btn.clicked.connect(self._build)
        self.publish_btn.clicked.connect(self._publish)
        arow.addWidget(self.build_btn)
        arow.addWidget(self.publish_btn)
        arow.addStretch(1)
        ab.addLayout(arow)
        self.author_status = label("", 10, role="muted", wrap=True)
        ab.addWidget(self.author_status)
        ac.addWidget(self.author_box)
        self.author_box.setVisible(s.author_mode)
        lay.addWidget(auth_card)

        # --- about
        about, abl = _section("О лаунчере")
        abl.addWidget(label(f".NET Launcher {__version__}", 10.5, role="muted"))
        from netlauncher.ui.app import CREDITS
        self.credits = label("Разработчики: " + " и ".join(CREDITS), 10.5)
        abl.addWidget(self.credits)
        abl.addWidget(label("Шрифты Unbounded и Onest распространяются по лицензии SIL Open Font License.", 9.5,
                            role="faint", wrap=True))
        lay.addWidget(about)
        lay.addStretch(1)
        self._build_result = None
        self._fill_packs()

    # ---------- game ----------
    def _ram_text(self, v: int) -> None:
        self.ram_label.setText(gb_text(v))

    def _ram_changed(self, v: int) -> None:
        v = round(v / 512) * 512
        self._ram_text(v)
        self.ctx.settings.max_ram_mb = v
        self.ctx.save()

    def _fullscreen(self, on: bool) -> None:
        self.ctx.settings.fullscreen = on
        self.res_line.setVisible(not on)
        self.ctx.save()

    def _resolution(self, _v) -> None:
        self.ctx.settings.width, self.ctx.settings.height = self.width_box.value(), self.height_box.value()
        self.ctx.save()

    # ---------- launcher ----------
    def _animations(self, on: bool) -> None:
        self.ctx.settings.animations = on
        anim.set_enabled(on)
        self.ctx.save()

    def set_theme(self, key: str) -> None:
        self.ctx.settings.theme = key
        self.ctx.save()
        for k, c in self.theme_chips.items():
            c.active = k == key
            c.update()
        if self.window is not None and hasattr(self.window, "set_theme"):
            self.window.set_theme(key)

    def _save_cf(self) -> None:
        self.ctx.settings.curseforge_key = self.cf_key.text().strip()
        self.ctx.save()

    def _open_game_dir(self) -> None:
        lp = common.current_pack(self.ctx)
        d = localpacks.game_dir(self.ctx.lay, lp.id) if lp else self.ctx.lay.instances
        d.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))

    def _logout(self) -> None:
        acc = self.ctx.accounts.load()
        if acc is None:
            return
        if not common.confirm(self, "Выход", f"Выйти из аккаунта {acc.name}?", "Выйти"):
            return
        self.ctx.auth.logout(acc)
        self.ctx.accounts.clear()
        if self.window is not None:
            self.window.set_account(None)
            home = self.window.page("home")
            if hasattr(home, "refresh"):
                home.refresh()
            self.window.open_page("home")

    # ---------- author ----------
    def on_shown(self) -> None:
        self._fill_packs()

    def _author_mode(self, on: bool) -> None:
        self.ctx.settings.author_mode = on
        self.author_box.setVisible(on)
        self.ctx.save()

    def _save_github(self) -> None:
        self.ctx.settings.github_repo = self.repo.text().strip()
        self.ctx.settings.github_token = self.token.text().strip()
        self.ctx.save()

    def _fill_packs(self) -> None:
        self._packs = localpacks.list_installed(self.ctx.lay)
        cur = self.author_pack.currentText()
        self.author_pack.blockSignals(True)
        self.author_pack.clear()
        for lp in self._packs:
            self.author_pack.addItem(lp.name, lp.id)
        idx = max(0, self.author_pack.findText(cur))
        self.author_pack.setCurrentIndex(idx)
        self.author_pack.blockSignals(False)
        self._pack_picked(idx)

    def _selected(self):
        i = self.author_pack.currentIndex()
        return self._packs[i] if 0 <= i < len(self._packs) else None

    def _pack_picked(self, _i) -> None:
        lp = self._selected()
        if lp is None:
            return
        self.pack_desc.setText(lp.description)
        self.pack_server.setText(lp.server)
        self.pack_version.setText(next_version(lp.version))
        self.publish_btn.setEnabled(False)
        self._build_result = None

    def _author_dir(self) -> Path:
        d = self.ctx.lay.cache / "author"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _prev_index(self, pack_id: str):
        built = sorted(self._author_dir().glob(f"{pack_id}-*.mrpack"), key=lambda p: p.stat().st_mtime)
        try:
            return MrPack.open(built[-1]) if built else None
        except Exception:  # noqa: BLE001 - a broken old build just means "no previous version"
            return None

    def _build(self) -> None:
        lp = self._selected()
        if lp is None:
            self.author_status.setText("Сначала установи или перенеси сборку на главной.")
            return
        version = self.pack_version.text().strip()
        if not version:
            self.author_status.setText("Укажи версию, например 0.2.")
            return
        gd = localpacks.game_dir(self.ctx.lay, lp.id)
        changelog = self.changelog.toPlainText().strip()
        self.author_status.setText("Собираю: сверяю моды с Modrinth")
        self.publish_btn.setEnabled(False)
        prev = self._prev_index(lp.id)

        def job(progress):
            cf = CurseForge(self.ctx.http, self.ctx.settings.curseforge_key) if self.ctx.settings.curseforge_key \
                else None
            res = author.build(gd, self.ctx.modrinth, lp.name, version, lp.mc_version, lp.loader, lp.loader_version,
                               changelog, prev, cf=cf)
            path = author.write(res, gd, self._author_dir(), lp.id)
            return res, path

        jobs.run(job, on_done=lambda r: self._built(lp, version, r), on_error=self._author_failed)

    def _built(self, lp, version: str, result) -> None:
        res, path = result
        self._build_result = (lp, version, res, path)
        d = res.diff
        lines = [f"Собрано: {len(res.index.files)} файлов с Modrinth, {len(res.overrides)} своих файлов.",
                 f"Добавлено {len(d.added)}, обновлено {len(d.updated)}, убрано {len(d.removed)}."]
        lines += res.warnings
        self.author_status.setText("\n".join(lines))
        self.publish_btn.setEnabled(True)

    def _publish(self) -> None:
        if not self._build_result:
            return
        lp, version, res, path = self._build_result
        repo, token = self.repo.text().strip(), self.token.text().strip()
        if not repo or not token:
            self.author_status.setText("Укажи репозиторий и токен GitHub.")
            return
        if not common.confirm(self, "Публикация", f"Опубликовать {lp.name} {version} для всех игроков?",
                              "Опубликовать"):
            return
        entry = PackEntry(lp.id, lp.name, self.pack_desc.text().strip(), version, lp.mc_version, lp.loader,
                          lp.loader_version, "", "", res.index.changelog, self.pack_server.text().strip())
        self.author_status.setText("Публикую")
        self.publish_btn.setEnabled(False)

        def job(progress):
            url = author.publish(self.ctx.http, repo, token, entry, path)
            lp.version, lp.description, lp.server = version, entry.description, entry.server
            localpacks.save(self.ctx.lay, lp)
            return url

        jobs.run(job, on_done=self._published, on_error=self._author_failed)

    def _published(self, url: str) -> None:
        self.author_status.setText(f"Опубликовано. Игроки увидят обновление при следующем запуске лаунчера.\n{url}")
        self._fill_packs()

    def _author_failed(self, e: BaseException) -> None:
        self.author_status.setText(_error_text(e))
        self.publish_btn.setEnabled(self._build_result is not None)
