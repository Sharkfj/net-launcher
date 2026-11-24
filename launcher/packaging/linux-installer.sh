#!/bin/sh
set -eu

case "${1:-}" in
    --help|-h)
        printf '%s\n' "Install .NET Launcher for the current user. Run with --uninstall to remove the program and menu entry."
        exit 0
        ;;
    --uninstall|'') ;;
    *) printf '%s\n' "Unknown argument: $1" >&2; exit 2 ;;
esac

data="${XDG_DATA_HOME:-$HOME/.local/share}"
target="$data/net-launcher-app"
menu="$data/applications/net-launcher.desktop"
icon="$data/icons/hicolor/512x512/apps/net-launcher.png"
bin="$HOME/.local/bin/net-launcher"
if [ "${1:-}" = "--uninstall" ]; then
    if [ -L "$bin" ] && [ "$(readlink "$bin")" = "$target/net-launcher" ]; then
        rm -f -- "$bin"
    fi
    rm -rf -- "$target"
    rm -f -- "$menu" "$icon"
    printf '%s\n' "Program removed. Minecraft worlds and launcher settings are kept."
    exit 0
fi

if [ "$(uname -m)" != x86_64 ]; then
    printf '%s\n' "This installer requires x86_64 Linux." >&2
    exit 1
fi
mkdir -p -- "$data" "${menu%/*}" "${icon%/*}" "${bin%/*}"
stage=$(mktemp -d "$data/.net-launcher-install.XXXXXXXX")
trap 'rm -rf -- "$stage"' EXIT
payload=$(awk '/^__NET_PAYLOAD__$/ {print NR+1; exit}' "$0")
tail -n "+$payload" "$0" | tar -xz -C "$stage"
test -x "$stage/net-launcher/net-launcher"
install -m 644 "$stage/net-launcher/launcher-icon.png" "$icon"
if [ -e "$target" ]; then
    mv -- "$target" "$stage/previous"
fi
if ! mv -- "$stage/net-launcher" "$target"; then
    if [ -e "$stage/previous" ]; then mv -- "$stage/previous" "$target"; fi
    exit 1
fi
if [ ! -e "$bin" ] && [ ! -L "$bin" ]; then
    ln -s -- "$target/net-launcher" "$bin"
fi
# Quote the Exec field using the Desktop Entry escaping rules.
exec_path=$(printf '%s' "$target/net-launcher" | sed 's/[\\"$`]/\\&/g; s/%/%%/g; s/\\/\\\\/g')
cat > "$menu" <<DESKTOP
[Desktop Entry]
Type=Application
Name=.NET Launcher
Exec="$exec_path"
Icon=net-launcher
Terminal=false
Categories=Game;
StartupWMClass=net-launcher
DESKTOP
printf 'Installed .NET Launcher. Open it from the application menu or run %s\n' "$target/net-launcher"
exit 0
__NET_PAYLOAD__
