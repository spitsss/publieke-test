"""
Tests voor de Quick Buy-wachter.

Quick Buy springt terug na een storting. Staat hij uit, dan stuurt de sniper
keurig het adres door en gebeurt er NIETS. Bij twijfel moet deze lezer
"onbekend" zeggen en dus waarschuwen, niet stilzwijgend aannemen dat het goed zit.
"""
import unittest

import hulp  # noqa: F401

import quickbuy_wacht
from telegram_brug import Knop


class TestStandLezen(unittest.TestCase):
    def test_aan_in_de_tekst(self):
        stand, _ = quickbuy_wacht.lees_quickbuy("Settings\nQuick Buy: ON\nSlippage: 15%", [])
        self.assertEqual("aan", stand)

    def test_uit_in_de_tekst(self):
        stand, _ = quickbuy_wacht.lees_quickbuy("Quick Buy: OFF", [])
        self.assertEqual("uit", stand)

    def test_uit_wint_van_het_woord_buy(self):
        """'Quick Buy: OFF' bevat ook 'buy'. Dat mag nooit 'aan' worden."""
        self.assertEqual("uit", quickbuy_wacht.lees_quickbuy("Quick Buy: OFF", [])[0])

    def test_in_een_knop(self):
        knoppen = [Knop(0, 0, "🟢 Quick Buy", "qb_toggle")]
        self.assertEqual("aan", quickbuy_wacht.lees_quickbuy("Menu", knoppen)[0])
        knoppen = [Knop(0, 0, "🔴 Quick Buy", "qb_toggle")]
        self.assertEqual("uit", quickbuy_wacht.lees_quickbuy("Menu", knoppen)[0])

    def test_nederlands(self):
        self.assertEqual("uit", quickbuy_wacht.lees_quickbuy("Quick Buy staat uit", [])[0])

    def test_niet_te_vinden_is_onbekend(self):
        stand, uitleg = quickbuy_wacht.lees_quickbuy("Wallet: 1.2 SOL", [])
        self.assertEqual("onbekend", stand)
        self.assertIn("nergens", uitleg)

    def test_gevonden_maar_onduidelijk_is_onbekend(self):
        stand, _ = quickbuy_wacht.lees_quickbuy("Quick Buy", [])
        self.assertEqual("onbekend", stand)

    def test_rommel_geeft_geen_crash(self):
        for tekst in (None, "", "\n\n", "x" * 5000):
            with self.subTest(tekst=repr(tekst)[:15]):
                stand, uitleg = quickbuy_wacht.lees_quickbuy(tekst, None)
                self.assertIn(stand, ("aan", "uit", "onbekend"))
                self.assertIsInstance(uitleg, str)


class TestTussentijd(unittest.TestCase):
    def test_nooit_vaker_dan_eens_per_vijf_minuten(self):
        """Vraag je BasedBot vaker om /manage, dan stopt hij met antwoorden."""
        self.assertGreaterEqual(quickbuy_wacht.MINIMALE_TUSSENTIJD_S, 300)


if __name__ == "__main__":
    unittest.main()
