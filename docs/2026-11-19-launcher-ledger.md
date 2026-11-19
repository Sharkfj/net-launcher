# SDD ledger — plan: ~/Games/NET/docs/plans/2026-11-19-net-launcher.md
Spec: ~/Games/NET/docs/2026-11-19-launcher-design.md
Setup: Ruling: new repo, isolation via branch feat/launcher (main holds only docs) instead of a worktree — repo created this session, nothing else to protect — cost if wrong: none.
Setup: Ruling: repo-local git identity "Shark <shark@net.local>" — user's real email must not leak into a public repo — cost: rewrite author before first push.
Pre-flight:
- T5↔T6: T5 takes pack_state as dict {relpath:{sha1,client,server}}; T6 state["files"] has same shape → T5 receives state["files"]. OK.
- T8↔T7/T1: Account(name,uuid,access_token,client_token), Layout fields → match.
- T9↔T2/T3/T6: uses Modrinth.versions_by_hash/projects, JarMeta.license/display_url, PackIndex/ManualFile/write_mrpack → match.
- T11↔T6/T7/T8/T9: channel.resolve, apply_update, GameInstaller.ensure, ensure_valid, LogProgress, crash_info → match.
- T12↔T4/T5/T9: Library API, snapshots.restore(root,snap,game_dir), author.build/write/publish → match.
Task 1: complete (commits 5782779..b53baff, tests: bash -c 'cd launcher && .venv/bin/pytest -q' → 10 passed in 0.01s)
Task 2: complete (commits b53baff..84568ee, tests: bash -c 'cd launcher && .venv/bin/pytest -q' → 26 passed in 1.58s)
Plan: Ruling: user added mid-run (19.11) — 3D player model with Ely.by skin → new Task 11b in plan + spec line; UI copy must go through skill unslop (apply in Tasks 11/12) — direct user requests — cost: none.
Task 3: Ruling: container jars (kotlinforforge-all, mezz_config standalone) have no own metadata → read_jar returns mod_ids = nested ids, name = file stem — plan's manual check expects every real jar to return ids — cost if wrong: dup-detection treats container as owning those ids (desired).
Task 3: complete (commits 84568ee..37373c9, tests: bash -c 'cd launcher && .venv/bin/pytest -q' → 36 passed in 1.62s)
Task 4: complete (commits 37373c9..f52a3ba, tests: bash -c 'cd launcher && .venv/bin/pytest -q' → 43 passed in 1.60s)
Task 5: Ruling: check_updates skips every pack item (not only locked) — a player-updated pack mod gets a new filename and the next pack update would re-download the old one → duplicate mod — cost: players can't update client-only pack mods themselves (author does it via pack).
Task 5: complete (commits f52a3ba..cbc87ba, tests: bash -c 'cd launcher && .venv/bin/pytest -q' → 53 passed in 1.63s)
Task 6: complete (commits cbc87ba..de848f4, tests: bash -c 'cd launcher && .venv/bin/pytest -q' → 65 passed in 1.65s)
Task 7: complete (commits de848f4..74366cb, tests: bash -c 'cd launcher && .venv/bin/pytest -q' → 75 passed in 1.67s)
Plan: Ruling: user (19.11) wants to publish NEW packs that players can install at once → channel.json replaced by catalog.json on the default branch (GitHub contents API), releases per pack tag <id>-v<ver>, Task 9 rewritten, Home gets pack switcher + 'Играть на сервере' (server field), Settings.selected_pack, LaunchSpec.server — cost if wrong: extra UI.
Task 9: Ruling: author.write takes pack_id (plan signature lacked it but names file <pack_id>-<version>.mrpack) — cost: none. Ruling: resourcepacks/shaderpacks zips found on Modrinth go into files[] (download) not overrides — smaller pack — cost: none.
Task 9: complete (commits f1c6780..90e4314, tests: bash -c 'cd launcher && .venv/bin/pytest -q' → 97 passed in 1.69s)
Task 8: integration check (Step 5) real install → InstalledGame('neoforge-21.1.267', …/java-runtime-delta/bin/java) in 141 s, java -version = openjdk 21.0.7, authlib-injector-1.2.8.jar; installed into the real data root ~/.local/share/net-launcher (reused by Task 14). Ruling: LogProgress MENU markers = Realms/TitleScreen lines + idle(3 s) fallback after 'Sound engine started' — no explicit title-screen log line exists — cost: menu stage may show ~3 s late.
Task 8: complete (commits 74366cb..90e4314, tests: bash -c 'cd launcher && .venv/bin/pytest -q' → 97 passed in 1.70s)
Task 10: Ruling: window open = fade + 14 px rise of content (+ sidebar slide) instead of scale 0.97→1 — Qt widgets can't scale without a snapshot overlay; frontend-design: one orchestrated entrance — cost: slightly different feel than spec.
Task 10: Ruling: no "breathing" Play button — frontend-design restraint: the 3D model is the only ambient motion — cost: spec line not implemented (AccentButton has no breathing flag).
Task 10: Ruling: fonts Unbounded (display) + Onest (body), OFL, bundled in ui/assets/fonts — Cyrillic-strong, distinctive — cost: +1 MB.
Task 10: Ruling: dark text #071224 on accent buttons (white on #4C9AFF fails contrast) — cost: none.
Task 10: visual check done on KDE: blur visible, Unbounded title, sliding nav indicator. Bug found+fixed: app QSS font rule overrode widget fonts (test_widget_fonts_survive_stylesheet RED→GREEN); SmoothBar stop() on self-deleted animation (anim.stop guard).
Note: user asked (19.11) credits "@looper_fj и Claude Code" → AppContext CREDITS, shown in Settings "О лаунчере" (Task 12); "систему авторизации" = Ely.by login screen (Task 11).
Task 10: complete (commits 90e4314..4c814ef, tests: bash -c 'cd launcher && .venv/bin/pytest -q' → 109 passed in 3.71s)
Task 11: Ruling: added core module localpacks.py (LocalPack in instances/<id>/.net/pack.json, version from pack-state, mod_count, newest_world, total_ram_mb) — Home needs installed-pack identity for catalog/import packs; plan had no owner — cost: none.
Task 11: Ruling: onboarding is inside HomePage (modes login/empty/pack/install/manual) instead of a separate OnboardingPage; empty state offers catalog packs + "Перенести «<instance>»" from PineconeMC — fewer screens; import replaces the plan's onboarding import step — cost: none.
Task 11: Ruling: Settings.selected_pack added (default "net") — plan revision for catalog — cost: none.
Task 11: copy written per unslop (plain, errors say what + what to do, no arrows/exclamations/middle-dot meta).
Task 11: complete (commits 4c814ef..d134b6d, tests: bash -c 'cd launcher && .venv/bin/pytest -q' → 122 passed in 4.96s)
Task 11b: Ruling: own default skin drawn in code (blue jacket) instead of bundling Mojang's Steve — Steve texture is Mojang's asset — cost: default looks different from vanilla.
Task 11b: Ruling: face shading via cached pre-shaded tiles (SourceAtop on the tile) — shading in the widget darkened faces behind transparent overlay pixels — cost: none.
Task 11/11b visual check: offscreen render of Home with sample data (title Unbounded 44, buttons, 3D model right) looks right; fixed idle progress track showing (test_progress_bar_hidden_when_idle RED→GREEN). Desktop check with blur + real Ely skin in Task 14 (needs user's login).
Task 11b: complete (commits d134b6d..9dc65ee, tests: bash -c 'cd launcher && .venv/bin/pytest -q' → 132 passed in 5.61s)
Task 12: Ruling: author "Новая сборка" = any pack installed/imported in the launcher that is not yet in the catalog (pack picker lists local packs; new ones get appended to catalog on first publish); previous index for diff = last local build in cache/author — no separate new-pack wizard needed — cost: author must import the pack on Home first.
Task 12: Ruling: snapshots are per pack (lay.snapshots/<pack_id>) — multi-pack catalog — cost: none.
Task 12: About block "Разработчики: @looper_fj и Claude Code" (user request) + OFL font note.
Task 12: visual check (offscreen render): mods list with real jar icons OK; fixed narrow author fields + RAM hint mismatch (test_settings_fields_wide_and_ram_hint_matches RED→GREEN), styled QComboBox.
Task 12: complete (commits 9dc65ee..225178c, tests: bash -c 'cd launcher && .venv/bin/pytest -q' → 140 passed in 9.53s)
Task 13: local Linux PyInstaller build OK (dist/net-launcher, 304 MB with system Qt; CI uses pip PySide6), --version → 0.1.0. Menu entry ~/.local/share/applications/net-launcher.desktop + ~/.local/bin/net-launcher (runs source tree venv); second start hands off to the running window (exit 0). Workflow YAML parses; real CI run pending GitHub repo (user's «да»).
Task 13: Ruling: ICO is a single 256 px image (Qt ico writer) — Windows scales it — cost: slightly soft 16 px icon.
Task 13: complete (commits 225178c..0ebdb77, tests: bash -c 'cd launcher && .venv/bin/pytest -q' → 140 passed in 9.18s)
Task 14: Ruling: pointblank/*.zip content packs resolved via Modrinth (CONTENT_DIRS) — CP2077 gun pack (33 MB) was inside the mrpack — cost: none. Ruling: manual mod page_url falls back to CurseForge search when the jar's displayURL is missing or points to Modrinth (a manual file is by definition not on Modrinth) — cost: search page instead of exact page (exact page comes with CurseForge support).
Plan: Ruling: user (19.11) asked for skin change + CurseForge → Tasks 15/16 added before E2E (Task 14) — E2E must cover them — cost: none.
Task 15: Ruling: CurseForge key belongs to the author (Settings → Лаунчер), players download CF files from edge.forgecdn URLs embedded in the mrpack (no key) — CF personal keys must not be shipped inside the launcher — cost: players can't search CF themselves without their own key.
Task 15: Ruling: murmur2 verified against independent murmurhash2 package values (seed 1, whitespace stripped) — no official vector — cost: none.
Task 15: Ruling: install() now raises AlreadyInstalled when the ROOT jar's modId is already present (needed for CF, which can't be pre-checked by Modrinth hashes) — cost: none.
Task 15: complete (commits 0ebdb77..da59994, tests: bash -c 'cd launcher && .venv/bin/pytest -q' → 154 passed in 10.14s)
Task 16: Ruling: skin change = local preview on the 3D model (PNG 64×64/64×32, slim toggle) + 'Загрузить на Ely.by' opens ely.by/load + 'Обновить' re-fetches with force — Ely.by has no public upload API for third-party apps — cost: one browser step.
Task 16: complete (commits da59994..139e482, tests: bash -c 'cd launcher && .venv/bin/pytest -q' → 157 passed in 10.31s)
Task 14 (E2E) finding → fixed: server-only Modrinth mods (YUNG's ×6, FarmersStructures, Daily Weather, Lithostitched) were env.client=unsupported and skipped for players, breaking singleplayer worldgen — author.build now maps client unsupported→optional (test_server_only_mods_still_installed_on_client RED→GREEN).
User-reported bug → fixed: "Найти новые" cards stacked at one point — fade_slide_in captured end pos before the layout placed new widgets; now begins after layout activation and re-settles after (test_stagger_keeps_layout_positions RED→GREEN, visual check OK).
User request (19.11) → done: theme choice glass/solid on first run (WelcomePanel, Settings.first_run_done) and in Settings → Лаунчер → Тема; solid turns KDE/Windows blur off (test_first_run_theme_choice, test_settings_theme_switch).
E2E findings fixed: pre-update snapshot went to snapshots/ root not snapshots/<pack> (test_update_snapshot_lands_in_pack_snapshots), author diff counted previous mods overrides as added (test_build_diff_counts_previous_overrides), job emit after app teardown raised (test_job_result_after_signals_deleted_does_not_raise). Friend update 0.1.0→0.1.1 via UI: +9 server-side mods, own mod + world + Chromeware kept, 124 jars.
Task 14: E2E results — Step 3: author build 0.1.0 → 3.1 MB mrpack, 120 Modrinth files (incl. shader + gun pack), 4 MIT jars in overrides, Chromeware manual (CurseForge search link). Step 4: friend (clean NET_LAUNCHER_HOME, shared minecraft/ via symlink — Ruling: MC/NeoForge/Java install already verified in Task 8, saves 1.1 GB) installed via real UI offscreen in 63 s, manual Chromeware accepted, update 0.1.0→0.1.1 kept world/own mod; launched with launcher's own command (mll + authlib-injector, windowed) → STARTING 2.5 s → LOADING 20.8 s → RESOURCES 28.8 s → MENU 44.8 s, then terminated. Step 1/2 (user's own Ely login + Play from the window) need the user's password — left for the user. Step 5 covered by unit/UI tests (toggle, install, rollback). GitHub publish not done (needs repo + «да»).
Final review: self-review (no subagent tool use without the user's request). Findings: Important — settings.json held GitHub/CurseForge tokens world-readable → fixed (test_settings_file_private RED→GREEN). Critical (E2E) — server-only mods skipped for players → fixed. 
Final: minor (deferred): publishing the same version twice → GitHub 422 shown as generic "Сервер ответил ошибкой 422".
Final: minor (deferred): ctx.save() is also called from worker threads (install/import jobs) — rare tmp-file race with a GUI-thread save.
Final: minor (deferred): QInputDialog/QMessageBox/QFileDialog use the native look, not the glass style.
Final: minor (deferred): catalog.PACK_REPO is empty until the GitHub repo exists — players see no catalog until it is set and the launcher rebuilt.
Final: minor (deferred): players can't search CurseForge without their own API key (only the author's builds use it).
Task 14: complete (commits 139e482..b2d6c5f, tests: bash -c 'cd launcher && .venv/bin/pytest -q' → 165 passed in 12.16s)
