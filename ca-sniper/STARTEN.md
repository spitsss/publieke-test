# Stap voor stap aan de praat

Dit is het volledige stappenplan van "niets" naar "hij koopt echt".
Werk het van boven naar beneden af. Sla geen stap over — bij elke stap staat
**wat je moet zien**, zodat je meteen weet of het goed ging.

Reken op ongeveer een uur. Dry run staat de hele tijd aan: er gaat pas geld
weg bij stap 12.

---

## Stap 1 — Terminal openen en de map vinden

Open **Terminal** (cmd-spatie, typ `Terminal`, enter).

Ga naar de map waar deze bot staat. Sleep de map vanuit Finder achter `cd `
in het Terminalvenster, dan vult hij het pad zelf in:

```bash
cd /pad/naar/ca-sniper
```

Controleer of je goed staat:

```bash
ls
```

**Wat je moet zien:** een lijst met `bot.py`, `meldingen.py`, `LEESMIJ.md`
enzovoort.

**Gaat het mis?** Zie je `No such file or directory`, dan klopt het pad niet.
Sleep de map opnieuw vanuit Finder.

---

## Stap 2 — Python controleren en de twee pakketten installeren

```bash
python3 --version
```

**Wat je moet zien:** `Python 3.9` of hoger. De Python die Apple zelf op je Mac
zet (`/usr/bin/python3`, versie 3.9.6) is genoeg — alle 214 tests zijn daarop
gecontroleerd.

**Gaat het mis?** Krijg je een venster over "command line developer tools",
klik op **Installeer** en wacht tot dat klaar is. Probeer het daarna opnieuw.

Dan de twee pakketten die de bot nodig heeft:

```bash
python3 -m pip install -r requirements.txt
```

**Wat je moet zien:** onderaan `Successfully installed telethon-... requests-...`
(of `Requirement already satisfied`, dat is ook goed). Een regel
`Defaulting to user installation` erboven is normaal.

**Staat er `No module named pip`?** Dan mist Apple's Python zijn installeerhulpje.
Haal het één keer op met:

```bash
python3 -m ensurepip --user
```

en doe daarna de regel hierboven opnieuw.

Controleer meteen of alle onderdelen het doen:

```bash
python3 test_alles.py
```

**Wat je moet zien:** onderaan `214 van de 214 tests geslaagd` en `ALLES IN ORDE.`

---

## Stap 3 — Volledige Schijftoegang geven

Dit is de belangrijkste stap van allemaal. Zonder dit ziet de bot **nooit** een
melding, en dat merk je niet: hij lijkt gewoon te draaien.

1. Open **Systeeminstellingen**
2. Ga naar **Privacy en beveiliging**
3. Klik op **Volledige schijftoegang**
4. Zet **Terminal** aan (schuifje naar rechts)
   - Staat Terminal er niet bij? Klik op de **+** en zoek hem op in
     Programma's → Hulpprogramma's
   - Start je de bot vanuit VSCode? Zet **VSCode** er ook bij
5. **Sluit Terminal volledig af met cmd-Q.** Alleen het venster wegklikken is
   niet genoeg — de toestemming gaat pas in bij een verse start
6. Open Terminal opnieuw en ga weer naar de map (`cd /pad/naar/ca-sniper`)

---

## Stap 4 — Controleren of hij je meldingen kan lezen

```bash
python3 meldingen.py --diag
```

**Wat je moet zien:**

- bij punt 1 een pad met `bestaat=JA leesbaar=JA`
- bij punt 2 `gelukt in de stand 'ro'` (of `nolock`)
- bij punt 4 een lijstje apps, met daarin `com.hnc.Discord`
- bij punt 5 je eigen laatste meldingen, met leesbare tekst

Zie je je eigen meldingen staan? **Dan werkt de moeilijkste helft al.**

**Gaat het mis?**

| Wat er staat | Wat je doet |
|---|---|
| `GEEN TOEGANG TOT DE MELDINGEN-DATABASE` | Stap 3 opnieuw, en écht cmd-Q |
| `com.hnc.Discord` staat er niet bij | Stuur jezelf een Discord-bericht vanaf je telefoon zodat er een melding komt, en probeer opnieuw. Blijft hij weg, kijk dan welke naam met `discord` erin er wél staat en gebruik die straks in stap 7 |
| `!!` met een waarschuwing over `immutable` | Meld het; dan ziet hij nieuwe meldingen mogelijk niet |

---

## Stap 5 — Discord goed zetten

Hier gaan de meeste calls verloren.

> **Discord stuurt geen melding voor het kanaal dat je open hebt staan.**
> Ook niet als je op je telefoon in datzelfde kanaal zit.

Dus: **laat het callskanaal niet openstaan.** Zet Discord op een ander kanaal,
of laat het programma op de achtergrond staan.

Verder:

1. Discord → **Instellingen** (tandwiel) → **Meldingen** →
   **Bureaubladmeldingen inschakelen** aan
2. Rechtermuisknop op het callskanaal → **Meldingen** → **Alle berichten**
   (anders krijg je alleen iets bij een `@everyone`)
3. Je status mag **niet op Niet storen** staan — dat onderdrukt alles
4. Discord moet draaien als dezelfde gebruiker op deze Mac

**Controleer het meteen.** Laat dit in Terminal draaien:

```bash
python3 meldingen.py --volg
```

Laat iemand iets in het callskanaal posten, of post zelf iets vanaf je telefoon
in een ánder Discord-kanaal dan je open hebt staan.

**Wat je moet zien:** binnen een paar seconden verschijnt er een regel met
`[nummer] com.hnc.Discord | #kanaalnaam (Server) | de tekst`.

Schrijf op wat er precies tussen de eerste twee streepjes staat — die
kanaalnaam heb je zo nodig.

Stoppen met **ctrl-C**.

---

## Stap 6 — Je Telegram-sleutels ophalen

1. Ga naar <https://my.telegram.org> en log in met je telefoonnummer
   (je krijgt een code in je Telegram-app zelf, niet per sms)
2. Klik op **API development tools**
3. Vul in:
   - *App title*: `sniper`
   - *Short name*: `sniper`
   - de rest mag leeg
4. Klik **Create application**

**Wat je moet zien:** een **App api_id** (een getal) en een **App api_hash**
(een lange reeks letters en cijfers).

Laat dit tabblad openstaan, je hebt het bij de volgende stap nodig.

> Deel deze twee met niemand. Ze horen bij jouw Telegram-account.

---

## Stap 7 — config.ini invullen

Maak je eigen instellingenbestand:

```bash
cp config.ini.voorbeeld config.ini
open -e config.ini
```

Dat laatste opent hem in TextEdit. Vul in:

```ini
[filter]
kanalen =
    microcaps-calls
```

Zet hier de kanaalnaam uit stap 5, **zonder hekje**. Dus zag je
`#microcaps-calls (Alpha Group)`, dan typ je `microcaps-calls`.

```ini
[chains]
basedbot_chain = solana
```

Op welke chain staat BasedBot nu? Kijk in Telegram bij BasedBot onder
`/manage`. Kies uit: `solana`, `base`, `ethereum`, `bsc`, `arbitrum`,
`polygon`, `avalanche`, `robinhood`.

```ini
[telegram]
api_id = 1234567
api_hash = a1b2c3d4e5f6...
basedbot = @BasedBot
```

De twee uit stap 6. Controleer bij `basedbot` de exacte @naam in je
Telegram-chat met de bot.

```ini
[handel]
bedrag = 0.05
valuta = SOL
```

Hoeveel per call. **Een vast bedrag, geen percentage.** Zet het op iets dat je
kunt missen — bij 90% van je saldo gaat alles in de eerste coin die langskomt.

Opslaan met **cmd-S**, venster sluiten.

---

## Stap 8 — Eenmalig inloggen bij Telegram

Praat eerst één keer met de hand met BasedBot in Telegram (stuur `/start`).
Anders kan Telegram hem straks niet opzoeken.

Dan:

```bash
python3 telegram_brug.py --inloggen
```

Hij vraagt om je telefoonnummer (met landnummer, dus `+31...`), daarna om de
code die je in je Telegram-app krijgt. Heb je tweestapsverificatie, dan vraagt
hij ook je wachtwoord.

**Wat je moet zien:**

```
Gelukt. Ingelogd als <jouw naam>.
BasedBot gevonden: BasedBot
```

**Gaat het mis?** Staat er dat BasedBot niet gevonden is, controleer dan de
@naam in `config.ini` en of je echt al een keer met de bot gepraat hebt.

> Er staat nu een bestand `gegevens/sniper.session`. **Kopieer dat nooit** naar
> een andere map of computer. Twee kopieën betekent dat er geen van beide nog
> berichten binnenkrijgt — en dat merk je niet, alles lijkt gewoon te werken.

---

## Stap 9 — Je eigen bedieningsbot maken

Hiermee bestuur je alles vanaf je telefoon, en hij waarschuwt je als er iets
misgaat.

1. Open in Telegram [@BotFather](https://t.me/BotFather)
2. Stuur `/newbot`
3. Geef een naam op, bijvoorbeeld `mijn sniper`
4. Geef een gebruikersnaam op die op `bot` eindigt, bijvoorbeeld
   `mijn_sniper_2024_bot`
5. **Wat je moet zien:** een token in de vorm `1234567890:AAF...`

Zet daarna deze drie in, één voor één (BotFather vraagt telkens welke bot):

```
/setjoingroups   ->  Disable
/setinline       ->  Disable
/setprivacy      ->  Enable
```

Dan je eigen Telegram-id ophalen: open
[@userinfobot](https://t.me/userinfobot) en stuur `/start`.

**Wat je moet zien:** een regel met `Id: 123456789`.

Zet allebei in `config.ini`:

```ini
[bediening]
bot_token = 1234567890:AAF...
toegestane_id = 123456789
```

Opslaan.

---

## Stap 10 — Kijken welke knoppen jouw BasedBot gebruikt

De knoppen om te kopen en te verkopen staan bij BasedBot vlak naast elkaar.
Deze stap laat zien hoe ze bij jou heten, zodat je zeker weet dat de
veiligheidscontrole klopt.

```bash
python3 verkoop.py --toon
```

**Wat je moet zien:** het menu van BasedBot met per knop de tekst en de data,
bijvoorbeeld:

```
  [0,0] 'Your Bags'  data='menu_bags'
  [1,0] 'Buy 0.1'    data='b_0x...'
  [1,1] 'Sell 50%'   data='se_0x...'
```

**Waar je op let:**

- is er een knop met **Bags** in de tekst? (daar zoekt de bot op)
- beginnen de koopknoppen met `b_` of `cb_`? (die weigert de bot altijd)
- beginnen de verkoopknoppen met `se_` of `msi_`? (alleen die mag hij gebruiken)

Klopt dat allemaal: mooi, je hoeft niets te doen.

Ziet het er anders uit: laat het me zien, dan pas ik de lijstjes bovenin
`verkoop.py` aan. **Verander dit niet op de gok** — hier zit het verschil
tussen verkopen en per ongeluk bijkopen.

---

## Stap 11 — De hele keten testen, zonder te kopen

### 11a. Een verzonnen melding door het filter halen

```bash
python3 bot.py --test-melding "#microcaps-calls (Alpha)|| CA: So11111111111111111111111111111111111111112"
```

Vervang `#microcaps-calls (Alpha)` door precies wat je in stap 5 zag staan.

**Wat je moet zien:**

```
kanaalfilter : DOOR — kanaal #microcaps-calls
adressen     : ['So1111...']
Zou versturen: So1111... (solana, via tekst)
```

Staat er `GEWEIGERD`? Dan klopt je kanaalnaam in `config.ini` nog niet.

### 11b. Een echte macOS-melding door de hele keten

Zet het app-filter **tijdelijk** open, want een zelf afgevuurde melding komt
niet van Discord maar van Scripteditor. In `config.ini`:

```ini
[meldingen]
bundle_ids = com.hnc.Discord, com.apple.ScriptEditor2
```

Opslaan. Start de sniper:

```bash
python3 bot.py
```

**Wat je moet zien:** een blokje met `Stand: DRY RUN (er wordt niets gekocht)`
en `Start bij rec_id ...`.

Open nu een **tweede** Terminalvenster (cmd-N), ga naar dezelfde map en vuur
een melding af:

```bash
osascript -e 'display notification "CA: So11111111111111111111111111111111111111112" with title "#microcaps-calls (Test)"'
```

**Wat je moet zien** in het eerste venster, binnen een paar seconden:

```
GEVONDEN in ...ms na bezorging | So1111... | #microcaps-calls (Test)
[DRY RUN] zou 0.05 SOL kopen van So1111... — niets verstuurd (... ms)
```

**Dit is het moment waarop je weet dat de hele keten werkt.**

Stop de sniper met **ctrl-C** en **zet `bundle_ids` terug**:

```ini
bundle_ids = com.hnc.Discord
```

### 11c. Een echte call afwachten

Start de sniper opnieuw (`python3 bot.py`) en laat hem een uur of een dag in
dry run staan terwijl er echte calls voorbijkomen.

**Waar je op let in het logboek:**

- verschijnt er `GEVONDEN` bij een echte call?
- staat er bij een call uit een ánder kanaal niets? (dat hoort zo)
- hoeveel milliseconden staat er? (verwacht een halve tot enkele seconden)

Gaat er een call voorbij die hij **niet** oppikte, kijk dan eerst of je dat
kanaal open had staan. Dat is bijna altijd de reden.

---

## Stap 12 — Pas nu: echt kopen

Alleen doen als stap 11 helemaal goed ging.

Controleer eerst bij BasedBot dat **Quick Buy aan staat** (`/manage`). Staat
hij uit, dan stuurt de sniper keurig het adres door en gebeurt er niets.

Zet dan in `config.ini`:

```ini
[algemeen]
dryrun = nee
```

En start alles op:

```bash
mkdir -p gegevens

nohup python3 bot.py > gegevens/bot.uit 2>&1 &
nohup python3 telegrambediening.py > gegevens/bediening.uit 2>&1 &
nohup python3 waakhond.py > gegevens/waakhond.uit 2>&1 &
python3 dashboard.py
```

Dat laatste drukt een link af met een sleutel erin — open die in je browser.

**Wat je moet zien:** in Telegram een bericht van je eigen bot
(`Bedieningsbot is opgestart.`), en in het dashboard een groene balk
`Live en actief.`

Vanaf nu gaat er bij elke call echt geld weg.

---

## Dagelijks gebruik

**Op je telefoon**, via je eigen bedieningsbot:

| Commando | Doet |
|---|---|
| `/status` | draait alles nog, en hoe snel |
| `/quickbuy` | staat Quick Buy nog aan |
| `/handel` | wat er gekocht is |
| `/pauze` en `/hervat` | tijdelijk stilzetten |
| `/dryrun aan` | meteen stoppen met kopen, zonder iets af te sluiten |

**Het enige wat je echt in de gaten moet houden:**

> Staat er in het dashboard of in `/handel` **"onbevestigd"**, dan is het adres
> wél verstuurd maar weet je niet of er iets gekocht is. Kijk dan meteen of
> Quick Buy nog aan staat — die springt terug na een storting.

**Alles stoppen:**

```bash
pkill -f "python3 bot.py"
pkill -f telegrambediening.py
pkill -f waakhond.py
```

**Automatisch starten bij inloggen:** zie `launchd/LEESMIJ.md`. Let op de
waarschuwing daar over Volledige Schijftoegang — die moet je dan apart aan
Python geven.

---

## Als er iets niet werkt

| Wat je ziet | Wat er aan de hand is |
|---|---|
| Hij pikt geen enkele call op | Had je het kanaal open staan? Dat is bijna altijd de reden |
| `GEEN TOEGANG` bij het starten | Stap 3 opnieuw, en écht cmd-Q |
| `Er draait al een sniper` | Er loopt er nog een. `pkill -f "python3 bot.py"` en opnieuw |
| Steeds `onbevestigd` | Quick Buy staat uit, of BasedBot gebruikt andere teksten — laat het me zien |
| `Nog niet ingelogd bij Telegram` | Stap 8 opnieuw |
| Waakhond meldt `geen hartslag` | De sniper is gestopt. Kijk in `gegevens/bot.uit` waarom |

Kom je er niet uit: kopieer de laatste twintig regels van

```bash
tail -20 gegevens/sniper.log
```

en laat ze zien.
