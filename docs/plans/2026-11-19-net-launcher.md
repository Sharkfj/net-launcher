# .NET Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A standalone Windows/Linux launcher for the ".NET" Minecraft pack: Ely.by login, installs Minecraft + NeoForge + Java + the pack from a GitHub release, keeps it updated, manages mods/resourcepacks/shaders with snapshots, launches the game — in a blurred glass, blue, animated UI.

**Architecture:** Pure-Python core (`netlauncher/*.py`, no Qt imports, unit-tested with a fake HTTP transport) + PySide6 UI layer (`netlauncher/ui/`) that runs core jobs on worker threads. Minecraft/NeoForge/Java installation and the launch command come from `minecraft-launcher-lib`; the pack is a standard `.mrpack` plus a small `net.json` extension; publishing goes through the GitHub REST API.

**Tech Stack:** Python ≥3.10 (dev: system 3.15, CI: 3.12), PySide6 ≥6.7 (dev: system 6.11.2), minecraft-launcher-lib 8.0, requests, pytest, PyInstaller (CI only), GitHub Actions.

**Spec:** `~/Games/NET/docs/2026-11-19-launcher-design.md`

## Global Constraints

- Repo root `~/Games/NET/` (git). Code `launcher/netlauncher/`, tests `launcher/tests/`. Run tests from `launcher/`: `.venv/bin/pytest -q`.
- Dev venv: `python3 -m venv --system-site-packages .venv` (uses system PySide6); `pip install minecraft-launcher-lib==8.0 pytest`.
- UI language Russian. Copy in this plan is exact where quoted.
- Data root: Linux `$XDG_DATA_HOME/net-launcher` (default `~/.local/share/net-launcher`), Windows `%APPDATA%\NET Launcher`; env `NET_LAUNCHER_HOME` overrides (tests always set it to a tmp dir).
- HTTP User-Agent exactly `NETLauncher/<__version__>`; no user data in requests except Ely.by credentials to authserver.ely.by and the GitHub token to api.github.com/uploads.github.com.
- Never store the Ely.by password. Accounts file mode 600 on POSIX.
- No change to mods/resourcepacks/shaderpacks/config without a snapshot first.
- Pack update never touches `saves/`, `screenshots/`, existing `options.txt`, or files not recorded in pack-state.
- Every download goes to `<name>.part`, is hash-verified, then renamed. Hash mismatch = error, file deleted.
- All paths via `pathlib`; subprocess args as lists; must work with Cyrillic and spaces in paths.
- Colors: window `rgba(12,18,32,0.72)`, card `rgba(255,255,255,0.06)`, card border `rgba(255,255,255,0.08)`, accent `#4C9AFF`, hover `#6AAEFF`, pressed `#3A86F0`, text `#E8EEF8`, secondary `#9AA8BF`, radius 14–18 px. No glow effects.
- Animation timings: window open scale 0.97→1 + fade; page switch 24 px slide + fade 220 ms OutCubic; hover 120 ms; list stagger 30 ms/row, max 12 rows. All disabled when `Settings.animations` is False.
- Ely.by: `https://authserver.ely.by/auth/{authenticate,refresh,validate,invalidate}`; 2FA = password `"<pass>:<code>"`; JVM arg `-javaagent:<authlib-injector.jar>=ely.by`.
- Pack for MC `1.21.1`, loader `neoforge` `21.1.267`, pack id `net`, display name `.NET`.
- Git: local commits after each task are fine; **nothing is pushed or published to GitHub without the user's explicit «да»**.

## Review Focus

1. **Network drops mid-install/update** → no half-written file is ever treated as valid; pack-state is written only after a fully successful apply; rerunning resumes. *(Task 6: `test_apply_update_failure_keeps_old_state`)*
2. **Cyrillic/space paths** (home `~/Рабочий стол`, Windows user `Вася Пупкин`) → scan, snapshot, update and command building all work. *(Task 4: `test_snapshot_cyrillic_paths`, Task 8: `test_command_with_cyrillic_dirs`)*
3. **Player state survives pack updates**: own mods, a disabled client-only pack mod, edited `options.txt`, worlds. *(Task 6: `test_update_preserves_player_state`)*
4. **Expired/revoked Ely.by token at Play** → silent refresh, else the login screen, never a crash or a game started with a dead token. *(Task 7: `test_ensure_valid_refreshes_then_needs_login`)*
5. **GitHub unreachable (blocked/offline)** → the installed pack still launches; update check failure is a quiet notice. *(Task 9: `test_check_update_offline_is_none`)*

---

### Task 1: Scaffold, paths, settings

**Files:**
- Create: `launcher/pyproject.toml`, `launcher/netlauncher/__init__.py` (`__version__ = "0.1.0"`), `launcher/netlauncher/__main__.py` (calls `netlauncher.ui.app.main()`; stub that prints version until Task 10), `launcher/netlauncher/paths.py`, `launcher/netlauncher/settings.py`, `launcher/tests/conftest.py`, `launcher/tests/test_paths_settings.py`, `.gitignore` (`.venv/ __pycache__/ build/ dist/ *.part`)

**Interfaces — Produces:**
- `paths.data_root() -> Path`
- `@dataclass(frozen=True) class Layout: root, minecraft, instances, snapshots, cache, settings_file, accounts_file` (all `Path`)
- `paths.layout(root: Path | None = None) -> Layout` (creates dirs)
- `paths.game_dir(lay: Layout, pack_id: str = "net") -> Path` → `lay.instances / pack_id`
- `@dataclass class Settings: max_ram_mb: int = 0 (0 = auto); fullscreen: bool = True; width: int = 1600; height: int = 900; animations: bool = True; author_mode: bool = False; github_repo: str = ""; github_token: str = ""; last_world: str = ""; source_instance: str = ""`
- `settings.load_settings(path) -> Settings` (missing/corrupt file → defaults; unknown keys ignored), `settings.save_settings(path, s) -> None` (atomic: tmp + replace)
- `settings.recommended_ram_mb(total_mb: int) -> int`
- `tests/conftest.py`: fixture `home(tmp_path, monkeypatch)` sets `NET_LAUNCHER_HOME` to `tmp_path / "Данные лаунчера"` and returns `paths.layout()`.

- [ ] **Step 1: git init `~/Games/NET`, create venv, write failing tests**

```python
def test_layout_under_env_root(home):
    assert home.root.name == "Данные лаунчера" and home.minecraft.is_dir() and home.snapshots.is_dir()
def test_windows_root(monkeypatch):
    monkeypatch.delenv("NET_LAUNCHER_HOME", raising=False); monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", r"C:\Users\Вася\AppData\Roaming")
    assert str(paths.data_root()).endswith("NET Launcher")
def test_settings_roundtrip_and_corrupt(home):
    s = Settings(max_ram_mb=6144, last_world="Новый мир"); save_settings(home.settings_file, s)
    assert load_settings(home.settings_file) == s
    home.settings_file.write_text("{oops"); assert load_settings(home.settings_file) == Settings()
@pytest.mark.parametrize("total,exp", [(8192, 4096), (16384, 8192), (32768, 8192), (4096, 3072)])
def test_recommended_ram(total, exp): assert recommended_ram_mb(total) == exp
```
`recommended_ram_mb` = `clamp(total//2, 3072, 8192)` rounded down to 512.

- [ ] **Step 2: Run** `.venv/bin/pytest -q tests/test_paths_settings.py` → FAIL (import errors)
- [ ] **Step 3: Implement** paths.py, settings.py, pyproject (deps `PySide6>=6.7`, `minecraft-launcher-lib==8.0`, `requests>=2.31`; script `net-launcher = netlauncher.__main__:main`)
- [ ] **Step 4: Run** → PASS
- [ ] **Step 5: Commit** `feat: scaffold, data layout and settings`

---

### Task 2: HTTP transport and Modrinth client

**Files:** Create `launcher/netlauncher/net.py`, `launcher/netlauncher/modrinth.py`, `launcher/tests/fakes.py`, `launcher/tests/test_net_modrinth.py`

**Interfaces — Produces:**
- `net.USER_AGENT`; exceptions `HttpError(status: int, url: str)`, `HashMismatch(path: Path)`, `Offline(url: str)` (connection/timeout)
- `class Http(Protocol)`: `get_json(url, params: dict | None = None, headers: dict | None = None) -> Any`; `post_json(url, body: Any, headers: dict | None = None) -> Any`; `download(url, dest: Path, sha1: str | None = None, sha512: str | None = None, progress: Callable[[int, int], None] | None = None) -> Path`; `request(method, url, *, data: bytes | None = None, headers: dict | None = None) -> tuple[int, bytes]`
- `class RequestsHttp(Http)` — requests.Session, timeout 30 s, 3 retries with backoff on connection errors/5xx, `.part` + verify + rename.
- `tests/fakes.FakeHttp(routes: dict[str, Any])` — exact-URL routes (params encoded sorted), `downloads: dict[url, bytes]`, records `calls`; unknown URL → `HttpError(404)`; `offline=True` → `Offline`.
- `modrinth.MrFile(url, filename, sha1, sha512, size, primary)`, `MrVersion(id, project_id, version_number, version_type, game_versions, loaders, files: list[MrFile], required_deps: list[str], date)` with `.primary_file`, `MrProject(id, slug, title, description, downloads, icon_url, project_type, client_side, server_side)`
- `class Modrinth(http)`: `search(query, project_type, game_version, loader, offset=0, limit=20) -> list[MrProject]`; `project(id_or_slug) -> MrProject`; `projects(ids) -> dict[str, MrProject]`; `versions(project, game_version, loader | None) -> list[MrVersion]` (newest first); `best_version(project, game_version, loader) -> MrVersion | None`; `versions_by_hash(sha1s) -> dict[str, MrVersion]`; `latest_by_hash(sha1s, game_version, loader) -> dict[str, MrVersion]` (POST `/version_files/update`)
- `modrinth.search_loader(kind: str, instance_loader: str) -> str | None`: `"mod"→instance_loader`, `"shader"→"iris"`, `"resourcepack"→None`

- [ ] **Step 1: Failing tests**

```python
def test_download_verifies_and_cleans(tmp_path):   # real RequestsHttp against a local http.server thread
    ...; with pytest.raises(HashMismatch): http.download(url, tmp_path/"a.jar", sha1="0"*40)
    assert not (tmp_path/"a.jar").exists() and not (tmp_path/"a.jar.part").exists()
def test_user_agent(): assert net.USER_AGENT == f"NETLauncher/{netlauncher.__version__}"
def test_best_version_prefers_release():   # fake versions: [beta 2.0 (newest), release 1.9]
    assert mr.best_version("p", "1.21.1", "neoforge").version_number == "1.9"
def test_best_version_falls_back_to_beta_when_no_release(): ...
def test_search_facets():
    mr.search("rain", "mod", "1.21.1", "neoforge")
    facets = json.loads(fake.calls[-1].params["facets"])
    assert ["versions:1.21.1"] in facets and ["categories:neoforge"] in facets and ["project_type:mod"] in facets
def test_search_loader():
    assert search_loader("shader", "neoforge") == "iris" and search_loader("resourcepack", "neoforge") is None
```
- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement** net.py, modrinth.py (API `https://api.modrinth.com/v2`), fakes.py
- [ ] **Step 4: Run** → PASS
- [ ] **Step 5: Commit** `feat: http transport and modrinth client`

---

### Task 3: Jar metadata

**Files:** Create `launcher/netlauncher/modmeta.py`, `launcher/tests/test_modmeta.py`, `launcher/tests/jars.py` (helper `make_jar(path, toml=None, fabric=None, logo=None, nested: dict[str, bytes] | None = None)`)

**Interfaces — Produces:**
- `@dataclass class JarMeta: mod_ids: list[str]; name: str; version: str; license: str; display_url: str; logo: bytes | None; nested_ids: list[str]`
- `modmeta.read_jar(path: Path) -> JarMeta | None` (None = not a mod jar / unreadable). Sources: `META-INF/neoforge.mods.toml` (tomllib; on TOML error fall back to regex for `modId`/`displayName`/`version`/`license`/`displayURL`/`logoFile`), `fabric.mod.json`; nested `META-INF/jarjar/*.jar` read one level deep → `nested_ids`. `version = "${file.jarVersion}"` resolves from `META-INF/MANIFEST.MF` `Implementation-Version`.
- `modmeta.sha1_file(path) -> str`

- [ ] **Step 1: Failing tests**

```python
def test_neoforge_toml(tmp_path):
    j = make_jar(tmp_path/"a.jar", toml='license="MIT"\n[[mods]]\nmodId="cinematic"\nversion="0.18"\ndisplayName="Cinematic Interaction"\nlogoFile="l.png"', logo=b"PNG")
    m = read_jar(j); assert m.mod_ids == ["cinematic"] and m.license == "MIT" and m.logo == b"PNG"
def test_broken_toml_regex_fallback(tmp_path): ...  # unquoted junk line + modId="x" → ["x"]
def test_nested_jarjar_ids(tmp_path): ...  # outer tectonic + nested apollib → nested_ids == ["apollib"]
def test_fabric_json(tmp_path): ...
def test_not_a_mod(tmp_path): assert read_jar(make_jar(tmp_path/"x.jar")) is None
```
Also run once against the real folder (manual check, not a test): `python -c` over `~/.local/share/ElyPrismLauncher/instances/1.21.1/minecraft/mods/*.jar` → every jar returns non-None and non-empty `mod_ids`.
- [ ] **Step 2: Run** → FAIL · **Step 3: Implement** · **Step 4: Run** → PASS + manual check prints `123 ok`
- [ ] **Step 5: Commit** `feat: read mod jar metadata`

---

### Task 4: Snapshots

**Files:** Create `launcher/netlauncher/snapshots.py`, `launcher/tests/test_snapshots.py`

**Interfaces — Produces:**
- `@dataclass class Snapshot: id: str; path: Path; created: datetime; reason: str; size_bytes: int; parts: list[str]`
- `DEFAULT_PARTS = ("mods", "config", "resourcepacks", "shaderpacks")`
- `create(root: Path, game_dir: Path, reason: str, parts=DEFAULT_PARTS) -> Snapshot` — copies existing parts into `root/<YYYYmmdd-HHMMSS>-<n>/`, writes `meta.json` (`reason`, `created`, `parts`)
- `list_snapshots(root) -> list[Snapshot]` newest first; `restore(root, snap, game_dir) -> Snapshot` (first creates `"Перед откатом"` snapshot, then replaces each part in `snap.parts`); `delete(snap)`; `prune(root, keep: int = 20)` (never deletes the newest)

- [ ] **Step 1: Failing tests**: `test_create_and_restore` (add/delete jars after snapshot → restore brings exact file set back), `test_restore_makes_safety_snapshot`, `test_prune_keeps_newest`, `test_snapshot_cyrillic_paths` (game dir `tmp/Рабочий стол/игра`, jar `Мод (1).jar`)
- [ ] **Step 2: Run** → FAIL · **Step 3: Implement** (shutil.copytree / rmtree) · **Step 4: Run** → PASS
- [ ] **Step 5: Commit** `feat: snapshots`

---

### Task 5: Content library (mods / resourcepacks / shaders)

**Files:** Create `launcher/netlauncher/library.py`, `launcher/tests/test_library.py`

**Interfaces:**
- Consumes: `Modrinth`, `Http` (Task 2), `read_jar`, `sha1_file` (Task 3), `snapshots.create` (Task 4), `PackState` (Task 6 — accept `pack_state: dict[str, dict] | None` = `{relpath: {"sha1":…, "client":…, "server":…}}` so this task does not import Task 6)
- Produces:
  - `Kind = Literal["mod", "resourcepack", "shader"]`; `FOLDERS = {"mod": "mods", "resourcepack": "resourcepacks", "shader": "shaderpacks"}`
  - `@dataclass class Item: kind; path: Path; name: str; version: str; enabled: bool; sha1: str; meta: JarMeta | None; from_pack: bool; locked: bool` (`locked` = from pack and its `server` env is `"required"`)
  - exceptions `Locked(item)`, `AlreadyInstalled(name)`
  - `@dataclass class InstallPlan: items: list[tuple[MrProject, MrVersion]]; skipped: list[str]` (skipped = deps already present)
  - `@dataclass class Update: item: Item; version: MrVersion`
  - `class Library(game_dir, snapshots_root, modrinth, http, cache_dir, game_version, loader, pack_state=None)` with `scan(kind) -> list[Item]` (sorted by name; `*.disabled` = disabled), `set_enabled(item, on) -> Item`, `remove(item)`, `plan_install(project_id, kind) -> InstallPlan`, `install(plan, kind, progress: Callable[[str, int, int], None] | None = None) -> list[Item]`, `check_updates(kind) -> list[Update]`, `apply_updates(updates, progress=None) -> list[Item]`
- Rules: every mutating call snapshots first (one snapshot per call, reason in Russian e.g. `"Установка: Particle Rain"`); `plan_install` resolves required deps recursively, skipping projects already installed (by `versions_by_hash` of installed files) — after download, a jar whose `mod_ids[0]` already exists among installed `mod_ids + nested_ids` is discarded and listed in `skipped`; updates never offer `beta/alpha` over an installed `release`.

- [ ] **Step 1: Failing tests** (FakeHttp + `make_jar`):

```python
def test_scan_and_toggle(lib): ...  # a.jar → set_enabled(False) → file a.jar.disabled, snapshot exists
def test_locked_pack_mod_cannot_be_disabled(lib_with_state):
    with pytest.raises(Locked): lib.set_enabled(item_server_required, False)
def test_install_resolves_deps_and_skips_present(lib):
    plan = lib.plan_install("shoulder", "mod")  # requires cloth-config (already installed by hash) and newlib
    assert [p.slug for p, _ in plan.items] == ["shoulder", "newlib"] and plan.skipped == ["cloth-config"]
def test_install_discards_dup_modid_from_nested(lib): ...  # dep apollib present inside tectonic jarjar → not added
def test_updates_skip_beta_over_release(lib): ...
```
- [ ] **Step 2: Run** → FAIL · **Step 3: Implement** · **Step 4: Run** → PASS
- [ ] **Step 5: Commit** `feat: content library with install, toggle, updates`

---

### Task 6: Pack format, update planning and applying

**Files:** Create `launcher/netlauncher/pack.py`, `launcher/tests/test_pack.py`

**Interfaces — Produces:**
- `@dataclass class PackFile: path: str; sha1: str; sha512: str; size: int; urls: list[str]; client: str = "required"; server: str = "required"`
- `@dataclass class ManualFile: path: str; sha1: str; name: str; page_url: str`
- `@dataclass class PackIndex: name: str; version: str; mc_version: str; loader: str; loader_version: str; files: list[PackFile]; manual: list[ManualFile]; preserve: list[str]; changelog: str`
- mrpack layout: `modrinth.index.json` (Modrinth formatVersion 1: `game`, `versionId`, `name`, `summary`, `files[{path,hashes{sha1,sha512},env{client,server},downloads,fileSize}]`, `dependencies{minecraft, neoforge}`), `net.json` (`manual`, `preserve`, `changelog`), `overrides/…`
- `class MrPack`: `open(path) -> MrPack`, `.index`, `.override_paths() -> list[str]`, `.read_override(rel) -> bytes`; `write_mrpack(dest, index, overrides_root: Path, override_files: list[str]) -> Path`
- `PackState` = JSON `<game_dir>/.net/pack-state.json`: `{"version": str, "files": {relpath: {"sha1", "client", "server"}}}`; `load_state(game_dir) -> dict | None`, `save_state(game_dir, state)`
- `@dataclass class UpdatePlan: downloads: list[PackFile]; overrides: list[str]; remove: list[str]; manual_missing: list[ManualFile]; keep_disabled: set[str]`
- `plan_update(pack: MrPack, game_dir: Path, state: dict | None) -> UpdatePlan`
- `apply_update(plan, pack, game_dir, http, cache_dir, snapshots_root, progress=None) -> dict` (new state)
- `add_manual(pack_index, game_dir, src_file: Path) -> ManualFile` (copies a user-dropped file if sha1 matches, else `HashMismatch`)
- `UnsafePath` for absolute paths, `..`, or drive letters.
- Rules: skip files with `client == "unsupported"`; never write under `saves/`, `screenshots/`; `options.txt` and `preserve` entries only if missing; a pack mod present as `<path>.disabled` whose `server != "required"` stays disabled (new version written as `.disabled`); `remove` = in old state, not in new index, still on disk; snapshot before applying when `game_dir/mods` exists; state saved last.

- [ ] **Step 1: Failing tests**

```python
def test_roundtrip_mrpack(tmp_path): ...  # write_mrpack → MrPack.open → same index, overrides list
def test_rejects_zip_slip(tmp_path): ...  # path "../../evil" → UnsafePath
def test_fresh_install_plan(tmp_path): ...  # all files downloaded, client-unsupported skipped
def test_update_only_changed(tmp_path): ...  # 1 changed sha1 → downloads == [that], removed file from v1 in remove
def test_update_preserves_player_state(tmp_path):
    # player: own mods/my.jar, mods/fog.jar.disabled (client-only pack mod), edited options.txt, saves/Мир/level.dat
    apply_update(...)
    assert (gd/"mods/my.jar").exists() and (gd/"mods/fog-2.jar.disabled").exists()
    assert (gd/"options.txt").read_text() == "lang:ru_ru\nmine" and (gd/"saves/Мир/level.dat").exists()
def test_apply_update_failure_keeps_old_state(tmp_path):
    # FakeHttp with wrong bytes for one file → HashMismatch; load_state(gd)["version"] == "0.1"; no *.part left
def test_manual_missing_and_add(tmp_path): ...
```
- [ ] **Step 2: Run** → FAIL · **Step 3: Implement** · **Step 4: Run** → PASS
- [ ] **Step 5: Commit** `feat: mrpack format and safe pack updates`

---

### Task 7: Ely.by accounts

**Files:** Create `launcher/netlauncher/auth_ely.py`, `launcher/tests/test_auth_ely.py`

**Interfaces — Produces:**
- `@dataclass class Account: name: str; uuid: str; access_token: str; client_token: str`
- exceptions `BadCredentials`, `TwoFactorRequired`, `NeedLogin`, `AuthUnavailable`
- `class ElyAuth(http)`: `login(username, password, totp: str | None = None) -> Account` (body `{"username", "password": pass or f"{pass}:{totp}", "clientToken": uuid4 hex, "requestUser": True}`; 401 with `errorMessage` containing `"two factor"` → `TwoFactorRequired`, other 401/403 → `BadCredentials`); `refresh(acc) -> Account`; `validate(acc) -> bool`; `logout(acc) -> None`
- `class AccountStore(path)`: `load() -> Account | None`, `save(acc)`, `clear()`; POSIX mode `0o600`
- `ensure_valid(auth, store) -> Account`: validate → refresh → `NeedLogin` (and clears store); `Offline` during validate → returns stored account (lets offline singleplayer start)
- `head_url(acc) -> str` = `f"https://skinsystem.ely.by/skins/{acc.name}.png"` (UI crops the 8×8 face)

- [ ] **Step 1: Failing tests**: `test_login_ok_stores_no_password`, `test_login_2fa_required`, `test_login_with_totp_concats`, `test_bad_credentials`, `test_ensure_valid_refreshes_then_needs_login` (validate 403 → refresh 200 → new token saved; then validate 403 + refresh 403 → `NeedLogin` and `store.load() is None`), `test_store_mode_600`
- [ ] **Step 2: Run** → FAIL · **Step 3: Implement** · **Step 4: Run** → PASS
- [ ] **Step 5: Commit** `feat: ely.by authentication`

---

### Task 8: Game install and launch

**Files:** Create `launcher/netlauncher/gameinstall.py`, `launcher/netlauncher/launch.py`, `launcher/tests/test_launch.py`, `launcher/tests/data/latest_sample.log` (copy of the real `instances/1.21.1/minecraft/logs/latest.log` with player name → `Player`, uuid → zeros, token line kept masked)

**Interfaces:**
- Consumes: `Layout` (Task 1), `Account` (Task 7), `Http` (Task 2)
- Produces:
  - `@dataclass class InstalledGame: version_id: str; java: Path`
  - `class GameInstaller(lay, http)`: `ensure(mc_version, loader, loader_version, progress: Callable[[str, int, int], None]) -> InstalledGame` — uses `minecraft_launcher_lib` (install vanilla, `mod_loader.get_mod_loader("neoforge").install(...)`, Java runtime for the version's `javaVersion.component`; check exact 8.0 signatures in the installed package source before writing); `ensure_authlib() -> Path` (from `https://authlib-injector.yushi.moe/artifact/latest.json`, sha256 verified, cached in `lay.cache`)
  - `@dataclass class LaunchSpec: game: InstalledGame; mc_dir: Path; game_dir: Path; account: Account; ram_mb: int; fullscreen: bool; width: int; height: int; authlib: Path; world: str | None = None`
  - `launch.build_command(spec) -> list[str]` via `minecraft_launcher_lib.command.get_minecraft_command`; must include `-Xmx{ram}m`, `-Xms{min(ram, 2048)}m`, `-javaagent:{authlib}=ely.by`, `-Dfile.encoding=UTF-8`, `--gameDir <game_dir>`, `--quickPlaySingleplayer <world>` when world set, launcher name `NETLauncher`
  - `class Stage(Enum): STARTING, LOADING, RESOURCES, MENU, WORLD, EXITED`; `class LogProgress`: `feed(line: str) -> tuple[Stage, float] | None` (fraction 0..1, monotonic)
  - `class GameProcess`: `start(cmd, cwd) -> None`, `poll() -> int | None`, `log_path: Path` (= `game_dir/logs/latest.log`)
  - `@dataclass class CrashInfo: description: str; cause: str; suspects: str; report: Path`; `crash_info(game_dir, since: float) -> CrashInfo | None` (newest `crash-reports/*.txt` with mtime ≥ since: `Description:` line, first exception line, `Suspected Mod`/`Suspected Mods:` block)
- Stage markers (from the sample log; executor confirms against it): `ModLauncher running` → STARTING; first `[modloading-worker` → LOADING; `Sound engine started` → RESOURCES; Iris/`Reloading ResourceManager` complete + no further worker lines for 2 s, or `Loaded … recipes`/`Joined`/`Preparing spawn area` → WORLD; MENU when RESOURCES seen and a `Render thread` line after `Created:` atlas lines.

- [ ] **Step 1: Failing tests**

```python
def test_command_has_ely_agent_and_ram(tmp_path): ...  # monkeypatch get_minecraft_command to echo options
def test_command_with_cyrillic_dirs(tmp_path): ...     # game_dir "Рабочий стол/игра" stays one argv element
def test_quickplay_world(tmp_path): ...
def test_log_progress_on_sample():
    stages = [s for s, _ in filter(None, map(LogProgress().feed, open(SAMPLE, encoding="utf-8")))]
    assert stages[0] is Stage.STARTING and Stage.LOADING in stages and Stage.RESOURCES in stages
def test_crash_info(tmp_path): ...  # synthetic crash report text
```
- [ ] **Step 2: Run** → FAIL · **Step 3: Implement** · **Step 4: Run** → PASS
- [ ] **Step 5: Integration check (manual, real network, ~1 GB):** `NET_LAUNCHER_HOME=~/Games/NET/.it .venv/bin/python -c "…GameInstaller(...).ensure('1.21.1','neoforge','21.1.267', print)"` → prints a version id like `neoforge-21.1.267` and a java path that runs `-version`.
- [ ] **Step 6: Commit** `feat: game install and launch`

---

### Task 9: Channel, author build and publish, PineconeMC import

**Files:** Create `launcher/netlauncher/channel.py`, `launcher/netlauncher/author.py`, `launcher/netlauncher/importer.py`, `launcher/tests/test_channel_author.py`

**Interfaces:**
- Consumes: Tasks 2, 3, 6
- Produces:
  - `@dataclass class Channel: pack_version: str; pack_url: str; pack_sha1: str; changelog: str; launcher_version: str; launcher_urls: dict[str, str]`
  - `channel.latest(http, repo: str) -> Channel | None` — GET `https://api.github.com/repos/{repo}/releases/latest`, download its `channel.json` asset; `Offline`/`HttpError` → `None`
  - `channel.is_newer(a: str, b: str) -> bool` (numeric dotted compare)
  - `channel.check_update(http, repo, installed_version: str | None) -> Channel | None` (None when offline or not newer)
  - `channel.PACK_REPO: str = ""` (filled once the GitHub repo exists); env `NET_LAUNCHER_CHANNEL` = local path or URL of a `channel.json` overrides the GitHub lookup (`channel.resolve(http) -> Channel | None` uses it first) — used for tests and the friend simulation in Task 14
  - `ALLOWED_LICENSES = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "LGPL-2.1", "LGPL-3.0", "GPL-3.0", "MPL-2.0", "CC0-1.0", "ISC", "Unlicense"}` (case-insensitive, also `*-only`/`*-or-later` forms)
  - `OVERRIDE_DIRS = ("config", "defaultconfigs", "resourcepacks", "shaderpacks", "pointblank")`, `OVERRIDE_FILES = ("options.txt",)`
  - `@dataclass class PackDiff: added: list[str]; removed: list[str]; updated: list[str]`; `@dataclass class BuildResult: index: PackIndex; overrides: list[str]; warnings: list[str]; diff: PackDiff`
  - `author.build(game_dir, modrinth, version, changelog, prev: PackIndex | None) -> BuildResult` — jar → Modrinth by sha1 (env from project `client_side`/`server_side`); else allowed license → `overrides/mods/<file>`; else `ManualFile` (page = jar `display_url`) + Russian warning `"<name>: закрытая лицензия, игроки скачают вручную"`
  - `author.write(result, game_dir, dest_dir) -> Path` (`net-<version>.mrpack`)
  - `author.publish(http, repo, token, result, mrpack: Path) -> str` — POST `/repos/{repo}/releases` (`tag_name: "pack-v<version>"`, `name: ".NET <version>"`, `body: changelog`, `make_latest: "true"`), upload `net-<version>.mrpack` and `channel.json` to `uploads.github.com/.../assets?name=…`; launcher fields from the newest `launcher-v*` release (if any). Returns release `html_url`.
  - `importer.find_instances() -> list[Path]` (Linux `~/.local/share/{ElyPrismLauncher,PrismLauncher}/instances/*`, Windows `%APPDATA%\{ElyPrismLauncher,PrismLauncher}\instances\*`; must contain `instance.cfg`)
  - `importer.read_versions(inst: Path) -> tuple[str, str, str]` (mc, loader, loader_version from `mmc-pack.json`)
  - `importer.import_instance(inst: Path, game_dir: Path, progress=None) -> None` — copies `inst/minecraft/*` except `logs`, `crash-reports`, `downloads`, `telemetry`, `.cache`

- [ ] **Step 1: Failing tests**: `test_is_newer` (`"0.10" > "0.9"`), `test_check_update_offline_is_none`, `test_build_classifies_mods` (modrinth hit → files; MIT jar → overrides; ARR jar → manual + warning), `test_build_diff`, `test_publish_calls` (FakeHttp records release POST with `tag_name == "pack-v0.2"` then two asset uploads), `test_import_skips_logs` (also `read_versions` on a fixture `mmc-pack.json` → `("1.21.1", "neoforge", "21.1.267")`)
- [ ] **Step 2: Run** → FAIL · **Step 3: Implement** · **Step 4: Run** → PASS
- [ ] **Step 5: Commit** `feat: update channel, author build/publish, prism import`

---

### Task 10: UI foundation (theme, blur, animations, window shell)

**Files:** Create `launcher/netlauncher/ui/__init__.py`, `ui/app.py`, `ui/theme.py`, `ui/blur.py`, `ui/anim.py`, `ui/widgets.py`, `ui/jobs.py`, `ui/window.py`, `launcher/tests/test_ui_shell.py`; Modify `netlauncher/__main__.py` to call `ui.app.main()`

**Interfaces — Produces:**
- `theme.TOKENS: dict[str, str]` (Global Constraints colors), `theme.qss() -> str`, `theme.apply(app)` (Fusion + palette + QSS; font: system UI font, 10.5 pt)
- `blur.enable(widget) -> bool` — Linux: ctypes `KWindowEffects::enableBlurBehind` (copy approach from `~/.local/share/glasscontrol/glasscontrol.py: enable_blur`); Windows: `DwmSetWindowAttribute` 20 (dark) + 38 = 3, fallback `SetWindowCompositionAttribute` accent 4; return False → window paints opaque `#0C1220`
- `anim`: `fade_slide_in(w, dx=24, ms=220)`, `fade_out(w, ms=160, then=None)`, `stagger(widgets, step_ms=30, max_rows=12)`, `HoverLift` (event filter: 120 ms color/offset), `set_enabled(bool)` (global switch, instant when off)
- `widgets`: `GlassCard(QFrame)`, `AccentButton(QPushButton)` (with `breathing: bool`), `GhostButton`, `Toggle(QAbstractButton)` (animated knob), `SmoothBar(QProgressBar)` (value animates), `IconCache` (memory+disk cache in `lay.cache/icons`), `SkinHead(QLabel)`
- `jobs.run(fn, *args, on_done, on_error, on_progress) -> Job` — QThreadPool worker; `on_progress(str, int, int)` delivered on GUI thread
- `window.MainWindow(ctx: AppContext)` — frameless, translucent, custom title area (drag, minimize, close), sidebar with sections `Главная, Моды, Ресурспаки, Шейдеры, Снимки, Настройки` + account chip at bottom, `QStackedWidget` with animated switching, tray icon (`Показать`, `Выход`), `open_page(name: str)`, `hide_to_tray()`, `restore_from_tray()`
- `@dataclass class AppContext: lay; settings; http; modrinth; auth; accounts; installer` built in `app.main()`; single-instance guard via `QLocalServer` name `net-launcher` (second start → raise existing window)

- [ ] **Step 1: Failing tests** (`QT_QPA_PLATFORM=offscreen`): `test_window_builds_all_pages`, `test_page_switch_animates_and_lands` (process events 400 ms → current page == target, opacity 1), `test_animations_off_is_instant`, `test_qss_uses_tokens` (`"#4C9AFF" in qss()` and no `"glow"`), `test_blur_noop_offscreen` (returns False, no exception)
- [ ] **Step 2: Run** → FAIL · **Step 3: Implement** · **Step 4: Run** → PASS
- [ ] **Step 5: Visual check:** run `.venv/bin/python -m netlauncher` on the KDE desktop, screenshot (`spectacle -b -n -a -o <scratchpad>/shell.png`), confirm blur visible behind the window and switch animation smooth; fix until it looks right
- [ ] **Step 6: Commit** `feat: glass ui shell`

---

### Task 11: Onboarding and Home

**Files:** Create `ui/pages/__init__.py`, `ui/pages/onboarding.py`, `ui/pages/home.py`, `launcher/tests/test_ui_home.py`

**Interfaces:**
- Consumes: Tasks 6–10
- Produces: `OnboardingPage(ctx)` with signals `finished()`; `HomePage(ctx)` with `play()`, `refresh()`
- Onboarding flow: welcome (`".NET"`, `"Добро пожаловать"`) → Ely.by login (fields `Логин или e-mail`, `Пароль`, button `Войти`, link `Создать аккаунт Ely.by` → `https://account.ely.by/register`, 2FA field appears on `TwoFactorRequired`, errors: `"Неверный логин или пароль"`, `"Ely.by не отвечает, проверь интернет"`) → if a Prism instance named `1.21.1` exists and author mode is possible: offer `"Перенести сборку из PineconeMC"` (importer) else install: latest channel pack → `GameInstaller.ensure` → `apply_update`, one combined `SmoothBar` with step text and MB/s → manual-file step if needed (`"Этот мод нельзя скачать автоматически: …"`, button `Открыть страницу`, drop zone `Перетащи файл сюда`)
- Home: background slideshow from `game_dir/screenshots/*.png` (slow 1.00→1.06 zoom over 20 s, crossfade 1.2 s; none → gradient `#0C1220→#14305A`), title `.NET`, line `NeoForge 1.21.1 · N модов`, pack version, update badge `"Вышло обновление <v>"` + button `Обновить`, `AccentButton("ИГРАТЬ", breathing=True)`, `"Продолжить: <мир>"` (newest `saves/*/level.dat` mtime), `"Что нового"` card (channel changelog), notice `"Вышла новая версия лаунчера <v>"` + `Скачать` (opens the platform URL from `Channel.launcher_urls`) when `is_newer(channel.launcher_version, __version__)`. Play: `ensure_valid` → `NeedLogin` → onboarding login; else `GameInstaller.ensure` (fast when present) → `build_command` → `GameProcess.start`; status line follows `LogProgress`; at `MENU`/`WORLD` → `hide_to_tray()`; exit code ≠0 or `crash_info` → restore + crash card (`"Игра вылетела"`, description, suspects, `Открыть отчёт`)

- [ ] **Step 1: Failing tests** (offscreen, fakes): `test_onboarding_login_error_message`, `test_onboarding_2fa_field_appears`, `test_home_shows_update_badge`, `test_home_continue_world_newest`, `test_play_needlogin_routes_to_login`, `test_crash_card_after_nonzero_exit` (fake GameProcess)
- [ ] **Step 2: Run** → FAIL · **Step 3: Implement** · **Step 4: Run** → PASS
- [ ] **Step 5: Visual check** as in Task 10 (home with real screenshots)
- [ ] **Step 6: Commit** `feat: onboarding and home`

### Task 11b: 3D player model with the Ely.by skin (user request 19.11)

**Files:** Create `launcher/netlauncher/skin.py`, `launcher/netlauncher/ui/skinview.py`, `launcher/tests/test_skin.py`; Modify `ui/pages/home.py` (model on the right side of Home), `ui/window.py` (account chip uses `skin.face()`)

**Interfaces — Produces:**
- `skin.TEXTURES = "https://skinsystem.ely.by/textures/{name}"` → JSON `{"SKIN": {"url", "metadata": {"model": "slim"}?}}`
- `@dataclass class Skin: png: bytes; slim: bool`; `skin.fetch(http, name, cache_dir) -> Skin | None` (cached per name for 1 h; offline → cached or None; None → default Steve texture bundled in `netlauncher/ui/assets/steve.png`)
- `skin.parts(width: int, height: int, slim: bool) -> dict[str, Box]` — `Box(size=(w,h,d), origin=(x,y,z), uv=(u,v), mirror: bool, overlay: Box | None)` for head, body, arm_r, arm_l, leg_r, leg_l; 64×32 legacy skins reuse right arm/leg mirrored for the left; slim arms are 3 px wide; overlay boxes inflated by 0.5 (head) / 0.25 (others)
- `skin.face(png: bytes) -> QImage` 8×8 face + hat overlay (lives in ui/skinview.py to keep core Qt-free)
- `ui.skinview.SkinView3D(QWidget)`: orthographic 3D, painter's-algorithm face sort, each face drawn as a textured parallelogram (`QTransform.quadToQuad`, no smoothing → crisp pixels); drag to rotate (yaw ±180°, pitch ±25°) with inertia; idle: slow breathing + arm/leg swing ±6°, gentle yaw sway when not dragged; `set_skin(Skin)`; redraws ≤60 fps only while visible and animating
- [ ] **Step 1: Failing tests**: `test_parts_modern_vs_legacy` (64×32 → left arm mirror of right, no overlay for arms/legs), `test_slim_arm_width`, `test_fetch_slim_and_cache` (FakeHttp; second call within 1 h makes no request), `test_fetch_offline_uses_cache`, `test_skinview_renders_pixels` (offscreen grab has non-transparent pixels in the centre), `test_back_faces_hidden` (at yaw 0 the back of the head is not drawn)
- [ ] **Step 2: Run** → FAIL · **Step 3: Implement** · **Step 4: Run** → PASS · **Step 5: Visual check** with the real skin
- [ ] **Step 6: Commit** `feat: 3d skin model`

---

### Task 12: Content pages, Snapshots, Settings

**Files:** Create `ui/pages/content.py` (one class for all three kinds), `ui/pages/snapshots.py`, `ui/pages/settings.py`, `launcher/tests/test_ui_pages.py`

**Interfaces:**
- Consumes: `Library` (Task 5), `snapshots` (Task 4), `Settings` (Task 1), `author` (Task 9)
- Produces: `ContentPage(ctx, kind: Kind)`, `SnapshotsPage(ctx)`, `SettingsPage(ctx)`
- Content: header with search box (filters installed), filter chips `Все / Выключенные / Есть обновления`, rows (icon, name, version, pack badge `сборка` / `моё`, `Toggle`, menu `Удалить`), disabled toggle + tooltip `"Нужен на сервере — выключить нельзя"` for locked; button `Найти` opens an in-page Modrinth browser (debounced 300 ms search, cards with icon/title/description/downloads, `Установить` → shows plan `"Будет установлено: … (зависимости: …)"` → confirm), button `Проверить обновления` → list + `Обновить всё`
- Snapshots: list (date, reason, size), `Откатить` (confirm dialog `"Вернуть моды и конфиги к состоянию от <дата>? Текущее состояние сохранится отдельным снимком."`), `Удалить`
- Settings: RAM slider (step 512 MB, 2048..min(16384, total), label `"Рекомендуется N ГБ"`), fullscreen, resolution, `Анимации`, `Открыть папку игры`, `Выйти из аккаунта`; section `Автор сборки` (toggle `author_mode`; when on: `Репозиторий GitHub (user/repo)`, `Токен`, version field, changelog box, `Собрать` → shows diff + warnings, `Опубликовать` → confirm `"Опубликовать .NET <v> для всех игроков?"`)

- [ ] **Step 1: Failing tests**: `test_content_lists_and_filters`, `test_locked_toggle_disabled`, `test_install_flow_shows_plan`, `test_snapshot_restore_confirm`, `test_settings_ram_persist`, `test_author_section_hidden_when_off`
- [ ] **Step 2: Run** → FAIL · **Step 3: Implement** · **Step 4: Run** → PASS
- [ ] **Step 5: Visual check** of all pages
- [ ] **Step 6: Commit** `feat: content, snapshots and settings pages`

---

### Task 13: Packaging and desktop integration

**Files:** Create `launcher/packaging/net-launcher.spec` (PyInstaller; onefile on Windows `NET-Launcher.exe`, onedir on Linux), `launcher/packaging/icon.svg` + `icon.ico` + `icon.png`, `.github/workflows/launcher.yml`, `launcher/packaging/install-linux-local.sh`

- Workflow: on tag `launcher-v*` → jobs `windows-latest` and `ubuntu-22.04`, Python 3.12, `pip install . pyinstaller`, run `pytest -q` (`QT_QPA_PLATFORM=offscreen`), build, create release `make_latest: false` with `NET-Launcher.exe` and `NET-Launcher-linux.tar.gz`.
- Local install script: `~/.local/bin/net-launcher` (runs `~/Games/NET/launcher/.venv/bin/python -m netlauncher`), `~/.local/share/applications/net-launcher.desktop` (`Name=.NET Launcher`, `Icon=net-launcher`, `StartupWMClass=net-launcher`), icon to `~/.local/share/icons/hicolor/scalable/apps/net-launcher.svg`; app sets `QGuiApplication.setDesktopFileName("net-launcher")`.
- Icon: blue (`#4C9AFF` on `#0C1220`) rounded square with a geometric ".N" mark, no glow.

- [ ] **Step 1:** Write spec + script; run `pyinstaller packaging/net-launcher.spec` locally (Linux) → `dist/net-launcher/net-launcher` starts (`--version` prints `0.1.0`)
- [ ] **Step 2:** Run install script → launcher appears in the KDE menu with its icon and starts from it
- [ ] **Step 3:** Validate workflow YAML (`python -c "import yaml…"`) — real CI run happens when the user creates the repo
- [ ] **Step 4: Commit** `build: packaging, CI workflow, desktop entry`

---

### Task 14: End-to-end on this PC

No new files except fixes. Steps:
- [ ] **Step 1:** Launch `.NET Launcher`, log in to Ely.by (the user types the password), import from PineconeMC `1.21.1` → Home shows 123 mods, screenshots background
- [ ] **Step 2:** Play → status goes STARTING→LOADING→RESOURCES→MENU, window hides to tray; quit game → window returns
- [ ] **Step 3:** Author mode: `Собрать` version `0.1.0` → diff lists 118 Modrinth mods, 4 MIT in overrides, Chromeware as manual, warnings shown; `write` produces `net-0.1.0.mrpack`
- [ ] **Step 4:** Friend simulation: `NET_LAUNCHER_HOME=/tmp/…/friend` + local channel stub pointing at that mrpack → fresh install completes, asks for Chromeware manual file, accepts it after drop, Play reaches MENU
- [ ] **Step 5:** Toggle a mod, install one from Modrinth search, roll back via Snapshots → files match pre-change state
- [ ] **Step 6:** Report to user with screenshots; GitHub repo creation + first publish only after the user's «да»
