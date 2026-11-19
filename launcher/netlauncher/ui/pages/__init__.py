from netlauncher.ui.pages.home import HomePage


def _content(kind):
    def make(ctx, window):
        from netlauncher.ui.pages.content import ContentPage
        return ContentPage(ctx, window, kind)
    return make


def _snapshots(ctx, window):
    from netlauncher.ui.pages.snapshots_page import SnapshotsPage
    return SnapshotsPage(ctx, window)


def _friends(ctx, window):
    from netlauncher.ui.pages.friends_page import FriendsPage
    return FriendsPage(ctx, window)


def _settings(ctx, window):
    from netlauncher.ui.pages.settings_page import SettingsPage
    return SettingsPage(ctx, window)


FACTORY = {"home": HomePage, "mods": _content("mod"), "resourcepacks": _content("resourcepack"),
           "shaders": _content("shader"), "friends": _friends, "snapshots": _snapshots, "settings": _settings}
