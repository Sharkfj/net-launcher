from PySide6.QtWidgets import QCheckBox

from netlauncher import coop, localpacks
from netlauncher.i18n import t
from netlauncher.ui import jobs


class CoopControl(QCheckBox):
    def __init__(self, ctx, window=None, parent=None):
        super().__init__(t('Приглашать друзей через e4mc'), parent)
        self.ctx, self.window = ctx, window
        self.setToolTip(t('Открой мир для сети в меню Minecraft. Друзья получат приглашение в лаунчере.'))
        self.pack = None
        self.request = 0
        self.busy = set()
        self.clicked.connect(self.change)
        self.hide()

    def show_pack(self, pack):
        self.request += 1
        request = self.request
        self.pack = pack
        self.hide()
        account = self.ctx.accounts.load()
        if (not pack or pack.loader not in coop.LOADERS or not self.ctx.friends_url()
                or not account or getattr(account, "offline", False)):
            return

        def checked(available):
            if self.request != request:
                return
            self.setChecked((localpacks.game_dir(self.ctx.lay, pack.id) / coop.OPT_IN).is_file())
            self.setEnabled(pack.id not in self.busy)
            self.setVisible(available)

        jobs.run(lambda progress: coop.available(self.ctx, pack), on_done=checked)

    def change(self, enabled):
        pack = self.pack
        self.busy.add(pack.id)
        self.setEnabled(False)

        def finish(error=None):
            self.busy.discard(pack.id)
            if self.pack and self.pack.id == pack.id:
                self.setEnabled(True)
                self.setChecked((localpacks.game_dir(self.ctx.lay, pack.id) / coop.OPT_IN).is_file())
            if error and self.window:
                self.window.toast(str(error))

        jobs.run(lambda progress: coop.set_enabled(self.ctx, pack, enabled, progress),
                 on_done=lambda _: finish(), on_error=finish)
