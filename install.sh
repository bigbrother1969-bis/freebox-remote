#!/bin/sh
# Installe le lanceur « Télécommande Freebox » (icône de zone de notification).
# Usage : ./install.sh 192.168.1.NN [--autostart]
set -e
cd "$(dirname "$0")"
HERE="$(pwd)"
APPS="$HOME/.local/share/applications"
CONF="${XDG_CONFIG_HOME:-$HOME/.config}"

if [ -n "$1" ] && [ "$1" != "--autostart" ]; then
    mkdir -p "$CONF/freebox-remote"
    echo "$1" > "$CONF/freebox-remote/host"
    echo "IP du Player enregistrée : $1"
fi

mkdir -p "$APPS"
cat > "$APPS/freebox-remote.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Télécommande Freebox
Comment=Piloter le Freebox Player Pop
Exec=/usr/bin/python3 $HERE/tray.py
Icon=$HERE/freebox-remote.svg
Terminal=false
Categories=AudioVideo;Utility;
EOF
chmod +x "$HERE/tray.py"
echo "Lanceur installé dans le menu des applications."

for arg in "$@"; do
    if [ "$arg" = "--autostart" ]; then
        mkdir -p "$CONF/autostart" "$CONF/freebox-remote"
        cat > "$CONF/autostart/freebox-remote.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Télécommande Freebox
Comment=Piloter le Freebox Player Pop
Exec=sh -c "/usr/bin/python3 $HERE/tray.py >> $CONF/freebox-remote/tray.log 2>&1"
Icon=$HERE/freebox-remote.svg
Terminal=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=8
EOF
        echo "Démarrage automatique activé (délai de 8 s, journal : $CONF/freebox-remote/tray.log)."
    fi
done
