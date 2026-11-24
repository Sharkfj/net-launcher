"""Share a custom pack by exact source hashes and game settings, without redistributing jars."""
from __future__ import annotations

import base64
import json
import re
import tempfile
import zlib
from pathlib import Path
from urllib.parse import quote

from netlauncher import author, curseforge, localpacks
from netlauncher.i18n import t
from netlauncher.modmeta import sha1_file
from netlauncher.pack import ManualFile, PackIndex

KINDS = {"mods": ".jar", "resourcepacks": ".zip", "shaderpacks": ".zip"}
CONFIG_EXT = {".cfg", ".conf", ".toml", ".json", ".json5", ".properties", ".txt", ".yaml", ".yml", ".ini"}
MAX_CONFIG = 12 * 1024 * 1024
VERSION = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9.+_-]{0,79}")
PACK_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,79}")
RESERVED = re.compile(r"(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?")


def _valid_part(s):
    return (isinstance(s,str) and 0 < len(s) <= 200 and s not in {".",".."} and not s.endswith((" ",".")) and
            not any(ord(c)<32 or c in '/\\:<>"|?*' for c in s) and not RESERVED.fullmatch(s))


def _check(ok):
    if not ok:
        raise ValueError(t("В карточке сборки неверные данные."))


def _config_path(key):
    if key == "options.txt":
        return True
    parts = key.split("/")
    return (len(parts) >= 2 and parts[0] in ("config","defaultconfigs") and all(map(_valid_part,parts))
            and Path(parts[-1]).suffix.lower() in CONFIG_EXT)


def make_card(ctx, pack):
    cat = ctx.catalog
    if pack.official or cat and cat.get(pack.id):
        return "official", {"name":pack.name,"id":pack.id}
    root = localpacks.game_dir(ctx.lay, pack.id)
    paths = []
    for folder, ext in KINDS.items():
        directory = root / folder
        if directory.is_dir() and not directory.is_symlink():
            paths += [p for p in sorted(directory.iterdir()) if p.is_file() and not p.is_symlink()
                      and p.name.lower().removesuffix(".disabled").endswith(ext)]
    hashes = {p:sha1_file(p) for p in paths}
    mr = ctx.modrinth.versions_by_hash(list(hashes.values()))
    missing = [p for p,h in hashes.items() if h not in mr]
    cf = curseforge.for_context(ctx) if missing else None
    hits = cf.match_files(missing) if cf else {}
    files = []
    for p,h in hashes.items():
        entry = {"path":p.relative_to(root).as_posix(),"sha1":h}
        if p in hits:
            project, f = hits[p]
            entry.update(cf_project=project["id"], cf_file=f["id"])
        files.append(entry)
    settings, total = {}, 0
    for path in [root/"options.txt", *(p for folder in ("config","defaultconfigs")
                                       for p in sorted((root/folder).rglob("*")))]:
        key = path.relative_to(root).as_posix()
        if not path.is_file() or path.is_symlink() or path.resolve() != root.resolve()/key or not _config_path(key):
            continue
        total += path.stat().st_size
        if total > MAX_CONFIG:
            raise ValueError(t("Настройки сборки слишком велики для чата."))
        try:
            settings[key] = path.read_text(encoding="utf-8")
        except UnicodeError:
            continue
    raw = json.dumps(settings,ensure_ascii=False).encode()
    if len(raw)>MAX_CONFIG:
        raise ValueError(t("Настройки сборки слишком велики для чата."))
    payload = base64.b64encode(zlib.compress(raw)).decode()
    origin = root/".net"/"shared-id"
    source = origin.read_text().strip() if origin.is_file() else pack.id
    card = {"name":pack.name,"id":source,"version":pack.version,"mc":pack.mc_version,
            "loader":pack.loader,"loader_version":pack.loader_version,"files":files,"settings":payload}
    if len(json.dumps(card,ensure_ascii=False).encode()) > 512*1024:
        raise ValueError(t("Настройки сборки слишком велики для чата."))
    return "pack",card


def validate(card):
    _check(isinstance(card,dict) and isinstance(card.get("name"),str) and 0 < len(card["name"]) <= 120)
    _check(isinstance(card.get("id"),str) and PACK_ID.fullmatch(card["id"]) and _valid_part(card["id"]))
    _check(isinstance(card.get("mc"),str) and VERSION.fullmatch(card["mc"]) and card.get("loader") in
           {"vanilla","fabric","quilt","forge","neoforge"})
    _check(isinstance(card.get("loader_version"),str) and
           (card["loader_version"]=="" or VERSION.fullmatch(card["loader_version"])))
    _check(isinstance(card.get("version"), str) and len(card["version"])<=80)
    files = card.get("files")
    _check(isinstance(files,list) and len(files)<=3000)
    used = set()
    for f in files:
        _check(isinstance(f,dict) and isinstance(f.get("path"),str) and isinstance(f.get("sha1"),str))
        components = f["path"].split("/")
        _check(len(components)==2 and components[0] in KINDS and _valid_part(components[1]) and
               components[1].lower().removesuffix(".disabled").endswith(KINDS[components[0]]) and
               re.fullmatch(r"[a-f0-9]{40}",f["sha1"]) and f["path"].lower() not in used)
        used.add(f["path"].lower())
        if "cf_project" in f or "cf_file" in f:
            _check(all(type(f.get(key)) is int and 0<f[key]<2**53 for key in ("cf_project","cf_file")))
    try:
        encoded = card["settings"]
        _check(isinstance(encoded,str) and len(encoded)<=512*1024)
        unpack = zlib.decompressobj()
        raw = unpack.decompress(base64.b64decode(encoded,validate=True),MAX_CONFIG+1)
        _check(unpack.eof and not unpack.unused_data and len(raw)<=MAX_CONFIG)
        settings = json.loads(raw)
        _check(isinstance(settings,dict) and all(_config_path(k) and isinstance(v,str) for k,v in settings.items()))
        return settings
    except (KeyError,TypeError,ValueError,zlib.error):
        raise ValueError(t("В карточке сборки неверные данные.")) from None


def install_card(ctx, card, progress):
    settings = validate(card)
    files = card["files"]
    mr = ctx.modrinth.versions_by_hash([f["sha1"] for f in files])
    cf = curseforge.for_context(ctx) if any("cf_file" in f for f in files) else None
    missing = []
    with tempfile.TemporaryDirectory(dir=ctx.lay.instances,prefix=".chat-") as temp:
        stage = Path(temp) / "pack"
        stage.mkdir()
        for index, f in enumerate(files):
            fp, digest = f["path"], f["sha1"]
            name = fp.split("/")[1]
            version = mr.get(digest)
            url = next((mf.url for mf in version.files if mf.sha1==digest),"") if version else ""
            if not url and cf and "cf_file" in f:
                remote = cf.file(f["cf_project"],f["cf_file"])
                if any(h.get("algo")==1 and h.get("value","").lower()==digest for h in remote.get("hashes",[])):
                    url = remote.get("downloadUrl") or ""
            if url:
                ctx.http.download(url,stage/fp,sha1=digest)
            else:
                missing.append(ManualFile(fp,digest,name,"https://www.curseforge.com/minecraft/search?search="+quote(name)))
            progress(name,index+1,len(files))
        for key,value in settings.items():
            target = stage/key
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(value,encoding="utf-8")
        reserved = {p.id for p in getattr(ctx.catalog,"packs",[])}
        existing = {p.name for p in ctx.lay.instances.iterdir()} | reserved
        pack_id = card["id"] if card["id"] not in existing else author.new_pack_id(card["name"],existing)
        lp = localpacks.LocalPack(pack_id,card["name"],card["version"],card["mc"],card["loader"],card["loader_version"])
        net = stage/".net"
        net.mkdir()
        from dataclasses import asdict
        (net/"pack.json").write_text(json.dumps(asdict(lp),ensure_ascii=False),encoding="utf-8")
        (net/"shared-id").write_text(card["id"],encoding="utf-8")
        stage.rename(ctx.lay.instances/pack_id)
    index = PackIndex(lp.name,lp.version,lp.mc_version,lp.loader,lp.loader_version,[],missing)
    return lp,index,missing
