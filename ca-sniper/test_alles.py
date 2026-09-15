#!/usr/bin/env python3
"""
test_alles.py — draait elke test van dit project met één opdracht.

    python3 test_alles.py

Er komt niets aan het internet te pas, er wordt niets gekocht en er wordt
niets naar Telegram gestuurd.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from gereedschap import zet_uitvoer_op_utf8

MAP = Path(__file__).resolve().parent
TESTMAP = MAP / "tests"


def controleer_imports() -> list[str]:
    """
    Kijkt eerst of elk onderdeel überhaupt te laden is. Een typefout in een
    bestand dat je zelden gebruikt merk je anders pas als het misgaat.
    """
    problemen: list[str] = []
    for naam in (
        "gereedschap", "instellingen", "staat", "extract", "filters", "exits",
        "meldingen", "markt", "telegram_brug", "verkoop", "quickbuy_wacht",
        "telegrambediening", "waakhond", "dashboard", "bot",
    ):
        try:
            __import__(naam)
        except Exception as fout:
            problemen.append(f"{naam}: {fout}")
    return problemen


def controleer_bestanden() -> list[str]:
    """Kijkt of alles wat erbij hoort er ook echt is."""
    ontbreekt = []
    for naam in ("dashboard.html", "config.ini.voorbeeld", "requirements.txt", "LEESMIJ.md"):
        if not (MAP / naam).exists():
            ontbreekt.append(naam)
    return ontbreekt


def main() -> int:
    zet_uitvoer_op_utf8()
    sys.path.insert(0, str(MAP))
    sys.path.insert(0, str(TESTMAP))

    print("=" * 70)
    print("ALLE TESTS")
    print("=" * 70)

    print("\n1. Is elk onderdeel te laden?")
    problemen = controleer_imports()
    if problemen:
        for probleem in problemen:
            print(f"   MISLUKT  {probleem}")
        print("\nEr is een onderdeel dat niet eens geladen kan worden. Stop hier.")
        return 1
    print("   alle onderdelen laden goed")

    print("\n2. Staat alles er wat erbij hoort?")
    ontbreekt = controleer_bestanden()
    for naam in ontbreekt:
        print(f"   ONTBREEKT  {naam}")
    if not ontbreekt:
        print("   alles aanwezig")

    print("\n3. De testsuites:\n")
    lader = unittest.TestLoader()
    verzameling = lader.discover(str(TESTMAP), pattern="test_*.py", top_level_dir=str(TESTMAP))
    uitkomst = unittest.TextTestRunner(verbosity=2).run(verzameling)

    print("\n" + "=" * 70)
    gelukt = uitkomst.testsRun - len(uitkomst.failures) - len(uitkomst.errors)
    print(f"{gelukt} van de {uitkomst.testsRun} tests geslaagd")
    if uitkomst.failures:
        print(f"{len(uitkomst.failures)} mislukt")
    if uitkomst.errors:
        print(f"{len(uitkomst.errors)} met een fout")
    if uitkomst.skipped:
        print(f"{len(uitkomst.skipped)} overgeslagen")

    if uitkomst.wasSuccessful() and not ontbreekt:
        print("\nALLES IN ORDE.")
        print("\nLet op: hiermee is de macOS-kant NIET getest. De meldingenlezer is")
        print("getest tegen een nagemaakte database. Draai op je Mac ook:")
        print("    python3 meldingen.py --diag")
        print("    osascript -e 'display notification \"CA: test\" with title \"#calls (Test)\"'")
        return 0

    print("\nER ZIJN PROBLEMEN. Los ze op voordat je live gaat.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
