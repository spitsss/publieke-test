"""
Tests voor de verkoopknoppen.

Hier zit de grootste kans op een dure fout: koop- en verkoopknoppen staan in
hetzelfde menu vlak bij elkaar. b_ en cb_ zijn KOPEN, se_ is verkopen.
"""
import unittest

import hulp  # noqa: F401

import verkoop
from telegram_brug import Knop

ADRES = "0x6b175474e89094c44da98b954eedeac495271d0f"
MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


class TestVeiligheidscontrole(unittest.TestCase):
    def test_koopknop_wordt_altijd_geweigerd(self):
        """b_ en cb_ zijn KOPEN. Nooit aanklikken tijdens het verkopen."""
        for voorvoegsel in ("b_", "cb_", "B_", "CB_"):
            with self.subTest(voorvoegsel=voorvoegsel):
                knop = Knop(0, 0, "Buy 0.1", f"{voorvoegsel}{ADRES}_BASE_0_0")
                mag, uitleg = verkoop.controleer_verkoopklik(knop, ADRES)
                self.assertFalse(mag)
                self.assertIn("KOPEN", uitleg)

    def test_verkoopknop_met_het_juiste_adres_mag(self):
        knop = Knop(0, 0, "Sell 50%", f"se_{ADRES}_BASE_50")
        mag, _ = verkoop.controleer_verkoopklik(knop, ADRES)
        self.assertTrue(mag)

    def test_initials_knop_mag(self):
        knop = Knop(0, 0, "Initials", f"msi_{ADRES}_BASE_0_0")
        mag, _ = verkoop.controleer_verkoopklik(knop, ADRES)
        self.assertTrue(mag)

    def test_knop_van_een_ander_token_wordt_geweigerd(self):
        ander = "0x1111111111111111111111111111111111111111"
        knop = Knop(0, 0, "Sell 50%", f"se_{ander}_BASE_50")
        mag, uitleg = verkoop.controleer_verkoopklik(knop, ADRES)
        self.assertFalse(mag)
        self.assertIn("staat niet in de knopdata", uitleg)

    def test_onbekend_voorvoegsel_wordt_geweigerd(self):
        knop = Knop(0, 0, "Iets", f"xyz_{ADRES}")
        mag, _ = verkoop.controleer_verkoopklik(knop, ADRES)
        self.assertFalse(mag)

    def test_knop_zonder_data_wordt_geweigerd(self):
        mag, uitleg = verkoop.controleer_verkoopklik(Knop(0, 0, "Website", ""), ADRES)
        self.assertFalse(mag)
        self.assertIn("geen data", uitleg)

    def test_evm_hoofdletters_maken_niet_uit(self):
        knop = Knop(0, 0, "Sell", f"se_{ADRES.upper()}_BASE_50")
        mag, _ = verkoop.controleer_verkoopklik(knop, ADRES)
        self.assertTrue(mag)

    def test_solana_hoofdletters_maken_wel_uit(self):
        """In base58 is een hoofdletter een ander teken — dus een ander token."""
        knop = Knop(0, 0, "Sell", f"se_{MINT.lower()}_SOL_50")
        mag, _ = verkoop.controleer_verkoopklik(knop, MINT)
        self.assertFalse(mag)


class TestBagsKnop(unittest.TestCase):
    def test_wordt_op_tekst_gevonden(self):
        knoppen = [
            Knop(0, 0, "Settings", "menu_settings"),
            Knop(0, 1, "Your Bags", "menu_bags"),
        ]
        self.assertEqual("Your Bags", verkoop.kies_bags_knop(knoppen).tekst)

    def test_terugpijl_met_dezelfde_datastructuur_wordt_niet_gepakt(self):
        """
        In hetzelfde menu zit een terugpijl met dezelfde opbouw. Zoek je op
        het datavoorvoegsel, dan klik je die aan en sta je in een ander menu.
        """
        knoppen = [
            Knop(0, 0, "« Back to bags", "menu_bags_back"),
            Knop(0, 1, "Your Bags", "menu_bags"),
        ]
        gekozen = verkoop.kies_bags_knop(knoppen)
        self.assertEqual("Your Bags", gekozen.tekst)

    def test_geen_bags_knop(self):
        self.assertIsNone(verkoop.kies_bags_knop([Knop(0, 0, "Settings", "x")]))
        self.assertIsNone(verkoop.kies_bags_knop([]))


class TestKnopKiezen(unittest.TestCase):
    def test_positie_van_het_juiste_token(self):
        knoppen = [
            Knop(0, 0, "PEPE", "pos_0x1111111111111111111111111111111111111111"),
            Knop(1, 0, "WIF", f"pos_{ADRES}"),
        ]
        self.assertEqual("WIF", verkoop.kies_positie_knop(knoppen, ADRES).tekst)

    def test_positie_pakt_nooit_een_koopknop(self):
        knoppen = [Knop(0, 0, "Buy more", f"b_{ADRES}_BASE_1")]
        self.assertIsNone(verkoop.kies_positie_knop(knoppen, ADRES))

    def test_percentage_kiezen(self):
        knoppen = [
            Knop(0, 0, "Sell 25%", f"se_{ADRES}_B_25"),
            Knop(0, 1, "Sell 50%", f"se_{ADRES}_B_50"),
            Knop(0, 2, "Sell 100%", f"se_{ADRES}_B_100"),
        ]
        self.assertEqual("Sell 50%", verkoop.kies_verkoopknop(knoppen, ADRES, "50").tekst)
        self.assertEqual("Sell 100%", verkoop.kies_verkoopknop(knoppen, ADRES, "100").tekst)

    def test_initials_wordt_gebruikt_in_plaats_van_zelf_rekenen(self):
        knoppen = [
            Knop(0, 0, "Sell 50%", f"se_{ADRES}_B_50"),
            Knop(0, 1, "Initials", f"msi_{ADRES}_BASE_0_0"),
        ]
        gekozen = verkoop.kies_verkoopknop(knoppen, ADRES, "initials")
        self.assertEqual("Initials", gekozen.tekst)
        self.assertTrue(gekozen.data.startswith("msi_"))

    def test_sell_all_telt_als_honderd_procent(self):
        knoppen = [Knop(0, 0, "Sell All", f"se_{ADRES}_B_all")]
        self.assertIsNotNone(verkoop.kies_verkoopknop(knoppen, ADRES, "100"))

    def test_kiest_liever_niets_dan_een_koopknop(self):
        knoppen = [Knop(0, 0, "Buy 50%", f"b_{ADRES}_B_50")]
        self.assertIsNone(verkoop.kies_verkoopknop(knoppen, ADRES, "50"))

    def test_lege_knoppenlijst(self):
        self.assertIsNone(verkoop.kies_verkoopknop([], ADRES, "50"))
        self.assertIsNone(verkoop.kies_initials_knop([], ADRES))


class TestHeleVerkoop(unittest.TestCase):
    """Loopt het menu na met een nagemaakte BasedBot."""

    class NepBrug:
        def __init__(self, menus):
            self.menus = menus
            self.stap = 0
            self.verstuurd = []
            self.geklikt = []

        def stuur(self, tekst):
            self.verstuurd.append(tekst)
            return 1

        def laatste_met_knoppen(self, aantal=10):
            return self.menus[self.stap]

        def klik(self, bericht_id, rij, kolom):
            _, _, knoppen = self.menus[self.stap]
            for knop in knoppen:
                if knop.rij == rij and knop.kolom == kolom:
                    self.geklikt.append(knop)
            self.stap = min(self.stap + 1, len(self.menus) - 1)
            return ""

    def test_volledige_ronde(self):
        menus = [
            (1, "Menu", [Knop(0, 0, "Your Bags", "menu_bags")]),
            (2, "Bags", [Knop(0, 0, "WIF", f"pos_{ADRES}")]),
            (3, "WIF", [
                Knop(0, 0, "Buy more", f"b_{ADRES}_B_1"),
                Knop(0, 1, "Initials", f"msi_{ADRES}_BASE_0_0"),
            ]),
            (4, "Sell Success: sold 1.2 SOL", []),
        ]
        brug = self.NepBrug(menus)
        uitkomst = verkoop.verkoop(brug, ADRES, "initials", pauze_s=0)

        self.assertEqual(["/manage"], brug.verstuurd, "verkopen gaat ALTIJD via /manage")
        self.assertNotIn(ADRES, brug.verstuurd, "een kaal adres sturen zou KOPEN zijn")
        self.assertEqual(["Your Bags", "WIF", "Initials"], [k.tekst for k in brug.geklikt])
        self.assertTrue(uitkomst.gelukt, uitkomst.uitleg)

    def test_stopt_als_de_positie_er_niet_is(self):
        menus = [
            (1, "Menu", [Knop(0, 0, "Your Bags", "menu_bags")]),
            (2, "Bags", [Knop(0, 0, "PEPE", "pos_0x2222222222222222222222222222222222222222")]),
        ]
        brug = self.NepBrug(menus)
        uitkomst = verkoop.verkoop(brug, ADRES, "initials", pauze_s=0)
        self.assertFalse(uitkomst.gelukt)
        self.assertIn("geen positie", uitkomst.uitleg)
        self.assertEqual(["Your Bags"], [k.tekst for k in brug.geklikt])

    def test_klikt_nooit_op_kopen_als_er_geen_verkoopknop_is(self):
        menus = [
            (1, "Menu", [Knop(0, 0, "Your Bags", "menu_bags")]),
            (2, "Bags", [Knop(0, 0, "WIF", f"pos_{ADRES}")]),
            (3, "WIF", [Knop(0, 0, "Buy more", f"b_{ADRES}_B_1")]),
        ]
        brug = self.NepBrug(menus)
        uitkomst = verkoop.verkoop(brug, ADRES, "50", pauze_s=0)
        self.assertFalse(uitkomst.gelukt)
        self.assertNotIn("Buy more", [k.tekst for k in brug.geklikt])


if __name__ == "__main__":
    unittest.main()
