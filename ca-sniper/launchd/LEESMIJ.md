# Automatisch starten bij inloggen (launchd)

Gebruik een **LaunchAgent**, geen launchd-*daemon*.

Een LaunchAgent draait in jouw ingelogde gebruikerssessie. Dat is precies wat
nodig is: meldingen bestaan alleen binnen een ingelogde sessie. Een daemon
draait buiten je sessie en ziet dus nooit één melding.

## Installeren

```bash
./launchd/installeer.sh
```

Dat script zet de plist-bestanden in `~/Library/LaunchAgents/`, vult het juiste
pad in, en laadt ze.

## Met de hand

```bash
cp launchd/nl.casniper.bot.plist ~/Library/LaunchAgents/
# pas de paden in het bestand aan naar waar deze map staat
launchctl load ~/Library/LaunchAgents/nl.casniper.bot.plist
```

## Stoppen

```bash
launchctl unload ~/Library/LaunchAgents/nl.casniper.bot.plist
```

## Kijken of hij draait

```bash
launchctl list | grep casniper
tail -f gegevens/sniper.log
```

## Let op: Volledige Schijftoegang

Een LaunchAgent start het programma buiten je Terminal om. De schijftoegang die
je aan Terminal gaf geldt dan niet. Je moet daarom **`/usr/bin/python3`** (of
de python die je gebruikt, zie `which python3`) apart toevoegen aan
Volledige Schijftoegang, anders ziet de bot geen enkele melding.

Controleer dat na het installeren met:

```bash
tail -20 gegevens/sniper.log
```

Zie je daar een melding over schijftoegang, dan is dit het probleem.
