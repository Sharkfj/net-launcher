"""Snapshots: list copies taken before changes, restore or delete them."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QScrollArea, QWidget

from netlauncher import localpacks, snapshots
from netlauncher.ui import anim, jobs
from netlauncher.ui.pages import common
from netlauncher.ui.pages.common import hbox, human_date, human_size, label, vbox
from netlauncher.ui.pages.home import _error_text
from netlauncher.ui.widgets import AccentButton, GhostButton, GlassCard


class SnapRow(GlassCard):
    restore = Signal(object)
    delete = Signal(object)

    def __init__(self, snap, parent=None):
        super().__init__(parent, radius=14)
        self.snap = snap
        row = hbox(self, (18, 12, 12, 12), 12)
        col = vbox(None, (0, 0, 0, 0), 2)
        col.addWidget(label(snap.reason or "Снимок", 11, 560))
        col.addWidget(label(f"{human_date(snap.created)}, {human_size(snap.size_bytes)}", 9.5, role="faint"))
        row.addLayout(col, 1)
        self.restore_btn = AccentButton("Откатить")
        self.delete_btn = GhostButton("Удалить")
        self.restore_btn.clicked.connect(lambda: self.restore.emit(self.snap))
        self.delete_btn.clicked.connect(lambda: self.delete.emit(self.snap))
        row.addWidget(self.restore_btn)
        row.addWidget(self.delete_btn)


class SnapshotsPage(QWidget):
    def __init__(self, ctx, window=None, parent=None):
        super().__init__(parent)
        self.ctx, self.window = ctx, window
        self.rows: list[SnapRow] = []
        lay = vbox(self, (8, 4, 0, 0), 12)
        lay.addWidget(label("Снимки", 22, 650, display=True))
        lay.addWidget(label("Перед каждой установкой, удалением и обновлением лаунчер копирует моды и настройки. "
                            "Отсюда их можно вернуть.", 10.5, role="muted", wrap=True))
        self.status = label("", 10, role="muted")
        lay.addWidget(self.status)
        inner = QWidget()
        self.list = vbox(inner, (0, 0, 6, 0), 8)
        self.list.addStretch(1)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(inner)
        sa.setFrameShape(QScrollArea.Shape.NoFrame)
        lay.addWidget(sa, 1)

    def _root(self):
        lp = common.current_pack(self.ctx)
        return (self.ctx.lay.snapshots / lp.id, localpacks.game_dir(self.ctx.lay, lp.id)) if lp else (None, None)

    def on_shown(self) -> None:
        self.reload()

    def reload(self) -> None:
        root, _ = self._root()
        for r in self.rows:
            r.setParent(None)
            r.deleteLater()
        self.rows = []
        snaps = snapshots.list_snapshots(root) if root else []
        self.status.setText("" if snaps else "Снимков пока нет. Они появятся после первого изменения модов.")
        for s in snaps:
            r = SnapRow(s)
            r.restore.connect(self._restore)
            r.delete.connect(self._delete)
            self.list.insertWidget(self.list.count() - 1, r)
            self.rows.append(r)
        anim.stagger(self.rows)

    def _restore(self, snap) -> None:
        text = (f"Вернуть моды и настройки к состоянию на {human_date(snap.created)}? "
                "Текущее состояние сохранится отдельным снимком.")
        if not common.confirm(self, "Откат", text, "Откатить"):
            return
        root, gd = self._root()
        self.status.setText("Возвращаю файлы")
        jobs.run(lambda progress: snapshots.restore(root, snap, gd),
                 on_done=lambda _: (self.status.setText("Готово. Файлы возвращены."), self.reload()),
                 on_error=lambda e: self.status.setText(_error_text(e)))

    def _delete(self, snap) -> None:
        if not common.confirm(self, "Удаление", "Удалить этот снимок? Вернуть его будет нельзя.", "Удалить"):
            return
        snapshots.delete(snap)
        self.reload()
