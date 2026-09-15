"""
staat.py — de gedeelde toestand: wat draait er, wat is er gekocht, wat is er al
een keer doorgestuurd.

De belangrijkste regel in dit bestand:

    HET WEGSCHRIJVEN VAN STATUS MAG NOOIT HET PROGRAMMA OMLEGGEN.

Het dashboard, de bedieningsbot en de waakhond lezen alle drie hetzelfde
statusbestand. Op het moment dat de sniper het wil vervangen kan een ander het
open hebben. Dat geeft een foutmelding — en als je die niet opvangt, valt je
hele sniper uit door een schrijffout in een informatiebestandje. Dat is precies
één keer echt gebeurd.

Daarom: elke schrijfactie zit in een vangnet, probeert het een paar keer
opnieuw, en gaat daarna gewoon door alsof er niets is.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from gereedschap import GEGEVENS, zorg_voor_mappen

STATUS_BESTAND = "status.json"
VERSTUURD_BESTAND = "verstuurd.txt"
HANDEL_BESTAND = "handel.jsonl"

# Hoe een aankoop ervoor staat. "verstuurd" en "gekocht" zijn met opzet twee
# verschillende dingen — zie valkuil 15. Als je die door elkaar haalt, lees je
# "gekocht" terwijl je niets hebt.
VERSTUURD = "verstuurd"       # bericht is de deur uit, meer weten we niet
GEKOCHT = "gekocht"           # BasedBot bevestigde een aankoop
MISLUKT = "mislukt"           # BasedBot zei duidelijk nee
ONBEKEND = "onbekend"         # geen of onbegrijpelijk antwoord -> NIET gekocht
DRYRUN = "dryrun"             # zou gekocht zijn, maar dryrun stond aan


class Staat:
    """Leest en schrijft de gedeelde bestanden in de map gegevens/."""

    def __init__(self, map_pad: Path | None = None) -> None:
        self.map = Path(map_pad) if map_pad else GEGEVENS
        self.map.mkdir(parents=True, exist_ok=True)
        self.status_pad = self.map / STATUS_BESTAND
        self.verstuurd_pad = self.map / VERSTUURD_BESTAND
        self.handel_pad = self.map / HANDEL_BESTAND
        self._slot = threading.RLock()
        self._verstuurd: set[str] | None = None
        self._verstuurd_gelezen_op = 0.0
        # Tellertje: hoe vaak ging schrijven mis? Zichtbaar in het dashboard,
        # zodat een stil probleem toch opvalt.
        self.schrijffouten = 0

    # ---------------- status.json ----------------

    def lees(self) -> dict[str, Any]:
        """Leest de status. Bij twijfel een lege dict — nooit een crash."""
        try:
            with open(self.status_pad, "r", encoding="utf-8-sig") as bestand:
                gegevens = json.load(bestand)
            return gegevens if isinstance(gegevens, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception:
            # Half geschreven bestand of rare inhoud: doe alsof hij leeg is.
            return {}

    def schrijf(self, gegevens: dict[str, Any]) -> bool:
        """
        Schrijft de status weg. Geeft True bij succes, False als het niet lukte.
        Gooit NOOIT een foutmelding omhoog.
        """
        gegevens = dict(gegevens)
        gegevens["bijgewerkt"] = time.time()
        try:
            tekst = json.dumps(gegevens, ensure_ascii=False, indent=1, default=str)
        except Exception:
            self.schrijffouten += 1
            return False

        # Eerst naar een tijdelijk bestand in dezelfde map, dan omwisselen.
        # Zo staat er nooit een half bestand op schijf.
        for poging in range(5):
            tijdelijk = None
            try:
                zorg_voor_mappen()
                fd, tijdelijk = tempfile.mkstemp(
                    dir=str(self.map), prefix=".status-", suffix=".tmp"
                )
                with os.fdopen(fd, "w", encoding="utf-8") as bestand:
                    bestand.write(tekst)
                    bestand.flush()
                    os.fsync(bestand.fileno())
                os.replace(tijdelijk, self.status_pad)
                return True
            except Exception:
                # Een ander proces heeft het bestand open. Even wachten en
                # nog eens proberen; steeds iets langer.
                if tijdelijk and os.path.exists(tijdelijk):
                    try:
                        os.unlink(tijdelijk)
                    except Exception:
                        pass
                time.sleep(0.05 * (poging + 1))

        self.schrijffouten += 1
        return False

    def werk_bij(self, **velden: Any) -> bool:
        """Past een paar velden aan en schrijft het geheel weg."""
        with self._slot:
            gegevens = self.lees()
            gegevens.update(velden)
            return self.schrijf(gegevens)

    def hartslag(self, onderdeel: str, extra: dict[str, Any] | None = None) -> bool:
        """
        Zet 'ik leef nog' voor een onderdeel. De waakhond kijkt hiernaar.
        Als een onderdeel te lang niets van zich laat horen, slaat die alarm.
        """
        with self._slot:
            gegevens = self.lees()
            kloppen = gegevens.get("hartslag")
            if not isinstance(kloppen, dict):
                kloppen = {}
            regel: dict[str, Any] = {"tijd": time.time()}
            if extra:
                regel.update(extra)
            kloppen[onderdeel] = regel
            gegevens["hartslag"] = kloppen
            return self.schrijf(gegevens)

    def hartslag_leeftijd(self, onderdeel: str) -> float | None:
        """Hoeveel seconden geleden gaf dit onderdeel voor het laatst een teken?"""
        kloppen = self.lees().get("hartslag") or {}
        regel = kloppen.get(onderdeel) if isinstance(kloppen, dict) else None
        if not isinstance(regel, dict) or "tijd" not in regel:
            return None
        try:
            return max(0.0, time.time() - float(regel["tijd"]))
        except Exception:
            return None

    # ---------------- verstuurde adressen ----------------

    def _laad_verstuurd(self) -> set[str]:
        """
        Houdt de lijst met al doorgestuurde adressen bij. Wordt opnieuw van
        schijf gelezen als het bestand veranderd is, zodat de bedieningsbot hem
        kan leegmaken zonder de sniper te herstarten.
        """
        try:
            gewijzigd = self.verstuurd_pad.stat().st_mtime
        except FileNotFoundError:
            gewijzigd = 0.0
        except Exception:
            gewijzigd = 0.0

        if self._verstuurd is None or gewijzigd != self._verstuurd_gelezen_op:
            adressen: set[str] = set()
            try:
                with open(self.verstuurd_pad, "r", encoding="utf-8-sig") as bestand:
                    for regel in bestand:
                        stuk = regel.split("\t", 1)[0].strip()
                        if stuk:
                            adressen.add(stuk)
            except FileNotFoundError:
                pass
            except Exception:
                # Onleesbaar bestand: dan liever een lege lijst dan een crash.
                pass
            self._verstuurd = adressen
            self._verstuurd_gelezen_op = gewijzigd
        return self._verstuurd

    def is_verstuurd(self, adres: str) -> bool:
        """Is dit adres al eens doorgestuurd? Zo ja: niet nog een keer kopen."""
        with self._slot:
            return adres.strip() in self._laad_verstuurd()

    def noteer_verstuurd(self, adres: str, notitie: str = "") -> None:
        """Schrijft een adres bij in de lijst. Faalt stil, nooit fataal."""
        adres = adres.strip()
        if not adres:
            return
        with self._slot:
            huidig = self._laad_verstuurd()
            if adres in huidig:
                return
            huidig.add(adres)
            regel = f"{adres}\t{time.strftime('%Y-%m-%d %H:%M:%S')}\t{notitie}\n"
            try:
                with open(self.verstuurd_pad, "a", encoding="utf-8") as bestand:
                    bestand.write(regel)
                    bestand.flush()
                self._verstuurd_gelezen_op = self.verstuurd_pad.stat().st_mtime
            except Exception:
                self.schrijffouten += 1

    def vergeet_verstuurd(self, adres: str) -> bool:
        """Haalt één adres uit de lijst, zodat je het opnieuw kunt kopen."""
        adres = adres.strip()
        with self._slot:
            regels: list[str] = []
            try:
                with open(self.verstuurd_pad, "r", encoding="utf-8-sig") as bestand:
                    regels = bestand.readlines()
            except FileNotFoundError:
                return False
            except Exception:
                return False
            overblijvend = [r for r in regels if r.split("\t", 1)[0].strip() != adres]
            if len(overblijvend) == len(regels):
                return False
            try:
                with open(self.verstuurd_pad, "w", encoding="utf-8") as bestand:
                    bestand.writelines(overblijvend)
                self._verstuurd = None  # opnieuw inlezen
                return True
            except Exception:
                self.schrijffouten += 1
                return False

    # ---------------- handelsboek ----------------

    def noteer_handel(self, regel: dict[str, Any]) -> None:
        """
        Schrijft één regel bij in het handelsboek (één JSON per regel).
        Hierin staat ALTIJD apart of iets alleen verstuurd is of echt gekocht.
        """
        regel = dict(regel)
        regel.setdefault("tijd", time.time())
        regel.setdefault("tijd_leesbaar", time.strftime("%Y-%m-%d %H:%M:%S"))
        try:
            with open(self.handel_pad, "a", encoding="utf-8") as bestand:
                bestand.write(json.dumps(regel, ensure_ascii=False, default=str) + "\n")
                bestand.flush()
        except Exception:
            self.schrijffouten += 1

    def lees_handel(self, aantal: int = 25) -> list[dict[str, Any]]:
        """Haalt de laatste regels uit het handelsboek op, nieuwste eerst."""
        try:
            with open(self.handel_pad, "r", encoding="utf-8-sig") as bestand:
                regels = bestand.readlines()
        except FileNotFoundError:
            return []
        except Exception:
            return []

        uitkomst: list[dict[str, Any]] = []
        for regel in reversed(regels[-max(aantal, 1) * 3:]):
            regel = regel.strip()
            if not regel:
                continue
            try:
                waarde = json.loads(regel)
            except Exception:
                continue  # kapotte regel overslaan, niet struikelen
            if isinstance(waarde, dict):
                uitkomst.append(waarde)
            if len(uitkomst) >= aantal:
                break
        return uitkomst

    def tel_resultaten(self) -> dict[str, int]:
        """Telt hoe vaak elk resultaat voorkwam — voor het dashboard."""
        tellers: dict[str, int] = {}
        try:
            with open(self.handel_pad, "r", encoding="utf-8-sig") as bestand:
                for regel in bestand:
                    regel = regel.strip()
                    if not regel:
                        continue
                    try:
                        waarde = json.loads(regel)
                    except Exception:
                        continue
                    soort = str(waarde.get("resultaat", "?"))
                    tellers[soort] = tellers.get(soort, 0) + 1
        except FileNotFoundError:
            pass
        except Exception:
            pass
        return tellers

    # ---------------- opdrachten van de bedieningsbot ----------------
    #
    # De sniper heeft de Telegram-verbinding in handen; de bedieningsbot niet.
    # (Twee clients met dezelfde sessie krijgen geen updates meer — zie
    # telegram_brug.py.) De bedieningsbot legt daarom een opdracht neer in een
    # bestandje, en de sniper pikt die in zijn eigen lus op.

    def zet_opdracht(self, opdracht: dict[str, Any]) -> bool:
        """Legt een opdracht klaar voor de sniper. Faalt stil."""
        opdracht = dict(opdracht)
        opdracht.setdefault("tijd", time.time())
        try:
            with open(self.map / "opdrachten.jsonl", "a", encoding="utf-8") as bestand:
                bestand.write(json.dumps(opdracht, ensure_ascii=False, default=str) + "\n")
                bestand.flush()
            return True
        except Exception:
            self.schrijffouten += 1
            return False

    def neem_opdrachten(self) -> list[dict[str, Any]]:
        """Haalt de klaarliggende opdrachten op en maakt het bestand leeg."""
        pad = self.map / "opdrachten.jsonl"
        with self._slot:
            try:
                with open(pad, "r", encoding="utf-8-sig") as bestand:
                    regels = bestand.readlines()
            except FileNotFoundError:
                return []
            except Exception:
                return []
            if not regels:
                return []
            try:
                # Leegmaken vóór uitvoeren: liever een opdracht kwijt dan hem
                # twee keer uitvoeren. Twee keer verkopen kost geld.
                with open(pad, "w", encoding="utf-8"):
                    pass
            except Exception:
                self.schrijffouten += 1

            uitkomst: list[dict[str, Any]] = []
            for regel in regels:
                regel = regel.strip()
                if not regel:
                    continue
                try:
                    waarde = json.loads(regel)
                except Exception:
                    continue
                if isinstance(waarde, dict):
                    uitkomst.append(waarde)
            return uitkomst
