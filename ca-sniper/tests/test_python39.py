"""
Bewaakt dat de code op Python 3.9 blijft werken.

Waarom dit bestand bestaat: macOS levert zelf Python 3.9.6 mee, en daar draait
deze bot op. Wie de code op een nieuwere Python ontwikkelt, schrijft zonder het
te merken iets als 'float | None' in een type-aanduiding. Dat is geldige
3.10-code, maar op 3.9 klapt het programma eruit zodra het bestand geladen
wordt — tenzij bovenaan 'from __future__ import annotations' staat.

Dat is precies één keer gebeurd, in een testbestand, en het viel alleen op
doordat de tests ook op een echte 3.9 gedraaid werden.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

import hulp  # noqa: F401

MAP = Path(__file__).resolve().parent.parent

# Een type-aanduiding met een liggend streepje erin, zoals ': int | None'.
UNIE_IN_AANDUIDING = re.compile(
    r"(?::\s*[A-Za-z_][A-Za-z_0-9\[\]\.\"']*\s*\|)|(?:->\s*[A-Za-z_][A-Za-z_0-9\[\]\.\"']*\s*\|)"
)


DIT_BESTAND = Path(__file__).name


def alle_bestanden() -> list[Path]:
    return sorted(pad for pad in MAP.rglob("*.py") if "__pycache__" not in pad.parts)


class TestPython39(unittest.TestCase):
    def test_alles_is_geldige_39_syntaxis(self):
        for pad in alle_bestanden():
            with self.subTest(bestand=pad.name):
                try:
                    ast.parse(pad.read_text(encoding="utf-8"), feature_version=(3, 9))
                except SyntaxError as fout:
                    self.fail(f"{pad.name}:{fout.lineno} kan niet op Python 3.9 — {fout.msg}")

    def test_unies_hebben_de_future_import(self):
        """'int | None' werkt op 3.9 alleen met de future-import bovenaan."""
        for pad in alle_bestanden():
            bron = pad.read_text(encoding="utf-8")
            if not UNIE_IN_AANDUIDING.search(bron):
                continue
            if "from __future__ import annotations" not in bron:
                treffer = UNIE_IN_AANDUIDING.search(bron)
                regel = bron[: treffer.start()].count("\n") + 1 if treffer else 0
                self.fail(
                    f"{pad.name}:{regel} gebruikt 'X | Y' in een type-aanduiding maar mist "
                    "bovenaan 'from __future__ import annotations' — dat gaat stuk op Python 3.9"
                )

    def test_geen_functies_van_na_39(self):
        """
        Een paar dingen die pas vanaf Python 3.10 bestaan.

        De namen worden hier in stukjes opgebouwd, anders komen ze letterlijk
        in dit bestand te staan en betrapt de bewaker zichzelf. (Dat gebeurde
        ook echt.) Voor de zekerheid slaan we dit bestand ook over.
        """
        verboden = ("slots" + "=True", "itertools." + "pairwise", "bit_" + "count", "kw_" + "only=")
        for pad in alle_bestanden():
            if pad.name == DIT_BESTAND:
                continue
            bron = pad.read_text(encoding="utf-8")
            for stuk in verboden:
                if stuk in bron:
                    regel = next(
                        (nr for nr, r in enumerate(bron.splitlines(), 1) if stuk in r), 0
                    )
                    self.fail(f"{pad.name}:{regel} gebruikt '{stuk}' — dat bestaat niet op 3.9")


if __name__ == "__main__":
    unittest.main()
