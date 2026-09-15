"""
telegrambediening.py — je eigen Telegram-bot om alles te bedienen.

WAAROM EEN EIGEN BOT MET EEN EIGEN TOKEN

Deze bot heeft een eigen token van BotFather. Daardoor staat hij gewoon tussen
je chats, met knoppen eronder, en heeft hij niets te maken met de
Telethon-sessie waarmee de sniper met BasedBot praat. Dat moet ook wel: twee
clients met dezelfde sessie krijgen geen updates meer.

ZET DIT BIJ BOTFATHER GOED
    /setjoingroups  Disable    (de bot kan niet in groepen gezet worden)
    /setinline      Disable    (geen inline-gebruik)
    /setprivacy     Enable     (hij leest niet mee in groepen)

BEPERKT TOT ÉÉN PERSOON
Elk bericht en elke knopdruk van iemand anders wordt geweigerd. Iemand die je
botnaam raadt kan anders je bot bedienen.

DE SNIPER HEEFT DE TELEGRAM-VERBINDING
Verkoopopdrachten voert deze bot niet zelf uit; hij legt ze klaar in een
bestandje en de sniper doet ze. Zo is er altijd maar één verbinding met
BasedBot.

ELK ANTWOORD ONDER DE 4096 TEKENS
Telegram weigert langere berichten. Alles wordt automatisch opgeknipt.
"""

from __future__ import annotations

import time
from typing import Any

from gereedschap import GEGEVENS, maak_logboek, zet_uitvoer_op_utf8
from instellingen import Instellingen, laad
from staat import DRYRUN, GEKOCHT, MISLUKT, ONBEKEND, Staat, VERSTUURD

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

API = "https://api.telegram.org/bot{token}/{methode}"

# Telegram weigert berichten boven 4096 tekens. We houden marge.
MAXIMALE_LENGTE = 3900


def verdeel(tekst: str, maximaal: int = MAXIMALE_LENGTE) -> list[str]:
    """
    Knipt een lange tekst in stukken die Telegram accepteert, bij voorkeur op
    een regelovergang zodat het leesbaar blijft.
    """
    tekst = tekst or "(leeg)"
    if len(tekst) <= maximaal:
        return [tekst]

    stukken: list[str] = []
    rest = tekst
    while len(rest) > maximaal:
        knip = rest.rfind("\n", 0, maximaal)
        if knip < maximaal // 2:
            knip = maximaal
        stukken.append(rest[:knip])
        rest = rest[knip:].lstrip("\n")
    if rest:
        stukken.append(rest)
    return stukken


def stuur_naar_eigenaar(opties: Instellingen, tekst: str) -> bool:
    """
    Stuurt een waarschuwing naar jezelf. Gebruikt door de sniper, de waakhond
    en de Quick Buy-wachter. Faalt stil: een mislukt alarm mag nooit een
    programma omleggen.
    """
    if requests is None:
        return False
    token = opties.bedien_token
    chat = opties.toegestane_id
    if not token or not chat:
        return False
    gelukt = True
    for stuk in verdeel(tekst):
        try:
            antwoord = requests.post(
                API.format(token=token, methode="sendMessage"),
                json={"chat_id": chat, "text": stuk},
                timeout=10,
            )
            gelukt = gelukt and antwoord.status_code == 200
        except Exception:
            gelukt = False
    return gelukt


# Het knoppenmenu onder de berichten.
HOOFDMENU = [
    [("Status", "cmd:status"), ("Laatste handel", "cmd:handel")],
    [("Logboek", "cmd:log"), ("Quick Buy", "cmd:quickbuy")],
    [("Pauze", "cmd:pauze"), ("Hervatten", "cmd:hervat")],
    [("Dry run AAN", "cmd:dryrun aan"), ("Dry run UIT", "cmd:dryrun uit")],
]

HELP = """Wat ik kan:

/status      hoe staat alles ervoor
/handel [n]  de laatste aankopen (standaard 10)
/log [n]     de laatste regels uit het logboek (standaard 20)
/quickbuy    staat Quick Buy nog aan
/pauze       de sniper reageert nergens meer op
/hervat      weer aanzetten
/dryrun aan  niets meer kopen, alleen opschrijven
/dryrun uit  ECHT kopen (denk twee keer na)
/adressen    hoeveel adressen al eens verstuurd zijn
/vergeet <adres>          zodat het opnieuw gekocht mag worden
/verkoop <adres> [deel]   deel = initials, 50, 100 (standaard initials)
/help        dit lijstje

Let op: /dryrun uit betekent dat er echt geld weggaat."""


class Bediening:
    """
    De bedieningsbot. 'verwerk' doet al het werk en raakt het netwerk niet aan,
    zodat de tests er rommelige invoer tegenaan kunnen gooien.
    """

    def __init__(self, opties: Instellingen, logboek=None, staat: Staat | None = None) -> None:
        self.opties = opties
        self.log = logboek or maak_logboek("bediening", opties.logniveau)
        self.staat = staat or Staat()
        self.laatste_update = 0

    # ------------------------------------------------------- de commando's

    def verwerk(self, ruw: str) -> tuple[str, list[list[tuple[str, str]]]]:
        """
        Zet een binnengekomen tekst om in een antwoord plus knoppen.
        Deze functie mag NOOIT een foutmelding omhoog gooien, wat er ook
        binnenkomt: '/', '/log abc', hoofdletters, of pure onzin.
        """
        try:
            return self._verwerk(ruw)
        except Exception as fout:
            self.log.exception("commando '%s' ging mis: %s", ruw, fout)
            return (f"Daar ging iets mis: {fout}\n\nProbeer /help", HOOFDMENU)

    def _verwerk(self, ruw: str) -> tuple[str, list[list[tuple[str, str]]]]:
        tekst = (ruw or "").strip()
        if not tekst:
            return ("Ik zie geen commando. Probeer /help", HOOFDMENU)

        delen = tekst.split()
        commando = delen[0].lower().lstrip("/")
        # "/status@mijnbot" werkt ook.
        commando = commando.split("@", 1)[0]
        argumenten = delen[1:]

        if not commando:
            return (HELP, HOOFDMENU)

        handelaar = {
            "start": self._start,
            "help": self._help,
            "status": self._status,
            "handel": self._handel,
            "log": self._log,
            "quickbuy": self._quickbuy,
            "pauze": self._pauze,
            "hervat": self._hervat,
            "dryrun": self._dryrun,
            "adressen": self._adressen,
            "vergeet": self._vergeet,
            "verkoop": self._verkoop,
        }.get(commando)

        if handelaar is None:
            return (f"'{commando}' ken ik niet.\n\n{HELP}", HOOFDMENU)
        return handelaar(argumenten)

    def _getal(self, argumenten: list[str], standaard: int, hoogste: int) -> tuple[int, str]:
        """
        Leest een aantal uit de argumenten. '/log abc' mag niet crashen: dan
        pakken we gewoon de standaard en zeggen we dat erbij.
        """
        if not argumenten:
            return standaard, ""
        try:
            aantal = int(argumenten[0])
        except (ValueError, TypeError):
            return standaard, f"('{argumenten[0]}' is geen getal, ik neem {standaard})\n"
        if aantal < 1:
            return 1, "(minimaal 1)\n"
        if aantal > hoogste:
            return hoogste, f"(maximaal {hoogste})\n"
        return aantal, ""

    def _start(self, _argumenten) -> tuple[str, list]:
        return (f"Sniper-bediening.\n\n{HELP}", HOOFDMENU)

    def _help(self, _argumenten) -> tuple[str, list]:
        return (HELP, HOOFDMENU)

    def _status(self, _argumenten) -> tuple[str, list]:
        gegevens = self.staat.lees()
        leeftijd = self.staat.hartslag_leeftijd("sniper")
        hartslag = gegevens.get("hartslag") or {}
        sniperregel = hartslag.get("sniper") or {} if isinstance(hartslag, dict) else {}
        tellers = sniperregel.get("tellers") or {}

        if leeftijd is None:
            leven = "GEEN hartslag — draait de sniper wel?"
        elif leeftijd > 90:
            leven = f"STIL sinds {int(leeftijd)}s — waarschijnlijk vastgelopen"
        else:
            leven = f"draait ({int(leeftijd)}s geleden)"

        dryrun = gegevens.get("dryrun", True)
        regels = [
            "STATUS",
            f"Sniper      : {leven}",
            f"Stand       : {'DRY RUN — koopt niets' if dryrun else 'LIVE — koopt echt'}",
            f"Gepauzeerd  : {'JA' if gegevens.get('gepauzeerd') else 'nee'}",
            f"Quick Buy   : {str(gegevens.get('quickbuy') or 'niet gecontroleerd').upper()}",
            f"Bedrag/call : {gegevens.get('bedrag', '?')} {gegevens.get('valuta', '')}",
            f"Chain       : {gegevens.get('chain', '?')}",
            f"Laatste tijd: {sniperregel.get('laatste_ms', '?')} ms van melding tot verstuurd",
            "",
            "Tellers:",
            f"  meldingen gezien : {tellers.get('gezien', 0)}",
            f"  weggefilterd     : {tellers.get('gefilterd', 0)}",
            f"  verstuurd        : {tellers.get('verstuurd', 0)}",
            f"  BEVESTIGD gekocht: {tellers.get('gekocht', 0)}",
            f"  mislukt          : {tellers.get('mislukt', 0)}",
            "",
            "'Verstuurd' is niet hetzelfde als 'gekocht'.",
        ]
        fouten = sniperregel.get("schrijffouten") or 0
        if fouten:
            regels.append(f"\nLet op: {fouten} schrijffouten op het statusbestand.")
        return ("\n".join(regels), HOOFDMENU)

    def _handel(self, argumenten) -> tuple[str, list]:
        aantal, opmerking = self._getal(argumenten, 10, 50)
        regels = self.staat.lees_handel(aantal)
        if not regels:
            return (f"{opmerking}Nog niets gekocht of verstuurd.", HOOFDMENU)

        namen = {
            GEKOCHT: "GEKOCHT", VERSTUURD: "verstuurd", MISLUKT: "MISLUKT",
            ONBEKEND: "onbevestigd", DRYRUN: "dry run",
        }
        uit = [f"{opmerking}Laatste {len(regels)}:"]
        for regel in regels:
            adres = str(regel.get("adres", "?"))
            resultaat = str(regel.get("resultaat", "?"))
            uit.append(
                f"\n{regel.get('tijd_leesbaar', '?')}  {namen.get(resultaat, resultaat)}"
                f"\n  {adres[:20]}…  {regel.get('ms', '?')} ms"
                f"\n  {str(regel.get('uitleg', ''))[:120]}"
            )
        return ("\n".join(uit), HOOFDMENU)

    def _log(self, argumenten) -> tuple[str, list]:
        aantal, opmerking = self._getal(argumenten, 20, 100)
        pad = GEGEVENS / "sniper.log"
        try:
            with open(pad, "r", encoding="utf-8-sig", errors="replace") as bestand:
                regels = bestand.readlines()
        except FileNotFoundError:
            return (f"{opmerking}Er is nog geen logboek ({pad}).", HOOFDMENU)
        except Exception as fout:
            return (f"Logboek niet leesbaar: {fout}", HOOFDMENU)
        staart = "".join(regels[-aantal:]) or "(leeg)"
        return (f"{opmerking}{staart}", HOOFDMENU)

    def _quickbuy(self, _argumenten) -> tuple[str, list]:
        gegevens = self.staat.lees()
        stand = str(gegevens.get("quickbuy") or "niet gecontroleerd")
        tijd = gegevens.get("quickbuy_tijd")
        wanneer = (
            time.strftime("%H:%M:%S", time.localtime(tijd)) if isinstance(tijd, (int, float)) else "?"
        )
        uitleg = str(gegevens.get("quickbuy_uitleg") or "")
        tekst = [f"Quick Buy: {stand.upper()}  (gekeken om {wanneer})"]
        if uitleg:
            tekst.append(uitleg)
        if stand == "uit":
            tekst.append(
                "\nZet hem aan in BasedBot via /manage. Zolang hij uit staat wordt er "
                "NIETS gekocht, ook al stuurt de sniper netjes het adres door."
            )
        elif stand != "aan":
            tekst.append(
                "\nDe wachter kijkt hoogstens eens per vijf minuten — vaker en BasedBot "
                "stopt met antwoorden."
            )
        return ("\n".join(tekst), HOOFDMENU)

    def _pauze(self, _argumenten) -> tuple[str, list]:
        self.staat.werk_bij(gepauzeerd=True)
        return ("Gepauzeerd. De sniper reageert nergens meer op. /hervat zet hem weer aan.", HOOFDMENU)

    def _hervat(self, _argumenten) -> tuple[str, list]:
        self.staat.werk_bij(gepauzeerd=False)
        return ("Hervat. De sniper kijkt weer mee.", HOOFDMENU)

    def _dryrun(self, argumenten) -> tuple[str, list]:
        if not argumenten:
            nu = self.staat.lees().get("dryrun", True)
            return (
                f"Dry run staat {'AAN — er wordt niets gekocht' if nu else 'UIT — er wordt echt gekocht'}.\n"
                "Zet om met: /dryrun aan   of   /dryrun uit",
                HOOFDMENU,
            )
        keuze = argumenten[0].lower()
        if keuze in ("aan", "ja", "on", "true", "1"):
            self.staat.werk_bij(dryrun=True)
            return ("Dry run AAN. Er wordt niets meer gekocht.", HOOFDMENU)
        if keuze in ("uit", "nee", "off", "false", "0"):
            self.staat.werk_bij(dryrun=False)
            return (
                "Dry run UIT. Er gaat nu ECHT geld weg bij elke call.\n"
                "Controleer of Quick Buy aan staat met /quickbuy.",
                HOOFDMENU,
            )
        return (f"'{argumenten[0]}' snap ik niet. Gebruik: /dryrun aan   of   /dryrun uit", HOOFDMENU)

    def _adressen(self, _argumenten) -> tuple[str, list]:
        try:
            with open(self.staat.verstuurd_pad, "r", encoding="utf-8-sig") as bestand:
                regels = [r for r in bestand if r.strip()]
        except FileNotFoundError:
            regels = []
        except Exception as fout:
            return (f"Lijst niet leesbaar: {fout}", HOOFDMENU)
        laatste = [r.split("\t")[0] for r in regels[-10:]]
        tekst = [f"{len(regels)} adressen zijn al eens verstuurd; die koopt hij niet nog eens."]
        if laatste:
            tekst.append("\nLaatste 10:")
            tekst.extend(f"  {adres}" for adres in laatste)
        tekst.append("\nMet /vergeet <adres> mag er opnieuw op gekocht worden.")
        return ("\n".join(tekst), HOOFDMENU)

    def _vergeet(self, argumenten) -> tuple[str, list]:
        if not argumenten:
            return ("Gebruik: /vergeet <adres>", HOOFDMENU)
        adres = argumenten[0]
        if self.staat.vergeet_verstuurd(adres):
            return (f"{adres} is vergeten. Bij een volgende call mag hij opnieuw gekocht worden.", HOOFDMENU)
        return (f"{adres} stond niet in de lijst.", HOOFDMENU)

    def _verkoop(self, argumenten) -> tuple[str, list]:
        if not self.opties.zelf_verkopen:
            return (
                "Zelf verkopen staat uit (zo is het standaard ingesteld).\n"
                "Zet [handel] zelf_verkopen = ja in config.ini als je dit wilt.",
                HOOFDMENU,
            )
        if not argumenten:
            return ("Gebruik: /verkoop <adres> [initials|50|100]", HOOFDMENU)

        adres = argumenten[0]
        import extract

        geldig = extract.is_evm_adres(adres) or extract.is_solana_adres(adres)
        if not geldig:
            return (f"'{adres[:24]}' ziet er niet uit als een geldig adres. Niets gedaan.", HOOFDMENU)

        deel = (argumenten[1] if len(argumenten) > 1 else "initials").lower().rstrip("%")
        if deel not in ("initials", "inleg", "25", "50", "75", "100"):
            return (f"'{deel}' snap ik niet. Kies: initials, 25, 50, 75 of 100.", HOOFDMENU)

        gelukt = self.staat.zet_opdracht({"soort": "verkoop", "adres": adres, "deel": deel})
        if not gelukt:
            return ("De opdracht kon ik niet wegschrijven. Probeer het nog eens.", HOOFDMENU)
        return (
            f"Opdracht klaargezet: {deel} van {adres[:16]}… verkopen.\n"
            "De sniper voert hem uit via /manage → Your Bags (nooit door een adres te "
            "sturen — dat zou juist bijkopen). Je hoort het resultaat hier.",
            HOOFDMENU,
        )

    # ------------------------------------------------------------- netwerk

    def _knoppen(self, menu) -> dict:
        return {
            "inline_keyboard": [
                [{"text": tekst, "callback_data": data} for tekst, data in rij] for rij in menu
            ]
        }

    def stuur(self, chat_id: int, tekst: str, menu=None) -> None:
        if requests is None:
            return
        stukken = verdeel(tekst)
        for nummer, stuk in enumerate(stukken):
            lading: dict[str, Any] = {"chat_id": chat_id, "text": stuk}
            if menu and nummer == len(stukken) - 1:
                lading["reply_markup"] = self._knoppen(menu)
            try:
                requests.post(
                    API.format(token=self.opties.bedien_token, methode="sendMessage"),
                    json=lading,
                    timeout=15,
                )
            except Exception as fout:
                self.log.warning("kon bericht niet sturen: %s", fout)

    def draai(self) -> int:
        """Haalt updates op (long polling) en beantwoordt ze."""
        if requests is None:
            self.log.error("requests ontbreekt. pip install -r requirements.txt")
            return 1
        if not self.opties.bedien_token:
            self.log.error(
                "[bediening] bot_token is leeg. Maak een bot bij @BotFather en zet het token "
                "in config.ini."
            )
            return 2
        if not self.opties.toegestane_id:
            self.log.error(
                "[bediening] toegestane_id is leeg. Zonder dat kan iedereen die je botnaam "
                "kent hem bedienen. Vraag je id op bij @userinfobot."
            )
            return 2

        self.log.info("Bedieningsbot draait. Alleen Telegram-id %s mag iets.", self.opties.toegestane_id)
        self.stuur(self.opties.toegestane_id, "Bedieningsbot is opgestart.", HOOFDMENU)

        while True:
            try:
                antwoord = requests.get(
                    API.format(token=self.opties.bedien_token, methode="getUpdates"),
                    params={"offset": self.laatste_update + 1, "timeout": 25},
                    timeout=40,
                )
                if antwoord.status_code != 200:
                    time.sleep(3)
                    continue
                gegevens = antwoord.json()
            except Exception as fout:
                self.log.debug("ophalen mislukte: %s", fout)
                time.sleep(3)
                continue

            for update in gegevens.get("result", []):
                try:
                    self._behandel(update)
                except Exception as fout:
                    # Eén rare update mag de bediening nooit omleggen.
                    self.log.exception("update ging mis: %s", fout)
                finally:
                    self.laatste_update = max(self.laatste_update, int(update.get("update_id", 0)))

            self.staat.hartslag("bediening")

    def _behandel(self, update: dict) -> None:
        bericht = update.get("message") or update.get("edited_message")
        knopdruk = update.get("callback_query")

        if knopdruk:
            afzender = (knopdruk.get("from") or {}).get("id")
            if not self._mag(afzender, "knopdruk"):
                self._beantwoord_knop(knopdruk.get("id"), "Geen toegang.")
                return
            self._beantwoord_knop(knopdruk.get("id"), "")
            data = str(knopdruk.get("data") or "")
            opdracht = data.split(":", 1)[1] if data.startswith("cmd:") else data
            chat = ((knopdruk.get("message") or {}).get("chat") or {}).get("id") or afzender
            antwoord, menu = self.verwerk("/" + opdracht.strip())
            self.stuur(chat, antwoord, menu)
            return

        if not bericht:
            return
        afzender = (bericht.get("from") or {}).get("id")
        if not self._mag(afzender, "bericht"):
            return
        chat = (bericht.get("chat") or {}).get("id") or afzender
        antwoord, menu = self.verwerk(bericht.get("text") or "")
        self.stuur(chat, antwoord, menu)

    def _mag(self, afzender, soort: str) -> bool:
        """Alleen de eigenaar mag deze bot bedienen."""
        try:
            toegestaan = int(afzender) == int(self.opties.toegestane_id)
        except (TypeError, ValueError):
            toegestaan = False
        if not toegestaan:
            self.log.warning("%s geweigerd van Telegram-id %s", soort, afzender)
        return toegestaan

    def _beantwoord_knop(self, knop_id, tekst: str) -> None:
        if requests is None or not knop_id:
            return
        try:
            requests.post(
                API.format(token=self.opties.bedien_token, methode="answerCallbackQuery"),
                json={"callback_query_id": knop_id, "text": tekst[:200]},
                timeout=10,
            )
        except Exception:
            pass


def main() -> int:
    zet_uitvoer_op_utf8()
    opties = laad()
    logboek = maak_logboek("bediening", opties.logniveau)
    try:
        return Bediening(opties, logboek).draai()
    except KeyboardInterrupt:
        logboek.info("Bedieningsbot gestopt.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
