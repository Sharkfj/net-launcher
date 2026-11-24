from netlauncher import catalog
from netlauncher.auth_ely import Account, offline_account
from netlauncher.ui import supporter
from netlauncher.ui.app import make_context
from tests.fakes import FakeHttp


def test_catalog_support_link_and_account_scoped_cache(home):
    raw = {"friends": {"url": "https://friends.example"}, "support": {"url": "https://boosty.to/shark_fj"}}
    cat = catalog.parse(raw)
    assert cat.support_url == raw["support"]["url"]
    assert catalog.to_json(cat)["support"] == raw["support"]
    ctx = make_context(home, FakeHttp())
    ctx.catalog = cat
    ctx.accounts.save(Account("Sam", "abc-def", "token", "ct"))
    supporter.remember(ctx, None, {"profile_uuid": "abcdef", "supporter": True})
    assert supporter.active(ctx)
    ctx.accounts.save(Account("Lee", "123", "token", "ct"))
    supporter.remember(ctx, None, {"profile_uuid": "abcdef", "supporter": True})
    assert not supporter.active(ctx)
    ctx.accounts.save(offline_account("Sam"))
    assert not supporter.active(ctx)
