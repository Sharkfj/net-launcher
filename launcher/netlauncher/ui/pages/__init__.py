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


def _packs(ctx, window):
    from netlauncher.ui.pages.packs_page import PacksPage
    return PacksPage(ctx, window)


def _pack(ctx, window):
    from netlauncher.ui.pages.pack_page import PackPage
    return PackPage(ctx, window)


def _official(ctx, window):
    from netlauncher.ui.pages.official_page import OfficialPage
    return OfficialPage(ctx, window)


def _profile(ctx, window):
    from netlauncher.ui.pages.profile import ProfilePage
    return ProfilePage(ctx, window)


FACTORY = {"home": HomePage, "packs": _packs, "pack": _pack, "official": _official, "friends": _friends,
           "settings": _settings, "profile": _profile}
