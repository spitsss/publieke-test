"""
Tests voor de bedieningsbot.

De eis uit de opdracht: elk commando, elke knop en rommelige invoer mag NOOIT
crashen, en elk bericht blijft onder de 4096 tekens.
"""
import tempfile
import unittest
from pathlib import Path

import hulp  # noqa: F401

import telegrambediening
from instellingen import Instellingen
from staat import Staat

CONFIG = """
[algemeen]
dryrun = ja
logniveau = ERROR

[filter]
kanalen = calls

[chains]
basedbot_chain = solana

[telegram]
api_id = 1
api_hash = abc
basedbot = @BasedBot

[handel]
bedrag = 0.05
valuta = SOL
zelf_verkopen = nee

[bediening]
bot_token = 123:abc
toegestane_id = 42
"""

ADRES = "0x6b175474e89094c44da98b954eedeac495271d0f"


class Basis(unittest.TestCase):
    def setUp(self):
        self.map = Path(tempfile.mkdtemp())
        pad = self.map / "config.ini"
        pad.write_text(CONFIG, encoding="utf-8")
        self.opties = Instellingen(pad)
        self.staat = Staat(self.map)
        import logging

        stil = logging.getLogger("stil")
        stil.disabled = True  # geweigerde toegang hoeft niet in de testuitvoer
        self.bediening = telegrambediening.Bediening(
            self.opties, stil, self.staat
        )

    def antwoord(self, tekst):
        uitkomst, menu = self.bediening.verwerk(tekst)
        # Deze twee eisen gelden voor ELK antwoord.
        self.assertIsInstance(uitkomst, str)
        self.assertGreater(len(uitkomst), 0)
        for stuk in telegrambediening.verdeel(uitkomst):
            self.assertLess(len(stuk), 4096, "Telegram weigert berichten boven 4096 tekens")
        self.assertIsInstance(menu, list)
        return uitkomst


class TestAlleCommandos(Basis):
    def test_elk_commando_geeft_antwoord(self):
        for commando in (
            "/start", "/help", "/status", "/handel", "/log", "/quickbuy",
            "/pauze", "/hervat", "/dryrun", "/adressen", "/vergeet", "/verkoop",
        ):
            with self.subTest(commando=commando):
                self.antwoord(commando)

    def test_hoofdletters_maken_niet_uit(self):
        self.assertEqual(self.antwoord("/STATUS"), self.antwoord("/status"))

    def test_met_botnaam_erachter(self):
        self.antwoord("/status@mijnsniperbot")

    def test_zonder_schuine_streep(self):
        self.antwoord("status")


class TestRommeligeInvoer(Basis):
    def test_niets_crasht(self):
        rommel = [
            "", " ", "/", "//", "///", "/log abc", "/log -5", "/log 99999",
            "/handel nee", "/dryrun misschien", "/vergeet", "/verkoop",
            "/onzin", "/" + "a" * 500, "\n", "\t\t", "🚀🚀🚀",
            "/log 1 2 3 4 5", "/status extra argumenten", "SELECT * FROM record",
            "../../etc/passwd", "%s%s%s", "{}", "null", "None", "-1",
            "/verkoop " + "x" * 200, "/vergeet " + ADRES,
        ]
        for tekst in rommel:
            with self.subTest(tekst=repr(tekst)[:30]):
                self.antwoord(tekst)

    def test_log_met_onzin_pakt_de_standaard(self):
        uitkomst = self.antwoord("/log abc")
        self.assertIn("geen getal", uitkomst)

    def test_log_wordt_afgetopt(self):
        self.antwoord("/log 100000")

    def test_onbekend_commando_legt_uit_wat_wel_kan(self):
        uitkomst = self.antwoord("/verzonnen")
        self.assertIn("ken ik niet", uitkomst)
        self.assertIn("/status", uitkomst)


class TestKnoppen(Basis):
    def test_elke_knop_uit_het_menu_werkt(self):
        """Elke knop stuurt zijn callback_data terug als commando."""
        for rij in telegrambediening.HOOFDMENU:
            for tekst, data in rij:
                with self.subTest(knop=tekst):
                    self.assertTrue(data.startswith("cmd:"), f"{tekst} mist het voorvoegsel cmd:")
                    opdracht = data.split(":", 1)[1]
                    self.antwoord("/" + opdracht)


class TestSchakelaars(Basis):
    def test_pauze_en_hervat(self):
        self.antwoord("/pauze")
        self.assertTrue(self.staat.lees()["gepauzeerd"])
        self.antwoord("/hervat")
        self.assertFalse(self.staat.lees()["gepauzeerd"])

    def test_dryrun_omzetten(self):
        self.antwoord("/dryrun uit")
        self.assertFalse(self.staat.lees()["dryrun"])
        self.antwoord("/dryrun aan")
        self.assertTrue(self.staat.lees()["dryrun"])

    def test_dryrun_uit_waarschuwt_over_echt_geld(self):
        uitkomst = self.antwoord("/dryrun uit")
        self.assertIn("ECHT geld", uitkomst)

    def test_dryrun_met_onzin_verandert_niets(self):
        self.antwoord("/dryrun aan")
        self.antwoord("/dryrun misschien")
        self.assertTrue(self.staat.lees()["dryrun"])


class TestVerkoopOpdracht(Basis):
    def test_verkopen_is_standaard_uit(self):
        uitkomst = self.antwoord(f"/verkoop {ADRES}")
        self.assertIn("staat uit", uitkomst)
        self.assertEqual([], self.staat.neem_opdrachten())

    def test_met_verkopen_aan_komt_er_een_opdracht(self):
        self.opties.zet("handel", "zelf_verkopen", "ja")
        self.antwoord(f"/verkoop {ADRES} initials")
        opdrachten = self.staat.neem_opdrachten()
        self.assertEqual(1, len(opdrachten))
        self.assertEqual(ADRES, opdrachten[0]["adres"])
        self.assertEqual("initials", opdrachten[0]["deel"])

    def test_een_ongeldig_adres_wordt_geweigerd(self):
        self.opties.zet("handel", "zelf_verkopen", "ja")
        uitkomst = self.antwoord("/verkoop nietbestaandadres")
        self.assertIn("niet uit als een geldig adres", uitkomst)
        self.assertEqual([], self.staat.neem_opdrachten())

    def test_een_raar_deel_wordt_geweigerd(self):
        self.opties.zet("handel", "zelf_verkopen", "ja")
        self.antwoord(f"/verkoop {ADRES} 37")
        self.assertEqual([], self.staat.neem_opdrachten())


class TestVerstuurdeAdressen(Basis):
    def test_vergeten(self):
        self.staat.noteer_verstuurd(ADRES)
        uitkomst = self.antwoord(f"/vergeet {ADRES}")
        self.assertIn("vergeten", uitkomst)
        self.assertFalse(self.staat.is_verstuurd(ADRES))

    def test_vergeten_van_iets_dat_er_niet_staat(self):
        self.assertIn("stond niet", self.antwoord(f"/vergeet {ADRES}"))


class TestOpknippen(unittest.TestCase):
    def test_kort_bericht_blijft_heel(self):
        self.assertEqual(["hallo"], telegrambediening.verdeel("hallo"))

    def test_lang_bericht_wordt_opgeknipt(self):
        stukken = telegrambediening.verdeel("regel\n" * 5000)
        self.assertGreater(len(stukken), 1)
        for stuk in stukken:
            self.assertLessEqual(len(stuk), telegrambediening.MAXIMALE_LENGTE)

    def test_knipt_bij_voorkeur_op_een_regelovergang(self):
        stukken = telegrambediening.verdeel("a" * 100 + "\n" + "b" * 4000, maximaal=200)
        self.assertTrue(stukken[0].endswith("a"))

    def test_een_lange_regel_zonder_overgang(self):
        stukken = telegrambediening.verdeel("x" * 10000, maximaal=1000)
        self.assertTrue(all(len(s) <= 1000 for s in stukken))

    def test_lege_tekst(self):
        self.assertEqual(["(leeg)"], telegrambediening.verdeel(""))


class TestToegang(Basis):
    def test_alleen_de_eigenaar_mag(self):
        self.assertTrue(self.bediening._mag(42, "bericht"))
        self.assertTrue(self.bediening._mag("42", "bericht"))
        for vreemde in (43, "43", None, "", "abc", 0):
            with self.subTest(vreemde=vreemde):
                self.assertFalse(self.bediening._mag(vreemde, "bericht"))


if __name__ == "__main__":
    unittest.main()
