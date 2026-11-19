# .NET Launcher

[English](#english) · [Русский](#русский)

## English

A Minecraft modpack launcher for Windows and Linux. The main pack is **.NET**: cyberpunk built on Create
(NeoForge 1.21.1, over a hundred mods, Chromeware implants, trains, airships, a shader with rain and fog).

The launcher interface is in Russian for now; the button names below are translated.

### Getting started

1. Download the launcher from [Releases](../../releases):
   - Windows: `NET-Launcher.exe`. Windows may warn about an "unknown publisher":
     click "More info", then "Run anyway".
   - Linux: `NET-Launcher-linux.tar.gz`, unpack it and run `net-launcher`.
2. Pick a theme and sign in with [Ely.by](https://account.ely.by/register). The account is free and gives you skins.
3. On the home screen, click "Install" next to the .NET pack. The launcher downloads Minecraft, NeoForge,
   Java and every mod by itself.
4. The author of one mod, Create: Chromeware, does not allow re-uploads. The launcher shows where to download it
   and asks you to drop the file into the window.
5. Click "Play".

Pack updates arrive on their own: on start the launcher shows "Version … is out" with an "Update" button.
Updates never touch your worlds, settings or the mods you added yourself.

### Development

```bash
cd launcher
python3 -m venv --system-site-packages .venv
.venv/bin/pip install minecraft-launcher-lib==8.0 pytest
.venv/bin/pytest -q
.venv/bin/python -m netlauncher
```

Developers: @looper_fj and Claude Code.
Fonts Unbounded and Onest are under the SIL Open Font License (`launcher/netlauncher/ui/assets/fonts`).

## Русский

Лаунчер сборок Minecraft для Windows и Linux. Главная сборка — **.NET**: киберпанк на Create
(NeoForge 1.21.1, больше сотни модов, импланты Chromeware, поезда, дирижабли, шейдер с дождём и туманом).

### Как начать играть

1. Скачай лаунчер со страницы [Releases](../../releases):
   - Windows: `NET-Launcher.exe`. Windows может предупредить про «неизвестного издателя»:
     нажми «Подробнее», затем «Выполнить в любом случае».
   - Linux: `NET-Launcher-linux.tar.gz`, распакуй и запусти `net-launcher`.
2. Выбери тему и войди через [Ely.by](https://account.ely.by/register). Аккаунт бесплатный, с ним работают скины.
3. На главной нажми «Установить» у сборки .NET. Лаунчер сам скачает Minecraft, NeoForge, Java и все моды.
4. Автор одного мода, Create: Chromeware, запретил его перезаливать. Лаунчер покажет, где его скачать,
   и попросит перетащить файл в окно.
5. «Играть».

Обновления сборки приходят сами: при запуске лаунчер покажет «Вышла версия …» и кнопку «Обновить».
Миры, настройки и свои моды при обновлении не трогаются.

### Для разработки

```bash
cd launcher
python3 -m venv --system-site-packages .venv
.venv/bin/pip install minecraft-launcher-lib==8.0 pytest
.venv/bin/pytest -q
.venv/bin/python -m netlauncher
```

Разработчики: @looper_fj и Claude Code.
Шрифты Unbounded и Onest распространяются по лицензии SIL Open Font License (`launcher/netlauncher/ui/assets/fonts`).
