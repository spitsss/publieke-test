"""
Tests voor het dashboard.

Twee harde regels: het luistert alleen op 127.0.0.1, en elke API-aanroep
vereist de sleutel.
"""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import hulp  # noqa: F401

import dashboard
from staat import GEKOCHT, Staat

SLEUTEL = "geheim-testsleuteltje"


class TestDashboard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.map = Path(tempfile.mkdtemp())
        cls.staat = Staat(cls.map)
        cls.staat.werk_bij(dryrun=True, quickbuy="aan", bedrag=0.05, valuta="SOL")
        cls.staat.hartslag("sniper", {"rec_id": 7, "laatste_ms": 889})
        cls.staat.noteer_handel({"adres": "0xabc", "resultaat": GEKOCHT, "ms": 889})

        dashboard.Bediener.sleutel = SLEUTEL
        dashboard.Bediener.staat = cls.staat
        dashboard.Bediener.logboek = None

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Bediener)
        cls.poort = cls.server.server_address[1]
        cls.draad = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.draad.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def haal(self, pad, sleutel=SLEUTEL, kop=None):
        url = f"http://127.0.0.1:{self.poort}{pad}"
        if sleutel is not None:
            url += ("&" if "?" in pad else "?") + f"sleutel={sleutel}"
        verzoek = urllib.request.Request(url)
        if kop:
            verzoek.add_header("X-Sleutel", kop)
        return urllib.request.urlopen(verzoek, timeout=5)

    # ---- de sleutel ----

    def test_met_de_juiste_sleutel(self):
        antwoord = self.haal("/api/status")
        self.assertEqual(200, antwoord.status)

    def test_zonder_sleutel_is_het_dicht(self):
        with self.assertRaises(urllib.error.HTTPError) as gevangen:
            self.haal("/api/status", sleutel=None)
        self.assertEqual(403, gevangen.exception.code)

    def test_met_een_verkeerde_sleutel(self):
        with self.assertRaises(urllib.error.HTTPError) as gevangen:
            self.haal("/api/status", sleutel="fout")
        self.assertEqual(403, gevangen.exception.code)

    def test_de_sleutel_mag_ook_in_een_kop(self):
        self.assertEqual(200, self.haal("/api/status", sleutel=None, kop=SLEUTEL).status)

    def test_elke_api_vereist_de_sleutel(self):
        for pad in ("/api/status", "/api/handel", "/api/log"):
            with self.subTest(pad=pad):
                with self.assertRaises(urllib.error.HTTPError) as gevangen:
                    self.haal(pad, sleutel=None)
                self.assertEqual(403, gevangen.exception.code)

    # ---- de inhoud ----

    def test_status_bevat_wat_het_dashboard_nodig_heeft(self):
        gegevens = json.loads(self.haal("/api/status").read())
        self.assertTrue(gegevens["draait"])
        self.assertTrue(gegevens["dryrun"])
        self.assertEqual("aan", gegevens["quickbuy"])
        self.assertEqual(889, gegevens["laatste_ms"])

    def test_verstuurd_en_gekocht_staan_apart(self):
        """Het hele punt: deze twee mogen nooit op één hoop."""
        tellers = json.loads(self.haal("/api/status").read())["tellers_boek"]
        for sleutel in ("gekocht", "verstuurd", "onbevestigd", "mislukt"):
            self.assertIn(sleutel, tellers)
        self.assertEqual(1, tellers["gekocht"])

    def test_handelsregels(self):
        gegevens = json.loads(self.haal("/api/handel?n=5").read())
        self.assertEqual("0xabc", gegevens["regels"][0]["adres"])

    def test_onzin_in_het_aantal_geeft_geen_crash(self):
        for vraag in ("?n=abc", "?n=-1", "?n=999999", "?n="):
            with self.subTest(vraag=vraag):
                self.assertEqual(200, self.haal(f"/api/handel{vraag}").status)

    def test_de_pagina_zelf(self):
        antwoord = self.haal("/", sleutel=None)
        inhoud = antwoord.read().decode("utf-8")
        self.assertEqual(200, antwoord.status)
        self.assertIn("CA-sniper", inhoud)

    def test_onbekend_pad(self):
        with self.assertRaises(urllib.error.HTTPError) as gevangen:
            self.haal("/iets/anders", sleutel=None)
        self.assertEqual(404, gevangen.exception.code)

    def test_onbekende_api(self):
        with self.assertRaises(urllib.error.HTTPError) as gevangen:
            self.haal("/api/verzonnen")
        self.assertEqual(404, gevangen.exception.code)

    def test_luistert_alleen_op_localhost(self):
        self.assertEqual("127.0.0.1", self.server.server_address[0])


if __name__ == "__main__":
    unittest.main()
