"""
telegram_brug.py — praat met BasedBot via je eigen Telegram-account.

WAAROM POLLEN EN NIET LUISTEREN

Telethon heeft een mooie events.NewMessage-handler. Die werkt hier niet
betrouwbaar: als er twee clients met dezelfde auth-key (hetzelfde
sessiebestand) bestaan, krijgt maar één van de twee updates. Een gekopieerd
sessiebestand zorgde er letterlijk voor dat een handler NIETS binnenkreeg,
zonder ook maar één foutmelding. Daarom:

  * KOPIEER NOOIT een .session-bestand naar een andere map of machine.
  * We vragen berichten op (get_messages) in plaats van erop te wachten.

WAAROM ÉÉN DRAAD MET ÉÉN CLIENT

Telethon is asynchroon, de rest van de bot niet. Daarom draait hier één
achtergronddraad met één eigen event-loop, en geven de gewone functies hun
opdrachten daaraan door. Er is dus precies één Telegram-verbinding in de hele
bot — zoals het hoort.

BEOORDELEN VAN HET ANTWOORD

"Verstuurd" en "gekocht" zijn niet hetzelfde. Als je die door elkaar haalt,
lees je in je logboek "gekocht" terwijl je niets hebt. Snapt deze module het
antwoord van BasedBot niet, dan is het resultaat ONBEKEND — nooit "gekocht".
"""

from __future__ import annotations

import asyncio
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from staat import GEKOCHT, MISLUKT, ONBEKEND, VERSTUURD

try:
    from telethon import TelegramClient
    from telethon.errors import FloodWaitError
except ImportError:  # pragma: no cover
    TelegramClient = None  # type: ignore
    FloodWaitError = Exception  # type: ignore


# Standaardpatronen om het antwoord van BasedBot te duiden. Ze staan ook in
# config.ini, zodat je ze kunt bijstellen als BasedBot zijn teksten verandert
# zonder dat je deze code hoeft aan te passen.
PATROON_MISLUKT = (
    r"insufficient|not enough|failed|failure|error|invalid|unable to|could not|"
    r"couldn'?t|no route|not found|rejected|cancell?ed|too low|slippage"
)
PATROON_GEKOCHT = (
    r"buy success|bought|purchase (?:success|complete)|successfully (?:bought|swapped|purchased)|"
    r"swap success|position opened|tx confirmed|transaction confirmed|✅"
)
PATROON_BEZIG = r"buying|processing|pending|sending|submitting|confirming|swapping"


@dataclass
class Knop:
    """Eén knop onder een bericht van BasedBot."""

    rij: int
    kolom: int
    tekst: str
    data: str = ""  # de callback-data, als tekst


@dataclass
class Antwoord:
    """Wat BasedBot terugzei op ons bericht."""

    resultaat: str = ONBEKEND
    uitleg: str = ""
    teksten: list[str] = field(default_factory=list)
    bericht_ids: list[int] = field(default_factory=list)
    ms: int = 0

    @property
    def is_gekocht(self) -> bool:
        return self.resultaat == GEKOCHT


def beoordeel_antwoord(
    teksten: list[str],
    patroon_mislukt: str = PATROON_MISLUKT,
    patroon_gekocht: str = PATROON_GEKOCHT,
    patroon_bezig: str = PATROON_BEZIG,
) -> tuple[str, str]:
    """
    Beoordeelt wat BasedBot terugzei.

    Volgorde is met opzet: eerst kijken of het MISLUKT is. "Buy failed" bevat
    ook het woord "buy"; zou je eerst op succes toetsen, dan tel je een
    mislukking als aankoop. En snappen we het niet, dan is het ONBEKEND —
    nooit stilzwijgend "gekocht".
    """
    alles = "\n".join(teksten).lower()
    if not alles.strip():
        return ONBEKEND, "BasedBot gaf geen antwoord"

    if re.search(patroon_mislukt, alles, re.IGNORECASE):
        treffer = re.search(patroon_mislukt, alles, re.IGNORECASE)
        return MISLUKT, f"antwoord bevat '{treffer.group(0) if treffer else '?'}'"

    if re.search(patroon_gekocht, alles, re.IGNORECASE):
        treffer = re.search(patroon_gekocht, alles, re.IGNORECASE)
        return GEKOCHT, f"antwoord bevat '{treffer.group(0) if treffer else '?'}'"

    if re.search(patroon_bezig, alles, re.IGNORECASE):
        return ONBEKEND, "BasedBot is nog bezig; nog geen bevestiging van een aankoop"

    return ONBEKEND, "antwoord niet herkend — NIET als aankoop geteld"


class TelegramBrug:
    """Eén Telegram-verbinding, bediend vanuit gewone (niet-async) code."""

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        sessienaam: str,
        basedbot: str,
        antwoord_wacht_s: float = 12.0,
        logboek=None,
        patronen: dict[str, str] | None = None,
    ) -> None:
        if TelegramClient is None:
            raise RuntimeError(
                "Telethon ontbreekt. Doe eerst: pip install -r requirements.txt"
            )
        self.api_id = int(api_id)
        self.api_hash = api_hash
        self.sessienaam = sessienaam
        self.basedbot = basedbot
        self.antwoord_wacht_s = float(antwoord_wacht_s)
        self.logboek = logboek
        self.patronen = {
            "mislukt": PATROON_MISLUKT,
            "gekocht": PATROON_GEKOCHT,
            "bezig": PATROON_BEZIG,
        }
        if patronen:
            self.patronen.update({k: v for k, v in patronen.items() if v})

        self._lus: asyncio.AbstractEventLoop | None = None
        self._draad: threading.Thread | None = None
        self._client: Any = None
        self._entiteit: Any = None
        self._klaar = threading.Event()
        self._opstartfout: Exception | None = None
        self._slot = threading.Lock()

    # ------------------------------------------------ opstarten/stoppen

    def start(self, tijdslimiet: float = 60.0) -> None:
        """Start de achtergronddraad en verbindt. Faalt hard als dat niet lukt."""
        self._draad = threading.Thread(target=self._draai_lus, name="telegram", daemon=True)
        self._draad.start()
        if not self._klaar.wait(tijdslimiet):
            raise RuntimeError("Telegram-verbinding kwam niet op gang binnen de tijd.")
        if self._opstartfout:
            raise self._opstartfout

    def _draai_lus(self) -> None:
        self._lus = asyncio.new_event_loop()
        asyncio.set_event_loop(self._lus)
        try:
            self._lus.run_until_complete(self._verbind())
        except Exception as fout:
            self._opstartfout = fout
            self._klaar.set()
            return
        self._klaar.set()
        self._lus.run_forever()

    async def _verbind(self) -> None:
        self._client = TelegramClient(self.sessienaam, self.api_id, self.api_hash)
        await self._client.connect()
        if not await self._client.is_user_authorized():
            raise RuntimeError(
                "Nog niet ingelogd bij Telegram.\n"
                "Doe dit één keer met de hand:\n"
                "    python3 telegram_brug.py --inloggen\n"
                "Je krijgt dan een code in je Telegram-app."
            )
        self._entiteit = await self._client.get_entity(self.basedbot)

    def stop(self) -> None:
        if self._lus and self._lus.is_running():
            async def _sluit():
                try:
                    await self._client.disconnect()
                except Exception:
                    pass
            try:
                asyncio.run_coroutine_threadsafe(_sluit(), self._lus).result(timeout=5)
            except Exception:
                pass
            self._lus.call_soon_threadsafe(self._lus.stop)

    def _draai(self, coroutine, tijdslimiet: float = 30.0):
        """Voert een async-opdracht uit vanuit gewone code."""
        if not self._lus:
            raise RuntimeError("De Telegram-brug is niet gestart.")
        toekomst = asyncio.run_coroutine_threadsafe(coroutine, self._lus)
        return toekomst.result(timeout=tijdslimiet)

    # ------------------------------------------------ berichten

    def stuur(self, tekst: str) -> int:
        """Stuurt een bericht naar BasedBot en geeft het bericht-id terug."""
        async def _doe():
            bericht = await self._client.send_message(self._entiteit, tekst)
            return int(bericht.id)

        return self._draai(_doe(), tijdslimiet=30.0)

    def lees_na(self, na_id: int, aantal: int = 20) -> list[tuple[int, str]]:
        """
        Haalt berichten op die ná een bepaald bericht-id binnenkwamen.
        Oudste eerst. Dit is het 'pollen' in plaats van 'luisteren'.
        """
        async def _doe():
            berichten = await self._client.get_messages(
                self._entiteit, limit=aantal, min_id=na_id
            )
            uitkomst = []
            for bericht in reversed(berichten):  # get_messages geeft nieuwste eerst
                if bericht.out:
                    continue  # onze eigen berichten slaan we over
                uitkomst.append((int(bericht.id), bericht.message or ""))
            return uitkomst

        return self._draai(_doe(), tijdslimiet=30.0)

    def stuur_en_lees(self, tekst: str, seconden: float | None = None) -> Antwoord:
        """
        Stuurt iets naar BasedBot en wacht op het antwoord. Beoordeelt daarna
        of er echt gekocht is.
        """
        seconden = self.antwoord_wacht_s if seconden is None else seconden
        begin = time.time()
        with self._slot:
            try:
                verzonden_id = self.stuur(tekst)
            except FloodWaitError as fout:
                wacht = getattr(fout, "seconds", "?")
                return Antwoord(
                    MISLUKT, f"Telegram houdt ons tegen (FloodWait {wacht}s)", [], [], 0
                )
            except Exception as fout:
                return Antwoord(MISLUKT, f"versturen mislukte: {fout}", [], [], 0)

            teksten: list[str] = []
            ids: list[int] = []
            einde = time.time() + seconden
            while time.time() < einde:
                time.sleep(0.4)
                try:
                    nieuw = self.lees_na(verzonden_id)
                except Exception:
                    continue
                for bericht_id, inhoud in nieuw:
                    if bericht_id not in ids:
                        ids.append(bericht_id)
                        teksten.append(inhoud)
                if teksten:
                    # BasedBot stuurt vaak eerst "buying..." en daarna het
                    # echte resultaat. Even doorkijken of er nog wat komt.
                    stand, _ = beoordeel_antwoord(
                        teksten,
                        self.patronen["mislukt"],
                        self.patronen["gekocht"],
                        self.patronen["bezig"],
                    )
                    if stand in (GEKOCHT, MISLUKT):
                        break

        resultaat, uitleg = beoordeel_antwoord(
            teksten, self.patronen["mislukt"], self.patronen["gekocht"], self.patronen["bezig"]
        )
        return Antwoord(
            resultaat=resultaat,
            uitleg=uitleg,
            teksten=teksten,
            bericht_ids=ids,
            ms=int((time.time() - begin) * 1000),
        )

    def stuur_alleen(self, tekst: str) -> Antwoord:
        """
        Stuurt iets door zonder op het antwoord te wachten. Het resultaat is
        dus VERSTUURD, uitdrukkelijk niet 'gekocht'.
        """
        begin = time.time()
        try:
            self.stuur(tekst)
        except Exception as fout:
            return Antwoord(MISLUKT, f"versturen mislukte: {fout}")
        return Antwoord(VERSTUURD, "verstuurd, nog niet bevestigd", ms=int((time.time() - begin) * 1000))

    # ------------------------------------------------ knoppen

    def laatste_met_knoppen(self, aantal: int = 10) -> tuple[int, str, list[Knop]]:
        """
        Zoekt het nieuwste bericht van BasedBot dat knoppen heeft.
        Geeft (bericht_id, tekst, knoppen) terug; bericht_id 0 = niets gevonden.
        """
        async def _doe():
            berichten = await self._client.get_messages(self._entiteit, limit=aantal)
            for bericht in berichten:
                if bericht.out or not getattr(bericht, "buttons", None):
                    continue
                knoppen: list[Knop] = []
                for r, rij in enumerate(bericht.buttons):
                    for k, knop in enumerate(rij):
                        rauw = getattr(knop, "data", None)
                        data = ""
                        if isinstance(rauw, (bytes, bytearray)):
                            data = bytes(rauw).decode("utf-8", "replace")
                        elif isinstance(rauw, str):
                            data = rauw
                        knoppen.append(Knop(r, k, getattr(knop, "text", "") or "", data))
                return int(bericht.id), bericht.message or "", knoppen
            return 0, "", []

        return self._draai(_doe(), tijdslimiet=30.0)

    def klik(self, bericht_id: int, rij: int, kolom: int) -> str:
        """Drukt op een knop. Geeft de tekst terug die Telegram terugmeldt."""
        async def _doe():
            bericht = await self._client.get_messages(self._entiteit, ids=bericht_id)
            if bericht is None:
                raise RuntimeError(f"Bericht {bericht_id} bestaat niet meer.")
            antwoord = await bericht.click(rij, kolom)
            return getattr(antwoord, "message", "") or ""

        return self._draai(_doe(), tijdslimiet=45.0)

    def tekst_van(self, bericht_id: int) -> str:
        async def _doe():
            bericht = await self._client.get_messages(self._entiteit, ids=bericht_id)
            return (bericht.message or "") if bericht else ""

        return self._draai(_doe(), tijdslimiet=20.0)


def _inloggen() -> int:
    """Eenmalig inloggen bij Telegram. Maakt het sessiebestand aan."""
    from gereedschap import zet_uitvoer_op_utf8
    from instellingen import laad

    zet_uitvoer_op_utf8()
    opties = laad()
    if TelegramClient is None:
        print("Telethon ontbreekt. Doe: pip install -r requirements.txt")
        return 1
    if not opties.api_id or not opties.api_hash:
        print("Vul eerst api_id en api_hash in config.ini in (van my.telegram.org).")
        return 1

    print("Inloggen bij Telegram. Je krijgt zo een code in je Telegram-app.")
    print("LET OP: kopieer het sessiebestand daarna NOOIT naar een andere map")
    print("of machine. Twee clients met dezelfde sessie krijgen geen updates meer.")
    client = TelegramClient(opties.sessienaam, opties.api_id, opties.api_hash)
    with client:
        client.start()
        ik = client.get_me()
        print(f"Gelukt. Ingelogd als {getattr(ik, 'username', None) or ik.id}.")
        try:
            bot = client.get_entity(opties.basedbot)
            print(f"BasedBot gevonden: {getattr(bot, 'username', opties.basedbot)}")
        except Exception as fout:
            print(f"Let op: '{opties.basedbot}' kon ik niet vinden ({fout}).")
            print("Klopt de @naam? Heb je al een keer met de bot gepraat?")
            return 1
    return 0


if __name__ == "__main__":
    import sys

    if "--inloggen" in sys.argv:
        raise SystemExit(_inloggen())
    print("Gebruik: python3 telegram_brug.py --inloggen")
