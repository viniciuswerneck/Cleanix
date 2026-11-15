#!/usr/bin/env bash
# Instala o Cleanix no menu de aplicativos do usuário (sem root).
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ID="br.cleanix.Cleanix"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

if ! command -v python3 >/dev/null; then
    echo "python3 não encontrado." >&2
    exit 1
fi

if ! python3 -c 'import gi; gi.require_version("Gtk", "4.0")' 2>/dev/null; then
    echo "GTK4 (python3-gi) não encontrado. Instale com:" >&2
    echo "  sudo apt install python3-gi gir1.2-gtk-4.0" >&2
    exit 1
fi

mkdir -p "$ICON_DIR" "$APPS_DIR"

install -m 644 "$PROJECT_DIR/data/$APP_ID.svg" "$ICON_DIR/$APP_ID.svg"

sed "s|@PROJECT_DIR@|$PROJECT_DIR|g" \
    "$PROJECT_DIR/data/$APP_ID.desktop" > "$APPS_DIR/$APP_ID.desktop"
chmod 644 "$APPS_DIR/$APP_ID.desktop"

if command -v desktop-file-validate >/dev/null; then
    desktop-file-validate "$APPS_DIR/$APP_ID.desktop"
fi

command -v update-desktop-database >/dev/null && \
    update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true

echo "Cleanix instalado no menu de aplicativos."
echo "  atalho: $APPS_DIR/$APP_ID.desktop"
echo "  ícone:  $ICON_DIR/$APP_ID.svg"
echo
echo "Procure por \"Cleanix\" no menu do Ubuntu."
