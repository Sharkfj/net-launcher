"""Packs tab: every installed pack with play, open, folder and delete."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLabel, QScrollArea, QWidget

from netlauncher import localpacks
from netlauncher.i18n import t
from netlauncher.ui.pages import common
from netlauncher.ui.pages.common import hbox, label, vbox
from netlauncher.ui.widgets import AccentButton, GhostButton, GlassCard

LOADER_NAMES = {"fabric": "Fabric", "forge": "Forge", "neoforge": "NeoForge", "quilt": "Quilt", "vanilla": "Minecraft"}


class PackRow(GlassCard):
    def __init__(self, lp: localpacks.LocalPack, official: bool, parent=None):
        super().__init__(parent, hoverable=True)
        self.pack_id = lp.id
        row = hbox(self, (18, 14, 14, 14), 10)
        col = vbox(None, (0, 0, 0, 0), 2)
        head = hbox(None, (0, 0, 0, 0), 8)
        self.title = label(lp.name, 12, 620)
        head.addWidget(self.title)
        self.tag = QLabel(t('официальная'))
        self.tag.setStyleSheet("color: #a9cbff; background: rgba(76,154,255,0.12); padding: 2px 8px; border-radius: 6px;")
        self.tag.setVisible(official)
        head.addWidget(self.tag)
        head.addStretch(1)
        col.addLayout(head)
        loader = LOADER_NAMES.get(lp.loader, lp.loader)
        self.meta = label(f"{loader} {lp.mc_version}" if lp.loader != "vanilla" else f"Minecraft {lp.mc_version}", 10,
                          role="muted")
        col.addWidget(self.meta)
        row.addLayout(col, 1)
        self.play_btn = AccentButton(t('Играть'))
        self.open_btn = GhostButton(t('Открыть'))
        self.folder_btn = GhostButton(t('Открыть папку'))
        self.delete_btn = GhostButton(t('Удалить'), danger=True)
        for b in (self.play_btn, self.open_btn, self.folder_btn, self.delete_btn):
            row.addWidget(b)


class PacksPage(QWidget):
    def __init__(self, ctx, window=None, parent=None):
        super().__init__(parent)
        self.ctx, self.window = ctx, window
        outer = vbox(self, (16, 8, 16, 16), 10)
        top = hbox(None, (0, 0, 0, 0), 10)
        top.addWidget(label(t('Сборки'), 22, 600, display=True))
        top.addStretch(1)
        self.new_btn = GhostButton(t('Новая сборка'))
        self.new_btn.clicked.connect(self._new_pack)
        top.addWidget(self.new_btn)
        outer.addLayout(top)
        self.empty = label(t('Сборок пока нет. Поставь сборку во вкладке «Официальные» или создай свою.'), 10.5,
                           role="muted", wrap=True)
        outer.addWidget(self.empty)
        inner = QWidget()
        self.list = vbox(inner, (0, 4, 0, 0), 10)
        self.list.addStretch(1)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(inner)
        sa.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(sa, 1)
        self.rows: list[PackRow] = []
        self.refresh()

    def on_shown(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        for r in self.rows:
            r.setParent(None)
            r.deleteLater()
        self.rows = []
        cat = getattr(self.ctx, "catalog", None)
        packs = localpacks.list_installed(self.ctx.lay)
        self.empty.setVisible(not packs)

        def is_official(lp):
            return lp.official or (cat is not None and cat.get(lp.id) is not None)
        packs.sort(key=lambda lp: (not is_official(lp), lp.name.lower()))
        for lp in packs:
            official = is_official(lp)
            r = PackRow(lp, official)
            r.play_btn.clicked.connect(lambda _=False, pid=lp.id: self._play(pid))
            r.open_btn.clicked.connect(lambda _=False, pid=lp.id: self._open(pid))
            r.folder_btn.clicked.connect(lambda _=False, pid=lp.id: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(localpacks.game_dir(self.ctx.lay, pid)))))
            r.delete_btn.clicked.connect(lambda _=False, lp=lp: self._delete(lp))
            self.list.insertWidget(self.list.count() - 1, r)
            self.rows.append(r)

    def _select(self, pack_id: str) -> None:
        home = self.window.page("home") if self.window is not None else None
        if home is not None and hasattr(home, "pick_pack"):
            home.pick_pack(pack_id)
        else:
            self.ctx.settings.selected_pack = pack_id
            self.ctx.save()

    def _play(self, pack_id: str) -> None:
        self._select(pack_id)
        if self.window is not None:
            self.window.open_page("home")
            home = self.window.page("home")
            if hasattr(home, "play"):
                home.play()

    def _open(self, pack_id: str) -> None:
        self._select(pack_id)
        if self.window is not None and hasattr(self.window, "open_pack"):
            self.window.open_pack(pack_id)

    def _new_pack(self) -> None:
        if self.window is None:
            return
        self.window.open_page("home")
        home = self.window.page("home")
        if hasattr(home, "open_creator"):
            home.open_creator()

    def _delete(self, lp: localpacks.LocalPack) -> None:
        ok, keep = common.confirm_with_option(
            self, t('Удаление сборки'), t('Удалить сборку «{name}»? Моды, настройки и снимки удалятся.', name=lp.name),
            t('Удалить'), t('Сохранить миры'), True)
        if not ok:
            return
        kept = localpacks.delete(self.ctx.lay, lp.id, keep_worlds=keep)
        if self.ctx.settings.selected_pack == lp.id:
            rest = localpacks.list_installed(self.ctx.lay)
            self.ctx.settings.selected_pack = rest[0].id if rest else ""
            self.ctx.save()
        if self.window is not None:
            home = self.window.page("home")
            if hasattr(home, "refresh"):
                home.refresh()
            if hasattr(self.window, "toast"):
                self.window.toast(t('Сборка удалена. Миры лежат в папке backups.') if kept else t('Сборка удалена.'))
        self.refresh()
