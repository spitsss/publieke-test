#!/bin/bash
# Zet de LaunchAgents klaar zodat alles bij het inloggen vanzelf start.
# Draai dit vanuit de map ca-sniper:   ./launchd/installeer.sh
set -e

MAP="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$(which python3)"
DOEL="$HOME/Library/LaunchAgents"

if [ "$(uname)" != "Darwin" ]; then
  echo "Dit werkt alleen op macOS."
  exit 1
fi

if [ ! -f "$MAP/config.ini" ]; then
  echo "Er is nog geen config.ini. Doe eerst:"
  echo "    cp $MAP/config.ini.voorbeeld $MAP/config.ini"
  exit 1
fi

mkdir -p "$DOEL" "$MAP/gegevens"

echo "Map    : $MAP"
echo "Python : $PYTHON"
echo

for plist in "$MAP"/launchd/nl.casniper.*.plist; do
  naam="$(basename "$plist")"
  sed -e "s|__MAP__|$MAP|g" -e "s|__PYTHON__|$PYTHON|g" "$plist" > "$DOEL/$naam"
  launchctl unload "$DOEL/$naam" 2>/dev/null || true
  launchctl load "$DOEL/$naam"
  echo "geladen: $naam"
done

echo
echo "Klaar. Controleer met:"
echo "    launchctl list | grep casniper"
echo "    tail -f $MAP/gegevens/sniper.log"
echo
echo "LET OP: geef ook $PYTHON Volledige Schijftoegang."
echo "De toestemming die je aan Terminal gaf geldt hier niet — een LaunchAgent"
echo "start buiten je Terminal om. Zonder dit ziet de bot geen enkele melding."
