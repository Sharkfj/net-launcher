"""CurseForge API v1 client with the same surface Library uses for Modrinth (ids are "cf:<modId>")."""

from __future__ import annotations

from pathlib import Path

from netlauncher.modmeta import sha1_file
from netlauncher.modrinth import MrFile, MrProject, MrVersion, ProjectDetails
from netlauncher.net import Http

API = "https://api.curseforge.com/v1"
GAME = 432
CLASSES = {"mod": 6, "resourcepack": 12, "shader": 6552}
LOADERS = {"forge": 1, "fabric": 4, "quilt": 5, "neoforge": 6}
RELEASE = {1: "release", 2: "beta", 3: "alpha"}
SORT_FIELDS = {"relevance": 1, "downloads": 6, "updated": 3, "newest": 11}
WHITESPACE = {9, 10, 13, 32}


class NotDistributable(Exception):
    def __init__(self, name: str, page_url: str):
        super().__init__(f"{name}: автор запретил скачивание через сторонние программы")
        self.name, self.page_url = name, page_url


def murmur2(data: bytes, seed: int = 1) -> int:
    """MurmurHash2 (32-bit) as CurseForge uses it for file fingerprints."""
    m, r = 0x5BD1E995, 24
    length = len(data)
    h = (seed ^ length) & 0xFFFFFFFF
    i = 0
    while length - i >= 4:
        k = data[i] | (data[i + 1] << 8) | (data[i + 2] << 16) | (data[i + 3] << 24)
        k = (k * m) & 0xFFFFFFFF
        k ^= k >> r
        k = (k * m) & 0xFFFFFFFF
        h = (h * m) & 0xFFFFFFFF
        h ^= k
        i += 4
    rest = length - i
    if rest == 3:
        h ^= data[i + 2] << 16
    if rest >= 2:
        h ^= data[i + 1] << 8
    if rest >= 1:
        h ^= data[i]
        h = (h * m) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * m) & 0xFFFFFFFF
    h ^= h >> 15
    return h


def fingerprint(path: Path) -> int:
    raw = Path(path).read_bytes()
    return murmur2(bytes(b for b in raw if b not in WHITESPACE))


def _num(pid: str) -> int:
    return int(str(pid).removeprefix("cf:"))


def _sha1(f: dict) -> str:
    return next((h["value"] for h in f.get("hashes") or [] if h.get("algo") == 1), "")


class CurseForge:
    def __init__(self, http: Http, key: str):
        self.http, self.key = http, key

    def _h(self) -> dict:
        return {"x-api-key": self.key, "Accept": "application/json"}

    @staticmethod
    def to_project(m: dict) -> MrProject:
        return MrProject(f"cf:{m['id']}", m.get("slug", ""), m.get("name", ""), m.get("summary", ""),
                         int(m.get("downloadCount") or 0), (m.get("logo") or {}).get("thumbnailUrl") or "",
                         "mod", "unknown", "unknown")

    @staticmethod
    def page(m: dict, file_id: int | None = None) -> str:
        base = (m.get("links") or {}).get("websiteUrl") or ""
        return f"{base}/files/{file_id}" if base and file_id else base

    @staticmethod
    def to_version(f: dict) -> MrVersion:
        deps = [f"cf:{d['modId']}" for d in f.get("dependencies") or [] if d.get("relationType") == 3]
        file = MrFile(f.get("downloadUrl") or "", f.get("fileName", ""), _sha1(f), "", int(f.get("fileLength") or 0),
                      True)
        return MrVersion(f"cf:{f['id']}", f"cf:{f['modId']}", f.get("displayName", ""),
                         RELEASE.get(f.get("releaseType"), "release"), list(f.get("gameVersions") or []), [],
                         [file], deps, f.get("fileDate", ""))

    def search(self, query: str, kind: str, game_version: str, loader: str | None,
               offset: int = 0, limit: int = 20, sort: str | None = None,
               category: str | None = None) -> list[MrProject]:
        params = {"gameId": GAME, "classId": CLASSES[kind], "searchFilter": query, "gameVersion": game_version,
                  "sortField": SORT_FIELDS.get(sort or "", 2), "sortOrder": "desc", "index": offset,
                  "pageSize": limit}
        if category:
            params["categoryId"] = int(category)
        if kind == "mod" and loader in LOADERS:
            params["modLoaderType"] = LOADERS[loader]
        data = self.http.get_json(f"{API}/mods/search", params=params, headers=self._h()).get("data") or []
        return [self.to_project(m) for m in data]

    def categories(self, kind: str) -> list[tuple[str, str]]:
        data = self.http.get_json(f"{API}/categories", params={"gameId": GAME, "classId": CLASSES[kind]},
                                  headers=self._h()).get("data") or []
        cats = [c for c in data if c.get("parentCategoryId") is not None]
        return sorted(((str(c["id"]), c["name"]) for c in cats), key=lambda x: x[1])

    def details(self, project_id: str) -> ProjectDetails:
        mid = _num(project_id)
        m = self.http.get_json(f"{API}/mods/{mid}", headers=self._h()).get("data") or {}
        try:
            body = self.http.get_json(f"{API}/mods/{mid}/description", headers=self._h()).get("data") or ""
        except Exception:  # noqa: BLE001
            body = m.get("summary", "")
        lk = m.get("links") or {}
        links = {title: lk[key] for key, title in (("sourceUrl", "Исходники"), ("wikiUrl", "Вики"),
                                                   ("issuesUrl", "Ошибки")) if lk.get(key)}
        return ProjectDetails(f"cf:{mid}", m.get("name", ""), m.get("summary", ""),
                              ((m.get("authors") or [{}])[0]).get("name", ""), int(m.get("downloadCount") or 0), 0,
                              [c.get("name", "") for c in m.get("categories") or []], body, "html",
                              [(sc["url"], sc.get("title") or "") for sc in m.get("screenshots") or []], links,
                              (m.get("logo") or {}).get("thumbnailUrl") or "", lk.get("websiteUrl", ""))

    def _mods(self, ids: list[int]) -> list[dict]:
        if not ids:
            return []
        return self.http.post_json(f"{API}/mods", {"modIds": ids}, headers=self._h()).get("data") or []

    def projects(self, ids: list[str]) -> dict[str, MrProject]:
        nums = [_num(i) for i in ids if str(i).startswith("cf:")]
        return {p.id: p for p in map(self.to_project, self._mods(nums))}

    def best_version(self, project_id: str, game_version: str, loader: str | None) -> MrVersion | None:
        params = {"gameVersion": game_version, "pageSize": 50}
        if loader in LOADERS:
            params["modLoaderType"] = LOADERS[loader]
        files = self.http.get_json(f"{API}/mods/{_num(project_id)}/files", params=params,
                                   headers=self._h()).get("data") or []
        files = sorted(files, key=lambda f: f.get("fileDate", ""), reverse=True)
        if not files:
            return None
        best = next((f for f in files if f.get("releaseType") == 1), files[0])
        if not best.get("downloadUrl"):
            mods = self._mods([_num(project_id)])
            m = mods[0] if mods else {"name": project_id}
            raise NotDistributable(m.get("name", project_id), self.page(m, best["id"]))
        return self.to_version(best)

    def match_files(self, paths: list[Path]) -> dict[Path, tuple[dict, dict]]:
        if not paths:
            return {}
        fps = {fingerprint(p): Path(p) for p in paths}
        r = self.http.post_json(f"{API}/fingerprints/{GAME}", {"fingerprints": list(fps)}, headers=self._h())
        matches = (r or {}).get("data", {}).get("exactMatches") or []
        mods = {m["id"]: m for m in self._mods(sorted({x["id"] for x in matches}))}
        out: dict[Path, tuple[dict, dict]] = {}
        by_sha = {sha1_file(p): p for p in fps.values()}
        for x in matches:
            f = x.get("file") or {}
            p = by_sha.get(_sha1(f))
            if p is not None and x["id"] in mods:
                out[p] = (mods[x["id"]], f)
        return out
