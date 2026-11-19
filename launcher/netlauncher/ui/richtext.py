"""A text view for mod pages: Markdown/HTML with images and animated GIFs loaded in the background."""

from __future__ import annotations

import hashlib
from pathlib import Path

import markdown as md
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QTimer, QUrl
from PySide6.QtGui import QImage, QMovie, QTextDocument
from PySide6.QtWidgets import QTextBrowser

from netlauncher.ui import jobs

MAX_GIFS = 6
CSS = """
body { color: #C9D3E4; font-size: 10.5pt; }
h1, h2, h3 { color: #E8EEF8; }
a { color: #6AAEFF; }
code { background: rgba(255,255,255,0.06); }
img { max-width: 100%; }
"""


class RichText(QTextBrowser):
    def __init__(self, http, cache_dir: Path, parent=None):
        super().__init__(parent)
        self.http, self.cache = http, Path(cache_dir) / "images"
        self.setOpenExternalLinks(True)
        self.setFrameShape(QTextBrowser.Shape.NoFrame)
        self.document().setDefaultStyleSheet(CSS)
        self.setStyleSheet("QTextBrowser { background: transparent; border: none; }")
        self._images: dict[str, QImage] = {}
        self._pending: set[str] = set()
        self._movies: dict[str, QMovie] = {}
        self._html = ""
        self._relayout = QTimer(self)
        self._relayout.setSingleShot(True)
        self._relayout.setInterval(120)
        self._relayout.timeout.connect(self._rerender)

    # ---------- content ----------
    def set_markdown(self, text: str) -> None:
        self.set_html(md.markdown(text or "", extensions=["tables", "fenced_code", "sane_lists"]))

    def set_html(self, html: str) -> None:
        for m in self._movies.values():
            m.stop()
        self._movies.clear()
        self._html = html or ""
        self.setHtml(self._html)

    def loaded(self, url: str) -> bool:
        return url in self._images

    # ---------- images ----------
    def _max_width(self) -> int:
        return max(200, self.viewport().width() - 24)

    def _fit(self, img: QImage) -> QImage:
        w = self._max_width()
        if img.width() > w:
            return img.scaledToWidth(w)
        return img

    def loadResource(self, rtype, url: QUrl):  # noqa: N802
        if rtype == QTextDocument.ResourceType.ImageResource and url.scheme() in ("http", "https"):
            key = url.toString()
            if key in self._images:
                return self._images[key]
            self._fetch(key)
            return QImage()
        return super().loadResource(rtype, url)

    def _fetch(self, url: str) -> None:
        if url in self._pending:
            return
        self._pending.add(url)
        dest = self.cache / hashlib.sha1(url.encode()).hexdigest()

        def job(progress):
            if not dest.exists():
                self.http.download(url, dest)
            return dest.read_bytes()

        jobs.run(job, on_done=lambda data: self._got(url, data), on_error=lambda e: self._pending.discard(url))

    def _got(self, url: str, data: bytes) -> None:
        self._pending.discard(url)
        if data[:6] in (b"GIF87a", b"GIF89a") and len(self._movies) < MAX_GIFS:
            self._animate(url, data)
            return
        img = QImage.fromData(data)
        if img.isNull():
            return
        self._images[url] = self._fit(img)
        self.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl(url), self._images[url])
        self._relayout.start()

    def _animate(self, url: str, data: bytes) -> None:
        buf = QBuffer(self)
        buf.setData(QByteArray(data))
        buf.open(QIODevice.OpenModeFlag.ReadOnly)
        movie = QMovie(buf, QByteArray(b"gif"), self)
        self._movies[url] = movie

        def frame(_n):
            img = self._fit(movie.currentImage())
            first = url not in self._images
            self._images[url] = img
            self.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl(url), img)
            if first:
                self._relayout.start()
            else:
                self.viewport().update()

        movie.frameChanged.connect(frame)
        movie.start()

    def _rerender(self) -> None:
        bar = self.verticalScrollBar().value()
        self.setHtml(self._html)
        self.verticalScrollBar().setValue(bar)
