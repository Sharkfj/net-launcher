"""Mods / resource packs / shader packs: list, toggle, remove, search Modrinth, install, update."""

from __future__ import annotations

import hashlib

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QLineEdit, QMenu, QScrollArea, QStackedWidget, QWidget

from netlauncher import localpacks
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

    def __init__(self, project, kind: str, parent=None):
        super().__init__(parent, radius=14)
        self.project = project
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


def _scroll(inner: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setWidget(inner)
    sa.setFrameShape(QScrollArea.Shape.NoFrame)
    return sa


class Browser(QWidget):
    back = Signal()
    install = Signal(object)

    def __init__(self, ctx, kind: str, parent=None):
        super().__init__(parent)
        self.ctx, self.kind = ctx, kind
        lay = vbox(self, (0, 0, 0, 0), 12)
        top = hbox(None, (0, 0, 0, 0), 10)
        back = GhostButton("Назад к списку")
        back.clicked.connect(self.back.emit)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Поиск на Modrinth")
        top.addWidget(back)
        top.addWidget(self.query, 1)
        lay.addLayout(top)
        self.status = label("", 10, role="muted")
        lay.addWidget(self.status)
        inner = QWidget()
        self.list = vbox(inner, (0, 0, 6, 0), 8)
        self.list.addStretch(1)
        lay.addWidget(_scroll(inner), 1)
        self.cards: list[ResultCard] = []
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(300)
        self.debounce.timeout.connect(self.run_search)
        self.query.textChanged.connect(lambda _: self.debounce.start())
        self._seq = 0

    def run_search(self) -> None:
        lp = common.current_pack(self.ctx)
        if lp is None:
            return
        self._seq += 1
        seq = self._seq
        q = self.query.text().strip()
        self.status.setText("Ищу")
        loader = search_loader(self.kind, lp.loader)
        jobs.run(lambda progress: self.ctx.modrinth.search(q, PROJECT_TYPES[self.kind], lp.mc_version, loader),
                 on_done=lambda hits: self._show(seq, hits),
                 on_error=lambda e: self.status.setText(_error_text(e)))

    def _show(self, seq: int, hits) -> None:
        if seq != self._seq:
            return
        for c in self.cards:
            c.setParent(None)
            c.deleteLater()
        self.cards = []
        self.status.setText("" if hits else "Ничего не нашлось. Попробуй другое слово.")
        for proj in hits:
            card = ResultCard(proj, self.kind)
            card.install.connect(self.install.emit)
            self.list.insertWidget(self.list.count() - 1, card)
            self.cards.append(card)
            if proj.icon_url:
                self._icon(card, proj.icon_url)
        anim.stagger(self.cards)

    def _icon(self, card: ResultCard, url: str) -> None:
        dest = self.ctx.lay.cache / "icons" / hashlib.sha1(url.encode()).hexdigest()

        def fetch(progress):
            if not dest.exists():
                self.ctx.http.download(url, dest)
            return dest.read_bytes()

        jobs.run(fetch, on_done=lambda data: card.icon.set_bytes(data) if not card.isHidden() else None,
                 on_error=lambda e: None)


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
        self.browser = Browser(ctx, kind)
        self.browser.back.connect(self.close_browser)
        self.browser.install.connect(self.install)
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

    def install(self, project) -> None:
        lib = self.library()
        if lib is None:
            return
        self.browser.status.setText(f"Проверяю {project.title}")
        jobs.run(lambda progress: lib.plan_install(project.id, self.kind),
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
        if isinstance(e, AlreadyInstalled):
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
