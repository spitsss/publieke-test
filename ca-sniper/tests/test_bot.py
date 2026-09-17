"""
Tests voor de sniper zelf: de hele keten van melding tot 'zou versturen'.

Er gaat hier niets naar Telegram en er wordt niets gekocht: de brug is
nagemaakt en dryrun staat aan.
"""
import logging
import tempfile
import unittest
from pathlib import Path

import hulp  # noqa: F401

import bot
from instellingen import Instellingen
from meldingen import Melding
from staat import DRYRUN, Staat

MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
MINT2 = "So11111111111111111111111111111111111111112"
EVM = "0x6b175474e89094c44da98b954eedeac495271d0f"

CONFIG = """
[algemeen]
dryrun = ja
logniveau = ERROR

[meldingen]
bundle_ids = com.hnc.Discord

[filter]
kanalen = microcaps-calls
negeerwoorden = rug, scam
meerdere_adressen = weiger

[chains]
basedbot_chain = solana
chaincontrole = slim

[telegram]
api_id = 1
api_hash = x
basedbot = @BasedBot

[handel]
bedrag = 0.05
valuta = SOL
zelf_verkopen = nee
"""


def melding(titel, body, rec_id=1):
    return Melding(rec_id=rec_id, bundle="com.hnc.Discord", titel=titel, body=body)


class Basis(unittest.TestCase):
    def setUp(self):
        self.map = Path(tempfile.mkdtemp())
        pad = self.map / "config.ini"
        pad.write_text(CONFIG, encoding="utf-8")
        self.opties = Instellingen(pad)
        self.staat = Staat(self.map)
        stil = logging.getLogger("stil-bot")
        stil.disabled = True
        self.sniper = bot.Sniper(self.opties, stil, self.staat)

    def werk(self):
        """Wat er in de wachtrij is gezet voor de werkdraad."""
        uit = []
        while not self.sniper.werk.empty():
            uit.append(self.sniper.werk.get_nowait())
        return uit


class TestFilteren(Basis):
    def test_call_uit_het_juiste_kanaal_komt_door(self):
        self.sniper._bekijk(melding("#microcaps-calls (Alpha)", f"CA: {MINT}"))
        opdrachten = self.werk()
        self.assertEqual(1, len(opdrachten))
        self.assertEqual("koop", opdrachten[0][0])
        self.assertEqual(MINT, opdrachten[0][2].adres)

    def test_ander_kanaal_komt_er_niet_door(self):
        self.sniper._bekijk(melding("#general (Alpha)", f"CA: {MINT}"))
        self.assertEqual([], self.werk())

    def test_privebericht_komt_er_niet_door(self):
        self.sniper._bekijk(melding("Sander", f"kijk: {MINT}"))
        self.assertEqual([], self.werk())

    def test_negeerwoord_houdt_hem_tegen(self):
        self.sniper._bekijk(melding("#microcaps-calls (Alpha)", f"dit is een rug {MINT}"))
        self.assertEqual([], self.werk())

    def test_negeerwoord_in_een_langer_woord_houdt_hem_niet_tegen(self):
        """'terug' bevat 'rug', maar is een ander woord."""
        self.sniper._bekijk(melding("#microcaps-calls (Alpha)", f"kijk terug: {MINT}"))
        self.assertEqual(1, len(self.werk()))

    def test_gepauzeerd_doet_niets(self):
        self.staat.werk_bij(gepauzeerd=True)
        self.sniper._bekijk(melding("#microcaps-calls (Alpha)", f"CA: {MINT}"))
        self.assertEqual([], self.werk())

    def test_melding_zonder_adres(self):
        self.sniper._bekijk(melding("#microcaps-calls (Alpha)", "gewoon gepraat"))
        self.assertEqual([], self.werk())


class TestEenAdresPerMelding(Basis):
    def test_twee_adressen_worden_geweigerd(self):
        self.sniper._bekijk(melding("#microcaps-calls (Alpha)", f"{MINT} en ook {MINT2}"))
        self.assertEqual([], self.werk(), "bij twee adressen weet je niet welke bedoeld wordt")

    def test_met_de_stand_eerste_pakt_hij_de_eerste(self):
        self.opties.zet("filter", "meerdere_adressen", "eerste")
        self.sniper._bekijk(melding("#microcaps-calls (Alpha)", f"{MINT} en ook {MINT2}"))
        opdrachten = self.werk()
        self.assertEqual(1, len(opdrachten))
        self.assertEqual(MINT, opdrachten[0][2].adres)


class TestNooitTweeKeer(Basis):
    def test_hetzelfde_adres_gaat_maar_een_keer_door(self):
        self.sniper._bekijk(melding("#microcaps-calls (Alpha)", f"CA: {MINT}", 1))
        self.assertEqual(1, len(self.werk()))
        self.sniper._bekijk(melding("#microcaps-calls (Alpha)", f"nog eens {MINT}", 2))
        self.assertEqual([], self.werk())

    def test_blijft_zo_na_een_herstart(self):
        self.sniper._bekijk(melding("#microcaps-calls (Alpha)", f"CA: {MINT}", 1))
        self.werk()
        nieuwe = bot.Sniper(self.opties, self.sniper.log, Staat(self.map))
        nieuwe._bekijk(melding("#microcaps-calls (Alpha)", f"CA: {MINT}", 2))
        self.assertTrue(nieuwe.werk.empty())


class TestPool(Basis):
    def test_een_poollink_gaat_naar_de_werkdraad_om_omgezet_te_worden(self):
        self.sniper._bekijk(
            melding("#microcaps-calls (Alpha)",
                    "https://dexscreener.com/solana/7xKXtg2CW3dYbPkMaQ2xhWMvLWtUC9wPmRfr5pRRNkBz")
        )
        opdrachten = self.werk()
        self.assertEqual(1, len(opdrachten))
        self.assertEqual("pool", opdrachten[0][0], "een pooladres mag nooit als token gekocht worden")


class TestDryrun(Basis):
    class NepBrug:
        def __init__(self):
            self.verstuurd = []

        def stuur_en_lees(self, tekst, seconden=None):
            self.verstuurd.append(tekst)
            raise AssertionError("in dryrun mag er NIETS verstuurd worden")

    def test_dryrun_stuurt_niets(self):
        self.sniper.brug = self.NepBrug()
        vondst = type("V", (), {"adres": MINT, "soort": "solana", "bron": "tekst"})()
        self.sniper._koop(melding("#microcaps-calls (A)", "x"), vondst)
        self.assertEqual([], self.sniper.brug.verstuurd)
        regels = self.staat.lees_handel(5)
        self.assertEqual(DRYRUN, regels[0]["resultaat"])

    def test_de_bediening_kan_dryrun_omzetten(self):
        self.assertTrue(self.sniper._dryrun_nu())
        self.staat.werk_bij(dryrun=False)
        self.assertFalse(self.sniper._dryrun_nu())

    def test_bij_twijfel_staat_dryrun_aan(self):
        self.staat.werk_bij(dryrun="onzin")
        self.assertTrue(self.sniper._dryrun_nu())


class TestChaincontrole(Basis):
    def test_een_evm_adres_wordt_geblokkeerd_als_basedbot_op_solana_staat(self):
        """BasedBot staat hier op solana; een 0x-adres hoort daar niet."""
        vondst = type("V", (), {"adres": EVM, "soort": "evm", "bron": "tekst"})()
        self.sniper._koop(melding("#microcaps-calls (A)", "x"), vondst)
        regels = self.staat.lees_handel(5)
        self.assertEqual("geblokkeerd", regels[0]["resultaat"])


class TestOpdrachten(Basis):
    def test_onbekende_opdracht_wordt_overgeslagen(self):
        self.staat.zet_opdracht({"soort": "iets-raars"})
        self.sniper._doe_opdrachten()  # mag niet crashen

    def test_verkoopopdracht_zonder_verbinding_crasht_niet(self):
        self.staat.zet_opdracht({"soort": "verkoop", "adres": MINT, "deel": "initials"})
        self.sniper.brug = None
        self.sniper._doe_opdrachten()


if __name__ == "__main__":
    unittest.main()


class TestHeleKeten(unittest.TestCase):
    """
    Van een echte melding in een nagemaakte Berichtencentrum-database tot
    'deze zou ik versturen'. Dit is de keten in het klein.
    """

    def setUp(self):
        import test_meldingen as nep

        self.map = Path(tempfile.mkdtemp())
        (self.map / "config.ini").write_text(CONFIG, encoding="utf-8")
        self.opties = Instellingen(self.map / "config.ini")
        self.staat = Staat(self.map)

        self.db = str(self.map / "meldingen.db")
        nep.maak_database(self.db)
        self.voeg = nep.voeg_melding_toe

        stil = logging.getLogger("stil-keten")
        stil.disabled = True
        self.sniper = bot.Sniper(self.opties, stil, self.staat)

        from meldingen import Meldingenlezer

        self.voeg(self.db, 1, 1, "#microcaps-calls (Alpha)", "", "oude call, van voor het opstarten")
        self.lezer = Meldingenlezer(self.db, ["com.hnc.Discord"])
        self.sniper.lezer = self.lezer
        # Zo start de sniper: alles wat er al staat wordt genegeerd.
        self.sniper.laatste_rec_id = self.lezer.hoogste_rec_id()

    def ronde(self):
        """Eén rondje van de hoofdlus."""
        for melding_ in self.lezer.nieuwe_meldingen(self.sniper.laatste_rec_id):
            self.sniper.laatste_rec_id = max(self.sniper.laatste_rec_id, melding_.rec_id)
            self.sniper._bekijk(melding_)
        uit = []
        while not self.sniper.werk.empty():
            uit.append(self.sniper.werk.get_nowait())
        return uit

    def test_oude_meldingen_worden_bij_het_opstarten_niet_gekocht(self):
        self.assertEqual([], self.ronde())

    def test_een_nieuwe_call_gaat_de_keten_door(self):
        self.voeg(self.db, 2, 1, "#microcaps-calls (Alpha)", "Alpha", f"🚀 nieuwe call CA: {MINT}")
        opdrachten = self.ronde()
        self.assertEqual(1, len(opdrachten))
        self.assertEqual(MINT, opdrachten[0][2].adres)

    def test_een_melding_van_een_andere_app_telt_niet_mee(self):
        self.voeg(self.db, 2, 2, "#microcaps-calls (Alpha)", "", f"CA: {MINT}")
        self.assertEqual([], self.ronde())

    def test_een_melding_uit_een_ander_kanaal_telt_niet_mee(self):
        self.voeg(self.db, 2, 1, "#general (Alpha)", "", f"CA: {MINT}")
        self.assertEqual([], self.ronde())

    def test_meerdere_meldingen_achter_elkaar(self):
        self.voeg(self.db, 2, 1, "#microcaps-calls (Alpha)", "", f"CA: {MINT}")
        self.voeg(self.db, 3, 1, "#general (Alpha)", "", f"CA: {MINT2}")
        self.voeg(self.db, 4, 1, "#microcaps-calls (Alpha)", "", f"CA: {MINT2}")
        adressen = [o[2].adres for o in self.ronde()]
        self.assertEqual([MINT, MINT2], adressen)


class TestExtraApp(Basis):
    """
    Met --extra-app kun je de keten testen met een zelf afgevuurde melding,
    zonder config.ini aan te passen. Dat laatste is met opzet: een instelling
    die je moet terugzetten, vergeet je een keer.
    """

    def test_extra_app_komt_erbij_en_niet_in_plaats_van(self):
        import test_meldingen as nep
        from meldingen import Meldingenlezer

        db = str(self.map / "m.db")
        nep.maak_database(db)
        nep.voeg_melding_toe(db, 1, 1, "#microcaps-calls (A)", "", f"CA: {MINT}")
        nep.voeg_melding_toe(db, 2, 2, "#microcaps-calls (Test)", "", f"CA: {MINT2}")

        sniper = bot.Sniper(
            self.opties, self.sniper.log, self.staat,
            extra_apps=["com.apple.ScriptEditor2"],
        )
        lezer = Meldingenlezer(db, list(self.opties.bundle_ids) + sniper.extra_apps)
        # Discord EN Scripteditor moeten nu allebei doorkomen.
        self.assertEqual([1, 2], [m.rec_id for m in lezer.nieuwe_meldingen(0)])

    def test_zonder_extra_app_alleen_discord(self):
        import test_meldingen as nep
        from meldingen import Meldingenlezer

        db = str(self.map / "m2.db")
        nep.maak_database(db)
        nep.voeg_melding_toe(db, 1, 1, "#microcaps-calls (A)", "", f"CA: {MINT}")
        nep.voeg_melding_toe(db, 2, 2, "#microcaps-calls (Test)", "", f"CA: {MINT2}")

        sniper = bot.Sniper(self.opties, self.sniper.log, self.staat)
        self.assertEqual([], sniper.extra_apps)
        lezer = Meldingenlezer(db, list(self.opties.bundle_ids))
        self.assertEqual([1], [m.rec_id for m in lezer.nieuwe_meldingen(0)])

    def test_lege_en_rommelige_waarden_worden_genegeerd(self):
        sniper = bot.Sniper(self.opties, self.sniper.log, self.staat, extra_apps=["", "  ", None])
        self.assertEqual([], sniper.extra_apps)
