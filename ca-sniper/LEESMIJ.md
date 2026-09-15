# CA-sniper — handleiding

Een bot die meekijkt met de **meldingen van je Discord-app**, daar
contractadressen uit haalt, en die via Telegram doorstuurt naar **BasedBot**,
die met Quick Buy koopt.

De bot logt **nergens in bij Discord**, gebruikt **geen Discord-token** en
praat **niet met Discord's servers**. Hij leest alleen de meldingen die macOS
je toch al laat zien. Er is ook **geen private key** in het spel: de bot stuurt
een tekstbericht, BasedBot doet de aankoop.

---

## Eerst dit: hoe snel is dit echt

Deze route is **niet de snelste**. Een melding komt een halve tot enkele
seconden na het bericht binnen. Je verslaat hiermee de mensen die het kanaal
zitten te verversen. Je verslaat **geen** bot die op Discord's gateway
meeluistert. "Eerste zijn" kan deze bot niet beloven.

Hij meet zijn eigen snelheid en zet die in het logboek en het dashboard, zodat
je ziet of hij trager wordt.

---

## DE MEEST VOORKOMENDE MANIER WAAROP JE EEN CALL MIST

> **Discord stuurt geen melding voor het kanaal dat je open hebt staan.**

Ook niet als je in datzelfde kanaal actief bent op je telefoon. Heb je het
callskanaal op je scherm staan, dan krijgt je Mac geen melding en ziet de bot
niets.

**Zet het callskanaal dus op een ander tabblad, of laat Discord op de
achtergrond staan.**

Verder in Discord:

* Instellingen → Meldingen → **bureaubladmeldingen aan**
* Rechtermuisknop op het kanaal → **Alle berichten** (anders krijg je alleen
  iets bij een `@everyone`)
* Je status mag **niet op Niet storen** staan — dat onderdrukt alles
* De bot moet draaien als **dezelfde gebruiker, in dezelfde sessie** als Discord

---

## Wat je nodig hebt

1. Een Mac waar Discord op draait
2. Python 3.10 of nieuwer (`python3 --version`)
3. Een Telegram-account met `api_id` en `api_hash` van <https://my.telegram.org>
4. BasedBot in je Telegram, met Quick Buy aan
5. Een eigen bot bij [@BotFather](https://t.me/BotFather) om alles te bedienen

---

## Installeren

```bash
cd ca-sniper
python3 -m pip install -r requirements.txt
cp config.ini.voorbeeld config.ini
```

Open `config.ini` en vul in wat er gevraagd wordt. De vijf dingen die je moet
weten staan er met naam en toenaam in:

| Vraag | Waar in config.ini |
|---|---|
| Welke macOS-versie? | nergens — hij zoekt beide paden zelf |
| Staat Volledige Schijftoegang aan? | zie hieronder, dat doe je in Systeeminstellingen |
| Op welke chain staat BasedBot? | `[chains] basedbot_chain` |
| Telegram `api_id` en `api_hash` | `[telegram]` |
| Hoeveel per call? | `[handel] bedrag` — **vast bedrag**, geen percentage |

Waarom een vast bedrag en geen percentage: bij 90% gaat je hele saldo in de
eerste coin die langskomt.

---

## Volledige Schijftoegang — dit moet je zelf doen

De meldingen-database is door macOS beschermd. Zonder toestemming ziet de bot
niets, en dat is de stilste fout die er bestaat: hij lijkt gewoon te draaien.

1. **Systeeminstellingen**
2. **Privacy en beveiliging → Volledige schijftoegang**
3. Zet **Terminal** aan (en **VSCode**, als je de bot daaruit start)
4. Sluit die app **helemaal** af met cmd-Q en open hem opnieuw
   (alleen het venster sluiten is niet genoeg)

Controleer daarna:

```bash
python3 meldingen.py --diag
```

Dit laat zien welk pad gebruikt wordt, of de tabellen kloppen, welke apps
meldingen sturen en hoe je laatste meldingen eruitzien. Zie je daar je eigen
meldingen staan, dan werkt de lezer.

### Waar de database staat

| macOS | Pad |
|---|---|
| Sequoia (15) en nieuwer | `~/Library/Group Containers/group.com.apple.usernoted/db2/db` |
| Sonoma (14) en ouder | `$(getconf DARWIN_USER_DIR)/com.apple.notificationcenter/db2/db` |

De bot zoekt ze allebei en gebruikt wat er is.

### Klopt `com.hnc.Discord` wel?

Dat is de normale bundelnaam van Discord, maar Canary en PTB hebben een andere.
Controleer het met:

```bash
python3 meldingen.py --apps
```

Staat er iets anders, zet dat dan in `config.ini` bij `bundle_ids`.

---

## Telegram klaarzetten

Eenmalig inloggen met je eigen account (je krijgt een code in je Telegram-app):

```bash
python3 telegram_brug.py --inloggen
```

> **Kopieer het sessiebestand nooit** naar een andere map of machine. Twee
> clients met dezelfde sessie krijgen allebei geen updates meer, en dan lijkt
> alles te werken terwijl er niets binnenkomt.

Praat één keer met de hand met BasedBot, anders kan Telegram hem niet opzoeken.

### De bedieningsbot

Maak bij [@BotFather](https://t.me/BotFather) een eigen bot en zet daar ook:

```
/setjoingroups Disable
/setinline     Disable
/setprivacy    Enable
```

Zet het token in `config.ini` bij `[bediening] bot_token`, en je eigen
Telegram-id (op te vragen bij [@userinfobot](https://t.me/userinfobot)) bij
`toegestane_id`. Alles van iemand anders wordt geweigerd.

---

## Testen vóór je iets aanzet

**Dry run staat standaard aan.** Hij schrijft op wat hij zou kopen en koopt
niets.

```bash
python3 test_alles.py                 # alle tests (214 stuks, zonder internet)
python3 meldingen.py --diag           # de macOS-kant
python3 meldingen.py --volg           # laat live zien welke meldingen binnenkomen
python3 bot.py --test-melding "#microcaps-calls (Alpha)|| CA: <een adres>"
```

Een echte melding afvuren om de keten te testen:

```bash
osascript -e 'display notification "CA: So11111111111111111111111111111111111111112" with title "#microcaps-calls (Test)"'
```

Let op: die komt binnen onder de bundel van **Scripteditor**, niet van Discord.
Zet `bundle_ids` tijdelijk op `com.apple.ScriptEditor2` om de keten te testen,
en **zet hem daarna terug**.

---

## Draaien

```bash
# de sniper (dry run zolang dat in config.ini staat)
nohup python3 bot.py > gegevens/bot.uit 2>&1 &

# het dashboard — drukt een link met sleutel af
python3 dashboard.py

# de bedieningsbot op Telegram
nohup python3 telegrambediening.py > gegevens/bediening.uit 2>&1 &

# de waakhond
nohup python3 waakhond.py > gegevens/waakhond.uit 2>&1 &
```

`nohup ... &` is nodig omdat een gewoon achtergrondproces meegaat als je
Terminal opruimt.

Automatisch starten bij inloggen: zie `launchd/` in deze map.

> Gebruik een **LaunchAgent** (in `~/Library/LaunchAgents/`), geen
> launchd-*daemon*. Alleen een agent draait in jouw gebruikerssessie, en dat is
> precies wat nodig is om de meldingen te kunnen zien.

### Echt kopen

Pas als je met eigen ogen hebt gezien dat de keten klopt:

* zet `dryrun = nee` in `config.ini`, óf
* stuur `/dryrun uit` naar je bedieningsbot

---

## De bedieningsbot

| Commando | Doet |
|---|---|
| `/status` | hoe staat alles ervoor |
| `/handel [n]` | de laatste aankopen |
| `/log [n]` | de laatste regels uit het logboek |
| `/quickbuy` | staat Quick Buy nog aan |
| `/pauze` en `/hervat` | de sniper stilzetten en weer aanzetten |
| `/dryrun aan\|uit` | wel of niet echt kopen |
| `/adressen` | wat al eens verstuurd is |
| `/vergeet <adres>` | zodat het opnieuw gekocht mag worden |
| `/verkoop <adres> [initials\|50\|100]` | verkopen via het menu van BasedBot |

Er zitten ook knoppen onder elk bericht.

---

## Wat het dashboard laat zien

`python3 dashboard.py` drukt een link af met een sleutel erin. Het luistert
**alleen op 127.0.0.1** en elke API-aanroep vereist die sleutel.

Het belangrijkste dat je er ziet:

> **"Verstuurd" en "gekocht" zijn niet hetzelfde.**
> Verstuurd = het adres is de deur uit. Gekocht = BasedBot heeft een aankoop
> bevestigd. Staat er "onbevestigd", dan weet je niet of je iets hebt — kijk
> dan meteen of Quick Buy nog aan staat.

---

## De valkuilen die erin verwerkt zijn

**Meldingen**

1. Discord stuurt geen melding voor het kanaal dat je open hebt staan.
2. Bij het opstarten wordt het hoogste `rec_id` onthouden, zodat oude meldingen
   niet alsnog gekocht worden.
3. Meldingen moeten in Discord aan staan, het kanaal op Alle berichten, en je
   status niet op Niet storen.
4. De bot moet in dezelfde ingelogde sessie draaien als Discord.

**Blockscout**

5. Er gaat een gewone browser-User-Agent mee; op een kale kop krijg je 403.
6. Een ADRES-object gebruikt `hash`, een TOKEN-object `address_hash`. Beide
   worden gelezen.
7. `tokens/{adres}/transfers` geeft alleen nieuwste-eerst; er wordt
   doorgebladerd tot voorbij het gevraagde moment.
8. Etherscan kent Robinhood Chain (4663) niet; er wordt Blockscout gebruikt.

**Tekens en bestanden**

9. De uitvoer staat op UTF-8 met `errors="replace"` — emoji in tokennamen
   leggen niets plat.
10. Configuratiebestanden worden met `utf-8-sig` gelezen.
11. Status wegschrijven kan nooit het programma omleggen; er zijn herkansingen.

**Telegram**

12. Er is één Telethon-client en er wordt gepolld, niet geluisterd.
13. De bedieningsbot heeft een eigen token en laat maar één Telegram-id toe.

**BasedBot**

14. Een wachter controleert elke vijf minuten of Quick Buy aan staat — en niet
    vaker, want dan stopt BasedBot met antwoorden.
15. Het antwoord van BasedBot wordt beoordeeld; snapt hij het niet, dan is het
    **onbevestigd** en nooit "gekocht".
16. Er wordt nooit een kaal adres gestuurd om te verkopen — dat zou bijkopen.
17. Alles wat met `b_` of `cb_` begint wordt geweigerd; vóór elke klik wordt
    gecontroleerd of het contractadres in de knopdata staat.
18. De `Initials`-knop van BasedBot wordt gebruikt in plaats van zelf rekenen.
19. "Your Bags" wordt op TEKST gezocht, want de terugpijl heeft dezelfde
    datastructuur.

**Snelheid en bedrijfsvoering**

20. Opzoekwerk gebeurt buiten de hoofdlus, met een harde limiet van 1,5 seconde.
21. De tijd van melding tot verstuurd wordt gemeten en gelogd.
22. Er kan maar één sniper tegelijk draaien (socket op een vaste poort).
23. Achtergrondprocessen starten losgekoppeld; voor automatisch starten is er
    een LaunchAgent.

---

## Waar deze bot met opzet streng is

1. **Dry run staat standaard aan.**
2. **Geen private keys.** De bot stuurt tekst, BasedBot handelt.
3. **Het dashboard luistert alleen op 127.0.0.1** en vraagt een sleutel.
4. **Kanaalfilter verplicht.** Zonder filter start hij niet.
5. **Eén adres per melding.** Staan er twee in, dan doet hij niets.
6. **Chaincontrole voor `0x`-adressen**, standaard op `slim`.
7. **Zelf verkopen staat uit.**
8. **Verstuurde adressen worden onthouden**, zodat hetzelfde token nooit twee
   keer gekocht wordt.

---

## Wat hier NIET getest kon worden

Eerlijk is eerlijk:

* De 214 tests draaien zonder Mac, zonder internet en zonder Telegram. De
  meldingenlezer is getest tegen een **nagemaakte** database met echte binaire
  plists erin. Of Apple de tabellen op jouw macOS-versie precies zo heeft, moet
  `python3 meldingen.py --diag` op je eigen Mac uitwijzen.
* De exacte teksten en knopdata van BasedBot zijn **niet** uit de code te
  raden. De patronen staan daarom apart in `telegram_brug.py` en
  `verkoop.py`, en er wordt op TEKST gekozen en op adres gecontroleerd.
  Controleer ze één keer met `python3 verkoop.py --toon` en stel ze zo nodig
  bij.
* Er is nooit echt een aankoop gedaan met deze code.

---

## Uit welke onderdelen het bestaat

| Bestand | Doet |
|---|---|
| `bot.py` | de sniper: melding → adres → BasedBot |
| `meldingen.py` | leest het macOS Berichtencentrum |
| `extract.py` | haalt contractadressen uit tekst |
| `filters.py` | kanaalfilter |
| `telegram_brug.py` | praat met BasedBot, beoordeelt het antwoord |
| `verkoop.py` | verkopen via BasedBot's knoppenmenu |
| `exits.py` | herkent verkoopsignalen in gewone taal |
| `staat.py` | gedeelde toestand tussen de onderdelen |
| `markt.py` | Dexscreener en Blockscout |
| `telegrambediening.py` | je eigen Telegram-bot met knoppen |
| `waakhond.py` | bewaakt of alles draait |
| `quickbuy_wacht.py` | bewaakt of Quick Buy aan blijft |
| `dashboard.py` + `.html` | webdashboard op 127.0.0.1 |
| `instellingen.py` | leest en controleert config.ini |
| `gereedschap.py` | logboek, UTF-8, één-exemplaar-slot |
| `test_alles.py` | draait elke test |

---

## Tot slot

Het stilste soort fout is hier het gevaarlijkst: **een bot die lijkt te draaien
maar niets koopt.** Daarom zitten de waakhond, de Quick Buy-wachter en het
strikte onderscheid tussen "verstuurd" en "gekocht" erin. Krijg je een
waarschuwing, neem hem serieus.

En: handelen in memecoins op basis van calls uit een Discord-kanaal is een
manier om geld kwijt te raken. Deze bot maakt dat sneller, niet veiliger. Zet
het bedrag per call op iets dat je kunt missen.
