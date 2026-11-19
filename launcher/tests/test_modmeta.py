import hashlib

from netlauncher.modmeta import read_jar, sha1_file
from tests.jars import jar_bytes, make_jar, toml_for


def test_neoforge_toml(tmp_path):
    j = make_jar(tmp_path / "a.jar", toml=toml_for("cinematic", "Cinematic Interaction", "0.18", logo="l.png"),
                 logo=b"PNG")
    m = read_jar(j)
    assert m.mod_ids == ["cinematic"] and m.name == "Cinematic Interaction" and m.version == "0.18"
    assert m.license == "MIT" and m.logo == b"PNG" and m.nested_ids == []


def test_display_url_and_multi_mods(tmp_path):
    toml = toml_for("a", url="https://example.org/a") + '[[mods]]\nmodId="a_extra"\nversion="1"\n'
    m = read_jar(make_jar(tmp_path / "a.jar", toml=toml))
    assert m.mod_ids == ["a", "a_extra"] and m.display_url == "https://example.org/a"


def test_broken_toml_regex_fallback(tmp_path):
    toml = 'license="All Rights Reserved"\nthis is = = not toml\n[[mods]]\nmodId="x"\nversion="2"\ndisplayName="X Mod"\n'
    m = read_jar(make_jar(tmp_path / "x.jar", toml=toml))
    assert m.mod_ids == ["x"] and m.name == "X Mod" and m.license == "All Rights Reserved"


def test_jar_version_from_manifest(tmp_path):
    toml = toml_for("y", version="${file.jarVersion}")
    m = read_jar(make_jar(tmp_path / "y.jar", toml=toml, manifest_version="3.4.5"))
    assert m.version == "3.4.5"


def test_nested_jarjar_ids(tmp_path):
    inner = jar_bytes(toml=toml_for("apollib"))
    m = read_jar(make_jar(tmp_path / "tectonic.jar", toml=toml_for("tectonic"), nested={"apollib-1.1.6.jar": inner}))
    assert m.mod_ids == ["tectonic"] and m.nested_ids == ["apollib"]


def test_fabric_json(tmp_path):
    m = read_jar(make_jar(tmp_path / "f.jar", fabric={"id": "sodium", "name": "Sodium", "version": "0.9",
                                                      "license": ["LGPL-3.0-only"], "icon": "i.png",
                                                      "contact": {"homepage": "https://h"}},
                          logo=b"I", logo_name="i.png"))
    assert m.mod_ids == ["sodium"] and m.license == "LGPL-3.0-only" and m.logo == b"I"
    assert m.display_url == "https://h"


def test_not_a_mod(tmp_path):
    assert read_jar(make_jar(tmp_path / "x.jar")) is None


def test_not_a_zip(tmp_path):
    p = tmp_path / "bad.jar"
    p.write_bytes(b"not a zip")
    assert read_jar(p) is None


def test_sha1_file(tmp_path):
    p = tmp_path / "Мод (1).jar"
    p.write_bytes(b"abc")
    assert sha1_file(p) == hashlib.sha1(b"abc").hexdigest()


def test_container_jar_uses_nested_ids(tmp_path):
    inner = jar_bytes(toml=toml_for("kotlinforforge", "Kotlin for Forge"))
    m = read_jar(make_jar(tmp_path / "kotlinforforge-5.13.0-all.jar", nested={"kff.jar": inner},
                          manifest_version="5.13.0"))
    assert m.mod_ids == ["kotlinforforge"] and m.nested_ids == []
    assert m.name == "kotlinforforge-5.13.0-all" and m.version == "5.13.0"
