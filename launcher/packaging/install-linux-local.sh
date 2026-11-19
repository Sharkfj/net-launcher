#!/usr/bin/env bash
# Puts the launcher (run from this source tree) into the KDE/GNOME application menu.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/scalable/apps"
mkdir -p "$BIN" "$APPS" "$ICONS"
cat > "$BIN/net-launcher" <<SH
#!/usr/bin/env bash
export PYTHONPATH="$ROOT\${PYTHONPATH:+:\$PYTHONPATH}"
exec "$ROOT/.venv/bin/python" -m netlauncher "\$@"
SH
chmod +x "$BIN/net-launcher"
cp "$ROOT/packaging/icon.svg" "$ICONS/net-launcher.svg"
cat > "$APPS/net-launcher.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=.NET Launcher
Comment=Лаунчер сборок Minecraft
Exec=$BIN/net-launcher
Icon=net-launcher
Terminal=false
Categories=Game;
StartupWMClass=net-launcher
DESKTOP
update-desktop-database "$APPS" >/dev/null 2>&1 || true
echo "Установлено: $APPS/net-launcher.desktop"
