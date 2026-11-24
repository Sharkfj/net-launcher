"""Screenshots section of a pack: a grid of previews, newest first; open, copy or show in the folder."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication, QImage, QImageReader, QPixmap
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QMenu, QScrollArea, QWidget

from netlauncher import localpacks
from netlauncher.i18n import t
from netlauncher.ui import anim, jobs
from netlauncher.ui.pages.common import label, vbox

THUMB = QSize(220, 124)
EXTS = (".png", ".jpg", ".jpeg")


def _thumb_path(cache: Path, shot: Path) -> Path:
    st = shot.stat()
    key = hashlib.sha1(f"{shot}|{st.st_mtime_ns}|{st.st_size}".encode()).hexdigest()
    return cache / "thumbs" / f"{key}.jpg"


def make_thumb(cache: Path, shot: Path) -> Path:
    """Cover-crop the screenshot to 220×124 and keep it in cache/thumbs/."""
    dest = _thumb_path(cache, shot)
    if dest.exists():
        return dest
    reader = QImageReader(str(shot))
    size = reader.size()
    if size.isValid() and size.width() > 0 and size.height() > 0:
        k = max(THUMB.width() / size.width(), THUMB.height() / size.height())
        reader.setScaledSize(QSize(max(1, round(size.width() * k)), max(1, round(size.height() * k))))
    img = reader.read()
    if img.isNull():
        raise OSError(f"cannot read {shot}")
    x, y = max(0, (img.width() - THUMB.width()) // 2), max(0, (img.height() - THUMB.height()) // 2)
    img = img.copy(QRect(x, y, min(THUMB.width(), img.width()), min(THUMB.height(), img.height())))
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(dest), "JPG", 85)
    return dest


def list_shots(game_dir: Path) -> list[Path]:
    d = game_dir / "screenshots"
    if not d.is_dir():
        return []
    shots = [p for p in d.iterdir() if p.is_file() and p.suffix.lower() in EXTS]
    return sorted(shots, key=lambda p: p.stat().st_mtime, reverse=True)


class ScreenshotTile(QFrame):
    share = Signal(object)

    def __init__(self, path: Path, thumb: Path, parent=None):
        super().__init__(parent)
        self.path = path
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(THUMB.width())
        lay = vbox(self, (0, 0, 0, 0), 6)
        self.thumb = QLabel()
        self.thumb.setFixedSize(THUMB)
        self.thumb.setPixmap(QPixmap(str(thumb)))
        self.thumb.setStyleSheet("border-radius: 10px; background: rgba(255,255,255,0.04);")
        lay.addWidget(self.thumb)
        when = datetime.fromtimestamp(path.stat().st_mtime)
        lay.addWidget(label(when.strftime("%d.%m.%Y %H:%M"), 9.5, role="muted"))
        self.setToolTip(path.name)

    def open(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.path)))

    def copy(self) -> None:
        QGuiApplication.clipboard().setImage(QImage(str(self.path)))

    def open_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.path.parent)))

    def mouseReleaseEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self.open()

    def contextMenuEvent(self, e):  # noqa: N802
        m = QMenu(self)
        m.addAction(t('Открыть'), self.open)
        m.addAction(t('Скопировать'), self.copy)
        m.addAction(t('Отправить в чат'), lambda:self.share.emit(self.path))
        m.addAction(t('Открыть папку'), self.open_folder)
        m.exec(e.globalPos())


class ScreenshotsView(QWidget):
    def __init__(self, ctx, window=None, parent=None):
        super().__init__(parent)
        self.ctx, self.window = ctx, window
        self.tiles: list[ScreenshotTile] = []
        self._seq = 0
        self._dir: Path | None = None
        lay = vbox(self, (0, 4, 0, 0), 10)
        self.empty = label(t('Скриншотов пока нет. Нажми F2 в игре, и скриншот появится здесь.'), 10.5, role="muted", wrap=True)
        self.empty.hide()
        lay.addWidget(self.empty)
        inner = QWidget()
        self.grid = QGridLayout(inner)
        self.grid.setContentsMargins(0, 0, 6, 0)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(14)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(inner)
        sa.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll = sa
        lay.addWidget(sa, 1)

    def on_shown(self) -> None:
        from netlauncher.ui.pages import common
        lp = common.current_pack(self.ctx)
        self.show_dir(localpacks.game_dir(self.ctx.lay, lp.id) if lp else None)

    def reset(self) -> None:
        self._seq += 1
        self._clear()

    def show_dir(self, game_dir: Path | None) -> None:
        self._seq += 1
        seq, cache = self._seq, self.ctx.lay.cache
        self._dir = game_dir

        def work(progress):
            out = []
            for shot in list_shots(game_dir) if game_dir else []:
                try:
                    out.append((shot, make_thumb(cache, shot)))
                except OSError:
                    continue
            return out
        jobs.run(work, on_done=lambda r: self._show(seq, r), on_error=lambda e: self._show(seq, []))

    def _clear(self) -> None:
        for tile in self.tiles:
            tile.setParent(None)
            tile.deleteLater()
        self.tiles = []

    def _show(self, seq: int, shots) -> None:
        if seq != self._seq:
            return
        self._clear()
        self.empty.setVisible(not shots)
        for shot, thumb in shots:
            tile = ScreenshotTile(shot, thumb)
            if self.window is not None:
                tile.share.connect(lambda path:self.window.page("friends").chats.share_screenshot(path))
            self.tiles.append(tile)
        self._layout_tiles()
        anim.stagger(self.tiles[:12])

    def _columns(self) -> int:
        w = self.scroll.viewport().width() or self.width()
        return max(1, (w + 12) // (THUMB.width() + 12))

    def _layout_tiles(self) -> None:
        cols = self._columns()
        for i, tile in enumerate(self.tiles):
            self.grid.addWidget(tile, i // cols, i % cols)

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        if self.tiles:
            self._layout_tiles()
