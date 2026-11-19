# .NET Launcher

Лаунчер сборок Minecraft для Windows и Linux. Главная сборка — **.NET**: киберпанк на Create
(NeoForge 1.21.1, больше сотни модов, импланты Chromeware, поезда, дирижабли, шейдер с дождём и туманом).

## Как начать играть

1. Скачай лаунчер со страницы [Releases](../../releases):
   - Windows: `NET-Launcher.exe`. Windows может предупредить про «неизвестного издателя»:
     нажми «Подробнее» → «Выполнить в любом случае».
   - Linux: `NET-Launcher-linux.tar.gz`, распакуй и запусти `net-launcher`.
2. Выбери тему и войди через [Ely.by](https://account.ely.by/register) (аккаунт бесплатный, с ним работают скины).
3. На главной нажми «Установить» у сборки .NET. Лаунчер сам скачает Minecraft, NeoForge, Java и моды.
4. Один мод, Create: Chromeware, автор запретил перезаливать: лаунчер покажет, где его скачать, и попросит
   перетащить файл в окно.
5. «Играть».

Обновления сборки приходят сами: при запуске лаунчер покажет «Вышла версия …» и кнопку «Обновить».
Миры, настройки и свои моды при обновлении не трогаются.

## Для разработки

```bash
cd launcher
python3 -m venv --system-site-packages .venv
.venv/bin/pip install minecraft-launcher-lib==8.0 pytest
.venv/bin/pytest -q
.venv/bin/python -m netlauncher
```

Разработчики: @looper_fj и Claude Code.
Шрифты Unbounded и Onest — SIL Open Font License (`launcher/netlauncher/ui/assets/fonts`).
