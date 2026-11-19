"""Mods / resource packs / shader packs: list, toggle, remove, search Modrinth, install, update."""

from __future__ import annotations

import hashlib

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QPainter, QPixmap
from PySide6.QtWidgets import QComboBox, QLineEdit, QMenu, QScrollArea, QStackedWidget, QWidget

from netlauncher import localpacks
from netlauncher.curseforge import CurseForge, NotDistributable
from netlauncher.library import AlreadyInstalled, Library, Locked, NotAvailable
from netlauncher.modrinth import search_loader
from netlauncher.pack import load_state
from netlauncher.ui import anim, icons, jobs
from netlauncher.ui.pages import common
from netlauncher.ui.pages.common import hbox, human_downloads, label, plural, vbox
from netlauncher.ui.pages.home import Chip, _error_text
from netlauncher.ui.theme import qcolor
from netlauncher.ui.widgets import AccentButton, GhostButton, GlassCard, Toggle

TITLES = {"mod": "Моды", "resourcepack": "Ресурспаки", "shader": "Шейдеры"}
WORDS = {"mod": ("мод", "мода", "модов"), "resourcepack": ("ресурспак", "ресурспака", "ресурспаков"),
         "shader": ("шейдер", "шейдера", "шейдеров")}
PROJECT_TYPES = {"mod": "mod", "resourcepack": "resourcepack", "shader": "shader"}
ICON_FOR = {"mod": "mods", "resourcepack": "resourcepacks", "shader": "shaders"}


class Icon(QWidget):
    def __init__(self, kind: str, size: int = 40, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(size, size)
        self.pm: QPixmap | None = None

    def set_bytes(self, data: bytes | None) -> None:
        pm = QPixmap()
        if data and pm.loadFromData(data):
            self.pm = pm
            self.update()

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qcolor("rgba(255,255,255,0.06)"))
        p.drawRoundedRect(r, 10, 10)
        if self.pm is not None:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self.pm.width() > 32)
            pm = self.pm.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation if self.pm.width() > 32
                                else Qt.TransformationMode.FastTransformation)
            p.drawPixmap(int((self.width() - pm.width()) / 2), int((self.height() - pm.height()) / 2), pm)
        else:
            icons.paint(p, ICON_FOR[self.kind], QRectF(10, 10, self.width() - 20, self.height() - 20), qcolor("muted"))


class ItemRow(GlassCard):
    toggled = Signal(object, bool)
    remove = Signal(object)

    def __init__(self, item, parent=None):
        super().__init__(parent, radius=14)
        self.item = item
        row = hbox(self, (14, 10, 12, 10), 14)
        self.icon = Icon(item.kind)
        if item.meta and item.meta.logo:
            self.icon.set_bytes(item.meta.logo)
        row.addWidget(self.icon)
        col = vbox(None, (0, 0, 0, 0), 1)
        self.name = label(item.name, 11, 560)
        sub = item.version or item.base_name
        self.sub = label(sub, 9.5, role="faint")
        col.addWidget(self.name)
        col.addWidget(self.sub)
        row.addLayout(col, 1)
        self.update_badge = label("есть обновление", 9.5, 560)
        self.update_badge.setStyleSheet(f"color: {qcolor('accent').name()};")
        self.update_badge.hide()
        row.addWidget(self.update_badge)
        self.badge = label("сборка" if item.from_pack else "моё", 9.5, role="faint")
        row.addWidget(self.badge)
        self.toggle = Toggle()
        self.toggle.setChecked(item.enabled)
        self.toggle._set_knob(1.0 if item.enabled else 0.0)
        if item.locked:
            self.toggle.setEnabled(False)
            self.toggle.setToolTip("Нужен на сервере, выключить нельзя")
        self.toggle.clicked.connect(lambda on: self.toggled.emit(self.item, on))
        row.addWidget(self.toggle)
        self.more = GhostButton("Ещё")
        self.more.setEnabled(not item.locked)
        self.more.clicked.connect(self._menu)
        row.addWidget(self.more)

    def _menu(self):
        m = QMenu(self)
        m.addAction("Удалить", lambda: self.remove.emit(self.item))
        m.exec(self.more.mapToGlobal(self.more.rect().bottomLeft()))


class ResultCard(GlassCard):
    install = Signal(object)
    selected = Signal(object)

    def __init__(self, project, kind: str, parent=None):
        super().__init__(parent, radius=14)
        self.project = project
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        row = hbox(self, (14, 12, 12, 12), 14)
        self.icon = Icon(kind, 48)
        row.addWidget(self.icon)
        col = vbox(None, (0, 0, 0, 0), 2)
        self.title = label(project.title, 11.5, 600)
        self.desc = label(project.description, 10, role="muted", wrap=True)
        self.meta = label(human_downloads(project.downloads), 9.5, role="faint")
        col.addWidget(self.title)
        col.addWidget(self.desc)
        col.addWidget(self.meta)
        row.addLayout(col, 1)
        self.install_btn = AccentButton("Установить")
        self.install_btn.clicked.connect(lambda: self.install.emit(self.project))
        row.addWidget(self.install_btn)

    def select(self) -> None:
        self.selected.emit(self.project)

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self.select()
        super().mousePressEvent(e)


def _scroll(inner: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setWidget(inner)
    sa.setFrameShape(QScrollArea.Shape.NoFrame)
    return sa


class Thumb(QWidget):
    clicked = Signal(str)

    def __init__(self, url: str, title: str, parent=None):
        super().__init__(parent)
        self.url, self.title = url, title
        self.setFixedSize(176, 99)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(title)
        self.pm: QPixmap | None = None

    def set_bytes(self, data: bytes) -> None:
        pm = QPixmap()
        if pm.loadFromData(data):
            self.pm = pm
            self.update()

    def mousePressEvent(self, e):  # noqa: N802
        self.clicked.emit(self.url)

    def paintEvent(self, e):  # noqa: N802
        from PySide6.QtGui import QPainterPath
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 10, 10)
        p.setClipPath(path)
        p.fillRect(self.rect(), qcolor("rgba(255,255,255,0.05)"))
        if self.pm:
            pm = self.pm.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap(int((self.width() - pm.width()) / 2), int((self.height() - pm.height()) / 2), pm)


class ImageViewer(QWidget):
    """Full-size picture over the page; click anywhere to close."""

    def __init__(self, parent):
        super().__init__(parent)
        self.pm: QPixmap | None = None
        self.hide()

    def show_bytes(self, data: bytes) -> None:
        pm = QPixmap()
        if not pm.loadFromData(data):
            return
        self.pm = pm
        self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()
        anim.fade_slide_in(self, dx=0, dy=0, ms=180)

    def mousePressEvent(self, e):  # noqa: N802
        self.hide()

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), qcolor("rgba(5,9,18,0.88)"))
        if self.pm:
            pm = self.pm.scaled(self.size() * 0.92, Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap(int((self.width() - pm.width()) / 2), int((self.height() - pm.height()) / 2), pm)


class DetailPanel(GlassCard):
    """Right-hand mod page: header, install with dependencies, gallery, description."""

    install_plan = Signal(object)
    closed = Signal()

    def __init__(self, ctx, kind: str, plan_fn, parent=None):
        super().__init__(parent, radius=18)
        from netlauncher.ui.richtext import RichText
        self.ctx, self.kind, self.plan_fn = ctx, kind, plan_fn
        self.project = None
        self.plan = None
        self._seq = 0
        lay = vbox(self, (20, 18, 20, 18), 10)
        head = hbox(None, (0, 0, 0, 0), 14)
        self.icon = Icon(kind, 56)
        head.addWidget(self.icon)
        col = vbox(None, (0, 0, 0, 0), 2)
        self.title = label("", 16, 650, display=True, wrap=True)
        self.meta = label("", 9.5, role="faint", wrap=True)
        col.addWidget(self.title)
        col.addWidget(self.meta)
        head.addLayout(col, 1)
        close = GhostButton("Закрыть")
        close.clicked.connect(self.closed.emit)
        head.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(head)
        brow = hbox(None, (0, 0, 0, 0), 8)
        self.install_btn = AccentButton("Установить")
        self.install_btn.clicked.connect(lambda: self.plan and self.install_plan.emit(self.plan))
        self.site_btn = GhostButton("Открыть на сайте")
        self.site_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self._page)))
        brow.addWidget(self.install_btn)
        brow.addWidget(self.site_btn)
        brow.addStretch(1)
        lay.addLayout(brow)
        self.deps = label("", 10, role="muted", wrap=True)
        lay.addWidget(self.deps)
        self.gallery_row = hbox(None, (0, 0, 0, 0), 8)
        gal = QWidget()
        gal.setLayout(self.gallery_row)
        self.gallery = QScrollArea()
        self.gallery.setWidget(gal)
        self.gallery.setWidgetResizable(True)
        self.gallery.setFixedHeight(116)
        self.gallery.setFrameShape(QScrollArea.Shape.NoFrame)
        self.gallery.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lay.addWidget(self.gallery)
        self.body = RichText(ctx.http, ctx.lay.cache)
        lay.addWidget(self.body, 1)
        self.links = label("", 9.5, role="faint", wrap=True)
        self.links.setOpenExternalLinks(True)
        self.links.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        lay.addWidget(self.links)
        self.thumbs: list[Thumb] = []
        self._page = ""
        self.viewer: ImageViewer | None = None

    def show_project(self, project, provider) -> None:
        self._seq += 1
        seq = self._seq
        self.project, self.plan = project, None
        self.title.setText(project.title)
        self.meta.setText(human_downloads(project.downloads))
        self.deps.setText("Проверяю зависимости")
        self.install_btn.setEnabled(False)
        self.body.set_html(f"<p>{project.description}</p>")
        for t in self.thumbs:
            t.setParent(None)
            t.deleteLater()
        self.thumbs = []
        self.gallery.hide()
        self.links.setText("")
        self.icon.pm = None
        self.icon.update()
        jobs.run(lambda progress: provider.details(project.id), on_done=lambda d: self._details(seq, d),
                 on_error=lambda e: None)
        jobs.run(lambda progress: self.plan_fn(project), on_done=lambda plan: self._planned(seq, plan),
                 on_error=lambda e: self._plan_failed(seq, e))

    def _details(self, seq: int, d) -> None:
        if seq != self._seq:
            return
        parts = [x for x in (d.author, human_downloads(d.downloads), ", ".join(d.categories[:4])) if x]
        self.meta.setText(", ".join(parts))
        self._page = d.page_url
        self.site_btn.setVisible(bool(d.page_url))
        if d.body_format == "markdown":
            self.body.set_markdown(d.body or d.summary)
        else:
            self.body.set_html(d.body or f"<p>{d.summary}</p>")
        for url, title in d.gallery[:12]:
            t = Thumb(url, title)
            t.clicked.connect(self._open_image)
            self.gallery_row.addWidget(t)
            self.thumbs.append(t)
            self._fetch(url, t.set_bytes)
        self.gallery_row.addStretch(1)
        self.gallery.setVisible(bool(self.thumbs))
        if d.icon_url:
            self._fetch(d.icon_url, self.icon.set_bytes)
        self.links.setText("  ".join(f'<a href="{u}" style="color:#6AAEFF">{t}</a>' for t, u in d.links.items()))

    def _planned(self, seq: int, plan) -> None:
        if seq != self._seq:
            return
        self.plan = plan
        deps = [p.title for p, _ in plan.items[1:]]
        self.deps.setText("Вместе с ним установятся: " + ", ".join(deps) + "." if deps
                          else "Дополнительные моды не нужны.")
        self.install_btn.setEnabled(True)

    def _plan_failed(self, seq: int, e) -> None:
        if seq != self._seq:
            return
        if isinstance(e, AlreadyInstalled):
            self.deps.setText("Уже установлен.")
        elif isinstance(e, NotDistributable):
            self.deps.setText("Автор запретил скачивание через сторонние программы. Скачай файл на сайте.")
            self._page = e.page_url
        elif isinstance(e, NotAvailable):
            self.deps.setText("Для этой версии Minecraft нет подходящего файла.")
        else:
            self.deps.setText(_error_text(e))

    def _fetch(self, url: str, cb) -> None:
        dest = self.ctx.lay.cache / "icons" / hashlib.sha1(url.encode()).hexdigest()

        def job(progress):
            if not dest.exists():
                self.ctx.http.download(url, dest)
            return dest.read_bytes()

        jobs.run(job, on_done=cb, on_error=lambda e: None)

    def _open_image(self, url: str) -> None:
        if self.viewer is None:
            self.viewer = ImageViewer(self.window())
        self._fetch(url, self.viewer.show_bytes)


SORT_CHIPS = (("downloads", "Популярное"), ("relevance", "Подходящее"), ("newest", "Новое"), ("updated", "Обновлённое"))
PAGE = 20


class Browser(QWidget):
    back = Signal()
    install = Signal(object)
    install_plan = Signal(object)

    def __init__(self, ctx, kind: str, plan_fn=None, parent=None):
        super().__init__(parent)
        self.ctx, self.kind = ctx, kind
        lay = vbox(self, (0, 0, 0, 0), 10)
        top = hbox(None, (0, 0, 0, 0), 10)
        back = GhostButton("Назад к списку")
        back.clicked.connect(self.back.emit)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Поиск на Modrinth")
        top.addWidget(back)
        top.addWidget(self.query, 1)
        self.source = "modrinth"
        self.source_chips = {}
        for key, text in (("modrinth", "Modrinth"), ("curseforge", "CurseForge")):
            c = Chip(text, key == "modrinth")
            c.clicked.connect(lambda key=key: self.set_source(key))
            top.addWidget(c)
            self.source_chips[key] = c
        lay.addLayout(top)
        filters = hbox(None, (0, 0, 0, 0), 8)
        self.sort = "downloads"
        self.sort_chips = {}
        for key, text in SORT_CHIPS:
            c = Chip(text, key == self.sort)
            c.clicked.connect(lambda key=key: self.set_sort(key))
            filters.addWidget(c)
            self.sort_chips[key] = c
        filters.addStretch(1)
        self.category = QComboBox()
        self.category.setMinimumWidth(200)
        self.category.addItem("Все категории", "")
        self.category.currentIndexChanged.connect(lambda _i: self.run_search())
        filters.addWidget(self.category)
        lay.addLayout(filters)
        srow = hbox(None, (0, 0, 0, 0), 10)
        self.status = label("", 10, role="muted", wrap=True)
        self.page_btn = GhostButton("Открыть страницу мода")
        self.page_btn.hide()
        self.page_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self._page_url)))
        srow.addWidget(self.status, 1)
        srow.addWidget(self.page_btn)
        lay.addLayout(srow)
        self._page_url = ""
        body = hbox(None, (0, 0, 0, 0), 14)
        inner = QWidget()
        self.list = vbox(inner, (0, 0, 6, 0), 8)
        self.more_btn = GhostButton("Показать ещё")
        self.more_btn.clicked.connect(self.load_more)
        self.more_btn.hide()
        self.list.addWidget(self.more_btn)
        self.list.addStretch(1)
        body.addWidget(_scroll(inner), 1)
        self.detail = DetailPanel(ctx, kind, plan_fn or (lambda project: None))
        self.detail.closed.connect(self.close_detail)
        self.detail.install_plan.connect(self.install_plan.emit)
        self.detail.setMinimumWidth(420)
        self.detail.hide()
        body.addWidget(self.detail, 1)
        lay.addLayout(body, 1)
        self.cards: list[ResultCard] = []
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(300)
        self.debounce.timeout.connect(self.run_search)
        self.query.textChanged.connect(lambda _: self.debounce.start())
        self._seq = 0
        self._offset = 0
        self._cats_for = None

    def provider(self):
        if self.source == "curseforge":
            return CurseForge(self.ctx.http, self.ctx.settings.curseforge_key)
        return self.ctx.modrinth

    def set_source(self, key: str) -> None:
        if key == "curseforge" and not self.ctx.settings.curseforge_key:
            self.status.setText("Чтобы искать на CurseForge, добавь ключ API в настройках, раздел «Лаунчер».")
            return
        self.source = key
        for k, c in self.source_chips.items():
            c.active = k == key
            c.update()
        self.query.setPlaceholderText("Поиск на CurseForge" if key == "curseforge" else "Поиск на Modrinth")
        self._load_categories()
        self.run_search()

    def set_sort(self, key: str) -> None:
        self.sort = key
        for k, c in self.sort_chips.items():
            c.active = k == key
            c.update()
        self.run_search()

    def show_page_link(self, url: str) -> None:
        self._page_url = url
        self.page_btn.setVisible(bool(url))

    def _load_categories(self) -> None:
        if self._cats_for == self.source:
            return
        self._cats_for = self.source
        prov, kind = self.provider(), self.kind
        jobs.run(lambda progress: prov.categories(PROJECT_TYPES[kind]), on_done=self._set_categories,
                 on_error=lambda e: None)

    def _set_categories(self, cats) -> None:
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItem("Все категории", "")
        for slug, name in cats:
            self.category.addItem(name, slug)
        self.category.blockSignals(False)

    def run_search(self, append: bool = False) -> None:
        lp = common.current_pack(self.ctx)
        if lp is None:
            return
        self._load_categories()
        self._seq += 1
        seq = self._seq
        if not append:
            self._offset = 0
        offset = self._offset
        q = self.query.text().strip()
        sort = self.sort if (q or self.sort != "relevance") else "downloads"
        cat = self.category.currentData() or None
        self.status.setText("Ищу")
        self.show_page_link("")
        loader = lp.loader if self.source == "curseforge" else search_loader(self.kind, lp.loader)
        prov = self.provider()
        jobs.run(lambda progress: prov.search(q, PROJECT_TYPES[self.kind], lp.mc_version, loader, offset=offset,
                                              limit=PAGE, sort=sort, category=cat),
                 on_done=lambda hits: self._show(seq, hits, append),
                 on_error=lambda e: self.status.setText(_error_text(e)))

    def load_more(self) -> None:
        self._offset += PAGE
        self.run_search(append=True)

    def _show(self, seq: int, hits, append: bool = False) -> None:
        if seq != self._seq:
            return
        if not append:
            for c in self.cards:
                c.setParent(None)
                c.deleteLater()
            self.cards = []
        new = []
        for proj in hits:
            card = ResultCard(proj, self.kind)
            card.install.connect(self.install.emit)
            card.selected.connect(self.open_detail)
            self.list.insertWidget(self.list.indexOf(self.more_btn), card)
            self.cards.append(card)
            new.append(card)
            if proj.icon_url:
                self._icon(card, proj.icon_url)
        self.status.setText("" if self.cards else "Ничего не нашлось. Попробуй другое слово или категорию.")
        self.more_btn.setVisible(len(hits) == PAGE)
        anim.stagger(new)

    def _icon(self, card: ResultCard, url: str) -> None:
        dest = self.ctx.lay.cache / "icons" / hashlib.sha1(url.encode()).hexdigest()

        def fetch(progress):
            if not dest.exists():
                self.ctx.http.download(url, dest)
            return dest.read_bytes()

        jobs.run(fetch, on_done=lambda data: card.icon.set_bytes(data) if shiboken_alive(card) else None,
                 on_error=lambda e: None)

    def open_detail(self, project) -> None:
        was_hidden = self.detail.isHidden()
        self.detail.show()
        self.detail.show_project(project, self.provider())
        if was_hidden:
            anim.fade_slide_in(self.detail, dx=30, ms=240)

    def close_detail(self) -> None:
        self.detail.hide()


def shiboken_alive(obj) -> bool:
    import shiboken6
    return shiboken6.isValid(obj)


class ContentPage(QWidget):
    def __init__(self, ctx, window=None, kind: str = "mod", parent=None):
        super().__init__(parent)
        self.ctx, self.window, self.kind = ctx, window, kind
        self.rows: list[ItemRow] = []
        self._filter = "all"
        self._updates = {}
        lay = vbox(self, (8, 4, 0, 0), 14)
        head = hbox(None, (0, 0, 0, 0), 12)
        col = vbox(None, (0, 0, 0, 0), 2)
        col.addWidget(label(TITLES[kind], 22, 650, display=True))
        self.subtitle = label("", 10.5, role="muted")
        col.addWidget(self.subtitle)
        head.addLayout(col, 1)
        self.find_btn = AccentButton("Найти новые")
        self.find_btn.clicked.connect(self.open_browser)
        head.addWidget(self.find_btn)
        lay.addLayout(head)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        listing = QWidget()
        ll = vbox(listing, (0, 0, 0, 0), 12)
        controls = hbox(None, (0, 0, 0, 0), 8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск среди установленных")
        self.search.textChanged.connect(lambda _: self._apply_filter())
        controls.addWidget(self.search, 1)
        self.chips = {}
        for key, text in (("all", "Все"), ("disabled", "Выключенные"), ("updates", "Есть обновления")):
            c = Chip(text, key == "all")
            c.clicked.connect(lambda key=key: self.set_filter(key))
            controls.addWidget(c)
            self.chips[key] = c
        self.check_btn = GhostButton("Проверить обновления")
        self.check_btn.clicked.connect(self.check_updates)
        controls.addWidget(self.check_btn)
        ll.addLayout(controls)
        self.status = label("", 10, role="muted", wrap=True)
        ll.addWidget(self.status)
        self.update_all = AccentButton("Обновить всё")
        self.update_all.clicked.connect(self.apply_updates)
        self.update_all.hide()
        ll.addWidget(self.update_all, 0, Qt.AlignmentFlag.AlignLeft)
        inner = QWidget()
        self.list = vbox(inner, (0, 0, 6, 0), 8)
        self.list.addStretch(1)
        ll.addWidget(_scroll(inner), 1)
        self.stack.addWidget(listing)
        self.listing = listing
        self.browser = Browser(ctx, kind, plan_fn=self._plan_for)
        self.browser.back.connect(self.close_browser)
        self.browser.install.connect(self.install)
        self.browser.install_plan.connect(self._install_planned)
        self.stack.addWidget(self.browser)

    # ---------- data ----------
    def library(self) -> Library | None:
        lp = common.current_pack(self.ctx)
        if lp is None:
            return None
        gd = localpacks.game_dir(self.ctx.lay, lp.id)
        state = load_state(gd) or {}
        return Library(gd, self.ctx.lay.snapshots / lp.id, self.ctx.modrinth, self.ctx.http, self.ctx.lay.cache,
                       lp.mc_version, lp.loader, pack_state=state.get("files"))

    def on_shown(self) -> None:
        self.reload()

    def reload(self) -> None:
        lib = self.library()
        lp = common.current_pack(self.ctx)
        vanilla = lp is not None and lp.loader == "vanilla" and self.kind == "mod"
        self.find_btn.setVisible(not vanilla and self.stack.currentWidget() is not self.browser)
        if vanilla:
            self.subtitle.setText("В сборке без загрузчика моды не работают. Создай сборку с Fabric, Forge или NeoForge.")
            self._fill([])
            return
        if lib is None:
            self.subtitle.setText("Сначала установи сборку на главной.")
            self._fill([])
            return
        self.subtitle.setText("Читаю файлы")
        jobs.run(lambda progress: lib.scan(self.kind), on_done=lambda items: self._loaded(items, lp.name),
                 on_error=lambda e: self.status.setText(_error_text(e)))

    def _loaded(self, items, pack_name: str) -> None:
        n = len(items)
        self.subtitle.setText(f"{n} {plural(n, *WORDS[self.kind])} в сборке «{pack_name}»")
        self._fill(items)

    def _fill(self, items) -> None:
        for r in self.rows:
            r.setParent(None)
            r.deleteLater()
        self.rows = []
        for it in items:
            r = ItemRow(it)
            r.toggled.connect(self._toggle)
            r.remove.connect(self._remove)
            r.update_badge.setVisible(it.path in self._updates)
            self.list.insertWidget(self.list.count() - 1, r)
            self.rows.append(r)
        self._apply_filter()
        anim.stagger(self.visible_rows())

    # ---------- filtering ----------
    def set_filter(self, key: str) -> None:
        self._filter = key
        for k, c in self.chips.items():
            c.active = k == key
            c.update()
        self._apply_filter()

    def _matches(self, r: ItemRow) -> bool:
        q = self.search.text().strip().lower()
        if q and q not in r.item.name.lower() and q not in r.item.base_name.lower():
            return False
        if self._filter == "disabled":
            return not r.item.enabled
        if self._filter == "updates":
            return r.item.path in self._updates
        return True

    def _apply_filter(self) -> None:
        for r in self.rows:
            r.setVisible(self._matches(r))

    def visible_rows(self) -> list[ItemRow]:
        return [r for r in self.rows if not r.isHidden()]

    # ---------- actions ----------
    def _toggle(self, item, on: bool) -> None:
        lib = self.library()
        jobs.run(lambda progress: lib.set_enabled(item, on), on_done=lambda _: self.reload(),
                 on_error=self._failed)

    def _remove(self, item) -> None:
        if not common.confirm(self, "Удаление", f"Удалить {item.name}? Копия останется в снимках.", "Удалить"):
            return
        lib = self.library()
        jobs.run(lambda progress: lib.remove(item), on_done=lambda _: self.reload(), on_error=self._failed)

    def _failed(self, e: BaseException) -> None:
        if isinstance(e, Locked):
            self.status.setText("Этот мод нужен на сервере, его нельзя выключить или удалить.")
        else:
            self.status.setText(_error_text(e))
        self.reload()

    def open_browser(self) -> None:
        self.stack.setCurrentWidget(self.browser)
        anim.fade_slide_in(self.browser, dx=24, ms=220)
        self.find_btn.hide()
        self.browser.query.setFocus()
        if not self.browser.cards:
            self.browser.run_search()

    def close_browser(self) -> None:
        self.stack.setCurrentWidget(self.listing)
        self.find_btn.show()
        self.reload()

    def _plan_for(self, project):
        lib = self.library()
        if lib is None:
            raise NotAvailable(project.title)
        return lib.plan_install(project.id, self.kind, source=self.browser.provider())

    def _install_planned(self, plan) -> None:
        lib = self.library()
        if lib is None or not plan.items:
            return
        names = [p.title for p, _ in plan.items]
        self.browser.detail.install_btn.setEnabled(False)
        self.browser.detail.deps.setText(f"Устанавливаю {names[0]}")
        jobs.run(lambda progress: lib.install(plan, self.kind, progress),
                 on_done=lambda items: self.browser.detail.deps.setText(f"Установлено: {', '.join(names)}."),
                 on_error=lambda e: self.browser.detail.deps.setText(_error_text(e)),
                 on_progress=lambda name, cur, mx: self.browser.detail.deps.setText(
                     f"Скачиваю {name}" + (f", {round(100 * cur / mx)} %" if mx else "")))

    def install(self, project) -> None:
        lib = self.library()
        if lib is None:
            return
        self.browser.status.setText(f"Проверяю {project.title}")
        self.browser.show_page_link("")
        source = self.browser.provider()
        jobs.run(lambda progress: lib.plan_install(project.id, self.kind, source=source),
                 on_done=lambda plan: self._confirm_install(lib, plan), on_error=self._install_failed)

    def _confirm_install(self, lib: Library, plan) -> None:
        names = [p.title for p, _ in plan.items]
        text = f"Будет установлено: {names[0]}."
        if len(names) > 1:
            text += " Зависимости: " + ", ".join(names[1:]) + "."
        if not common.confirm(self, "Установка", text, "Установить"):
            self.browser.status.setText("")
            return
        self.browser.status.setText(f"Устанавливаю {names[0]}")
        jobs.run(lambda progress: lib.install(plan, self.kind, progress),
                 on_done=lambda items: self.browser.status.setText(f"Установлено: {', '.join(names)}."),
                 on_error=self._install_failed,
                 on_progress=lambda name, cur, mx: self.browser.status.setText(
                     f"Скачиваю {name}" + (f", {round(100 * cur / mx)} %" if mx else "")))

    def _install_failed(self, e: BaseException) -> None:
        if isinstance(e, NotDistributable):
            self.browser.status.setText(f"{e.name}: автор запретил скачивание через сторонние программы. "
                                        "Скачай файл на странице мода и положи в папку mods.")
            self.browser.show_page_link(e.page_url)
        elif isinstance(e, AlreadyInstalled):
            self.browser.status.setText(f"{e.name} уже установлен.")
        elif isinstance(e, NotAvailable):
            self.browser.status.setText("Для этой версии Minecraft нет подходящего файла.")
        else:
            self.browser.status.setText(_error_text(e))

    def check_updates(self) -> None:
        lib = self.library()
        if lib is None:
            return
        self.status.setText("Проверяю обновления")
        jobs.run(lambda progress: lib.check_updates(self.kind), on_done=self._updates_found, on_error=self._failed)

    def _updates_found(self, ups) -> None:
        self._updates = {u.item.path: u for u in ups}
        n = len(ups)
        self.status.setText(f"Обновления есть у {n} {plural(n, 'файла', 'файлов', 'файлов')}." if n
                            else "Всё свежее. Файлы сборки обновляются вместе со сборкой.")
        self.update_all.setVisible(bool(n))
        for r in self.rows:
            r.update_badge.setVisible(r.item.path in self._updates)
        self._apply_filter()

    def apply_updates(self) -> None:
        lib = self.library()
        ups = list(self._updates.values())
        self.update_all.setEnabled(False)
        jobs.run(lambda progress: lib.apply_updates(ups, progress),
                 on_done=lambda _: self._updated(len(ups)), on_error=self._failed)

    def _updated(self, n: int) -> None:
        self._updates = {}
        self.update_all.setEnabled(True)
        self.update_all.hide()
        self.status.setText(f"Обновлено: {n}.")
        self.reload()
