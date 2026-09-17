"""
meldingen.py — leest de meldingen van het macOS Berichtencentrum.

Wat hier gebeurt: macOS bewaart elke melding die je krijgt in een
SQLite-database. Wij kijken daarin mee. We loggen NERGENS in bij Discord, we
gebruiken geen Discord-token en we praten niet met Discord's servers. We lezen
alleen wat je Mac je toch al laat zien.

DE PADEN (macOS heeft ze verplaatst in Sequoia)

    Sequoia (15) en nieuwer:
        ~/Library/Group Containers/group.com.apple.usernoted/db2/db
    Sonoma (14) en ouder:
        $(getconf DARWIN_USER_DIR)/com.apple.notificationcenter/db2/db

We proberen ze allebei en gebruiken wat er is.

VOLLEDIGE SCHIJFTOEGANG IS VERPLICHT

Zonder Volledige Schijftoegang krijg je een foutmelding of een lege lijst.
Dat moet je zelf doen; een programma mag zichzelf die toegang niet geven:

    Systeeminstellingen -> Privacy en beveiliging -> Volledige schijftoegang
    -> zet Terminal aan (en VSCode, als je de bot daaruit start)
    -> daarna de app helemaal afsluiten (cmd-Q) en opnieuw openen

DE DATABASE ALLEEN LEZEN

Het Berichtencentrum schrijft zelf in deze database. Wij openen hem read-only,
zodat we hem nooit op slot zetten of beschadigen.

EEN VALKUIL DIE DE OPDRACHT NIET NOEMT

De opdracht schrijft 'mode=ro&immutable=1' voor. 'immutable' betekent tegen
SQLite: "dit bestand verandert nooit". Dat is precies NIET waar — het
Berichtencentrum schrijft er continu in. Staat de database in WAL-stand, dan
negeert SQLite met immutable=1 het bijbehorende -wal bestand en zie je nieuwe
meldingen NOOIT. De bot lijkt dan te draaien maar ziet niets. Dat is precies de
stille fout waar we bang voor moeten zijn.

Daarom: we proberen eerst gewoon 'mode=ro' (die leest WAL wél goed), dan
'nolock=1', en pas als laatste redmiddel 'immutable=1'. Belandt hij op
immutable terwijl er een -wal bestand naast ligt, dan waarschuwen we hard.
En we openen elke keer een VERSE verbinding, want een openstaande verbinding
kan oude bladzijden in het geheugen houden.
"""

from __future__ import annotations

import argparse
import os
import plistlib
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from gereedschap import kort, zet_uitvoer_op_utf8

# Apple telt seconden vanaf 1 januari 2001, Unix vanaf 1970. Dit is het verschil.
APPLE_EPOCH_VERSCHIL = 978307200

# De bundelnaam van de Discord-desktopapp. Kan per installatie verschillen
# (bijvoorbeeld bij Discord Canary of PTB), dus laat 'python3 meldingen.py
# --apps' het je bevestigen.
DISCORD_BUNDLE = "com.hnc.Discord"

UITLEG_SCHIJFTOEGANG = """
GEEN TOEGANG TOT DE MELDINGEN-DATABASE
--------------------------------------
macOS beschermt dit bestand. Je moet zelf toestemming geven:

  1. Open Systeeminstellingen
  2. Ga naar Privacy en beveiliging -> Volledige schijftoegang
  3. Zet Terminal AAN (en VSCode, als je de bot daaruit start)
  4. Sluit die app daarna VOLLEDIG af met cmd-Q en open hem opnieuw
     (alleen het venster sluiten is niet genoeg)
  5. Start dit programma opnieuw

Zonder deze stap ziet de bot nooit één melding.
""".strip()


class MeldingFout(Exception):
    """Er is iets mis met de database of de toegang ertoe."""


@dataclass
class Melding:
    """Eén melding, uitgepakt."""

    rec_id: int
    bundle: str
    titel: str = ""
    ondertitel: str = ""
    body: str = ""
    bezorgd_op: float = 0.0          # Unix-tijd
    gezien_op: float = field(default_factory=time.time)  # wanneer wij hem oppikten

    @property
    def tekst(self) -> str:
        """Alles bij elkaar — hier zoeken we het contractadres in."""
        return "\n".join(deel for deel in (self.titel, self.ondertitel, self.body) if deel)

    def __str__(self) -> str:
        return f"[{self.rec_id}] {self.bundle} | {kort(self.titel, 60)} | {kort(self.body, 120)}"


# ---------------------------------------------------------------- paden

def darwin_gebruikersmap() -> Path | None:
    """Zoekt $(getconf DARWIN_USER_DIR) op — het pad voor Sonoma en ouder."""
    try:
        uitvoer = subprocess.run(
            ["getconf", "DARWIN_USER_DIR"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        pad = uitvoer.stdout.strip()
        if pad:
            return Path(pad)
    except Exception:
        pass

    # Vangnet: TMPDIR is /var/folders/ab/cdef/T/, de map die we willen is .../0/
    tmp = os.environ.get("TMPDIR", "")
    if "/var/folders/" in tmp:
        return Path(tmp).parent / "0"
    return None


def mogelijke_paden() -> list[Path]:
    """Alle plekken waar de database kan staan, nieuwste macOS eerst."""
    paden: list[Path] = []

    # Sequoia (15) en nieuwer
    paden.append(
        Path.home() / "Library" / "Group Containers" / "group.com.apple.usernoted" / "db2" / "db"
    )

    # Sonoma (14) en ouder
    basis = darwin_gebruikersmap()
    if basis:
        paden.append(basis / "com.apple.notificationcenter" / "db2" / "db")

    return paden


def vind_database(opgegeven: str = "auto") -> Path:
    """
    Zoekt de database. Faalt HARD met uitleg als hij niet te vinden of niet te
    lezen is — stil doorgaan met een lege lijst is hier het gevaarlijkst.
    """
    if opgegeven and opgegeven != "auto":
        pad = Path(opgegeven).expanduser()
        if not pad.exists():
            raise MeldingFout(f"Het opgegeven pad bestaat niet: {pad}")
        return pad

    if sys.platform != "darwin":
        raise MeldingFout(
            "Automatisch zoeken werkt alleen op macOS. Dit draait op "
            f"'{sys.platform}'. Geef anders zelf een pad op met db_pad in config.ini."
        )

    gevonden = [pad for pad in mogelijke_paden() if pad.exists()]
    if not gevonden:
        regels = "\n".join(f"    {pad}" for pad in mogelijke_paden())
        raise MeldingFout(
            "Ik kan de meldingen-database nergens vinden. Gezocht op:\n"
            f"{regels}\n\n"
            "Als je zeker weet dat hij ergens anders staat, zet dat pad dan in "
            "config.ini onder [meldingen] db_pad."
        )

    for pad in gevonden:
        if os.access(pad, os.R_OK):
            return pad

    raise MeldingFout(f"{gevonden[0]} bestaat wel, maar ik mag hem niet lezen.\n\n{UITLEG_SCHIJFTOEGANG}")


# ---------------------------------------------------------------- lezer

class Meldingenlezer:
    """Leest nieuwe meldingen uit het Berichtencentrum."""

    LEESMODI = {
        "ro": "mode=ro",
        "nolock": "mode=ro&nolock=1",
        "immutable": "mode=ro&immutable=1",
    }

    def __init__(
        self,
        db_pad: str | Path = "auto",
        bundle_ids: list[str] | None = None,
        leesmodus: str = "auto",
    ) -> None:
        self.pad = vind_database(str(db_pad))
        # Onderscheid met opzet: None = "niet opgegeven, neem Discord",
        # [] = "bewust geen filter, laat ALLE apps door". Zou een lege lijst
        # stilletjes Discord worden, dan kun je de keten niet testen met een
        # zelf afgevuurde melding (die komt van Scripteditor).
        if bundle_ids is None:
            bundle_ids = [DISCORD_BUNDLE]
        self.bundle_ids = [b.strip() for b in bundle_ids if b and b.strip()]
        # LET OP: we vergelijken ZONDER op hoofdletters te letten.
        # Op de ene Mac staat Discord in de database als 'com.hnc.Discord',
        # op de andere als 'com.hnc.discord'. Vergelijk je letter voor letter,
        # dan ziet de bot NUL meldingen terwijl al het andere perfect werkt —
        # en dat merk je niet. Dit is echt op een Mac gebeurd.
        self._bundels_laag = {b.lower() for b in self.bundle_ids}
        self.gevraagde_modus = (leesmodus or "auto").lower()
        self.modus = ""            # welke modus uiteindelijk werkt
        self.waarschuwingen: list[str] = []
        self._kolommen: dict[str, list[str]] = {}
        self._app_kolom = ""
        self._bepaal_modus()
        self._controleer_schema()

    # ---- verbinding ----

    def _probeer(self, modus: str) -> sqlite3.Connection:
        opties = self.LEESMODI[modus]
        return sqlite3.connect(f"file:{self.pad}?{opties}", uri=True, timeout=2.0)

    def _bepaal_modus(self) -> None:
        """Kiest de eerste leesmodus die werkt, en waarschuwt bij de riskante."""
        if not os.access(self.pad, os.R_OK):
            raise MeldingFout(f"Geen leesrechten op {self.pad}.\n\n{UITLEG_SCHIJFTOEGANG}")

        volgorde = (
            ["ro", "nolock", "immutable"]
            if self.gevraagde_modus == "auto"
            else [self.gevraagde_modus]
        )
        laatste_fout: Exception | None = None

        for modus in volgorde:
            if modus not in self.LEESMODI:
                raise MeldingFout(
                    f"Onbekende leesmodus '{modus}'. Kies uit: auto, ro, nolock, immutable."
                )
            try:
                verbinding = self._probeer(modus)
                verbinding.execute("select count(*) from record").fetchone()
                verbinding.close()
                self.modus = modus
                break
            except PermissionError as fout:
                raise MeldingFout(f"{fout}\n\n{UITLEG_SCHIJFTOEGANG}") from fout
            except sqlite3.Error as fout:
                laatste_fout = fout
                continue
        else:
            boodschap = f"Kan {self.pad} niet lezen: {laatste_fout}"
            if isinstance(laatste_fout, sqlite3.OperationalError) and "authoriz" in str(
                laatste_fout
            ).lower():
                boodschap += f"\n\n{UITLEG_SCHIJFTOEGANG}"
            raise MeldingFout(boodschap)

        if self.modus == "immutable" and Path(str(self.pad) + "-wal").exists():
            self.waarschuwingen.append(
                "LET OP: de database wordt gelezen met immutable=1 terwijl er een "
                "-wal bestand naast ligt. In die combinatie ziet SQLite nieuwe "
                "meldingen mogelijk NOOIT. De bot lijkt dan te draaien maar pikt "
                "niets op. Test met --volg of hij echt meldingen ziet."
            )

    def verbinding(self) -> sqlite3.Connection:
        """
        Opent elke keer een VERSE verbinding.

        Waarom niet één verbinding openhouden: bij nolock en immutable kan
        SQLite oude bladzijden in het geheugen houden en zie je nieuwe rijen
        niet. Een database openen kost een fractie van een milliseconde; we
        doen dit hooguit tien keer per seconde. Zekerheid is hier meer waard.
        """
        return sqlite3.connect(f"file:{self.pad}?{self.LEESMODI[self.modus]}", uri=True, timeout=2.0)

    # ---- schema ----

    def _kolommen_van(self, verbinding: sqlite3.Connection, tabel: str) -> list[str]:
        try:
            rijen = verbinding.execute(f"pragma table_info({tabel})").fetchall()
        except sqlite3.Error:
            return []
        return [rij[1] for rij in rijen]

    def _controleer_schema(self) -> None:
        """
        Kijkt of de tabellen en kolommen echt zijn zoals we denken. Klopt er
        iets niet, dan stoppen we meteen — beter dan stilletjes lege gegevens
        doorgeven.
        """
        with self.verbinding() as verbinding:
            record = self._kolommen_van(verbinding, "record")
            app = self._kolommen_van(verbinding, "app")

        if not record:
            raise MeldingFout(
                f"In {self.pad} zit geen tabel 'record'. Dit is waarschijnlijk niet "
                "de database van het Berichtencentrum."
            )

        ontbreekt = [k for k in ("rec_id", "data") if k not in record]
        if ontbreekt:
            raise MeldingFout(
                f"De tabel 'record' mist de kolom(men) {', '.join(ontbreekt)}. "
                f"Gevonden kolommen: {', '.join(record)}.\n"
                "Apple heeft de database blijkbaar veranderd; deze bot moet worden aangepast."
            )

        self._kolommen = {"record": record, "app": app}

        # In 'app' heet de bundelnaam meestal 'identifier'. We controleren het
        # in plaats van het aan te nemen.
        for mogelijk in ("identifier", "bundleid", "bundle_id", "app_identifier"):
            if mogelijk in app:
                self._app_kolom = mogelijk
                break

        if app and not self._app_kolom:
            self.waarschuwingen.append(
                "De tabel 'app' heeft geen herkenbare kolom met de bundelnaam "
                f"(gevonden: {', '.join(app)}). Ik kan dan niet op app filteren."
            )

    @property
    def kan_op_app_filteren(self) -> bool:
        return bool(self._app_kolom) and "app_id" in self._kolommen.get("record", [])

    # ---- lezen ----

    def _selectie(self) -> str:
        record = self._kolommen["record"]
        bezorgd = "r.delivered_date" if "delivered_date" in record else "NULL"
        if self.kan_op_app_filteren:
            return (
                f"select r.rec_id, r.data, {bezorgd}, coalesce(a.{self._app_kolom}, '') "
                "from record r left join app a on a.app_id = r.app_id"
            )
        return f"select r.rec_id, r.data, {bezorgd}, '' from record r"

    def hoogste_rec_id(self) -> int:
        """
        Het hoogste nummer dat nu in de database staat.

        Hier begin je bij het opstarten. Zonder dit verwerkt de bot bij ELKE
        herstart alle oude meldingen die nog in het centrum staan — en koopt
        dus alles opnieuw. Dat ging op de Windows-versie bijna mis.
        """
        try:
            with self.verbinding() as verbinding:
                rij = verbinding.execute("select max(rec_id) from record").fetchone()
            return int(rij[0]) if rij and rij[0] is not None else 0
        except sqlite3.Error as fout:
            raise MeldingFout(f"Kan het hoogste rec_id niet ophalen: {fout}") from fout

    def controleer_terugval(self, laatste_rec_id: int) -> int | None:
        """
        Kijkt of het Berichtencentrum is opgeschoond en de nummering daardoor
        is terugverdwenen.

        Waarom dit bestaat: wist de gebruiker zijn meldingen (de knop 'Wis' in
        het Berichtencentrum), dan gooit macOS oude rijen weg en begint hij
        opnieuw te tellen. Het hoogste rec_id wordt dan LAGER dan wat de bot
        onthouden had. Nieuwe meldingen komen daarna binnen met een nummer
        onder ons startpunt — en die zou de bot allemaal negeren, zonder ook
        maar één foutmelding. Hij draait, ziet niets, en je merkt het niet.

        Geeft het nieuwe (lagere) startpunt terug, of None als er niets aan de
        hand is.
        """
        hoogste = self.hoogste_rec_id()
        if hoogste < laatste_rec_id:
            return hoogste
        return None

    def meldingen_na_tijd(self, na_tijd: float, limiet: int = 100) -> list[Melding]:
        """
        Haalt meldingen op die NA een bepaald tijdstip bezorgd zijn, ongeacht
        hun nummer. Oudste eerst.

        Dit is het vangnet voor als de nummering is terugverdwenen doordat de
        gebruiker zijn meldingen wiste. Het nummer is dan niet te vertrouwen,
        de bezorgtijd wel. We vragen de NIEUWSTE rijen op (order by desc), want
        precies daar zitten de meldingen die we gemist kunnen hebben.
        """
        vraag = f"{self._selectie()} order by r.rec_id desc limit ?"
        try:
            with self.verbinding() as verbinding:
                rijen = verbinding.execute(vraag, (limiet,)).fetchall()
        except sqlite3.Error as fout:
            raise MeldingFout(str(fout)) from fout

        uitkomst: list[Melding] = []
        for rec_id, blob, bezorgd, bundle in rijen:
            bundle = bundle or ""
            if self.bundle_ids and bundle and bundle.lower() not in self._bundels_laag:
                continue
            if self.bundle_ids and not bundle and self.kan_op_app_filteren:
                continue
            melding = self._pak_uit(rec_id, blob, bezorgd, bundle)
            if melding is None:
                continue
            # Zonder bezorgtijd kunnen we niet beoordelen of hij nieuw is.
            # Dan laten we hem liggen: liever een call missen dan een oude
            # melding opnieuw kopen.
            if not melding.bezorgd_op or melding.bezorgd_op <= na_tijd:
                continue
            uitkomst.append(melding)

        uitkomst.sort(key=lambda m: m.rec_id)
        return uitkomst

    def nieuwe_meldingen(self, na_rec_id: int, limiet: int = 50) -> list[Melding]:
        """
        Haalt alle meldingen op met een rec_id hoger dan wat je al gezien hebt,
        oudste eerst. Alleen van de apps in bundle_ids.
        """
        vraag = f"{self._selectie()} where r.rec_id > ? order by r.rec_id asc limit ?"
        try:
            with self.verbinding() as verbinding:
                rijen = verbinding.execute(vraag, (na_rec_id, limiet)).fetchall()
        except sqlite3.Error as fout:
            # Database even op slot of midden in een schrijfactie: dit mag de
            # bot niet omleggen. Volgende ronde weer proberen.
            raise MeldingFout(str(fout)) from fout

        uitkomst: list[Melding] = []
        for rec_id, blob, bezorgd, bundle in rijen:
            bundle = bundle or ""
            if self.bundle_ids and bundle and bundle.lower() not in self._bundels_laag:
                continue
            if self.bundle_ids and not bundle and self.kan_op_app_filteren:
                continue
            melding = self._pak_uit(rec_id, blob, bezorgd, bundle)
            if melding:
                uitkomst.append(melding)
        return uitkomst

    def _pak_uit(self, rec_id: int, blob, bezorgd, bundle: str) -> Melding | None:
        """Haalt titel, ondertitel en tekst uit de binaire plist in 'data'."""
        titel = ondertitel = body = ""
        if blob:
            try:
                inhoud = plistlib.loads(bytes(blob))
            except Exception:
                inhoud = None
            if isinstance(inhoud, dict):
                verzoek = inhoud.get("req")
                if isinstance(verzoek, dict):
                    titel = str(verzoek.get("titl") or "")
                    ondertitel = str(verzoek.get("subt") or "")
                    body = str(verzoek.get("body") or "")
                else:
                    # Enkele meldingen hebben geen 'req'-blok; dan proberen we
                    # de velden op het hoogste niveau.
                    titel = str(inhoud.get("titl") or "")
                    ondertitel = str(inhoud.get("subt") or "")
                    body = str(inhoud.get("body") or "")

        bezorgd_unix = 0.0
        if bezorgd:
            try:
                bezorgd_unix = float(bezorgd) + APPLE_EPOCH_VERSCHIL
            except (TypeError, ValueError):
                bezorgd_unix = 0.0

        return Melding(
            rec_id=int(rec_id),
            bundle=bundle,
            titel=titel,
            ondertitel=ondertitel,
            body=body,
            bezorgd_op=bezorgd_unix,
        )

    def apps_met_aantallen(self, laatste: int = 500) -> list[tuple[str, int]]:
        """Welke apps hebben recent meldingen gestuurd? Voor de diagnose."""
        if not self.kan_op_app_filteren:
            return []
        vraag = (
            f"select coalesce(a.{self._app_kolom}, '(onbekend)'), count(*) "
            "from record r left join app a on a.app_id = r.app_id "
            "where r.rec_id > (select max(rec_id) - ? from record) "
            f"group by 1 order by 2 desc"
        )
        try:
            with self.verbinding() as verbinding:
                return [(rij[0], rij[1]) for rij in verbinding.execute(vraag, (laatste,))]
        except sqlite3.Error:
            return []

    def laatste_meldingen(self, aantal: int = 5, alle_apps: bool = True) -> list[Melding]:
        """De laatste meldingen, om te controleren of het uitpakken werkt."""
        vraag = f"{self._selectie()} order by r.rec_id desc limit ?"
        oude_filter = self.bundle_ids
        if alle_apps:
            self.bundle_ids = []
        try:
            with self.verbinding() as verbinding:
                rijen = verbinding.execute(vraag, (aantal,)).fetchall()
            return [
                melding
                for melding in (
                    self._pak_uit(rij[0], rij[1], rij[2], rij[3] or "") for rij in rijen
                )
                if melding
            ]
        except sqlite3.Error:
            return []
        finally:
            self.bundle_ids = oude_filter


# ---------------------------------------------------------------- diagnose

def diagnose(db_pad: str = "auto", bundle_ids: list[str] | None = None) -> int:
    """Controleert stap voor stap of alles klopt. Geeft 0 terug als het goed is."""
    zet_uitvoer_op_utf8()
    print("DIAGNOSE MELDINGEN")
    print("=" * 60)
    print(f"Besturingssysteem : {sys.platform}")
    if sys.platform == "darwin":
        try:
            versie = subprocess.run(
                ["sw_vers", "-productVersion"], capture_output=True, text=True, timeout=5
            ).stdout.strip()
            print(f"macOS-versie      : {versie}")
        except Exception:
            pass

    print("\n1. Waar staat de database?")
    for pad in mogelijke_paden():
        bestaat = "JA " if pad.exists() else "nee"
        leesbaar = "JA " if pad.exists() and os.access(pad, os.R_OK) else "nee"
        print(f"   bestaat={bestaat} leesbaar={leesbaar}  {pad}")

    try:
        pad = vind_database(db_pad)
    except MeldingFout as fout:
        print(f"\nGESTOPT: {fout}")
        return 1
    print(f"   -> gekozen: {pad}")

    print("\n2. Kan ik hem openen?")
    try:
        lezer = Meldingenlezer(pad, bundle_ids or [DISCORD_BUNDLE], "auto")
    except MeldingFout as fout:
        print(f"\nGESTOPT: {fout}")
        return 1
    print(f"   gelukt in de stand '{lezer.modus}'")

    try:
        with lezer.verbinding() as verbinding:
            stand = verbinding.execute("pragma journal_mode").fetchone()
            print(f"   journal_mode = {stand[0] if stand else '?'}")
    except Exception:
        pass
    print(f"   los -wal bestand aanwezig: {'ja' if Path(str(pad) + '-wal').exists() else 'nee'}")

    for waarschuwing in lezer.waarschuwingen:
        print(f"\n   !! {waarschuwing}")

    print("\n3. Kloppen de tabellen?")
    print(f"   record: {', '.join(lezer._kolommen.get('record', [])) or '(leeg)'}")
    print(f"   app   : {', '.join(lezer._kolommen.get('app', [])) or '(geen app-tabel)'}")
    print(f"   filteren op app mogelijk: {'ja' if lezer.kan_op_app_filteren else 'NEE'}")

    print("\n4. Welke apps sturen meldingen? (laatste 500)")
    apps = lezer.apps_met_aantallen()
    if not apps:
        print("   (kon ik niet bepalen)")
    for naam, aantal in apps[:15]:
        merk = "  <-- dit is Discord" if naam.lower() == DISCORD_BUNDLE.lower() else ""
        print(f"   {aantal:5d}  {naam}{merk}")
    if apps and not any(naam.lower() == DISCORD_BUNDLE.lower() for naam, _ in apps):
        print(
            f"\n   !! {DISCORD_BUNDLE} staat er niet bij. Óf Discord heeft recent geen\n"
            "      melding gestuurd, óf jouw installatie heeft een andere bundelnaam\n"
            "      (Canary/PTB). Zet de juiste naam in config.ini bij bundle_ids."
        )

    print("\n5. Laatste meldingen, uitgepakt:")
    for melding in lezer.laatste_meldingen(5):
        tijd = (
            time.strftime("%H:%M:%S", time.localtime(melding.bezorgd_op))
            if melding.bezorgd_op
            else "??:??:??"
        )
        print(f"   {tijd} [{melding.rec_id}] {melding.bundle}")
        print(f"       titel      : {kort(melding.titel, 80)}")
        print(f"       ondertitel : {kort(melding.ondertitel, 80)}")
        print(f"       tekst      : {kort(melding.body, 120)}")

    print(f"\n6. Hoogste rec_id nu: {lezer.hoogste_rec_id()}")
    print("\nKlaar. Zie je hierboven je eigen meldingen staan, dan werkt de lezer.")
    print("Test de keten met:")
    print("   osascript -e 'display notification \"CA: So11111111111111111111111111111111111111112\" with title \"#microcaps-calls (Test)\"'")
    print("Let op: die melding komt binnen onder de bundel van Scripteditor, niet")
    print("van Discord. Zet bundle_ids tijdelijk ruimer om de keten te testen.")
    return 0


def _volg(db_pad: str, bundle_ids: list[str], poll_ms: int) -> int:
    """Laat live zien welke meldingen binnenkomen. Stoppen met ctrl-C."""
    zet_uitvoer_op_utf8()
    lezer = Meldingenlezer(db_pad, bundle_ids, "auto")
    for waarschuwing in lezer.waarschuwingen:
        print(f"!! {waarschuwing}")
    laatste = lezer.hoogste_rec_id()
    print(f"Meekijken vanaf rec_id {laatste} (stand: {lezer.modus}). Ctrl-C om te stoppen.")
    print("Vuur een testmelding af met:")
    print("   osascript -e 'display notification \"hallo\" with title \"test\"'")
    laatste_controle = 0.0
    laatste_tijd = time.time()
    try:
        while True:
            try:
                gevonden = lezer.nieuwe_meldingen(laatste)
                for melding in gevonden:
                    laatste = max(laatste, melding.rec_id)
                    laatste_tijd = max(laatste_tijd, melding.bezorgd_op or 0.0)
                    print(melding)
                # Niets nieuws? Kijk dan af en toe of het Berichtencentrum
                # is opgeschoond en de nummering is terugverdwenen.
                if not gevonden and time.time() - laatste_controle > 5:
                    laatste_controle = time.time()
                    terug = lezer.controleer_terugval(laatste)
                    if terug is not None:
                        print(
                            f"(meldingen zijn gewist: nummering viel terug van "
                            f"{laatste} naar {terug} — ik kijk op bezorgtijd verder)"
                        )
                        for melding in lezer.meldingen_na_tijd(laatste_tijd):
                            laatste_tijd = max(laatste_tijd, melding.bezorgd_op)
                            print(melding)
                        laatste = lezer.hoogste_rec_id()
            except MeldingFout as fout:
                print(f"(even niet gelukt: {fout})")
            time.sleep(poll_ms / 1000)
    except KeyboardInterrupt:
        print("\nGestopt.")
    return 0


def main(argv: list[str] | None = None) -> int:
    zet_uitvoer_op_utf8()
    ontleder = argparse.ArgumentParser(description="Lezer van het macOS Berichtencentrum")
    ontleder.add_argument("--diag", action="store_true", help="controleer de hele opstelling")
    ontleder.add_argument("--volg", action="store_true", help="laat live meldingen zien")
    ontleder.add_argument("--apps", action="store_true", help="toon alle bundelnamen")
    ontleder.add_argument("--db", default="auto", help="pad naar de database")
    ontleder.add_argument(
        "--bundle",
        action="append",
        default=None,
        help="alleen deze app (meerdere keren te gebruiken); leeg = alle apps",
    )
    ontleder.add_argument("--poll-ms", type=int, default=150)
    argumenten = ontleder.parse_args(argv)

    bundels = argumenten.bundle if argumenten.bundle is not None else [DISCORD_BUNDLE]

    try:
        if argumenten.apps:
            lezer = Meldingenlezer(argumenten.db, bundels, "auto")
            for naam, aantal in lezer.apps_met_aantallen():
                print(f"{aantal:6d}  {naam}")
            return 0
        if argumenten.volg:
            return _volg(argumenten.db, [b for b in bundels if b], argumenten.poll_ms)
        return diagnose(argumenten.db, bundels)
    except MeldingFout as fout:
        print(f"\nFOUT: {fout}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
