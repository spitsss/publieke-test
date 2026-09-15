"""
Tests voor de gedeelde toestand.

De belangrijkste eis: het wegschrijven van status mag NOOIT een foutmelding
omhoog gooien. De hele sniper viel ooit uit door een schrijffout in een
informatiebestandje.
"""
import json
import tempfile
import threading
import unittest
from pathlib import Path

import hulp  # noqa: F401

from staat import GEKOCHT, ONBEKEND, Staat


class Basis(unittest.TestCase):
    def setUp(self):
        self.map = Path(tempfile.mkdtemp())
        self.staat = Staat(self.map)


class TestStatus(Basis):
    def test_lezen_van_een_lege_map(self):
        self.assertEqual({}, self.staat.lees())

    def test_schrijven_en_lezen(self):
        self.assertTrue(self.staat.schrijf({"a": 1}))
        self.assertEqual(1, self.staat.lees()["a"])

    def test_bijwerken_laat_de_rest_staan(self):
        self.staat.schrijf({"a": 1, "b": 2})
        self.staat.werk_bij(b=3)
        gegevens = self.staat.lees()
        self.assertEqual(1, gegevens["a"])
        self.assertEqual(3, gegevens["b"])

    def test_kapot_statusbestand_geeft_geen_crash(self):
        (self.map / "status.json").write_text("{dit is geen json", encoding="utf-8")
        self.assertEqual({}, self.staat.lees())

    def test_onwegschrijfbare_waarde_gooit_niets_omhoog(self):
        class Raar:
            pass
        # default=str vangt dit op; het mag in geen geval een crash geven.
        self.assertIsInstance(self.staat.schrijf({"x": Raar()}), bool)

    def test_hartslag(self):
        self.staat.hartslag("sniper", {"rec_id": 5})
        self.assertLess(self.staat.hartslag_leeftijd("sniper"), 5)
        self.assertIsNone(self.staat.hartslag_leeftijd("bestaat-niet"))

    def test_veel_draden_tegelijk(self):
        """Het dashboard, de bediening en de waakhond schrijven door elkaar."""
        def werk(nummer):
            for _ in range(20):
                self.staat.hartslag(f"draad{nummer}")

        draden = [threading.Thread(target=werk, args=(n,)) for n in range(5)]
        for draad in draden:
            draad.start()
        for draad in draden:
            draad.join()
        # Het bestand moet nog steeds leesbare JSON zijn.
        json.loads((self.map / "status.json").read_text(encoding="utf-8"))


class TestVerstuurd(Basis):
    ADRES = "0x6b175474e89094c44da98b954eedeac495271d0f"

    def test_onthouden_zodat_hij_niet_twee_keer_koopt(self):
        self.assertFalse(self.staat.is_verstuurd(self.ADRES))
        self.staat.noteer_verstuurd(self.ADRES, "test")
        self.assertTrue(self.staat.is_verstuurd(self.ADRES))

    def test_blijft_na_herstart(self):
        self.staat.noteer_verstuurd(self.ADRES)
        self.assertTrue(Staat(self.map).is_verstuurd(self.ADRES))

    def test_twee_keer_noteren_geeft_een_regel(self):
        self.staat.noteer_verstuurd(self.ADRES)
        self.staat.noteer_verstuurd(self.ADRES)
        regels = (self.map / "verstuurd.txt").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(1, len(regels))

    def test_vergeten(self):
        self.staat.noteer_verstuurd(self.ADRES)
        self.assertTrue(self.staat.vergeet_verstuurd(self.ADRES))
        self.assertFalse(self.staat.is_verstuurd(self.ADRES))
        self.assertFalse(self.staat.vergeet_verstuurd("bestaat-niet"))

    def test_leeg_adres_wordt_genegeerd(self):
        self.staat.noteer_verstuurd("")
        self.assertFalse((self.map / "verstuurd.txt").exists())


class TestHandelsboek(Basis):
    def test_regels_bijschrijven_en_terugkrijgen(self):
        self.staat.noteer_handel({"adres": "a", "resultaat": GEKOCHT})
        self.staat.noteer_handel({"adres": "b", "resultaat": ONBEKEND})
        regels = self.staat.lees_handel(10)
        self.assertEqual("b", regels[0]["adres"])  # nieuwste eerst

    def test_kapotte_regel_wordt_overgeslagen(self):
        self.staat.noteer_handel({"adres": "a", "resultaat": GEKOCHT})
        with open(self.map / "handel.jsonl", "a", encoding="utf-8") as bestand:
            bestand.write("dit is geen json\n")
        self.staat.noteer_handel({"adres": "c", "resultaat": GEKOCHT})
        self.assertEqual(["c", "a"], [r["adres"] for r in self.staat.lees_handel(10)])

    def test_tellen_per_resultaat(self):
        self.staat.noteer_handel({"resultaat": GEKOCHT})
        self.staat.noteer_handel({"resultaat": GEKOCHT})
        self.staat.noteer_handel({"resultaat": ONBEKEND})
        tellers = self.staat.tel_resultaten()
        self.assertEqual(2, tellers[GEKOCHT])
        self.assertEqual(1, tellers[ONBEKEND])


class TestOpdrachten(Basis):
    def test_klaarzetten_en_ophalen(self):
        self.staat.zet_opdracht({"soort": "verkoop", "adres": "a"})
        opdrachten = self.staat.neem_opdrachten()
        self.assertEqual(1, len(opdrachten))
        self.assertEqual("verkoop", opdrachten[0]["soort"])

    def test_een_opdracht_wordt_maar_een_keer_uitgevoerd(self):
        """Twee keer verkopen kost geld."""
        self.staat.zet_opdracht({"soort": "verkoop", "adres": "a"})
        self.staat.neem_opdrachten()
        self.assertEqual([], self.staat.neem_opdrachten())

    def test_zonder_bestand_geen_crash(self):
        self.assertEqual([], self.staat.neem_opdrachten())


if __name__ == "__main__":
    unittest.main()
