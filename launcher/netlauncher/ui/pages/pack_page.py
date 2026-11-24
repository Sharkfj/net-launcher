"""One pack: header plus sections (mods, resource packs, shaders, snapshots, screenshots, worlds)."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QStackedWidget, QWidget

from netlauncher import localpacks
from netlauncher.i18n import t
from netlauncher.ui import anim
from netlauncher.ui.pages.common import FpsControl, hbox, label, vbox
from netlauncher.ui.pages.coop_control import CoopControl
from netlauncher.ui.pages.home import Chip
from netlauncher.ui.pages.packs_page import LOADER_NAMES
from netlauncher.ui.widgets import AccentButton, GhostButton

ORDER = ("mods", "resourcepacks", "shaders", "snapshots", "screenshots", "worlds")
LABELS = {"mods": "Моды", "resourcepacks": "Ресурспаки", "shaders": "Шейдеры", "snapshots": "Снимки",
          "screenshots": "Скриншоты", "worlds": "Миры"}
EDITABLE = ("mods", "resourcepacks", "shaders", "snapshots")


class PackPage(QWidget):
    def __init__(self, ctx, window=None, parent=None):
        super().__init__(parent)
        self.ctx, self.window = ctx, window
        self.pack_id: str | None = None
        self.locked = False
        outer = vbox(self, (16, 8, 16, 16), 12)
        head = hbox(None, (0, 0, 0, 0), 10)
        col = vbox(None, (0, 0, 0, 0), 2)
        self.back_btn = GhostButton(t('Все сборки'))
        self.back_btn.clicked.connect(lambda: self.window.open_page("packs") if self.window is not None else None)
        top = hbox(None, (0, 0, 0, 0), 0)
        top.addWidget(self.back_btn)
        top.addStretch(1)
        col.addLayout(top)
        self.title = label("", 22, 600, display=True)
        col.addWidget(self.title)
        self.meta = label("", 10, role="muted")
        col.addWidget(self.meta)
        self.coop = CoopControl(ctx, window)
        col.addWidget(self.coop)
        head.addLayout(col, 1)
        from netlauncher.ui.supporter import edit_style
        self.style_btn = GhostButton(t("Оформление"))
        self.style_btn.clicked.connect(lambda: edit_style(ctx, window, self.pack_id, self))
        self.style_btn.hide()
        head.addWidget(self.style_btn)
        self.folder_btn = GhostButton(t('Открыть папку'))
        self.folder_btn.clicked.connect(self._open_folder)
        self.play_btn = AccentButton(t('Играть'), icon="play")
        self.play_btn.clicked.connect(self._play)
        self.fps_control = FpsControl()
        self.fps_toggle = self.fps_control.toggle
        self.fps_toggle.clicked.connect(self._configure_fps)
        self._fps_busy = False
        head.addWidget(self.folder_btn)
        head.addWidget(self.play_btn)
        outer.addLayout(head)
        outer.addWidget(self.fps_control)

        tabs = hbox(None, (0, 0, 0, 0), 8)
        self.tabs: dict[str, Chip] = {}
        for key in ORDER:
            c = Chip(t(LABELS[key]), False)
            c.clicked.connect(lambda key=key: self.open_section(key))
            tabs.addWidget(c)
            self.tabs[key] = c
        tabs.addStretch(1)
        outer.addLayout(tabs)
        self.locked_note = label(t('Сборку собирает автор, менять её нельзя.'), 10.5, role="muted", wrap=True)
        self.locked_note.hide()
        outer.addWidget(self.locked_note)

        from netlauncher.ui.pages.content import ContentPage
        from netlauncher.ui.pages.screenshots import ScreenshotsView
        from netlauncher.ui.pages.snapshots_page import SnapshotsPage
        from netlauncher.ui.pages.worlds import WorldsView
        self.stack = QStackedWidget()
        self.sections: dict[str, QWidget] = {
            "mods": ContentPage(ctx, window, "mod"),
            "resourcepacks": ContentPage(ctx, window, "resourcepack"),
            "shaders": ContentPage(ctx, window, "shader"),
            "snapshots": SnapshotsPage(ctx, window),
            "screenshots": ScreenshotsView(ctx, window),
            "worlds": WorldsView(ctx, window),
        }
        for key in ORDER:
            sec = self.sections[key]
            if hasattr(sec, "heading"):
                sec.heading.hide()
            if sec.layout() is not None:
                sec.layout().setContentsMargins(0, 4, 0, 0)
            self.stack.addWidget(sec)
        outer.addWidget(self.stack, 1)
        self._section = "mods"

    # ---------- state ----------
    def current_section(self) -> str:
        return self._section

    def show_pack(self, pack_id: str | None, section: str | None = None) -> None:
        changed = pack_id != self.pack_id
        self.pack_id = pack_id
        lp = localpacks.get(self.ctx.lay, pack_id) if pack_id else None
        if lp is None:
            self.title.setText(t('Сборка не выбрана'))
            self.meta.setText("")
            self.locked = False
        else:
            self.title.setText(lp.name)
            loader = LOADER_NAMES.get(lp.loader, lp.loader)
            self.meta.setText(f"Minecraft {lp.mc_version}" if lp.loader == "vanilla" else f"{loader} {lp.mc_version}")
            self.locked = localpacks.locked(lp, self.ctx.settings, getattr(self.ctx, "catalog", None))
        cat = getattr(self.ctx, "catalog", None)
        self.fps_control.setVisible(bool(lp and not lp.official and not (cat and cat.get(lp.id))))
        self.fps_toggle.setChecked(bool(lp and lp.fps))
        self.fps_toggle.setEnabled(not self._fps_busy)
        for key in EDITABLE:
            self.tabs[key].setVisible(not self.locked)
        self.locked_note.setVisible(self.locked)
        from netlauncher.ui.supporter import active
        catalog = getattr(self.ctx, "catalog", None)
        self.style_btn.setVisible(bool(lp and not lp.official and not (catalog and catalog.get(lp.id)) and active(self.ctx)))
        self.coop.show_pack(lp)
        self.folder_btn.setEnabled(lp is not None)
        self.play_btn.setEnabled(lp is not None)
        if changed:
            for sec in self.sections.values():
                if hasattr(sec, "reset"):
                    sec.reset()
        want = section or (self._section if not changed else None) or ("worlds" if self.locked else "mods")
        if self.locked and want in EDITABLE:
            want = "worlds"
        self._show_section(want)

    def open_section(self, name: str) -> None:
        if name not in self.sections or (self.locked and name in EDITABLE):
            return
        if name == self._section:
            return
        self._show_section(name)
        anim.fade_slide_in(self.sections[name], dx=0, dy=8, ms=220)

    def _show_section(self, name: str) -> None:
        self._section = name
        for key, c in self.tabs.items():
            c.active = key == name
            c.update()
        sec = self.sections[name]
        self.stack.setCurrentWidget(sec)
        if hasattr(sec, "on_shown"):
            sec.on_shown()

    def on_shown(self) -> None:
        from netlauncher.ui.pages import common
        lp = common.current_pack(self.ctx)
        self.show_pack(lp.id if lp else None)

    # ---------- actions ----------
    def _configure_fps(self, enabled):
        from netlauncher import fps
        from netlauncher.ui import jobs
        from netlauncher.ui.pages.home import _error_text
        lp = localpacks.get(self.ctx.lay, self.pack_id)
        if not lp or self._fps_busy:
            return
        self._fps_busy = True
        self.fps_toggle.setEnabled(False)

        def finished(error=None):
            self._fps_busy = False
            self.show_pack(self.pack_id)
            if error and self.window:
                self.window.toast(_error_text(error), "error")

        jobs.run(lambda progress: fps.configure(self.ctx, lp, enabled, progress),
                 on_done=lambda _: finished(), on_error=finished)

    def _open_folder(self) -> None:
        if self.pack_id:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(localpacks.game_dir(self.ctx.lay, self.pack_id))))

    def _play(self) -> None:
        if self.window is None or not self.pack_id:
            return
        self.window.open_page("home")
        home = self.window.page("home")
        if hasattr(home, "play"):
            home.play()
