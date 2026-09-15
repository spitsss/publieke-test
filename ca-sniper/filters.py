"""
filters.py — bepaalt of een melding überhaupt meetelt.

Dit filter is VERPLICHT. Zonder kanaalfilter reageert de bot op élke
Discord-melding: ook op een privébericht van een vriend die een adres plakt,
of op een willekeurig ander kanaal van dezelfde server.

Hoe een Discord-melding eruitziet:

    titel      "#microcaps-calls (Alpha Group)"   <- kanaal in een server
    titel      "Sander"                           <- privébericht (DM)
    ondertitel soms de servernaam of de afzender
    body       de berichttekst zelf

Hoe je een kanaal opgeeft in config.ini, onder [filter] kanalen:

    microcaps-calls          precies dit kanaal   <- gebruik dit meestal
    bevat:Alpha Group        komt ergens in de titel voor: dus de hele server
    re:#(calls|alpha)\\b      een eigen zoekpatroon, voor gevorderden

Het hekje mag je weglaten. Schrijf je het er toch bij op een INGESPRONGEN
regel, dan ziet het instellingenbestand die regel als commentaar en verdwijnt
je kanaal stilletjes. Daarom laten we het hekje hier gewoon weg — en weigert
de bot te starten als de kanaallijst leeg blijkt.
"""

from __future__ import annotations

import re

# Uit "#microcaps-calls (Alpha Group)" halen we "microcaps-calls".
_KANAAL_IN_TITEL = re.compile(r"#\s*([^\s()]+)")


def kanaal_uit_titel(titel: str) -> str:
    """Geeft de kanaalnaam zonder # terug, of een lege tekst als er geen staat."""
    treffer = _KANAAL_IN_TITEL.search(titel or "")
    return treffer.group(1).strip().lower() if treffer else ""


def is_privebericht(titel: str, ondertitel: str = "") -> bool:
    """
    Een melding zonder # in de titel is vrijwel altijd een privébericht of een
    groeps-DM. Dat is een vuistregel, geen wet — daarom mag je met
    'sta_dm_toe' in config.ini alsnog DM's toelaten.
    """
    return not kanaal_uit_titel(f"{titel or ''} {ondertitel or ''}")


def kanaal_toegestaan(
    titel: str,
    ondertitel: str,
    kanalen: list[str],
    sta_dm_toe: bool = False,
) -> tuple[bool, str]:
    """
    Mag deze melding door? Geeft (ja/nee, uitleg) terug. Die uitleg komt in het
    logboek, zodat je bij een gemiste call kunt zien waarom hij eruit viel.
    """
    titel = titel or ""
    ondertitel = ondertitel or ""
    volledig = f"{titel} {ondertitel}".strip()

    if not kanalen:
        # Bewust dicht: liever niets kopen dan alles.
        return False, "geen kanaalfilter ingesteld — alles wordt geweigerd"

    dm = is_privebericht(titel, ondertitel)
    if dm and not sta_dm_toe:
        return False, "privébericht (DM), en DM's staan uit"

    kanaal = kanaal_uit_titel(volledig)

    for patroon in kanalen:
        patroon = patroon.strip()
        if not patroon:
            continue

        if patroon.lower().startswith("re:"):
            try:
                if re.search(patroon[3:], volledig, re.IGNORECASE):
                    return True, f"patroon '{patroon}'"
            except re.error:
                # Een kapot zoekpatroon in config.ini mag de bot niet slopen.
                continue
            continue

        if patroon.lower().startswith("bevat:"):
            stuk = patroon[6:].strip()
            if stuk and stuk.lower() in volledig.lower():
                return True, f"tekst '{stuk}'"
            continue

        # Alles wat overblijft is een kanaalnaam. Een hekje ervoor mag, maar
        # hoeft niet. "calls" matcht exact het kanaal #calls, dus NIET
        # #calls-vip — dat is met opzet streng.
        naam = patroon.lstrip("#").strip().lower()
        if naam and kanaal and kanaal == naam:
            return True, f"kanaal #{naam}"

    return False, f"'{volledig}' staat niet in de kanaallijst"
