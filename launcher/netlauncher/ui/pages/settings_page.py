"""Settings: game memory and window, launcher options, author access (GitHub), about."""

from __future__ import annotations

from netlauncher.i18n import t

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLineEdit, QScrollArea, QSlider, QSpinBox, QWidget

from netlauncher import __version__, localpacks, discord_presence
from netlauncher.settings import recommended_ram_mb
from netlauncher.ui import anim
from netlauncher.ui.pages import common
from netlauncher.ui.pages.common import hbox, label, vbox
from netlauncher.ui.widgets import GhostButton, GlassCard, Toggle


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
    from netlauncher.i18n import language
    text = t('{x0:g} ГБ', x0=mb / 1024)
    return text.replace(".", ",") if language() == "ru" else text


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
        outer.addWidget(label(t('Настройки'), 22, 650, display=True))
        inner = QWidget()
        lay = vbox(inner, (0, 0, 8, 12), 14)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(inner)
        sa.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(sa, 1)

        # --- game
        game, g = _section(t('Игра'))
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
        g.addWidget(_line(t('Память для игры'), ram_box, t('Рекомендуется {x1} из {x3} ГБ.', x1=gb_text(rec), x3=round(total / 1024))))
        self.ram.setValue(s.max_ram_mb or rec)
        self._ram_text(self.ram.value())
        self.ram.valueChanged.connect(self._ram_changed)
        self.fullscreen = Toggle()
        self.fullscreen.setChecked(s.fullscreen)
        self.fullscreen._set_knob(1.0 if s.fullscreen else 0.0)
        self.fullscreen.toggled.connect(self._fullscreen)
        g.addWidget(_line(t('Полноэкранный режим'), self.fullscreen))
        self.res_box = QWidget()
        rr = hbox(self.res_box, (0, 0, 0, 0), 8)
        self.width_box, self.height_box = QSpinBox(), QSpinBox()
        for sb, v in ((self.width_box, s.width), (self.height_box, s.height)):
            sb.setRange(640, 7680)
            sb.setValue(v)
            sb.valueChanged.connect(self._resolution)
            rr.addWidget(sb)
        self.res_line = _line(t('Размер окна игры'), self.res_box)
        self.res_line.setVisible(not s.fullscreen)
        g.addWidget(self.res_line)
        lay.addWidget(game)

        # --- launcher
        launcher, lc = _section(t('Лаунчер'))
        self.animations = Toggle()
        self.animations.setChecked(s.animations)
        self.animations._set_knob(1.0 if s.animations else 0.0)
        self.animations.toggled.connect(self._animations)
        lc.addWidget(_line(t('Анимации'), self.animations, t('Плавные переходы и движения фигуры.')))
        self.backgrounds = Toggle()
        self.backgrounds.setChecked(s.backgrounds)
        self.backgrounds._set_knob(1.0 if s.backgrounds else 0.0)
        self.backgrounds.toggled.connect(self._backgrounds)
        lc.addWidget(_line(t('Фоны'), self.backgrounds, t('Город и сцена с персонажем за страницами.')))
        self.discord_toggle = Toggle()
        self.discord_toggle.setChecked(s.discord_presence)
        self.discord_toggle._set_knob(float(s.discord_presence))
        self.discord_toggle.toggled.connect(self._save_discord)
        lc.addWidget(_line(t("Активность в Discord"), self.discord_toggle,
                           t("Показывать лаунчер и название запущенной сборки.")))
        self.discord_id = QLineEdit(s.discord_app_id or discord_presence.APPLICATION_ID)
        self.discord_id.setPlaceholderText("Discord Application ID")
        self.discord_id.setMaxLength(20)
        self.discord_id.editingFinished.connect(self._save_discord)
        lc.addWidget(_line("Discord Application ID", self.discord_id))
        self.shortcut_btn = GhostButton(t('Добавить'))
        self.shortcut_btn.clicked.connect(self._shortcut)
        lc.addWidget(_line(t('Ярлык на рабочем столе'), self.shortcut_btn, t('Значок .NET Launcher на рабочем столе.')))
        from netlauncher.ui.pages.home import Chip
        lang_box = QWidget()
        lb = hbox(lang_box, (0, 0, 0, 0), 8)
        from netlauncher.i18n import LANGS
        self.lang_chips = {}
        for key, text in LANGS:
            c = Chip(text, s.language == key)
            c.clicked.connect(lambda key=key: self.set_language(key))
            lb.addWidget(c)
            self.lang_chips[key] = c
        lc.addWidget(_line(t('Язык'), lang_box))
        self.cf_key = QLineEdit(s.curseforge_key)
        self.cf_key.setPlaceholderText(t('Ключ CurseForge API'))
        self.cf_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.cf_key.setMinimumWidth(340)
        self.cf_key.editingFinished.connect(self._save_cf)
        self.friends_url = QLineEdit(s.friends_url)
        self.friends_url.setPlaceholderText("https://friends.example.net")
        self.friends_url.setMinimumWidth(340)
        self.friends_url.editingFinished.connect(self._save_friends)
        lc.addWidget(_line(t('Сервер друзей'), self.friends_url,
                           t('Обычно его задаёт автор сборки. Заполняй, только если тебе дали другой адрес.')))
        lc.addWidget(_line("CurseForge", self.cf_key,
                           t('Поле можно оставить пустым, если CurseForge подключён на сервере друзей.')))
        btns = hbox(None, (0, 4, 0, 0), 8)
        open_dir = GhostButton(t('Открыть папку игры'))
        open_dir.clicked.connect(self._open_game_dir)
        logout = GhostButton(t('Выйти из аккаунта'), danger=True)
        logout.clicked.connect(self.logout)
        btns.addWidget(open_dir)
        btns.addWidget(logout)
        btns.addStretch(1)
        lc.addLayout(btns)
        lay.addWidget(launcher)

        from netlauncher.ui.supporter import RedeemCard
        self.support = RedeemCard(ctx, window)
        lay.addWidget(self.support)

        # --- author
        auth_card, ac = _section(t('Автор сборки'))
        self.author_toggle = Toggle()
        self.author_toggle.setChecked(s.author_mode)
        self.author_toggle._set_knob(1.0 if s.author_mode else 0.0)
        self.author_toggle.toggled.connect(self._author_mode)
        ac.addWidget(_line(t('Публиковать сборки'), self.author_toggle,
                           t('Собирай и публикуй сборки во вкладке «Официальные».')))
        self.author_box = QWidget()
        ab = vbox(self.author_box, (0, 6, 0, 0), 10)
        self.repo = QLineEdit(s.github_repo)
        self.repo.setPlaceholderText(t('пользователь/репозиторий'))
        self.token = QLineEdit(s.github_token)
        self.token.setPlaceholderText(t('Токен GitHub с доступом к репозиторию'))
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.repo.editingFinished.connect(self._save_github)
        self.token.editingFinished.connect(self._save_github)
        ab.addWidget(_line(t('Репозиторий'), self.repo))
        ab.addWidget(_line(t('Токен'), self.token))
        for f in (self.repo, self.token):
            f.setMinimumWidth(340)
        ac.addWidget(self.author_box)
        self.author_box.setVisible(s.author_mode)
        lay.addWidget(auth_card)

        # --- about
        about, abl = _section(t('О лаунчере'))
        abl.addWidget(label(f".NET Launcher {__version__}", 10.5, role="muted"))
        from netlauncher.ui.app import CREDITS
        self.credits = label(t('Разработчик: {name}', name=', '.join(CREDITS)), 10.5)
        abl.addWidget(self.credits)
        abl.addWidget(label(t('Шрифты Oswald и Onest распространяются по лицензии SIL Open Font License.'), 9.5,
                            role="faint", wrap=True))
        lay.addWidget(about)
        lay.addStretch(1)

    def on_shown(self):
        self.support.refresh_status()

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
    def _save_discord(self):
        value = self.discord_id.text().strip()
        if value and not (value.isascii() and value.isdigit() and 17 <= len(value) <= 20 and not value.startswith("0")):
            self._toast(t("Проверь Application ID в Discord Developer Portal."))
            return
        self.ctx.settings.discord_app_id = value
        self.ctx.settings.discord_presence = self.discord_toggle.isChecked()
        self.ctx.save()
        if self.ctx.discord:
            self.ctx.discord.configure()

    def _animations(self, on: bool) -> None:
        self.ctx.settings.animations = on
        anim.set_enabled(on)
        self.ctx.save()

    def set_language(self, lang: str):
        from netlauncher import i18n
        self.ctx.settings.language = lang
        self.ctx.save()
        i18n.set_language(lang)
        if self.window is not None and hasattr(self.window, "rebuild"):
            return self.window.rebuild()
        return None

    def _backgrounds(self, on: bool) -> None:
        self.ctx.settings.backgrounds = on
        self.ctx.save()
        if self.window is not None and hasattr(self.window, "page"):
            home = self.window.page("home")
            if hasattr(home, "update_scene"):
                home.update_scene()

    def _shortcut(self) -> None:
        from netlauncher import shortcut
        try:
            shortcut.create(shortcut.launch_command(), shortcut.icon_path())
        except Exception as e:  # noqa: BLE001
            self._toast(t('Не получилось создать ярлык: {error}', error=str(e)), "error")
            return
        self._toast(t('Ярлык на рабочем столе создан'))

    def _toast(self, text: str, kind: str = "ok") -> None:
        if self.window is not None and hasattr(self.window, "toast"):
            self.window.toast(text, kind)

    def _save_friends(self) -> None:
        self.ctx.settings.friends_url = self.friends_url.text().strip()
        self.ctx.save()

    def _save_cf(self) -> None:
        self.ctx.settings.curseforge_key = self.cf_key.text().strip()
        self.ctx.save()

    def _open_game_dir(self) -> None:
        lp = common.current_pack(self.ctx)
        d = localpacks.game_dir(self.ctx.lay, lp.id) if lp else self.ctx.lay.instances
        d.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))

    def logout(self) -> None:
        acc = self.ctx.accounts.load()
        if acc is None:
            return
        if not common.confirm(self, t('Выход'), t('Выйти из аккаунта {name}?', name=acc.name), t('Выйти')):
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
    def _author_mode(self, on: bool) -> None:
        self.ctx.settings.author_mode = on
        self.author_box.setVisible(on)
        self.ctx.save()

    def _save_github(self) -> None:
        self.ctx.settings.github_repo = self.repo.text().strip()
        self.ctx.settings.github_token = self.token.text().strip()
        self.ctx.save()
