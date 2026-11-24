"""Worlds section of a pack: play a world directly, back it up, put a backup back."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMenu, QScrollArea, QWidget

from netlauncher import localpacks, worlds
from netlauncher.i18n import t
from netlauncher.ui import anim, jobs
from netlauncher.ui.pages import common
from netlauncher.ui.pages.common import hbox, label, vbox
from netlauncher.ui.widgets import AccentButton, GhostButton, GlassCard


def _size(n: int) -> str:
    mb = n / 1024 / 1024
    return t('{x} МБ', x=f"{mb:.1f}" if mb < 10 else f"{mb:.0f}")


class WorldRow(GlassCard):
    def __init__(self, world: worlds.World, saved: list[Path], parent=None):
        super().__init__(parent, hoverable=True)
        from datetime import datetime
        self.world, self.saved = world, saved
        row = hbox(self, (18, 14, 14, 14), 10)
        col = vbox(None, (0, 0, 0, 0), 2)
        self.title = label(world.name, 12, 620)
        col.addWidget(self.title)
        when = datetime.fromtimestamp(world.last_played).strftime("%d.%m.%Y %H:%M")
        copies = t('копий: {n}', n=len(saved)) if saved else t('копий нет')
        self.meta = label(t('Последняя игра {when}, {size}, {copies}', when=when, size=_size(world.size), copies=copies),
                          10, role="muted")
        col.addWidget(self.meta)
        row.addLayout(col, 1)
        self.play_btn = AccentButton(t('Играть'))
        self.backup_btn = GhostButton(t('Сделать копию'))
        self.restore_btn = GhostButton(t('Вернуть копию'))
        self.restore_btn.setEnabled(bool(saved))
        self.folder_btn = GhostButton(t('Открыть папку'))
        for b in (self.play_btn, self.backup_btn, self.restore_btn, self.folder_btn):
            row.addWidget(b)


class WorldsView(QWidget):
    def __init__(self, ctx, window=None, parent=None):
        super().__init__(parent)
        self.ctx, self.window = ctx, window
        self.rows: list[WorldRow] = []
        self._seq = 0
        self.pack_id: str | None = None
        lay = vbox(self, (0, 4, 0, 0), 10)
        self.status = label("", 10, role="muted", wrap=True)
        lay.addWidget(self.status)
        self.empty = label(t('Миров пока нет. Создай мир в игре, и он появится здесь.'), 10.5, role="muted", wrap=True)
        self.empty.hide()
        lay.addWidget(self.empty)
        inner = QWidget()
        self.list = vbox(inner, (0, 0, 6, 0), 8)
        self.list.addStretch(1)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(inner)
        sa.setFrameShape(QScrollArea.Shape.NoFrame)
        lay.addWidget(sa, 1)

    def game_dir(self) -> Path | None:
        return localpacks.game_dir(self.ctx.lay, self.pack_id) if self.pack_id else None

    def on_shown(self) -> None:
        lp = common.current_pack(self.ctx)
        self.pack_id = lp.id if lp else None
        cat = getattr(self.ctx, "catalog", None)
        official = lp is not None and (lp.official or (cat is not None and cat.get(lp.id) is not None))
        keep = t('Хранятся пять последних копий каждого мира.')
        self.status.setText(t('Перед каждым обновлением официальной сборки лаунчер сам копирует миры.') + " " + keep
                            if official else keep)
        self.reload()

    def reset(self) -> None:
        self._seq += 1
        self._fill([])

    def reload(self) -> None:
        self._seq += 1
        seq, gd, pid, lay = self._seq, self.game_dir(), self.pack_id, self.ctx.lay

        def work(progress):
            found = worlds.list_worlds(gd) if gd else []
            return [(w, worlds.backups(lay, pid, w.name)) for w in found]
        jobs.run(work, on_done=lambda r: self._loaded(seq, r), on_error=lambda e: self._loaded(seq, []))

    def _loaded(self, seq: int, items) -> None:
        if seq != self._seq:
            return
        self._fill(items)

    def _fill(self, items) -> None:
        for r in self.rows:
            r.setParent(None)
            r.deleteLater()
        self.rows = []
        self.empty.setVisible(not items and self.pack_id is not None)
        for world, saved in items:
            r = WorldRow(world, saved)
            r.play_btn.clicked.connect(lambda _=False, w=world: self._play(w))
            r.backup_btn.clicked.connect(lambda _=False, w=world, r=r: self._backup(w, r))
            r.restore_btn.clicked.connect(lambda _=False, r=r: self._restore_menu(r))
            r.folder_btn.clicked.connect(lambda _=False, w=world: QDesktopServices.openUrl(QUrl.fromLocalFile(str(w.path))))
            self.list.insertWidget(self.list.count() - 1, r)
            self.rows.append(r)
        anim.stagger(self.rows)

    def _toast(self, text: str) -> None:
        if self.window is not None and hasattr(self.window, "toast"):
            self.window.toast(text)

    def _play(self, world: worlds.World) -> None:
        if self.window is None:
            return
        self.window.open_page("home")
        home = self.window.page("home")
        if hasattr(home, "play"):
            home.play(world=world.name)

    def _backup(self, world: worlds.World, row: WorldRow) -> None:
        row.backup_btn.setEnabled(False)
        row.backup_btn.setText(t('Копирую'))
        pid, lay = self.pack_id, self.ctx.lay

        def done(_):
            self._toast(t('Копия мира «{name}» сделана.', name=world.name))
            self.reload()

        def failed(e):
            self._toast(t('Не получилось скопировать мир: {err}', err=str(e)))
            self.reload()
        jobs.run(lambda progress: worlds.backup(lay, pid, world), on_done=done, on_error=failed)

    def _restore_menu(self, row: WorldRow) -> None:
        m = QMenu(self)
        for z in row.saved:
            when = worlds.taken_at(z)
            m.addAction(when.strftime("%d.%m.%Y %H:%M:%S") if when else z.stem,
                        lambda z=z, row=row: self._restore(row.world, z))
        m.exec(row.restore_btn.mapToGlobal(row.restore_btn.rect().bottomLeft()))

    def _restore(self, world: worlds.World, zip_path: Path) -> None:
        when = worlds.taken_at(zip_path)
        stamp = when.strftime("%d.%m.%Y %H:%M") if when else zip_path.stem
        if not common.confirm(self, t('Вернуть копию'),
                              t('Вернуть мир «{name}» к копии от {stamp}? Перед этим лаунчер сделает копию мира в нынешнем виде.',
                                name=world.name, stamp=stamp), t('Вернуть')):
            return
        gd, pid, lay = self.game_dir(), self.pack_id, self.ctx.lay
        jobs.run(lambda progress: worlds.restore(lay, pid, gd, zip_path),
                 on_done=lambda _: (self._toast(t('Мир «{name}» возвращён к копии от {stamp}.', name=world.name, stamp=stamp)),
                                    self.reload()),
                 on_error=lambda e: self._toast(t('Не получилось вернуть копию: {err}', err=str(e))))
