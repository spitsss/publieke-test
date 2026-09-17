"""
Tests voor het eenmalige inloggen bij Telegram.

Waarom dit bestand bestaat: dit was het enige stukje code dat nooit door een
test liep, omdat er een echte Telegram-verbinding voor nodig is. En precies
daar zat een fout. Het inloggen lukte, maar de regel die "Gelukt" moest
afdrukken sloeg stuk met:

    AttributeError: 'coroutine' object has no attribute 'id'

De oorzaak: elke functie van Telethon moet met 'await' aangeroepen worden.
Zonder await krijg je de coroutine zelf terug in plaats van het antwoord.

De client wordt nu los meegegeven, zodat we hem hier kunnen nabootsen en de
hele inlogronde kunnen nalopen zonder internet, zonder Telegram en zonder
code.
"""

from __future__ import annotations

import asyncio
import unittest

import hulp  # noqa: F401

import telegram_brug


class NepGebruiker:
    username = "armaan"
    first_name = "Achraf"
    id = 123456


class NepBot:
    username = "BasedBot"


class NepClient:
    """Bootst een Telethon-client na: alles is een coroutine, net als echt."""

    def __init__(self, bot_bestaat: bool = True) -> None:
        self.bot_bestaat = bot_bestaat
        self.gestart = False
        self.afgesloten = False

    async def start(self):
        self.gestart = True

    async def get_me(self):
        return NepGebruiker()

    async def get_entity(self, naam):
        if not self.bot_bestaat:
            raise ValueError(f"Cannot find any entity corresponding to {naam!r}")
        return NepBot()

    async def disconnect(self):
        self.afgesloten = True


class TestInloggen(unittest.TestCase):
    def test_een_geslaagde_inlogronde(self):
        client = NepClient()
        code = asyncio.run(telegram_brug._doe_inloggen(lambda: client, "@BasedBot"))
        self.assertEqual(0, code)
        self.assertTrue(client.gestart)
        self.assertTrue(client.afgesloten, "de verbinding moet netjes gesloten worden")

    def test_basedbot_niet_gevonden_geeft_een_nette_fout(self):
        client = NepClient(bot_bestaat=False)
        code = asyncio.run(telegram_brug._doe_inloggen(lambda: client, "@BestaatNiet"))
        self.assertEqual(1, code, "dit moet een foutcode geven, geen crash")
        self.assertTrue(client.afgesloten)

    def test_de_echte_naam_wordt_afgedrukt(self):
        """
        DIT is de test die de echte fout vindt.

        Mijn eerste poging keek alleen of er geen crash kwam. Maar ik had een
        vangnet ingebouwd dat bij twijfel "?" afdrukte, en daardoor slaagde die
        test óók met de fout er nog in: er stond dan "Ingelogd als ?." en dat
        zag niemand. Nu controleren we of de ECHTE naam eruit komt.
        """
        import contextlib
        import io

        client = NepClient()
        uitvoer = io.StringIO()
        with contextlib.redirect_stdout(uitvoer):
            code = asyncio.run(telegram_brug._doe_inloggen(lambda: client, "@BasedBot"))
        tekst = uitvoer.getvalue()
        self.assertEqual(0, code)
        self.assertIn("armaan", tekst, "de echte gebruikersnaam hoort afgedrukt te worden")
        self.assertNotIn("?.", tekst, "een vraagteken betekent dat er iets niet is uitgelezen")
        self.assertTrue(client.gestart, "start() is niet echt uitgevoerd — await vergeten?")

    def test_een_vergeten_await_geeft_een_harde_fout(self):
        """
        Bootst na wat er gebeurt als iemand later per ongeluk het 'await' bij
        get_me() weghaalt: dan komt er een coroutine uit in plaats van een
        gebruiker. Dat moet een duidelijke klap geven, geen vraagteken.
        """

        class ZonderAwait(NepClient):
            async def get_me(self):
                # Een coroutine teruggeven zonder hem uit te voeren — precies
                # wat er gebeurt als 'await' ontbreekt.
                async def niks():
                    return NepGebruiker()

                return niks()

        client = ZonderAwait()
        with self.assertRaises(RuntimeError) as gevangen:
            asyncio.run(telegram_brug._doe_inloggen(lambda: client, "@BasedBot"))
        self.assertIn("programmeerfout", str(gevangen.exception))

    def test_een_client_die_bij_het_starten_stukloopt(self):
        class Stuk(NepClient):
            async def start(self):
                raise ConnectionError("geen internet")

        client = Stuk()
        with self.assertRaises(ConnectionError):
            asyncio.run(telegram_brug._doe_inloggen(lambda: client, "@BasedBot"))
        self.assertTrue(client.afgesloten, "ook bij een fout moet de verbinding dicht")


if __name__ == "__main__":
    unittest.main()
