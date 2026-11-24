"""Official tab: packs from the .NET Launcher catalog, and the author's build and publish tools."""

from __future__ import annotations

from PySide6.QtWidgets import QScrollArea, QWidget

from netlauncher import localpacks
from netlauncher.catalog import is_newer
from netlauncher.i18n import t
from netlauncher.ui import anim, jobs
from netlauncher.ui.pages.common import hbox, label, vbox
from netlauncher.ui.pages.packs_page import LOADER_NAMES
from netlauncher.ui.widgets import AccentButton, GhostButton, GlassCard


class OfficialCard(GlassCard):
    def __init__(self, entry, action: str, parent=None):
        super().__init__(parent, hoverable=True)
        self.entry, self.action = entry, action
        row = hbox(self, (18, 14, 14, 14), 12)
        col = vbox(None, (0, 0, 0, 0), 2)
        col.addWidget(label(entry.name, 12, 620))
        self.desc = label(entry.description, 10.5, role="muted", wrap=True)
        self.desc.setVisible(bool(entry.description))
        col.addWidget(self.desc)
        loader = LOADER_NAMES.get(entry.loader, entry.loader)
        col.addWidget(label(t('{loader} {mc}, версия {version}', loader=loader, mc=entry.mc_version, version=entry.version),
                            10, role="faint"))
        row.addLayout(col, 1)
        text = {"install": t('Установить'), "update": t('Обновить'), "play": t('Играть')}[action]
        self.action_btn = AccentButton(text)
        row.addWidget(self.action_btn)


class OfficialPage(QWidget):
    def __init__(self, ctx, window=None, parent=None):
        super().__init__(parent)
        self.ctx, self.window = ctx, window
        outer = vbox(self, (16, 8, 16, 16), 10)
        outer.addWidget(label(t('Официальные'), 22, 600, display=True))
        outer.addWidget(label(t('Сборки от .NET Launcher. Их собирает автор, у всех игроков они одинаковые.'), 10.5,
                              role="muted", wrap=True))
        inner = QWidget()
        body = vbox(inner, (0, 4, 6, 0), 10)
        self.list = vbox(None, (0, 0, 0, 0), 10)
        body.addLayout(self.list)
        self.empty = label("", 10.5,
                           role="muted", wrap=True)
        self.empty.hide()
        body.addWidget(self.empty)
        self.retry = GhostButton(t('Повторить'))
        self.retry.clicked.connect(self._retry)
        body.addWidget(self.retry)
        from netlauncher.ui.pages.author_tools import AuthorTools
        from netlauncher.ui.supporter import IssueCard
        self.keys = IssueCard(ctx, window)
        body.addWidget(self.keys)
        self.author_box = AuthorTools(ctx)
        self.author_box.hide()
        body.addSpacing(8)
        body.addWidget(self.author_box)
        body.addStretch(1)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(inner)
        sa.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(sa, 1)
        self.cards: list[OfficialCard] = []

    def _retry(self) -> None:
        self.window.page("home")._load_catalog()
        self.refresh_cards()

    def _is_author(self) -> bool:
        s = self.ctx.settings
        return bool(s.author_mode and s.github_token)

    def refresh_cards(self) -> None:
        for c in self.cards:
            c.setParent(None)
            c.deleteLater()
        self.cards = []
        cat = getattr(self.ctx, "catalog", None)
        installed = {lp.id: lp for lp in localpacks.list_installed(self.ctx.lay)}
        loading = self.window and not getattr(self.window.page("home"), "startup_done", True)
        self.empty.setVisible(cat is None or not cat.packs)
        self.empty.setText(t('Загружаю каталог') if loading else
                           t('Список сборок не загрузился. Проверь интернет.') if cat is None else
                           t('Официальных сборок пока нет.'))
        self.retry.setVisible(cat is None and not loading)
        for entry in (cat.packs if cat else []):
            lp = installed.get(entry.id)
            action = "install" if lp is None else "update" if is_newer(entry.version, lp.version) else "play"
            card = OfficialCard(entry, action)
            card.action_btn.clicked.connect(lambda _=False, e=entry, a=action: self._act(e, a))
            self.list.addWidget(card)
            self.cards.append(card)
        anim.stagger(self.cards)

    def on_shown(self) -> None:
        self.keys.refresh()
        self.refresh_cards()
        self.author_box.hide()
        s = self.ctx.settings
        repo, token = s.github_repo.strip(), s.github_token.strip()
        if not (self._is_author() and repo and token):
            return

        def checked(allowed):
            if allowed and self._is_author() and (repo, token) == (s.github_repo.strip(), s.github_token.strip()):
                self.author_box.refresh()
                self.author_box.show()

        def can_publish(progress):
            info = self.ctx.http.get_json(f"https://api.github.com/repos/{repo}",
                                          headers={"Authorization": f"Bearer {token}"})
            return info.get("permissions", {}).get("push") is True

        jobs.run(can_publish, on_done=checked)

    def _act(self, entry, action: str) -> None:
        if self.window is None:
            return
        home = self.window.page("home")
        self.window.open_page("home")
        if action == "play":
            if hasattr(home, "pick_pack"):
                home.pick_pack(entry.id)
            if hasattr(home, "play"):
                home.play()
        elif hasattr(home, "install_entry"):
            home.install_entry(entry)
