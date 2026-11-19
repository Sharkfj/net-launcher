import json

from netlauncher.curseforge import API as CF, CurseForge
from netlauncher.modrinth import API, Modrinth
from tests.fakes import FakeHttp


def test_modrinth_search_sort_and_category():
    fake = FakeHttp({f"{API}/search": {"hits": []}})
    Modrinth(fake).search("", "mod", "1.21.1", "neoforge", sort="newest", category="technology")
    p = fake.calls[-1].params
    assert p["index"] == "newest" and ["categories:technology"] in json.loads(p["facets"])
    Modrinth(fake).search("rain", "mod", "1.21.1", "neoforge")
    assert fake.calls[-1].params["index"] == "relevance"
    Modrinth(fake).search("", "mod", "1.21.1", "neoforge")
    assert fake.calls[-1].params["index"] == "downloads"


def test_modrinth_categories_for_kind():
    fake = FakeHttp({f"{API}/tag/category": [
        {"name": "technology", "project_type": "mod", "header": "categories", "icon": ""},
        {"name": "adventure", "project_type": "mod", "header": "categories", "icon": ""},
        {"name": "neoforge", "project_type": "mod", "header": "loaders", "icon": ""},
        {"name": "realistic", "project_type": "resourcepack", "header": "categories", "icon": ""}]})
    assert Modrinth(fake).categories("mod") == [("adventure", "Adventure"), ("technology", "Technology")]


def test_modrinth_details():
    fake = FakeHttp({f"{API}/project/sodium": {
        "id": "AANobbMI", "slug": "sodium", "title": "Sodium", "description": "Fast", "body": "# Sodium\n![x](https://i/x.gif)",
        "downloads": 90, "followers": 5, "categories": ["optimization"], "icon_url": "https://i/icon.png",
        "gallery": [{"url": "https://i/1.png", "title": "Shot", "featured": True}],
        "source_url": "https://github.com/x", "wiki_url": None, "discord_url": "https://discord.gg/x"},
        f"{API}/project/sodium/members": [{"role": "Owner", "user": {"username": "jellysquid"}}]})
    d = Modrinth(fake).details("sodium")
    assert d.title == "Sodium" and d.author == "jellysquid" and d.body_format == "markdown"
    assert d.gallery == [("https://i/1.png", "Shot")] and d.links == {"Исходники": "https://github.com/x",
                                                                         "Discord": "https://discord.gg/x"}
    assert d.page_url == "https://modrinth.com/mod/sodium"


def test_curseforge_search_sort_category_and_details():
    fake = FakeHttp({f"{CF}/mods/search": {"data": []},
                     f"{CF}/categories": {"data": [{"id": 412, "name": "Technology", "parentCategoryId": 6},
                                                   {"id": 6, "name": "Mods", "parentCategoryId": None}]},
                     f"{CF}/mods/7": {"data": {"id": 7, "name": "Chromeware", "slug": "c", "summary": "s",
                                                "downloadCount": 3, "logo": {"thumbnailUrl": "https://i/l.png"},
                                                "links": {"websiteUrl": "https://cf/c", "sourceUrl": "https://gh/c"},
                                                "authors": [{"name": "breenihilation"}],
                                                "categories": [{"name": "Technology"}],
                                                "screenshots": [{"url": "https://i/s.png", "title": "Arm"}]}},
                     f"{CF}/mods/7/description": {"data": "<p>Импланты <img src='https://i/a.gif'></p>"}})
    cf = CurseForge(fake, "KEY")
    cf.search("", "mod", "1.21.1", "neoforge", sort="updated", category="412")
    p = fake.calls[-1].params
    assert p["sortField"] == 3 and p["categoryId"] == 412
    assert cf.categories("mod") == [("412", "Technology")]
    d = cf.details("cf:7")
    assert d.author == "breenihilation" and d.body_format == "html" and "Импланты" in d.body
    assert d.gallery == [("https://i/s.png", "Arm")] and d.page_url == "https://cf/c"
    assert d.links == {"Исходники": "https://gh/c"}
