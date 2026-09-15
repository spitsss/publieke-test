"""Tests voor het kanaalfilter — zonder filter koopt de bot op élke melding."""
import unittest

import hulp  # noqa: F401  (zet sys.path goed)

import filters


class TestKanaalfilter(unittest.TestCase):
    KANALEN = ["microcaps-calls"]

    def test_het_callskanaal_komt_door(self):
        mag, reden = filters.kanaal_toegestaan("#microcaps-calls (Alpha Group)", "", self.KANALEN)
        self.assertTrue(mag, reden)

    def test_een_dm_komt_er_niet_door(self):
        mag, reden = filters.kanaal_toegestaan("Sander", "stuurt je een adres", self.KANALEN)
        self.assertFalse(mag)
        self.assertIn("DM", reden)

    def test_ander_kanaal_van_dezelfde_server_komt_er_niet_door(self):
        mag, _ = filters.kanaal_toegestaan("#general (Alpha Group)", "", self.KANALEN)
        self.assertFalse(mag)

    def test_lijkend_kanaal_komt_er_niet_door(self):
        """#microcaps-calls-vip is een ANDER kanaal."""
        mag, _ = filters.kanaal_toegestaan("#microcaps-calls-vip (Alpha)", "", self.KANALEN)
        self.assertFalse(mag)

    def test_zonder_kanaallijst_gaat_er_niets_door(self):
        mag, reden = filters.kanaal_toegestaan("#microcaps-calls (Alpha)", "", [])
        self.assertFalse(mag)
        self.assertIn("geen kanaalfilter", reden)

    def test_hekje_mag_wel_of_niet(self):
        for patroon in ("microcaps-calls", "#microcaps-calls"):
            with self.subTest(patroon=patroon):
                mag, _ = filters.kanaal_toegestaan("#microcaps-calls (Alpha)", "", [patroon])
                self.assertTrue(mag)

    def test_bevat_pakt_de_hele_server(self):
        mag, _ = filters.kanaal_toegestaan("#willekeurig (Alpha Group)", "", ["bevat:Alpha Group"])
        self.assertTrue(mag)

    def test_eigen_zoekpatroon(self):
        mag, _ = filters.kanaal_toegestaan("#alpha-calls (X)", "", [r"re:#(calls|alpha)"])
        self.assertTrue(mag)

    def test_kapot_zoekpatroon_laat_de_bot_niet_crashen(self):
        mag, _ = filters.kanaal_toegestaan("#calls (X)", "", ["re:[onafgemaakt"])
        self.assertFalse(mag)

    def test_dm_mag_wel_als_je_dat_instelt(self):
        mag, _ = filters.kanaal_toegestaan("Sander", "", ["bevat:Sander"], sta_dm_toe=True)
        self.assertTrue(mag)

    def test_rommel_maakt_niets_stuk(self):
        for titel in ("", None, "#", "()", "###", "a" * 5000):
            with self.subTest(titel=repr(titel)[:20]):
                mag, reden = filters.kanaal_toegestaan(titel, None, self.KANALEN)
                self.assertIsInstance(mag, bool)
                self.assertIsInstance(reden, str)


class TestKanaalnaam(unittest.TestCase):
    def test_naam_uit_titel(self):
        self.assertEqual("calls", filters.kanaal_uit_titel("#calls (Server)"))
        self.assertEqual("", filters.kanaal_uit_titel("Sander"))

    def test_privebericht_herkennen(self):
        self.assertTrue(filters.is_privebericht("Sander"))
        self.assertFalse(filters.is_privebericht("#calls (Server)"))


if __name__ == "__main__":
    unittest.main()
