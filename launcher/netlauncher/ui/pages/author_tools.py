"""Author tools on the Official tab: build a pack from its game folder and publish it to the catalog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QComboBox, QLineEdit, QPlainTextEdit, QWidget

from netlauncher import author, localpacks
from netlauncher.catalog import PackEntry
from netlauncher.curseforge import for_context
from netlauncher.i18n import t
from netlauncher.pack import MrPack
from netlauncher.ui import jobs
from netlauncher.ui.pages import common
from netlauncher.ui.pages.common import hbox, label, vbox
from netlauncher.ui.pages.home import _error_text
from netlauncher.ui.pages.settings_page import _line, next_version
from netlauncher.ui.widgets import AccentButton, GhostButton, GlassCard


class AuthorTools(GlassCard):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._working = False
        self._packs = []
        self._build_result = None
        ab = vbox(self, (20, 16, 20, 16), 10)
        ab.addWidget(label(t('Публикация сборок'), 12.5, 620))
        self.author_pack = QComboBox()
        self.author_pack.currentIndexChanged.connect(self._pack_picked)
        ab.addWidget(_line(t('Сборка'), self.author_pack, t('Новая сборка появится в каталоге после первой публикации.')))
        self.pack_desc = QLineEdit()
        self.pack_desc.setPlaceholderText(t('Одно предложение о сборке'))
        self.pack_server = QLineEdit()
        self.pack_server.setPlaceholderText("play.example.net:25565")
        self.pack_version = QLineEdit()
        self.pack_version.setFixedWidth(120)
        ab.addWidget(_line(t('Описание'), self.pack_desc))
        ab.addWidget(_line(t('Адрес сервера'), self.pack_server, t('Если указать, у игроков появится «Играть на сервере».')))
        ab.addWidget(_line(t('Версия'), self.pack_version))
        for f in (self.pack_desc, self.pack_server):
            f.setMinimumWidth(340)
        self.author_pack.setMinimumWidth(200)
        self.changelog = QPlainTextEdit()
        self.changelog.setPlaceholderText(t('Что изменилось в этой версии'))
        self.changelog.setFixedHeight(90)
        ab.addWidget(self.changelog)
        arow = hbox(None, (0, 0, 0, 0), 8)
        self.build_btn = GhostButton(t('Собрать'))
        self.publish_btn = AccentButton(t('Опубликовать'))
        self.publish_btn.setEnabled(False)
        self.build_btn.clicked.connect(self._build)
        self.publish_btn.clicked.connect(self._publish)
        arow.addWidget(self.build_btn)
        arow.addWidget(self.publish_btn)
        arow.addStretch(1)
        ab.addLayout(arow)
        self.author_status = label("", 10, role="muted", wrap=True)
        ab.addWidget(self.author_status)

    def refresh(self) -> None:
        if not self._working:
            self._fill_packs()

    def _busy(self, on):
        self._working = on
        for field in (self.author_pack, self.pack_desc, self.pack_server, self.pack_version, self.changelog, self.build_btn):
            field.setEnabled(not on)
        self.publish_btn.setEnabled(not on and self._build_result is not None)

    def _fill_packs(self) -> None:
        self._packs = localpacks.list_installed(self.ctx.lay)
        cur = self.author_pack.currentData()
        self.author_pack.blockSignals(True)
        self.author_pack.clear()
        for lp in self._packs:
            self.author_pack.addItem(lp.name, lp.id)
        idx = max(0, self.author_pack.findData(cur))
        self.author_pack.setCurrentIndex(idx)
        self.author_pack.blockSignals(False)
        self._pack_picked(idx)

    def _selected(self):
        i = self.author_pack.currentIndex()
        return self._packs[i] if 0 <= i < len(self._packs) else None

    def _pack_picked(self, _i) -> None:
        lp = self._selected()
        self._build_result = None
        self.publish_btn.setEnabled(False)
        if lp is None:
            return
        self.pack_desc.setText(lp.description)
        self.pack_server.setText(lp.server)
        self.pack_version.setText(next_version(lp.version))
        cat = getattr(self.ctx, "catalog", None)
        self.publish_btn.setText(t('Обновить сборку') if cat is not None and cat.get(lp.id) else t('Опубликовать'))

    def _author_dir(self) -> Path:
        d = self.ctx.lay.cache / "author"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _prev_index(self, pack_id: str):
        built = sorted(self._author_dir().glob(f"{pack_id}-*.mrpack"), key=lambda p: p.stat().st_mtime)
        try:
            return MrPack.open(built[-1]) if built else None
        except Exception:  # noqa: BLE001 - a broken old build just means "no previous version"
            return None

    def _build(self) -> None:
        lp = self._selected()
        if lp is None:
            self.author_status.setText(t('Сначала установи или перенеси сборку на главной.'))
            return
        version = self.pack_version.text().strip()
        if not version:
            self.author_status.setText(t('Укажи версию, например 0.2.'))
            return
        gd = localpacks.game_dir(self.ctx.lay, lp.id)
        changelog = self.changelog.toPlainText().strip()
        self.author_status.setText(t('Собираю: сверяю моды с Modrinth'))
        self.publish_btn.setEnabled(False)
        self._build_result = None
        self._busy(True)
        prev = self._prev_index(lp.id)

        def job(progress):
            cf = for_context(self.ctx)
            res = author.build(gd, self.ctx.modrinth, lp.name, version, lp.mc_version, lp.loader, lp.loader_version,
                               changelog, prev, cf=cf)
            path = author.write(res, gd, self._author_dir(), lp.id)
            return res, path

        jobs.run(job, on_done=lambda r: self._built(lp, version, r), on_error=self._author_failed)

    def _built(self, lp, version: str, result) -> None:
        res, path = result
        self._build_result = (lp, version, res, path)
        self._busy(False)
        d = res.diff
        lines = [t('Собрано: {x1} файлов с Modrinth, {x3} своих файлов.', x1=len(res.index.files), x3=len(res.overrides)),
                 t('Добавлено {x1}, обновлено {x3}, убрано {x5}.', x1=len(d.added), x3=len(d.updated), x5=len(d.removed))]
        lines += res.warnings
        self.author_status.setText("\n".join(lines))
        self.publish_btn.setEnabled(True)

    def _publish(self) -> None:
        if not self._build_result:
            return
        lp, version, res, path = self._build_result
        repo, token = self.ctx.settings.github_repo.strip(), self.ctx.settings.github_token.strip()
        if not repo or not token:
            self.author_status.setText(t('Укажи репозиторий и токен GitHub в настройках.'))
            return
        update = self.publish_btn.text() == t('Обновить сборку')
        question = (t('Обновить сборку «{name}» до {version} у всех игроков?', name=lp.name, version=version) if update
                    else t('Опубликовать {name} {version} для всех игроков?', name=lp.name, version=version))
        if not common.confirm(self, t('Публикация'), question, self.publish_btn.text()):
            return
        entry = PackEntry(lp.id, lp.name, self.pack_desc.text().strip(), version, lp.mc_version, lp.loader,
                          lp.loader_version, "", "", res.index.changelog, self.pack_server.text().strip())
        self.author_status.setText(t('Публикую'))
        self._busy(True)

        def job(progress):
            url = author.publish(self.ctx.http, repo, token, entry, path)
            lp.version, lp.description, lp.server = version, entry.description, entry.server
            localpacks.save(self.ctx.lay, lp)
            return url

        jobs.run(job, on_done=self._published, on_error=self._author_failed)

    def _published(self, url: str) -> None:
        self._busy(False)
        self.author_status.setText(t('Опубликовано. Игроки увидят обновление при следующем запуске лаунчера.\n{url}', url=url))
        self._fill_packs()

    def _author_failed(self, e: BaseException) -> None:
        self.author_status.setText(_error_text(e))
        self._busy(False)
