"""
exits.py — herkent in gewone taal of iemand zegt dat je moet verkopen.

Dit is lastiger dan het lijkt, want in een callskanaal staat over hetzelfde
onderwerp van alles dat GEEN opdracht is:

    "haal een deel of je initials eruit"   -> dit IS een opdracht
    "Initials betekent je inleg!"          -> dit is UITLEG, niet vuren
    "Wanneer moeten we winst nemen?"       -> dit is een VRAAG, niet vuren
    "niet verkopen, we houden vast"        -> dit is het TEGENOVERGESTELDE

De aanpak is daarom met drie zeven:

  zeef 1  is het een vraag?           -> dan nooit
  zeef 2  is het uitleg of ontkennend? -> dan nooit
  zeef 3  staat er een WERKWOORD (haal, verkoop, neem, take, sell) én een
          DOELWIT (initials, winst, deel, alles) in? -> pas dan een signaal

Elke zin wordt apart bekeken. "Initials betekent je inleg! Haal ze er nu uit."
moet namelijk wél vuren, op die tweede zin.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---- zeef 1: vragen ----
VRAAGWOORDEN = (
    r"^\s*(wanneer|hoe|wat|waarom|wie|welke|moeten?\s+we|zullen\s+we|zal\s+ik|"
    r"when|how|what|why|who|which|should\s+(?:we|i)|do\s+(?:we|i|you)|is\s+it|are\s+we)\b"
)

# ---- zeef 2: uitleg en ontkenning ----
UITLEGWOORDEN = (
    r"\b(betekent|beteken|bedoelt|bedoel\s+ik|staat\s+voor|is\s+wanneer|uitleg|"
    r"means|meaning|stands\s+for|refers\s+to|definition|is\s+when|in\s+other\s+words|"
    r"dat\s+wil\s+zeggen|oftewel|ter\s+info|for\s+reference|fyi)\b"
)
ONTKENNING = (
    r"\b(niet\s+verkopen|nog\s+niet\s+verkopen|niet\s+uitstappen|blijf\s+zitten|"
    r"vasthouden|hold(?:en|ing)?\b|don'?t\s+sell|do\s+not\s+sell|not\s+selling|"
    r"no\s+need\s+to\s+sell|geen\s+reden\s+om\s+te\s+verkopen)"
)

# ---- zeef 3: werkwoord + doelwit ----
WERKWOORDEN = (
    r"\b(haal|haalt|pak|pakt|neem|neemt|verkoop|verkopen|verkocht|stap|stappen|"
    r"sell|selling|take|taking|secure|trim|scale\s+out|derisk|de-risk|exit|dump|"
    r"close|cash\s+out)\b"
)

DOELWITTEN = {
    "initials": r"\b(initials?|inleg|instap|entry\s+back|je\s+geld\s+terug|"
                r"break\s*even|original(?:s)?)\b",
    "deel": r"\b(deel|helft|stuk|gedeelte|wat\s+winst|winst|profit|profits|tp\b|"
            r"half|some|partial|beetje|paar\s+procent|\d{1,3}\s*%)",
    "alles": r"\b(alles|volledig|helemaal|all|everything|full\s+exit|full\s+send\s+out|"
             r"complete(?:ly)?)\b",
}

# Uitdrukkingen die "eruit stappen" betekenen zonder dat ze het doelwit
# noemen: "haal ze er nu uit", "take them out". Die zijn een signaal, maar we
# weten niet HOEVEEL. Ze krijgen daarom zeker=False: de bot meldt ze wel, maar
# verkoopt er nooit blind op. Een onnodige verkoop kost net zo goed geld.
UITSTAP_UITDRUKKINGEN = (
    # "eruit", maar ook "er nu uit" / "er even uit": er mag wat tussen staan.
    r"\beruit\b|\ber\b[^.!?]{0,15}\buit\b|\buit\s*stappen\b|"
    r"\b(?:take|get|pull)\b[^.!?]{0,15}\bout\b"
)

# Percentages halen we los op: "verkoop 50%" -> deel 50.
PERCENTAGE = re.compile(r"(\d{1,3})\s*%")


@dataclass
class Exitsignaal:
    """Wat we uit een bericht hebben opgemaakt."""

    gevonden: bool = False
    soort: str = ""       # "initials", "deel" of "alles"
    deel: str = ""        # bijvoorbeeld "50" of "initials"
    zin: str = ""         # de zin waar het uit kwam
    reden: str = ""       # waarom wel of niet
    zeker: bool = True    # False = wel een signaal, maar hoeveel is onduidelijk

    def __bool__(self) -> bool:
        return self.gevonden


def _zinnen(tekst: str) -> list[str]:
    """Knipt een bericht in zinnen, inclusief de leestekens."""
    tekst = (tekst or "").strip()
    if not tekst:
        return []
    stukken = re.split(r"(?<=[.!?\n])\s+", tekst)
    return [stuk.strip() for stuk in stukken if stuk.strip()]


def zoek_exit(tekst: str) -> Exitsignaal:
    """
    Kijkt of dit bericht een verkoopopdracht bevat.
    Bij twijfel: GEEN signaal. Onnodig verkopen kost geld.
    """
    for zin in _zinnen(tekst):
        kaal = zin.strip()
        laag = kaal.lower()

        # zeef 1: vragen
        if kaal.endswith("?") or re.search(VRAAGWOORDEN, laag):
            continue

        # zeef 2: uitleg of ontkenning
        if re.search(UITLEGWOORDEN, laag) or re.search(ONTKENNING, laag):
            continue

        # zeef 3: werkwoord én doelwit
        if not re.search(WERKWOORDEN, laag):
            continue

        for soort in ("initials", "alles", "deel"):
            if re.search(DOELWITTEN[soort], laag):
                deel = soort
                if soort == "deel":
                    percentage = PERCENTAGE.search(laag)
                    deel = percentage.group(1) if percentage else "50"
                elif soort == "alles":
                    deel = "100"
                else:
                    deel = "initials"
                return Exitsignaal(
                    gevonden=True,
                    soort=soort,
                    deel=deel,
                    zin=kaal,
                    reden=f"werkwoord + doelwit '{soort}' in: {kaal[:80]}",
                    zeker=True,
                )

        # Geen doelwit, maar wel een uitstap-uitdrukking: "haal ze er nu uit".
        # Wel melden, niet automatisch op handelen.
        if re.search(UITSTAP_UITDRUKKINGEN, laag):
            return Exitsignaal(
                gevonden=True,
                soort="deel",
                deel="50",
                zin=kaal,
                reden=f"uitstap-uitdrukking zonder duidelijke hoeveelheid: {kaal[:80]}",
                zeker=False,
            )

    return Exitsignaal(False, reden="geen opdracht om te verkopen gevonden")
