"""
Tests voor de lezer van het macOS Berichtencentrum.

We bouwen hier een NAGEMAAKTE database met dezelfde opbouw en met ECHTE
binaire plists erin (plistlib maakt die op elk besturingssysteem). Daardoor
kunnen we de hele lezer testen zonder een Mac.

Wat we hier NIET kunnen testen: of Apple de tabellen op jouw macOS-versie
precies zo heeft. Daarvoor is 'python3 meldingen.py --diag' op de Mac zelf.
"""
import os
import plistlib
import sqlite3
import tempfile
import time
import unittest

import hulp  # noqa: F401

import meldingen


def maak_database(pad: str, met_app_tabel: bool = True) -> None:
    verbinding = sqlite3.connect(pad)
    if met_app_tabel:
        verbinding.execute("create table app (app_id integer primary key, identifier text)")
        verbinding.execute("insert into app values (1, 'com.hnc.Discord')")
        verbinding.execute("insert into app values (2, 'com.apple.ScriptEditor2')")
    verbinding.execute(
        "create table record (rec_id integer primary key, app_id integer, uuid blob, "
        "data blob, request_date real, delivered_date real, presented integer)"
    )
    verbinding.commit()
    verbinding.close()


def voeg_melding_toe(pad: str, rec_id: int, app_id: int, titl: str, subt: str, body: str) -> None:
    blob = plistlib.dumps(
        {"req": {"titl": titl, "subt": subt, "body": body}}, fmt=plistlib.FMT_BINARY
    )
    verbinding = sqlite3.connect(pad)
    verbinding.execute(
        "insert into record (rec_id, app_id, data, delivered_date, presented) values (?,?,?,?,1)",
        (rec_id, app_id, blob, time.time() - meldingen.APPLE_EPOCH_VERSCHIL),
    )
    verbinding.commit()
    verbinding.close()


class Basis(unittest.TestCase):
    def setUp(self):
        self.pad = tempfile.mktemp(suffix=".db")
        maak_database(self.pad)

    def tearDown(self):
        for achtervoegsel in ("", "-wal", "-shm"):
            try:
                os.unlink(self.pad + achtervoegsel)
            except OSError:
                pass


class TestUitpakken(Basis):
    def test_titel_ondertitel_en_tekst_komen_eruit(self):
        voeg_melding_toe(self.pad, 1, 1, "#calls (Alpha)", "Alpha", "CA: abc123")
        lezer = meldingen.Meldingenlezer(self.pad, ["com.hnc.Discord"])
        gevonden = lezer.nieuwe_meldingen(0)
        self.assertEqual(1, len(gevonden))
        self.assertEqual("#calls (Alpha)", gevonden[0].titel)
        self.assertEqual("Alpha", gevonden[0].ondertitel)
        self.assertEqual("CA: abc123", gevonden[0].body)
        self.assertEqual("com.hnc.Discord", gevonden[0].bundle)

    def test_emoji_in_de_tekst(self):
        """Memecoins heten dingen mét emoji. Dat mag nooit stukgaan."""
        voeg_melding_toe(self.pad, 1, 1, "#calls (Alpha)", "", "🚀 MOON🌙 CA: xyz")
        lezer = meldingen.Meldingenlezer(self.pad, ["com.hnc.Discord"])
        self.assertIn("🚀", lezer.nieuwe_meldingen(0)[0].body)

    def test_appletijd_wordt_unixtijd(self):
        voeg_melding_toe(self.pad, 1, 1, "t", "", "b")
        lezer = meldingen.Meldingenlezer(self.pad, ["com.hnc.Discord"])
        bezorgd = lezer.nieuwe_meldingen(0)[0].bezorgd_op
        self.assertAlmostEqual(time.time(), bezorgd, delta=5)

    def test_kapotte_blob_wordt_overgeslagen_zonder_crash(self):
        verbinding = sqlite3.connect(self.pad)
        verbinding.execute(
            "insert into record (rec_id, app_id, data, delivered_date) values (1,1,?,0)",
            (b"dit is geen plist",),
        )
        verbinding.commit()
        verbinding.close()
        lezer = meldingen.Meldingenlezer(self.pad, ["com.hnc.Discord"])
        gevonden = lezer.nieuwe_meldingen(0)
        self.assertEqual(1, len(gevonden))
        self.assertEqual("", gevonden[0].body)


class TestNieuweMeldingen(Basis):
    def test_alleen_wat_nieuwer_is_dan_het_laatst_geziene(self):
        for rec_id in (1, 2, 3):
            voeg_melding_toe(self.pad, rec_id, 1, "#calls (A)", "", f"bericht {rec_id}")
        lezer = meldingen.Meldingenlezer(self.pad, ["com.hnc.Discord"])
        self.assertEqual([2, 3], [m.rec_id for m in lezer.nieuwe_meldingen(1)])

    def test_oude_meldingen_worden_bij_het_opstarten_genegeerd(self):
        """
        DIT IS DE BELANGRIJKSTE TEST VAN DIT BESTAND.

        Zonder deze regel verwerkt de bot bij elke herstart alle oude meldingen
        die nog in het centrum staan — en koopt dus alles opnieuw.
        """
        for rec_id in (1, 2, 3):
            voeg_melding_toe(self.pad, rec_id, 1, "#calls (A)", "", f"oud {rec_id}")

        lezer = meldingen.Meldingenlezer(self.pad, ["com.hnc.Discord"])
        begin = lezer.hoogste_rec_id()          # zo start de sniper
        self.assertEqual(3, begin)
        self.assertEqual([], lezer.nieuwe_meldingen(begin))  # niets ouds

        voeg_melding_toe(self.pad, 4, 1, "#calls (A)", "", "nieuw")
        self.assertEqual([4], [m.rec_id for m in lezer.nieuwe_meldingen(begin)])

    def test_hoogste_rec_id_van_een_lege_database(self):
        lezer = meldingen.Meldingenlezer(self.pad, ["com.hnc.Discord"])
        self.assertEqual(0, lezer.hoogste_rec_id())

    def test_meldingen_van_andere_apps_worden_gefilterd(self):
        voeg_melding_toe(self.pad, 1, 1, "#calls (A)", "", "van discord")
        voeg_melding_toe(self.pad, 2, 2, "test", "", "van scripteditor")
        lezer = meldingen.Meldingenlezer(self.pad, ["com.hnc.Discord"])
        self.assertEqual([1], [m.rec_id for m in lezer.nieuwe_meldingen(0)])

    def test_zonder_appfilter_komt_alles_door(self):
        voeg_melding_toe(self.pad, 1, 1, "a", "", "x")
        voeg_melding_toe(self.pad, 2, 2, "b", "", "y")
        lezer = meldingen.Meldingenlezer(self.pad, [])
        self.assertEqual([1, 2], [m.rec_id for m in lezer.nieuwe_meldingen(0)])

    def test_apps_met_aantallen(self):
        voeg_melding_toe(self.pad, 1, 1, "a", "", "x")
        voeg_melding_toe(self.pad, 2, 1, "b", "", "y")
        voeg_melding_toe(self.pad, 3, 2, "c", "", "z")
        lezer = meldingen.Meldingenlezer(self.pad, ["com.hnc.Discord"])
        self.assertEqual([("com.hnc.Discord", 2), ("com.apple.ScriptEditor2", 1)],
                         lezer.apps_met_aantallen())


class TestAlleenLezen(Basis):
    def test_de_database_wordt_niet_aangeraakt(self):
        voeg_melding_toe(self.pad, 1, 1, "a", "", "x")
        voor = os.stat(self.pad).st_mtime_ns
        lezer = meldingen.Meldingenlezer(self.pad, [])
        lezer.nieuwe_meldingen(0)
        lezer.hoogste_rec_id()
        self.assertEqual(voor, os.stat(self.pad).st_mtime_ns)

    def test_schrijven_wordt_geweigerd(self):
        voeg_melding_toe(self.pad, 1, 1, "a", "", "x")
        lezer = meldingen.Meldingenlezer(self.pad, [])
        with lezer.verbinding() as verbinding:
            with self.assertRaises(sqlite3.OperationalError):
                verbinding.execute("delete from record")


class TestHardFalen(unittest.TestCase):
    def test_bestand_dat_niet_bestaat(self):
        with self.assertRaises(meldingen.MeldingFout) as gevangen:
            meldingen.Meldingenlezer("/bestaat/echt/niet.db", [])
        self.assertIn("bestaat niet", str(gevangen.exception))

    def test_database_zonder_record_tabel(self):
        pad = tempfile.mktemp(suffix=".db")
        verbinding = sqlite3.connect(pad)
        verbinding.execute("create table iets_anders (a integer)")
        verbinding.commit()
        verbinding.close()
        try:
            with self.assertRaises(meldingen.MeldingFout) as gevangen:
                meldingen.Meldingenlezer(pad, [])
            self.assertIn("record", str(gevangen.exception))
        finally:
            os.unlink(pad)

    def test_record_tabel_zonder_de_juiste_kolommen(self):
        """Apple verandert de opbouw -> hard stoppen, niet stil doorgaan."""
        pad = tempfile.mktemp(suffix=".db")
        verbinding = sqlite3.connect(pad)
        verbinding.execute("create table record (iets integer, anders text)")
        verbinding.commit()
        verbinding.close()
        try:
            with self.assertRaises(meldingen.MeldingFout) as gevangen:
                meldingen.Meldingenlezer(pad, [])
            self.assertIn("rec_id", str(gevangen.exception))
        finally:
            os.unlink(pad)

    def test_onbekende_leesmodus(self):
        pad = tempfile.mktemp(suffix=".db")
        maak_database(pad)
        try:
            with self.assertRaises(meldingen.MeldingFout):
                meldingen.Meldingenlezer(pad, [], "verzonnen")
        finally:
            os.unlink(pad)

    def test_zonder_app_tabel_draait_hij_door(self):
        pad = tempfile.mktemp(suffix=".db")
        maak_database(pad, met_app_tabel=False)
        voeg_melding_toe(pad, 1, 1, "titel", "", "tekst")
        try:
            lezer = meldingen.Meldingenlezer(pad, [])
            self.assertFalse(lezer.kan_op_app_filteren)
            self.assertEqual(1, len(lezer.nieuwe_meldingen(0)))
        finally:
            os.unlink(pad)


class TestPaden(unittest.TestCase):
    def test_beide_paden_worden_gezocht(self):
        paden = [str(p) for p in meldingen.mogelijke_paden()]
        self.assertTrue(
            any("group.com.apple.usernoted" in p for p in paden),
            "het Sequoia-pad moet erbij zitten",
        )


if __name__ == "__main__":
    unittest.main()
