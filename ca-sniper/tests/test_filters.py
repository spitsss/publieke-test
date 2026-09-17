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


class TestEchteDiscordTitels(unittest.TestCase):
    """
    Deze titels komen LETTERLIJK van een echte Mac. Ik had de vorm verkeerd
    geraden: ik dacht "#kanaal (Server)", maar het is
    "Afzender (#emoji|kanaalnaam, Servernaam)". Wie hier alleen "#iets" uit
    plukt, krijgt "💵|algemene-chat," terug — mét emoji en komma — en matcht
    dus nooit. Precies zo'n stille fout.
    """

    ALGEMEEN = "KOOBY (#\U0001F4B5|algemene-chat, Algemeen)"
    KOFFIE = "Thexrpjunk (#☕|koffiehuis\U0001F51E, \U0001F525 Lifestyle & Koffiehuis)"
    ANDER = "W8rldisyours01 (#\U0001F4B5|algemene-chat, Algemeen)"
    TESTMELDING = "#microcaps-calls (Test)"
    DM = "Peter"

    def test_de_kanaalnaam_wordt_er_schoon_uitgehaald(self):
        self.assertEqual("algemene-chat", filters.kanaal_uit_titel(self.ALGEMEEN))
        self.assertEqual("algemene-chat", filters.kanaal_uit_titel(self.ANDER))
        self.assertEqual("microcaps-calls", filters.kanaal_uit_titel(self.TESTMELDING))

    def test_geen_komma_en_geen_emoji_meer_in_de_naam(self):
        naam = filters.kanaal_uit_titel(self.ALGEMEEN)
        self.assertNotIn(",", naam)
        self.assertNotIn("|", naam)
        self.assertNotIn("\U0001F4B5", naam)

    def test_een_dm_geeft_geen_kanaalnaam(self):
        self.assertEqual("", filters.kanaal_uit_titel(self.DM))
        self.assertTrue(filters.is_privebericht(self.DM))

    def test_het_juiste_kanaal_komt_door(self):
        mag, reden = filters.kanaal_toegestaan(self.ALGEMEEN, "", ["algemene-chat"])
        self.assertTrue(mag, reden)

    def test_een_ander_kanaal_van_dezelfde_server_niet(self):
        mag, _ = filters.kanaal_toegestaan(self.KOFFIE, "", ["algemene-chat"])
        self.assertFalse(mag)

    def test_een_dm_niet(self):
        mag, _ = filters.kanaal_toegestaan(self.DM, "", ["algemene-chat"])
        self.assertFalse(mag)

    def test_emoji_in_de_kanaalnaam_hoef_je_niet_te_typen(self):
        """Het kanaal heet 'koffiehuis🔞'; 'koffiehuis' moet genoeg zijn."""
        mag, reden = filters.kanaal_toegestaan(self.KOFFIE, "", ["koffiehuis"])
        self.assertTrue(mag, reden)

    def test_maar_een_andere_naam_matcht_nog_steeds_niet(self):
        mag, _ = filters.kanaal_toegestaan(self.KOFFIE, "", ["koffie"])
        self.assertFalse(mag, "'koffie' is niet hetzelfde kanaal als 'koffiehuis'")

    def test_de_afzender_maakt_niet_uit(self):
        """Dezelfde kanaalnaam, andere afzender: allebei door."""
        for titel in (self.ALGEMEEN, self.ANDER):
            with self.subTest(titel=titel):
                mag, _ = filters.kanaal_toegestaan(titel, "", ["algemene-chat"])
                self.assertTrue(mag)
