"""
Tests voor het herkennen van verkoopsignalen.

Het onderscheid dat ertoe doet: een OPDRACHT vuurt, UITLEG en een VRAAG niet.
"""
import unittest

import hulp  # noqa: F401

import exits


class TestOpdrachten(unittest.TestCase):
    def test_de_opdracht_uit_de_bouwopdracht(self):
        signaal = exits.zoek_exit("haal een deel of je initials eruit")
        self.assertTrue(signaal)
        self.assertEqual("initials", signaal.soort)
        self.assertTrue(signaal.zeker)

    def test_percentage(self):
        signaal = exits.zoek_exit("verkoop 50% hier jongens")
        self.assertTrue(signaal)
        self.assertEqual("50", signaal.deel)

    def test_alles(self):
        signaal = exits.zoek_exit("sell all now")
        self.assertTrue(signaal)
        self.assertEqual("100", signaal.deel)

    def test_engels(self):
        self.assertTrue(exits.zoek_exit("take initials out"))
        self.assertTrue(exits.zoek_exit("Take profits boys"))


class TestGeenOpdracht(unittest.TestCase):
    def test_uitleg_vuurt_niet(self):
        """'Initials betekent je inleg!' is uitleg, geen opdracht."""
        self.assertFalse(exits.zoek_exit("Initials betekent je inleg!"))
        self.assertFalse(exits.zoek_exit("Initials means your entry, fyi"))

    def test_vraag_vuurt_niet(self):
        self.assertFalse(exits.zoek_exit("Wanneer moeten we winst nemen?"))
        self.assertFalse(exits.zoek_exit("when should we take profit"))
        self.assertFalse(exits.zoek_exit("Moeten we verkopen?"))

    def test_ontkenning_vuurt_niet(self):
        self.assertFalse(exits.zoek_exit("niet verkopen, we houden vast"))
        self.assertFalse(exits.zoek_exit("don't sell yet"))

    def test_gewoon_gepraat_vuurt_niet(self):
        for tekst in (
            "dit token is een 10x geworden",
            "mooie chart",
            "",
            "wat een brug naar de volgende call",
            "de liquidity is gelockt",
        ):
            with self.subTest(tekst=tekst):
                self.assertFalse(exits.zoek_exit(tekst))


class TestOnzeker(unittest.TestCase):
    def test_werkwoord_zonder_doelwit_is_onzeker(self):
        """
        'Haal ze er nu uit' is wel een signaal, maar hoeveel? Onbekend.
        Dan melden we het, en verkopen we er niet blind op.
        """
        signaal = exits.zoek_exit("Initials betekent je inleg! Haal ze er nu uit.")
        self.assertTrue(signaal)
        self.assertFalse(signaal.zeker)

    def test_uitleg_eerst_dan_opdracht(self):
        signaal = exits.zoek_exit("Initials betekent je inleg. Verkoop nu 50%.")
        self.assertTrue(signaal)
        self.assertTrue(signaal.zeker)
        self.assertEqual("50", signaal.deel)


class TestRommel(unittest.TestCase):
    def test_rare_invoer_crasht_niet(self):
        for tekst in (None, "", " ", "?" * 100, "\n\n\n", "🚀" * 50, "a" * 10000):
            with self.subTest(tekst=repr(tekst)[:20]):
                self.assertIsInstance(exits.zoek_exit(tekst).gevonden, bool)


if __name__ == "__main__":
    unittest.main()
