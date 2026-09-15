"""
dashboard.py — een klein webdashboard op je eigen computer.

DRIE HARDE REGELS

1. Hij luistert ALLEEN op 127.0.0.1. Niemand anders in je netwerk kan erbij.
2. Elke API-aanroep vereist een sleutel. Staat er geen sleutel in config.ini,
   dan maakt hij er zelf één en drukt die af — hij start nooit zonder.
3. 'Verstuurd' en 'gekocht' staan hier strikt uit elkaar. Dat is het hele
   punt: anders lees je 'gekocht' terwijl je niets hebt.

Starten:   python3 dashboard.py
Openen:    de link die hij afdrukt (met de sleutel erin)
"""

from __future__ import annotations

import hmac
import json
import secrets
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from gereedschap import GEGEVENS, maak_logboek, zet_uitvoer_op_utf8
from instellingen import laad
from staat import DRYRUN, GEKOCHT, MISLUKT, ONBEKEND, Staat, VERSTUURD

MAP = Path(__file__).resolve().parent


class Bediener(BaseHTTPRequestHandler):
    sleutel = ""
    staat: Staat = None  # type: ignore
    logboek = None

    # De standaardregel van http.server schrijft naar stderr; wij willen hem
    # in ons eigen logboek, en alleen als er iets bijzonders is.
    def log_message(self, opmaak, *argumenten):
        if self.logboek:
            self.logboek.debug("%s - %s", self.address_string(), opmaak % argumenten)

    # ---------------------------------------------------------- hulpjes

    def _stuur(self, code: int, inhoud: bytes, soort: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", f"{soort}; charset=utf-8")
        self.send_header("Content-Length", str(len(inhoud)))
        # Dit dashboard hoort nergens ingesloten te worden.
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(inhoud)

    def _json(self, gegevens, code: int = 200) -> None:
        self._stuur(code, json.dumps(gegevens, ensure_ascii=False, default=str).encode("utf-8"))

    def _sleutel_klopt(self, vraag: dict) -> bool:
        """
        Vergelijkt de sleutel tijdsveilig (hmac.compare_digest), zodat je hem
        niet teken voor teken kunt raden.
        """
        gegeven = (vraag.get("sleutel") or [""])[0] or self.headers.get("X-Sleutel", "")
        return bool(gegeven) and hmac.compare_digest(str(gegeven), self.sleutel)

    # ---------------------------------------------------------- verzoeken

    def do_GET(self) -> None:  # noqa: N802 (naam komt van http.server)
        try:
            ontleed = urlparse(self.path)
            vraag = parse_qs(ontleed.query)

            if ontleed.path in ("/", "/index.html"):
                bestand = MAP / "dashboard.html"
                try:
                    self._stuur(200, bestand.read_bytes(), "text/html")
                except FileNotFoundError:
                    self._stuur(500, b"dashboard.html ontbreekt", "text/plain")
                return

            if not ontleed.path.startswith("/api/"):
                self._stuur(404, b"niet gevonden", "text/plain")
                return

            # Vanaf hier: elke API-aanroep vereist de sleutel.
            if not self._sleutel_klopt(vraag):
                self._json({"fout": "sleutel ontbreekt of klopt niet"}, 403)
                return

            if ontleed.path == "/api/status":
                self._json(self._status())
            elif ontleed.path == "/api/handel":
                aantal = self._aantal(vraag, 25, 100)
                self._json({"regels": self.staat.lees_handel(aantal)})
            elif ontleed.path == "/api/log":
                self._json({"regels": self._log(self._aantal(vraag, 40, 200))})
            else:
                self._json({"fout": "onbekende api"}, 404)
        except Exception as fout:
            # Het dashboard mag nooit de rest meeslepen.
            try:
                self._json({"fout": str(fout)}, 500)
            except Exception:
                pass

    def _aantal(self, vraag: dict, standaard: int, hoogste: int) -> int:
        try:
            return max(1, min(int((vraag.get("n") or [standaard])[0]), hoogste))
        except (ValueError, TypeError):
            return standaard

    def _log(self, aantal: int) -> list[str]:
        try:
            with open(GEGEVENS / "sniper.log", "r", encoding="utf-8-sig", errors="replace") as b:
                return [regel.rstrip() for regel in b.readlines()[-aantal:]]
        except FileNotFoundError:
            return ["(nog geen logboek)"]
        except Exception as fout:
            return [f"(logboek niet leesbaar: {fout})"]

    def _status(self) -> dict:
        gegevens = self.staat.lees()
        hartslag = gegevens.get("hartslag") or {}
        sniper = hartslag.get("sniper") or {} if isinstance(hartslag, dict) else {}
        leeftijd = self.staat.hartslag_leeftijd("sniper")
        tellers = self.staat.tel_resultaten()

        return {
            "tijd": time.time(),
            "draait": leeftijd is not None and leeftijd < 90,
            "stilte_s": None if leeftijd is None else int(leeftijd),
            "dryrun": gegevens.get("dryrun", True),
            "gepauzeerd": bool(gegevens.get("gepauzeerd")),
            "quickbuy": gegevens.get("quickbuy") or "niet gecontroleerd",
            "quickbuy_uitleg": gegevens.get("quickbuy_uitleg") or "",
            "bedrag": gegevens.get("bedrag"),
            "valuta": gegevens.get("valuta"),
            "chain": gegevens.get("chain"),
            "leesmodus": gegevens.get("leesmodus"),
            "db_pad": gegevens.get("db_pad"),
            "laatste_ms": sniper.get("laatste_ms"),
            "rec_id": sniper.get("rec_id"),
            "schrijffouten": sniper.get("schrijffouten", 0),
            "tellers_lopend": sniper.get("tellers") or {},
            "tellers_boek": {
                "gekocht": tellers.get(GEKOCHT, 0),
                "verstuurd": tellers.get(VERSTUURD, 0),
                "onbevestigd": tellers.get(ONBEKEND, 0),
                "mislukt": tellers.get(MISLUKT, 0),
                "dryrun": tellers.get(DRYRUN, 0),
                "geblokkeerd": tellers.get("geblokkeerd", 0),
            },
        }


def main() -> int:
    zet_uitvoer_op_utf8()
    opties = laad()
    logboek = maak_logboek("dashboard", opties.logniveau)

    sleutel = opties.dashboard_sleutel
    zelf_gemaakt = False
    if not sleutel:
        # Nooit zonder sleutel draaien. Dan maar er zelf één maken.
        sleutel = secrets.token_urlsafe(24)
        zelf_gemaakt = True

    Bediener.sleutel = sleutel
    Bediener.staat = Staat()
    Bediener.logboek = logboek

    poort = opties.dashboard_poort
    # Uitsluitend 127.0.0.1: alleen deze computer kan erbij.
    server = ThreadingHTTPServer(("127.0.0.1", poort), Bediener)

    print("=" * 66)
    print(f"Dashboard draait op:  http://127.0.0.1:{poort}/?sleutel={sleutel}")
    if zelf_gemaakt:
        print("\nEr stond geen sleutel in config.ini, dus deze is nu gemaakt.")
        print("Wil je steeds dezelfde link? Zet dan in config.ini onder [dashboard]:")
        print(f"    sleutel = {sleutel}")
    print("\nAlleen deze computer kan erbij (127.0.0.1). Elke API-aanroep")
    print("vereist de sleutel. Stoppen met ctrl-C.")
    print("=" * 66)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard gestopt.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
