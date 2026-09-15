"""
gereedschap.py — kleine hulpjes die elk programma nodig heeft.

Waarom dit bestand bestaat: twee dingen moeten in ELK programma als eerste
gebeuren, anders gaat het een keer 's nachts stuk:

1. De uitvoer op UTF-8 zetten. Memecoins heten dingen met emoji erin. Zonder
   deze regel klapt het programma eruit zodra het zo'n naam wil afdrukken.
2. Een logboek dat naar het scherm EN naar een bestand schrijft, zodat je
   achteraf kunt zien wat er gebeurd is.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import time
from pathlib import Path

# Basismap: de map waar dit bestand in staat.
MAP = Path(__file__).resolve().parent
GEGEVENS = MAP / "gegevens"


def zet_uitvoer_op_utf8() -> None:
    """
    Zorgt dat print() en het logboek niet stukgaan op emoji.

    Roep dit aan als ALLEREERSTE regel van elk programma. Zonder dit lag de
    Windows-versie van de wallet-monitor een hele nacht plat op een tokennaam
    met een emoji erin.
    """
    for stroom in (sys.stdout, sys.stderr):
        try:
            # errors="replace": liever een vraagteken dan een crash.
            stroom.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            # Oudere Python of een rare omgeving: dan maar zonder.
            pass


def zorg_voor_mappen() -> None:
    """Maakt de map voor logboeken en toestand aan als die nog niet bestaat."""
    GEGEVENS.mkdir(parents=True, exist_ok=True)


def maak_logboek(naam: str, niveau: str = "INFO") -> logging.Logger:
    """
    Maakt een logboek dat naar het scherm en naar gegevens/<naam>.log schrijft.

    Het logbestand rouleert bij 5 MB en bewaart 3 oude bestanden, zodat je
    schijf niet volloopt als de bot maanden draait.
    """
    zet_uitvoer_op_utf8()
    zorg_voor_mappen()

    logboek = logging.getLogger(naam)
    if logboek.handlers:
        # Al eerder aangemaakt; niet nog een keer dezelfde regels toevoegen.
        return logboek

    logboek.setLevel(getattr(logging, niveau.upper(), logging.INFO))
    opmaak = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    naar_scherm = logging.StreamHandler(sys.stdout)
    naar_scherm.setFormatter(opmaak)
    logboek.addHandler(naar_scherm)

    try:
        naar_bestand = logging.handlers.RotatingFileHandler(
            GEGEVENS / f"{naam}.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
            errors="replace",
        )
        naar_bestand.setFormatter(opmaak)
        logboek.addHandler(naar_bestand)
    except Exception as fout:
        # Kan niet naar bestand schrijven? Dan alleen naar het scherm. Het
        # logboek mag NOOIT de reden zijn dat de bot stopt.
        print(f"Waarschuwing: logbestand kon niet geopend worden: {fout}")

    logboek.propagate = False
    return logboek


def nu_ms() -> int:
    """Huidige tijd in milliseconden — voor het meten van snelheid."""
    return int(time.time() * 1000)


def kort(tekst: str, maximaal: int = 300) -> str:
    """Kort een tekst in voor in het logboek, zodat regels leesbaar blijven."""
    tekst = (tekst or "").replace("\n", " ⏎ ")
    if len(tekst) <= maximaal:
        return tekst
    return tekst[: maximaal - 1] + "…"


class EnkeleInstantie:
    """
    Zorgt dat er maar ÉÉN exemplaar van een programma draait.

    Waarom een socket en geen slotbestand: als het programma crasht of je trekt
    de stekker eruit, blijft een slotbestand achter en start je bot nooit meer.
    Een socket geeft het besturingssysteem vanzelf vrij zodra het proces weg is.

    Twee snipers tegelijk sturen hetzelfde adres twee keer door — dat koop je
    dus dubbel.
    """

    def __init__(self, poort: int) -> None:
        self.poort = poort
        self._socket = None

    def neem(self) -> bool:
        """Probeert de poort te claimen. True = jij bent de enige."""
        import socket

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Bewust GEEN SO_REUSEADDR: we willen juist dat een tweede
            # exemplaar hier stukloopt.
            s.bind(("127.0.0.1", self.poort))
            s.listen(1)
            self._socket = s
            return True
        except OSError:
            return False

    def geef_vrij(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None


def draait_al(poort: int) -> bool:
    """True als er al iets op deze poort luistert (dus: de bot draait)."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", poort)) == 0
