"""
Tests voor het beoordelen van BasedBot's antwoord.

De kern: "verstuurd" en "gekocht" zijn niet hetzelfde. Snappen we het antwoord
niet, dan is het ONBEKEND — nooit stilzwijgend "gekocht". Anders lees je in je
logboek dat je iets hebt terwijl je niets hebt.
"""
import unittest

import hulp  # noqa: F401

from staat import GEKOCHT, MISLUKT, ONBEKEND
from telegram_brug import beoordeel_antwoord


class TestBeoordelen(unittest.TestCase):
    def test_bevestigde_aankoop(self):
        for tekst in (
            "Buy Success! You bought 1,000,000 WIF",
            "Successfully bought 0.5 SOL of PEPE",
            "Swap success ✅",
            "Position opened",
        ):
            with self.subTest(tekst=tekst):
                self.assertEqual(GEKOCHT, beoordeel_antwoord([tekst])[0])

    def test_duidelijke_mislukking(self):
        for tekst in (
            "Insufficient balance",
            "Buy failed: slippage too low",
            "Error: token not found",
            "Unable to find a route",
        ):
            with self.subTest(tekst=tekst):
                self.assertEqual(MISLUKT, beoordeel_antwoord([tekst])[0])

    def test_mislukking_wint_van_het_woord_buy(self):
        """'Buy failed' bevat ook 'buy'. Dat mag nooit als aankoop tellen."""
        self.assertEqual(MISLUKT, beoordeel_antwoord(["Buy failed"])[0])

    def test_geen_antwoord_is_niet_gekocht(self):
        resultaat, uitleg = beoordeel_antwoord([])
        self.assertEqual(ONBEKEND, resultaat)
        self.assertIn("geen antwoord", uitleg)

    def test_onbegrijpelijk_antwoord_is_niet_gekocht(self):
        resultaat, uitleg = beoordeel_antwoord(["🤖 beep boop 42"])
        self.assertEqual(ONBEKEND, resultaat)
        self.assertIn("NIET als aankoop", uitleg)

    def test_nog_bezig_is_nog_geen_aankoop(self):
        resultaat, uitleg = beoordeel_antwoord(["Buying... please wait"])
        self.assertEqual(ONBEKEND, resultaat)
        self.assertIn("nog bezig", uitleg)

    def test_lege_tekst(self):
        self.assertEqual(ONBEKEND, beoordeel_antwoord([""])[0])
        self.assertEqual(ONBEKEND, beoordeel_antwoord(["", "  "])[0])

    def test_eigen_patroon_voor_verkopen(self):
        import verkoop

        resultaat, _ = beoordeel_antwoord(
            ["Sell Success: sold 1.2 SOL"], patroon_gekocht=verkoop.PATROON_VERKOCHT
        )
        self.assertEqual(GEKOCHT, resultaat)
        # Met de KOOPwoorden zou dezelfde tekst onbevestigd blijven:
        self.assertEqual(ONBEKEND, beoordeel_antwoord(["Sell Success: sold 1.2 SOL"])[0])


if __name__ == "__main__":
    unittest.main()
