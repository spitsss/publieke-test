"""
Tests voor het inlezen van config.ini.

Twee dingen die eerder stukgingen:
 * een onzichtbaar BOM-teken vooraan laat configparser crashen
 * '#' als commentaarteken vreet een kanaalnaam als '#calls' op
"""
import tempfile
import unittest
from pathlib import Path

import hulp  # noqa: F401

from instellingen import InstellingFout, Instellingen

BASIS = """
[algemeen]
dryrun = ja

[filter]
kanalen =
    microcaps-calls
    bevat:Alpha Group
negeerwoorden = rug, scam

[chains]
basedbot_chain = solana

[telegram]
api_id =
api_hash =

[handel]
bedrag = 0,05
"""


def schrijf(inhoud: str, codering: str = "utf-8") -> Path:
    pad = Path(tempfile.mktemp(suffix=".ini"))
    pad.write_text(inhoud, encoding=codering)
    return pad


class TestInlezen(unittest.TestCase):
    def test_gewoon_inlezen(self):
        opties = Instellingen(schrijf(BASIS))
        self.assertTrue(opties.dryrun)
        self.assertEqual(["microcaps-calls", "bevat:Alpha Group"], opties.kanalen)
        self.assertEqual(["rug", "scam"], opties.negeerwoorden)

    def test_bom_teken_laat_het_niet_crashen(self):
        """Een teksteditor zet er soms een onzichtbaar teken voor."""
        opties = Instellingen(schrijf(BASIS, "utf-8-sig"))
        self.assertTrue(opties.dryrun)

    def test_lege_waarde_gebruikt_de_standaard(self):
        opties = Instellingen(schrijf(BASIS))
        self.assertEqual(0, opties.api_id)          # leeg, geen crash
        self.assertEqual(150, opties.poll_ms)       # niet opgegeven

    def test_komma_als_decimaalteken(self):
        self.assertEqual(0.05, Instellingen(schrijf(BASIS)).bedrag)

    def test_bestand_dat_niet_bestaat(self):
        with self.assertRaises(InstellingFout) as gevangen:
            Instellingen("/bestaat/niet/config.ini")
        self.assertIn("config.ini", str(gevangen.exception))

    def test_kapot_bestand_geeft_uitleg(self):
        with self.assertRaises(InstellingFout):
            Instellingen(schrijf("dit is geen ini-bestand\nzomaar tekst"))

    def test_ja_en_nee_in_allerlei_vormen(self):
        for waarde, verwacht in (
            ("ja", True), ("JA", True), ("aan", True), ("true", True), ("1", True),
            ("nee", False), ("uit", False), ("false", False), ("0", False), ("onzin", False),
        ):
            with self.subTest(waarde=waarde):
                opties = Instellingen(schrijf(f"[algemeen]\ndryrun = {waarde}\n"))
                self.assertEqual(verwacht, opties.dryrun)

    def test_geen_getal_waar_een_getal_hoort(self):
        opties = Instellingen(schrijf("[algemeen]\ninstantie_poort = abc\n"))
        with self.assertRaises(InstellingFout) as gevangen:
            _ = opties.instantie_poort
        self.assertIn("heel getal", str(gevangen.exception))

    def test_poll_ms_wordt_begrensd(self):
        self.assertEqual(50, Instellingen(schrijf("[meldingen]\npoll_ms = 1\n")).poll_ms)
        self.assertEqual(2000, Instellingen(schrijf("[meldingen]\npoll_ms = 999999\n")).poll_ms)

    def test_verkeerde_chaincontrole(self):
        opties = Instellingen(schrijf("[chains]\nchaincontrole = streng\n"))
        with self.assertRaises(InstellingFout):
            _ = opties.chaincontrole

    def test_slim_is_de_standaard(self):
        self.assertEqual("slim", Instellingen(schrijf("[chains]\nbasedbot_chain=solana\n")).chaincontrole)

    def test_dryrun_staat_standaard_aan(self):
        """Als er niets staat, wordt er niets gekocht."""
        self.assertTrue(Instellingen(schrijf("[algemeen]\n")).dryrun)

    def test_zelf_verkopen_staat_standaard_uit(self):
        self.assertFalse(Instellingen(schrijf("[handel]\n")).zelf_verkopen)


class TestControle(unittest.TestCase):
    def test_leeg_kanaalfilter_wordt_afgekeurd(self):
        opties = Instellingen(schrijf("[chains]\nbasedbot_chain = solana\n"))
        problemen = " ".join(opties.controleer_voor_sniper())
        self.assertIn("kanaalfilter", problemen)

    def test_ontbrekende_telegramsleutels_worden_afgekeurd(self):
        opties = Instellingen(schrijf(BASIS))
        self.assertIn("api_id", " ".join(opties.controleer_voor_sniper()))

    def test_live_zonder_bedrag_wordt_afgekeurd(self):
        opties = Instellingen(schrijf(
            "[algemeen]\ndryrun = nee\n[chains]\nbasedbot_chain=solana\n"
            "[filter]\nkanalen = calls\n[telegram]\napi_id=1\napi_hash=x\n[handel]\nbedrag = 0\n"
        ))
        self.assertIn("bedrag is 0", " ".join(opties.controleer_voor_sniper()))

    def test_alles_ingevuld_geeft_geen_problemen(self):
        opties = Instellingen(schrijf(
            "[algemeen]\ndryrun = ja\n[chains]\nbasedbot_chain=solana\n"
            "[filter]\nkanalen = calls\n[telegram]\napi_id=1\napi_hash=x\n[handel]\nbedrag=0.05\n"
        ))
        self.assertEqual([], opties.controleer_voor_sniper())


if __name__ == "__main__":
    unittest.main()
