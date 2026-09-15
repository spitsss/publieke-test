"""
instellingen.py — leest config.ini en controleert of alles klopt.

Twee dingen die hier bewust gebeuren:

* Het bestand wordt gelezen als "utf-8-sig". Als je config.ini in Kladblok of
  TextEdit opslaat, zet die er soms een onzichtbaar teken vooraan. Zonder
  "-sig" crasht Python daarop met de onbegrijpelijke melding
  "File contains no section headers".
* Ontbreekt er iets belangrijks, dan stopt het programma METEEN met een
  duidelijke uitleg. Stil doorgaan met verkeerde gegevens is hier het
  gevaarlijkst wat er is.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import configparser
except ImportError:  # pragma: no cover
    raise SystemExit("Python is niet compleet geïnstalleerd (configparser ontbreekt).")

MAP = Path(__file__).resolve().parent
STANDAARD_PAD = MAP / "config.ini"
VOORBEELD_PAD = MAP / "config.ini.voorbeeld"


class InstellingFout(Exception):
    """Er klopt iets niet aan config.ini. De tekst legt uit wat."""


# Waarden die als "ja" tellen. Alles wat hier niet in staat is "nee".
_JA = {"ja", "j", "aan", "waar", "true", "1", "yes", "y", "on"}


class Instellingen:
    """Alle instellingen uit config.ini, met vangnetten en controles."""

    def __init__(self, pad: Path | str | None = None) -> None:
        self.pad = Path(pad) if pad else STANDAARD_PAD
        # LET OP: alleen ';' geldt als commentaar áchter een waarde. Zou '#'
        # dat ook doen, dan verdwijnt een kanaalnaam als '#microcaps-calls'
        # stilletjes en reageert de bot nergens meer op. Een regel die MET een
        # # begint blijft gewoon commentaar.
        self._c = configparser.ConfigParser(inline_comment_prefixes=(";",))

        if not self.pad.exists():
            raise InstellingFout(
                f"Ik vind {self.pad} niet.\n"
                f"Kopieer {VOORBEELD_PAD.name} naar config.ini en vul hem in:\n"
                f"    cp {VOORBEELD_PAD.name} config.ini"
            )

        try:
            # utf-8-sig: slikt het onzichtbare BOM-teken van teksteditors.
            with open(self.pad, "r", encoding="utf-8-sig") as bestand:
                self._c.read_file(bestand)
        except configparser.Error as fout:
            raise InstellingFout(
                f"config.ini is niet leesbaar: {fout}\n"
                "Let op dat elke sectie tussen [blokhaken] staat."
            ) from fout

    # ---------- basale ophalers ----------

    def tekst(self, sectie: str, sleutel: str, standaard: str = "") -> str:
        return self._c.get(sectie, sleutel, fallback=standaard).strip()

    def getal(self, sectie: str, sleutel: str, standaard: int) -> int:
        rauw = self.tekst(sectie, sleutel, str(standaard))
        if not rauw:
            return standaard  # niet ingevuld = standaardwaarde, geen crash
        try:
            return int(rauw)
        except ValueError:
            raise InstellingFout(
                f"[{sectie}] {sleutel} moet een heel getal zijn, maar er staat '{rauw}'."
            )

    def kommagetal(self, sectie: str, sleutel: str, standaard: float) -> float:
        rauw = self.tekst(sectie, sleutel, str(standaard)).replace(",", ".")
        if not rauw:
            return standaard
        try:
            return float(rauw)
        except ValueError:
            raise InstellingFout(
                f"[{sectie}] {sleutel} moet een getal zijn, maar er staat '{rauw}'."
            )

    def aan(self, sectie: str, sleutel: str, standaard: bool) -> bool:
        rauw = self.tekst(sectie, sleutel, "ja" if standaard else "nee").lower()
        return rauw in _JA

    def lijst(self, sectie: str, sleutel: str, standaard: str = "") -> list[str]:
        """
        Leest een lijst. Items mogen gescheiden zijn door komma's of nieuwe
        regels, zodat je in config.ini gewoon onder elkaar kunt typen.
        """
        rauw = self._c.get(sectie, sleutel, fallback=standaard)
        stukken = re.split(r"[,\n]", rauw or "")
        return [s.strip() for s in stukken if s.strip()]

    def zet(self, sectie: str, sleutel: str, waarde: str) -> None:
        """
        Past een instelling aan zolang het programma draait (niet in het
        bestand). Maakt de sectie aan als die ontbreekt, zodat een config.ini
        zonder [algemeen] hier niet op stukloopt.
        """
        if not self._c.has_section(sectie):
            self._c.add_section(sectie)
        self._c.set(sectie, sleutel, waarde)

    # ---------- de instellingen zelf ----------

    @property
    def dryrun(self) -> bool:
        """AAN = niets kopen, alleen opschrijven wat hij zou doen."""
        return self.aan("algemeen", "dryrun", True)

    @property
    def logniveau(self) -> str:
        return self.tekst("algemeen", "logniveau", "INFO").upper()

    @property
    def instantie_poort(self) -> int:
        return self.getal("algemeen", "instantie_poort", 47611)

    # meldingen
    @property
    def db_pad(self) -> str:
        return self.tekst("meldingen", "db_pad", "auto")

    @property
    def bundle_ids(self) -> list[str]:
        return self.lijst("meldingen", "bundle_ids", "com.hnc.Discord")

    @property
    def poll_ms(self) -> int:
        waarde = self.getal("meldingen", "poll_ms", 150)
        # Onder de 50 ms vraag je de database stuk zonder dat het sneller wordt.
        return max(50, min(waarde, 2000))

    @property
    def leesmodus(self) -> str:
        return self.tekst("meldingen", "leesmodus", "auto").lower()

    # filter
    @property
    def kanalen(self) -> list[str]:
        return self.lijst("filter", "kanalen")

    @property
    def sta_dm_toe(self) -> bool:
        return self.aan("filter", "sta_dm_toe", False)

    @property
    def negeerwoorden(self) -> list[str]:
        return self.lijst("filter", "negeerwoorden")

    @property
    def meerdere_adressen(self) -> str:
        keuze = self.tekst("filter", "meerdere_adressen", "weiger").lower()
        if keuze not in ("weiger", "eerste"):
            raise InstellingFout(
                "[filter] meerdere_adressen moet 'weiger' of 'eerste' zijn."
            )
        return keuze

    # chains
    @property
    def basedbot_chain(self) -> str:
        chain = self.tekst("chains", "basedbot_chain", "").lower()
        if not chain:
            raise InstellingFout(
                "[chains] basedbot_chain is leeg. Vul in op welke chain BasedBot "
                "op dit moment staat (bijvoorbeeld: solana, base, ethereum, bsc)."
            )
        return chain

    @property
    def chaincontrole(self) -> str:
        stand = self.tekst("chains", "chaincontrole", "slim").lower()
        if stand not in ("slim", "warn", "off"):
            raise InstellingFout(
                "[chains] chaincontrole moet 'slim', 'warn' of 'off' zijn."
            )
        return stand

    @property
    def dexscreener_limiet_ms(self) -> int:
        return self.getal("chains", "dexscreener_limiet_ms", 1500)

    # telegram (naar BasedBot)
    @property
    def api_id(self) -> int:
        return self.getal("telegram", "api_id", 0)

    @property
    def api_hash(self) -> str:
        return self.tekst("telegram", "api_hash")

    @property
    def sessienaam(self) -> str:
        return self.tekst("telegram", "sessienaam", "gegevens/sniper")

    @property
    def basedbot(self) -> str:
        return self.tekst("telegram", "basedbot", "@BasedBot")

    @property
    def antwoord_wacht_s(self) -> float:
        return self.kommagetal("telegram", "antwoord_wacht_s", 12.0)

    # handel
    @property
    def bedrag(self) -> float:
        """VAST bedrag per call. Bewust geen percentage van je saldo."""
        return self.kommagetal("handel", "bedrag", 0.0)

    @property
    def valuta(self) -> str:
        return self.tekst("handel", "valuta", "SOL")

    @property
    def zelf_verkopen(self) -> bool:
        return self.aan("handel", "zelf_verkopen", False)

    # bediening
    @property
    def bedien_token(self) -> str:
        return self.tekst("bediening", "bot_token")

    @property
    def toegestane_id(self) -> int:
        return self.getal("bediening", "toegestane_id", 0)

    # dashboard
    @property
    def dashboard_poort(self) -> int:
        return self.getal("dashboard", "poort", 8787)

    @property
    def dashboard_sleutel(self) -> str:
        return self.tekst("dashboard", "sleutel")

    # ---------- controle vooraf ----------

    def controleer_voor_sniper(self) -> list[str]:
        """
        Kijkt of de sniper kán draaien. Geeft een lijst met problemen terug;
        leeg betekent: in orde.
        """
        problemen: list[str] = []

        if not self.api_id or not self.api_hash:
            problemen.append(
                "[telegram] api_id en api_hash zijn leeg. Haal ze op bij "
                "https://my.telegram.org → API development tools."
            )
        if not self.basedbot:
            problemen.append("[telegram] basedbot is leeg (bijvoorbeeld @BasedBot).")

        if not self.kanalen and not self.sta_dm_toe:
            problemen.append(
                "[filter] kanalen is leeg. Zonder kanaalfilter reageert de bot op "
                "ELKE Discord-melding — ook op een privébericht van een vriend die "
                "toevallig een adres plakt. Vul minstens één kanaal in."
            )

        if not self.dryrun and self.bedrag <= 0:
            problemen.append(
                "[handel] bedrag is 0 terwijl dryrun uit staat. Zet een vast bedrag "
                "per call (bijvoorbeeld 0.05)."
            )

        try:
            _ = self.basedbot_chain
        except InstellingFout as fout:
            problemen.append(str(fout))

        return problemen


def laad(pad: Path | str | None = None) -> Instellingen:
    """Laadt de instellingen of stopt met een duidelijke uitleg."""
    try:
        return Instellingen(pad)
    except InstellingFout as fout:
        print(f"\nFOUT IN DE INSTELLINGEN\n{'-' * 23}\n{fout}\n", file=sys.stderr)
        raise SystemExit(2)
