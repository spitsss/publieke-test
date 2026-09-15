"""
quickbuy_wacht.py — bewaakt of Quick Buy bij BasedBot aan blijft staan.

WAAROM DIT BESTAAT

Quick Buy springt terug na een storting. Twee keer waargenomen: aan, geld
gestort, uit. De sniper stuurt dan keurig het contractadres door en er gebeurt
NIETS. Je logboek zegt "verstuurd", je portefeuille zegt niets.

Op 8 september ging zo een call verloren: in 889 milliseconden gedetecteerd en
doorgestuurd, nul gekocht.

TWEE REGELS

1. Vraag BasedBot NOOIT vaker dan eens per vijf minuten om /manage. Doe je dat
   wel, dan stopt hij met antwoorden — en dan weet je helemaal niets meer.
2. Klik hier nooit op iets. Deze wachter kijkt alleen. Koop- en verkoopknoppen
   liggen in hetzelfde menu vlak bij elkaar.
"""

from __future__ import annotations

import time

# Nooit vaker dan dit. BasedBot stopt met antwoorden als je hem bestookt.
MINIMALE_TUSSENTIJD_S = 300

AAN_WOORDEN = ("on", "aan", "enabled", "actief", "active", "✅", "🟢", "☑")
UIT_WOORDEN = ("off", "uit", "disabled", "inactief", "inactive", "❌", "🔴", "⬜", "☐")


def lees_quickbuy(tekst: str, knoppen) -> tuple[str, str]:
    """
    Kijkt in de tekst en de knoppen van het /manage-menu of Quick Buy aan staat.

    Geeft ("aan" | "uit" | "onbekend", uitleg) terug.
    Bij twijfel: "onbekend". Dan waarschuwen we liever ten onrechte dan dat we
    stilzwijgend aannemen dat het goed zit.
    """
    stukken: list[str] = []
    if tekst:
        stukken.extend(regel for regel in tekst.splitlines() if regel.strip())
    for knop in knoppen or []:
        knoptekst = getattr(knop, "tekst", "") or ""
        if knoptekst:
            stukken.append(knoptekst)

    kandidaten = [stuk for stuk in stukken if "quick buy" in stuk.lower() or "quickbuy" in stuk.lower()]
    if not kandidaten:
        return "onbekend", "ik zie 'Quick Buy' nergens in het menu staan"

    for stuk in kandidaten:
        laag = stuk.lower()
        # Eerst op 'uit' toetsen: "Quick Buy: OFF" bevat ook het woord 'buy'.
        if any(woord in laag for woord in UIT_WOORDEN):
            return "uit", f"gevonden: '{stuk.strip()}'"
        if any(woord in laag for woord in AAN_WOORDEN):
            return "aan", f"gevonden: '{stuk.strip()}'"

    return "onbekend", f"gevonden: '{kandidaten[0].strip()}' — maar aan of uit kan ik niet zien"


def controleer_een_keer(brug, logboek=None) -> tuple[str, str]:
    """Vraagt het menu op en leest de stand. Klikt nergens op."""
    brug.stuur("/manage")
    time.sleep(2.5)
    _, tekst, knoppen = brug.laatste_met_knoppen()
    stand, uitleg = lees_quickbuy(tekst, knoppen)
    if logboek:
        logboek.info("Quick Buy staat: %s (%s)", stand.upper(), uitleg)
    return stand, uitleg


def draai_wachter(brug, opties, staat, logboek, stoppen, tussentijd_s: int | None = None) -> None:
    """
    Blijft draaien en controleert periodiek. Bedoeld als achtergronddraad van
    de sniper; werkt ook los.
    """
    tussentijd = max(MINIMALE_TUSSENTIJD_S, int(tussentijd_s or MINIMALE_TUSSENTIJD_S))
    vorige_stand = ""
    # Eerste controle niet meteen: de sniper is net opgestart.
    volgende = time.time() + 30

    while not stoppen.is_set():
        if time.time() < volgende:
            time.sleep(1)
            continue
        volgende = time.time() + tussentijd

        try:
            stand, uitleg = controleer_een_keer(brug, logboek)
        except Exception as fout:
            logboek.warning("Quick Buy-controle mislukte: %s", fout)
            staat.hartslag("quickbuy", {"stand": "onbekend", "fout": str(fout)})
            continue

        staat.hartslag("quickbuy", {"stand": stand, "uitleg": uitleg})
        staat.werk_bij(quickbuy=stand, quickbuy_uitleg=uitleg, quickbuy_tijd=time.time())

        if stand != vorige_stand:
            if stand == "uit":
                boodschap = (
                    "QUICK BUY STAAT UIT.\n"
                    "De sniper stuurt adressen door, maar BasedBot koopt NIETS.\n"
                    "Zet hem aan in /manage. Dit gebeurt vaak na een storting."
                )
                logboek.error(boodschap.replace("\n", " "))
                _alarm(opties, boodschap)
            elif stand == "onbekend":
                logboek.warning("Quick Buy-stand onduidelijk: %s", uitleg)
                _alarm(opties, f"Kan Quick Buy-stand niet aflezen: {uitleg}")
            else:
                logboek.info("Quick Buy staat aan.")
            vorige_stand = stand


def _alarm(opties, tekst: str) -> None:
    try:
        import telegrambediening

        telegrambediening.stuur_naar_eigenaar(opties, tekst)
    except Exception:
        pass


def main() -> int:
    """Eenmalige controle vanaf de opdrachtregel."""
    import threading

    from gereedschap import draait_al, maak_logboek, zet_uitvoer_op_utf8
    from instellingen import laad
    from staat import Staat

    zet_uitvoer_op_utf8()
    opties = laad()
    logboek = maak_logboek("quickbuy", opties.logniveau)

    if draait_al(opties.instantie_poort):
        print(
            "De sniper draait en bewaakt Quick Buy zelf al.\n"
            "Twee Telegram-clients met dezelfde sessie krijgen geen updates meer,\n"
            "dus ik doe hier niets. Kijk in het dashboard of gebruik /quickbuy in\n"
            "de bedieningsbot."
        )
        return 1

    from telegram_brug import TelegramBrug

    brug = TelegramBrug(
        opties.api_id, opties.api_hash, opties.sessienaam, opties.basedbot, opties.antwoord_wacht_s
    )
    brug.start()
    try:
        stand, uitleg = controleer_een_keer(brug, logboek)
        print(f"Quick Buy: {stand.upper()} — {uitleg}")
        Staat().werk_bij(quickbuy=stand, quickbuy_uitleg=uitleg, quickbuy_tijd=time.time())
        return 0 if stand == "aan" else 1
    finally:
        brug.stop()
        _ = threading


if __name__ == "__main__":
    raise SystemExit(main())
