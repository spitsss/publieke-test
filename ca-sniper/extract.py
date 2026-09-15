"""
extract.py — haalt contractadressen uit een stuk tekst.

Dit bestand bepaalt WAT er gekocht wordt. Een fout hier kost direct geld, dus
alles is streng en er zijn echte tests voor (tests/test_extract.py).

De drie dingen die hier goed moeten gaan:

1. Een Solana-adres is base58 van 32 tot 44 tekens dat naar PRECIES 32 bytes
   decodeert. Een Solana-handtekening (88 tekens) en een transactiehash
   (64 hex-tekens) lijken erop, maar zijn het niet. Die mogen nooit matchen —
   anders stuurt de bot een transactienummer door alsof het een token is.

2. Een link naar Dexscreener wijst naar een POOL, niet naar het token. Koop je
   het pooladres, dan koop je iets heel anders dan de call. Pools worden apart
   behandeld en via de Dexscreener-API omgezet naar het echte tokenadres, of
   anders overgeslagen.

3. Negeerwoorden gelden op HELE woorden. "rug" mag niet matchen in "terug" of
   "brug" — dat kostte bijna een gemiste call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Het base58-alfabet van Bitcoin/Solana: geen 0, geen hoofdletter O, geen
# hoofdletter I en geen kleine l, want die lijken te veel op elkaar.
BASE58_ALFABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_BASE58_WAARDE = {teken: i for i, teken in enumerate(BASE58_ALFABET)}


def base58_decodeer(tekst: str) -> bytes | None:
    """
    Zet base58 om naar bytes. Geeft None terug als er een teken in staat dat
    niet in het alfabet hoort.
    """
    if not tekst:
        return None
    getal = 0
    for teken in tekst:
        waarde = _BASE58_WAARDE.get(teken)
        if waarde is None:
            return None
        getal = getal * 58 + waarde

    # Omzetten naar bytes.
    rauw = b""
    while getal > 0:
        rauw = bytes([getal & 0xFF]) + rauw
        getal >>= 8

    # Elke '1' vooraan staat voor een nulbyte vooraan.
    nullen = len(tekst) - len(tekst.lstrip("1"))
    return b"\x00" * nullen + rauw


def is_solana_adres(tekst: str) -> bool:
    """
    Een geldig Solana-adres: 32 tot 44 base58-tekens die naar precies 32 bytes
    decoderen. Die 32 bytes zijn de echte controle — op lengte alleen glipt er
    van alles doorheen.
    """
    if not (32 <= len(tekst) <= 44):
        return False
    rauw = base58_decodeer(tekst)
    return rauw is not None and len(rauw) == 32


def is_evm_adres(tekst: str) -> bool:
    """Een EVM-adres: 0x gevolgd door precies 40 hex-tekens."""
    return bool(re.fullmatch(r"0x[a-fA-F0-9]{40}", tekst))


# Een kandidaat mag links en rechts niet tegen een letter of cijfer aan staan.
# Daardoor wordt een hash van 64 tekens één lang stuk (en dus te lang), in
# plaats van dat er een stukje van 43 tekens uit geknipt wordt.
_GEEN_BUURMAN_LINKS = r"(?<![0-9A-Za-z])"
_GEEN_BUURMAN_RECHTS = r"(?![0-9A-Za-z])"

EVM_PATROON = re.compile(_GEEN_BUURMAN_LINKS + r"(0x[a-fA-F0-9]{40})" + _GEEN_BUURMAN_RECHTS)
BASE58_PATROON = re.compile(
    _GEEN_BUURMAN_LINKS + r"([1-9A-HJ-NP-Za-km-z]{32,44})" + _GEEN_BUURMAN_RECHTS
)
URL_PATROON = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)


@dataclass
class Vondst:
    """Eén gevonden adres, plus waar het vandaan komt."""

    adres: str
    soort: str            # "evm" of "solana"
    bron: str             # "tekst", "token-link" of "pool-link"
    chain_hint: str = ""  # wat de link zegt over de chain, bijvoorbeeld "base"
    ruw: str = ""         # het stuk tekst waar het uit kwam


@dataclass
class Resultaat:
    """Alles wat we uit één melding hebben gehaald."""

    vondsten: list[Vondst] = field(default_factory=list)
    pools: list[Vondst] = field(default_factory=list)
    notities: list[str] = field(default_factory=list)


# Links die naar een POOL wijzen. Het adres hierin is NOOIT het token.
POOL_LINKS = [
    (re.compile(r"dexscreener\.com/([a-zA-Z0-9-]+)/([A-Za-z0-9]{25,60})"), 1, 2),
    (re.compile(r"geckoterminal\.com/([a-zA-Z0-9-]+)/pools/([A-Za-z0-9]{25,60})"), 1, 2),
    (re.compile(r"dextools\.io/app/[^/]+/([a-zA-Z0-9-]+)/pair-explorer/([A-Za-z0-9]{25,60})"), 1, 2),
]

# Links die wél direct naar een token wijzen.
TOKEN_LINKS = [
    (re.compile(r"birdeye\.so/token/([A-Za-z0-9]{32,44})"), "solana"),
    (re.compile(r"solscan\.io/token/([A-Za-z0-9]{32,44})"), "solana"),
    (re.compile(r"pump\.fun/(?:coin/)?([A-Za-z0-9]{32,44})"), "solana"),
    (re.compile(r"jup\.ag/swap/[A-Za-z0-9]+-([A-Za-z0-9]{32,44})"), "solana"),
    (re.compile(r"etherscan\.io/(?:token|address)/(0x[a-fA-F0-9]{40})"), "ethereum"),
    (re.compile(r"basescan\.org/(?:token|address)/(0x[a-fA-F0-9]{40})"), "base"),
    (re.compile(r"bscscan\.com/(?:token|address)/(0x[a-fA-F0-9]{40})"), "bsc"),
    (re.compile(r"arbiscan\.io/(?:token|address)/(0x[a-fA-F0-9]{40})"), "arbitrum"),
    (
        re.compile(r"robinhoodchain\.blockscout\.com/(?:token|address)/(0x[a-fA-F0-9]{40})"),
        "robinhood",
    ),
]


def _normaliseer(adres: str, soort: str) -> str:
    """
    EVM-adressen zetten we in kleine letters, zodat hetzelfde token niet twee
    keer gekocht wordt omdat iemand het met hoofdletters plakte. Solana-adressen
    blijven precies zoals ze zijn — daar betekent een hoofdletter iets anders.
    """
    return adres.lower() if soort == "evm" else adres


def zoek_adressen(tekst: str) -> Resultaat:
    """
    Haalt alle adressen uit een tekst.

    Volgorde is bewust:
    1. eerst de links eruit halen en apart beoordelen (pool of token),
    2. dan pas de kale tekst afzoeken.

    Zou je het andersom doen, dan pak je het pooladres uit een
    Dexscreener-link op alsof het een token is — en koop je de pool.
    """
    uitkomst = Resultaat()
    tekst = tekst or ""
    gezien: set[str] = set()

    def voeg_toe(lijst: list[Vondst], vondst: Vondst) -> None:
        sleutel = vondst.adres
        if sleutel in gezien:
            return
        gezien.add(sleutel)
        lijst.append(vondst)

    # ---- stap 1: links ----
    links = URL_PATROON.findall(tekst)
    for link in links:
        herkend = False

        for patroon, chain_groep in TOKEN_LINKS:
            treffer = patroon.search(link)
            if treffer:
                adres = treffer.group(1)
                soort = "evm" if is_evm_adres(adres) else "solana"
                if soort == "solana" and not is_solana_adres(adres):
                    uitkomst.notities.append(f"link met ongeldig tokenadres: {link}")
                    herkend = True
                    break
                voeg_toe(
                    uitkomst.vondsten,
                    Vondst(_normaliseer(adres, soort), soort, "token-link", chain_groep, link),
                )
                herkend = True
                break
        if herkend:
            continue

        for patroon, chain_groep, adres_groep in POOL_LINKS:
            treffer = patroon.search(link)
            if treffer:
                adres = treffer.group(adres_groep)
                chain = treffer.group(chain_groep).lower()
                soort = "evm" if is_evm_adres(adres) else "solana"
                if soort == "solana" and not is_solana_adres(adres):
                    uitkomst.notities.append(f"poollink met raar adres: {link}")
                    herkend = True
                    break
                voeg_toe(
                    uitkomst.pools,
                    Vondst(_normaliseer(adres, soort), soort, "pool-link", chain, link),
                )
                uitkomst.notities.append(
                    f"poollink gevonden ({chain}) — dit is NIET het token, moet omgezet worden"
                )
                herkend = True
                break
        if herkend:
            continue

        uitkomst.notities.append(f"onbekende link overgeslagen: {link}")

    # ---- stap 2: de kale tekst, zonder de links ----
    # De links halen we weg, anders vist stap 2 alsnog het pooladres eruit.
    kaal = URL_PATROON.sub(" ", tekst)

    # Eerst EVM. Daarna maskeren we ze, zodat de base58-zoeker er niet
    # overheen struikelt.
    for treffer in EVM_PATROON.finditer(kaal):
        adres = treffer.group(1)
        voeg_toe(uitkomst.vondsten, Vondst(_normaliseer(adres, "evm"), "evm", "tekst", "", adres))
    kaal = EVM_PATROON.sub(" ", kaal)

    for treffer in BASE58_PATROON.finditer(kaal):
        kandidaat = treffer.group(1)
        if is_solana_adres(kandidaat):
            voeg_toe(
                uitkomst.vondsten, Vondst(kandidaat, "solana", "tekst", "solana", kandidaat)
            )

    return uitkomst


def bevat_negeerwoord(tekst: str, woorden: list[str]) -> str | None:
    """
    Kijkt of er een negeerwoord in de tekst staat, op HELE woorden.

    "rug" mag niet matchen in "terug" of "brug". Daarom staat er \\b omheen en
    niet een simpele 'in'-controle. Dat laatste kostte bijna een gemiste call.
    """
    if not woorden:
        return None
    for woord in woorden:
        woord = woord.strip()
        if not woord:
            continue
        patroon = r"\b" + re.escape(woord) + r"\b"
        if re.search(patroon, tekst or "", re.IGNORECASE):
            return woord
    return None


def los_pool_op(vondst: Vondst, ophaler=None, limiet_ms: int = 1500) -> Vondst | None:
    """
    Zet een POOL-adres om naar het echte TOKEN-adres via Dexscreener.

    'ophaler' is los meegegeven zodat de tests dit kunnen nabootsen zonder
    internet. Lukt het niet binnen de tijdslimiet, dan geven we None terug:
    liever geen aankoop dan de verkeerde.
    """
    if ophaler is None:
        from markt import haal_paar  # pas hier importeren: tests hoeven geen requests

        ophaler = haal_paar

    try:
        gegevens = ophaler(vondst.chain_hint, vondst.adres, limiet_ms)
    except Exception:
        return None
    if not gegevens:
        return None

    basis = (gegevens.get("baseToken") or {}).get("address") or ""
    if not basis:
        return None

    soort = "evm" if is_evm_adres(basis) else "solana"
    if soort == "solana" and not is_solana_adres(basis):
        return None

    return Vondst(
        _normaliseer(basis, soort),
        soort,
        "pool-omgezet",
        (gegevens.get("chainId") or vondst.chain_hint or "").lower(),
        vondst.ruw,
    )
