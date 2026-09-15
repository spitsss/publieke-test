"""
verkoop.py — verkopen via het knoppenmenu van BasedBot.

LEES DIT EERST

Met Quick Buy AAN betekent een kaal contractadres naar BasedBot sturen: KOPEN.
Je kunt dus nooit "even een adres sturen om te verkopen" — dan koop je bij.
Verkopen gaat uitsluitend via het menu:

    /manage  ->  Your Bags  ->  de positie  ->  de verkoopknop

DE KNOPPEN LIGGEN GEVAARLIJK DICHT BIJ ELKAAR

  b_...    kopen
  cb_...   kopen
  se_...   verkopen
  msi_...  Initials: verkoopt precies je inleg terug

In hetzelfde menu staan koop- en verkoopknoppen naast elkaar. Daarom
controleren we vóór ELKE klik twee dingen:

  1. staat het contractadres in de knopdata? (anders klikken we op een knop
     van een ánder token)
  2. begint de data met een toegestaan voorvoegsel, en zeker niet met b_ of cb_?

Voldoet het niet, dan klikken we NIET. Liever een mislukte verkoop dan per
ongeluk bijkopen.

NOG EEN VALKUIL

De knop "Your Bags" zoek je op TEKST, niet op het voorvoegsel van de data. In
hetzelfde menu zit een terugpijl met precies dezelfde datastructuur. Klik je
die aan, dan sta je in een ander menu en klik je daarna blind verder.

OVER DE PRECIEZE DATAVORM

De exacte opbouw van de knopdata verschilt per versie van BasedBot. Daarom
raden we die nergens: we kiezen knoppen op hun TEKST en controleren daarna op
het adres en het voorvoegsel. Dat blijft werken als BasedBot zijn opmaak
aanpast, en weigert netjes als er iets niet klopt.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from staat import GEKOCHT, MISLUKT, ONBEKEND
from telegram_brug import Antwoord, Knop

# Voorvoegsels die ALTIJD geweigerd worden: dit zijn koopknoppen.
VERBODEN_VOORVOEGSELS = ("b_", "cb_")

# Voorvoegsels die bij verkopen horen. se_ = verkopen, msi_ = Initials.
VERKOOP_VOORVOEGSELS = ("se_", "msi_")

# Teksten die op een terugknop wijzen — nooit als "Your Bags" aanzien.
TERUG_TEKSTEN = ("terug", "back", "«", "‹", "←", "⬅", "🔙", "home", "main menu")

# Woorden waarmee BasedBot een geslaagde VERKOOP bevestigt. De patronen in
# telegram_brug.py gaan over kopen ("buy success", "bought"); die passen hier
# niet. Zou je die gebruiken, dan lees je elke geslaagde verkoop als
# "onbevestigd" en denk je onterecht dat er iets misging.
PATROON_VERKOCHT = (
    r"sell success|sold|successfully sold|position closed|swap success|"
    r"tx confirmed|transaction confirmed|✅"
)


class KlikGeweigerd(Exception):
    """Een klik is tegengehouden omdat hij niet veilig was."""


@dataclass
class Verkoopresultaat:
    gelukt: bool
    resultaat: str
    uitleg: str
    stappen: list[str]


def _bevat_adres(data: str, adres: str) -> bool:
    """
    Staat het adres in de knopdata? EVM-adressen vergelijken we zonder te
    letten op hoofdletters, Solana-adressen precies — daar betekent een
    hoofdletter iets anders.
    """
    if not data or not adres:
        return False
    if adres.lower().startswith("0x"):
        return adres.lower() in data.lower()
    return adres in data


def controleer_verkoopklik(knop: Knop, adres: str) -> tuple[bool, str]:
    """
    De veiligheidscontrole die vóór elke verkoopklik draait.
    Geeft (mag het, uitleg) terug.
    """
    data = (knop.data or "").strip()
    if not data:
        return False, f"knop '{knop.tekst}' heeft geen data (waarschijnlijk een link)"

    laag = data.lower()
    for verboden in VERBODEN_VOORVOEGSELS:
        if laag.startswith(verboden):
            return False, f"GEWEIGERD: '{data[:40]}' begint met '{verboden}' — dat is KOPEN"

    if not any(laag.startswith(goed) for goed in VERKOOP_VOORVOEGSELS):
        return False, (
            f"GEWEIGERD: '{data[:40]}' begint niet met "
            f"{' of '.join(VERKOOP_VOORVOEGSELS)}"
        )

    if not _bevat_adres(data, adres):
        return False, f"GEWEIGERD: het adres {adres[:10]}… staat niet in de knopdata"

    return True, f"knop '{knop.tekst}' is veilig ({data[:40]})"


def kies_bags_knop(knoppen: list[Knop]) -> Knop | None:
    """
    Zoekt de knop 'Your Bags' op TEKST. Een terugpijl heeft dezelfde
    datastructuur, dus op data zoeken pakt de verkeerde.
    """
    for knop in knoppen:
        tekst = (knop.tekst or "").strip().lower()
        if not tekst:
            continue
        if any(terug in tekst for terug in TERUG_TEKSTEN):
            continue
        if "bag" in tekst:  # "Your Bags", "💼 Bags", "My Bags"
            return knop
    return None


def kies_positie_knop(knoppen: list[Knop], adres: str) -> Knop | None:
    """Zoekt in de lijst met posities de knop die bij dit token hoort."""
    for knop in knoppen:
        if _bevat_adres(knop.data or "", adres):
            laag = (knop.data or "").lower()
            if any(laag.startswith(v) for v in VERBODEN_VOORVOEGSELS):
                continue  # dit is een koopknop; niet aanraken
            return knop
    return None


def kies_initials_knop(knoppen: list[Knop], adres: str) -> Knop | None:
    """
    Zoekt de Initials-knop: die verkoopt precies je inleg terug.
    Gebruik die in plaats van zelf uit te rekenen hoeveel je moet verkopen.
    """
    for knop in knoppen:
        data = (knop.data or "")
        if data.lower().startswith("msi_") and _bevat_adres(data, adres):
            return knop
    # Vangnet: op tekst zoeken als de data anders is opgebouwd.
    for knop in knoppen:
        if "initial" in (knop.tekst or "").lower():
            mag, _ = controleer_verkoopklik(knop, adres)
            if mag:
                return knop
    return None


def kies_verkoopknop(knoppen: list[Knop], adres: str, deel: str = "100") -> Knop | None:
    """
    Zoekt een verkoopknop voor een percentage, bijvoorbeeld '50' of '100'.
    We zoeken op de tekst van de knop (daar staat "50%" in) en controleren
    daarna op adres en voorvoegsel.
    """
    deel = str(deel).strip().rstrip("%")
    if deel.lower() in ("initials", "inleg"):
        return kies_initials_knop(knoppen, adres)

    kandidaten = []
    for knop in knoppen:
        mag, _ = controleer_verkoopklik(knop, adres)
        if not mag:
            continue
        tekst = (knop.tekst or "")
        getallen = re.findall(r"(\d{1,3})\s*%", tekst)
        if getallen and getallen[0] == deel:
            return knop
        kandidaten.append(knop)

    # Geen percentage gevonden? Bij 100% mag "Sell All" ook.
    if deel == "100":
        for knop in kandidaten:
            if re.search(r"\ball\b|alles", (knop.tekst or ""), re.IGNORECASE):
                return knop
    return None


def verkoop(
    brug,
    adres: str,
    deel: str = "initials",
    logboek=None,
    pauze_s: float = 1.5,
) -> Verkoopresultaat:
    """
    Loopt het hele verkoopmenu af. Elke stap wordt gecontroleerd; bij twijfel
    stoppen we en klikken we niets meer aan.

    'pauze_s' is de wachttijd tussen twee klikken: BasedBot moet zijn menu
    kunnen bijwerken. In de tests staat die op 0.
    """
    stappen: list[str] = []

    def noteer(regel: str) -> None:
        stappen.append(regel)
        if logboek:
            logboek.info("verkoop: %s", regel)

    # Stap 1: het menu opvragen. NOOIT een kaal adres sturen — dat koopt.
    noteer("/manage versturen")
    brug.stuur("/manage")
    time.sleep(pauze_s)

    bericht_id, _, knoppen = brug.laatste_met_knoppen()
    if not bericht_id or not knoppen:
        return Verkoopresultaat(False, MISLUKT, "BasedBot gaf geen menu met knoppen", stappen)

    # Stap 2: "Your Bags" — op TEKST zoeken.
    bags = kies_bags_knop(knoppen)
    if bags is None:
        namen = ", ".join(f"'{k.tekst}'" for k in knoppen[:8])
        return Verkoopresultaat(
            False, MISLUKT, f"geen knop met 'Bags' gevonden. Wel: {namen}", stappen
        )
    noteer(f"klik op '{bags.tekst}'")
    brug.klik(bericht_id, bags.rij, bags.kolom)
    time.sleep(pauze_s)

    # Stap 3: de juiste positie.
    bericht_id, _, knoppen = brug.laatste_met_knoppen()
    positie = kies_positie_knop(knoppen, adres)
    if positie is None:
        return Verkoopresultaat(
            False, MISLUKT, f"geen positie gevonden voor {adres[:12]}…", stappen
        )
    noteer(f"klik op positie '{positie.tekst}'")
    brug.klik(bericht_id, positie.rij, positie.kolom)
    time.sleep(pauze_s)

    # Stap 4: de verkoopknop, mét volledige veiligheidscontrole.
    bericht_id, _, knoppen = brug.laatste_met_knoppen()
    knop = kies_verkoopknop(knoppen, adres, deel)
    if knop is None:
        namen = ", ".join(f"'{k.tekst}'" for k in knoppen[:10])
        return Verkoopresultaat(
            False, MISLUKT, f"geen verkoopknop voor '{deel}'. Wel: {namen}", stappen
        )

    mag, uitleg = controleer_verkoopklik(knop, adres)
    if not mag:
        return Verkoopresultaat(False, MISLUKT, uitleg, stappen)
    noteer(uitleg)

    brug.klik(bericht_id, knop.rij, knop.kolom)
    time.sleep(pauze_s * 1.5)

    # Stap 5: het antwoord lezen. Niet aannemen dat het gelukt is.
    _, tekst, _ = brug.laatste_met_knoppen()
    from telegram_brug import beoordeel_antwoord

    # Let op het derde argument: we toetsen op VERKOOP-woorden, niet op de
    # koopwoorden uit telegram_brug.py.
    resultaat, reden = beoordeel_antwoord([tekst], patroon_gekocht=PATROON_VERKOCHT)
    gelukt = resultaat == GEKOCHT
    if resultaat == ONBEKEND:
        reden = "geklikt, maar BasedBot bevestigde niets — controleer het met de hand"
    return Verkoopresultaat(gelukt, resultaat, reden, stappen)


def _toon_menu() -> int:
    """Laat zien welke knoppen BasedBot nu toont. Klikt nergens op."""
    import sys

    from gereedschap import draait_al, zet_uitvoer_op_utf8
    from instellingen import laad

    zet_uitvoer_op_utf8()
    opties = laad()

    if draait_al(opties.instantie_poort):
        print(
            "De sniper draait al en heeft de Telegram-verbinding in handen.\n"
            "Twee clients met dezelfde sessie krijgen geen updates meer — stop eerst\n"
            "de sniper, of gebruik de bedieningsbot."
        )
        return 1

    from telegram_brug import TelegramBrug

    brug = TelegramBrug(
        opties.api_id, opties.api_hash, opties.sessienaam, opties.basedbot, opties.antwoord_wacht_s
    )
    brug.start()
    try:
        brug.stuur("/manage")
        time.sleep(2.5)
        bericht_id, tekst, knoppen = brug.laatste_met_knoppen()
        print(f"Bericht {bericht_id}:\n{tekst}\n")
        print("Knoppen:")
        for knop in knoppen:
            print(f"  [{knop.rij},{knop.kolom}] '{knop.tekst}'  data={knop.data!r}")
        print("\nControleer hier welke voorvoegsels jouw BasedBot gebruikt.")
        print(f"Wij weigeren alles dat begint met: {', '.join(VERBODEN_VOORVOEGSELS)}")
        print(f"Wij staan toe:                     {', '.join(VERKOOP_VOORVOEGSELS)}")
        return 0
    finally:
        brug.stop()


if __name__ == "__main__":
    import sys

    if "--toon" in sys.argv:
        raise SystemExit(_toon_menu())
    print("Gebruik: python3 verkoop.py --toon   (laat het menu van BasedBot zien)")
