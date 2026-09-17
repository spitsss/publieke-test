"""
filters.py — bepaalt of een melding überhaupt meetelt.

Dit filter is VERPLICHT. Zonder kanaalfilter reageert de bot op élke
Discord-melding: ook op een privébericht van een vriend die een adres plakt,
of op een willekeurig ander kanaal van dezelfde server.

Hoe een Discord-melding er ECHT uitziet (afgekeken van een echte Mac):

    titel  "KOOBY (#💵|algemene-chat, Algemeen)"     <- kanaal in een server
    titel  "Thexrpjunk (#☕|koffiehuis🔞, 🔥 Lifestyle)"  <- met emoji in de naam
    titel  "Sander"                                  <- privébericht (DM)
    titel  "#microcaps-calls (Test)"                 <- zelf afgevuurde testmelding
    body   de berichttekst zelf

Let op hoe rommelig dat is: eerst de naam van de afzender, dan tussen haakjes
het kanaal met een emoji en een liggend streepje ervoor, een komma, en dan de
server. Wie hier alleen naar "#iets" zoekt, haalt "💵|algemene-chat," uit de
titel — mét emoji, streepje en komma — en matcht dus nooit met wat jij in
config.ini hebt getypt. Daarom knippen we het netjes uit elkaar.

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

# Het stuk achter een # tot aan een komma, een haakje of een spatie.
# De komma en de haakjes horen NIET bij de kanaalnaam.
_KANAAL_IN_TITEL = re.compile(r"#\s*([^\s,()]+)")

# Wat overblijft als je emoji en leestekens weghaalt: letters, cijfers,
# streepje en liggend streepje.
_ALLEEN_LETTERS = re.compile(r"[^0-9a-z\u00e0-\u00ff_-]+")


def kanaal_uit_titel(titel: str) -> str:
    """
    Haalt de kanaalnaam uit de titel, zonder #, zonder emoji ervoor en zonder
    komma erachter.

        "KOOBY (#💵|algemene-chat, Algemeen)"  ->  "algemene-chat"
        "#microcaps-calls (Test)"              ->  "microcaps-calls"
        "Sander"                               ->  ""  (privébericht)
    """
    treffer = _KANAAL_IN_TITEL.search(titel or "")
    if not treffer:
        return ""
    naam = treffer.group(1).strip()
    # Discord zet soms een emoji vóór de naam, met een liggend streepje ertussen:
    # "💵|algemene-chat". De echte naam staat achter het laatste streepje.
    if "|" in naam:
        naam = naam.rsplit("|", 1)[-1]
    return naam.strip().strip(",.;:").lower()


def vereenvoudig(naam: str) -> str:
    """
    Haalt emoji en leestekens uit een kanaalnaam, zodat "koffiehuis🔞" ook
    matcht als jij gewoon "koffiehuis" in config.ini hebt getypt. Anders zou je
    emoji moeten kunnen typen om je eigen kanaal op te geven.
    """
    return _ALLEEN_LETTERS.sub("", (naam or "").lower())


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
        if not naam or not kanaal:
            continue
        if kanaal == naam:
            return True, f"kanaal #{kanaal}"
        # Tweede kans zonder emoji: "koffiehuis" matcht dan ook "koffiehuis🔞".
        if vereenvoudig(kanaal) and vereenvoudig(kanaal) == vereenvoudig(naam):
            return True, f"kanaal #{kanaal} (op naam zonder emoji)"

    return False, f"'{volledig}' staat niet in de kanaallijst"
