"""
markt.py — opzoekwerk: Dexscreener (welke chain, welk token) en Blockscout.

DRIE DINGEN DIE HIER EERDER MISGINGEN

1. Blockscout zit achter Cloudflare en geeft 403 op een kale User-Agent.
   'python-requests/2.x' wordt geweigerd. Daarom sturen we een gewone
   browser-User-Agent mee.

2. Blockscout gebruikt TWEE verschillende veldnamen voor hetzelfde:
   een ADRES-object heeft 'hash', een TOKEN-object heeft 'address_hash'.
   Kijk je alleen naar 'hash', dan komt élk tokenadres leeg binnen — zonder
   enige foutmelding. Dat kostte 16.254 transfers met een leeg tokenveld
   voordat het opviel.

3. tokens/{adres}/transfers geeft alleen nieuwste-eerst. Bij een druk token
   beslaan 2.000 transfers nog geen dag. Wil je weten wie er vóór een call
   kocht, dan MOET je doorbladeren tot voorbij dat moment — anders krijg je
   "niemand kocht vooraf" en dat is gewoon het verkeerde antwoord.

En over snelheid: een opzoeking mag NOOIT in de hoofdlus van de sniper. Bij een
verse launch kent Dexscreener het token toch nog niet, dus lang wachten levert
alleen vertraging op. Harde limiet: ongeveer anderhalve seconde.
"""

from __future__ import annotations

import time
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

DEXSCREENER = "https://api.dexscreener.com/latest/dex"
BLOCKSCOUT_ROBINHOOD = "https://robinhoodchain.blockscout.com/api/v2"

# Een kale User-Agent wordt door Cloudflare geweigerd. Dit is een gewone
# browser-kop; zonder dit krijg je 403 van Blockscout.
KOPPEN = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# Namen die mensen gebruiken tegenover wat Dexscreener terugstuurt.
CHAIN_ALIASSEN = {
    "sol": "solana",
    "solana": "solana",
    "eth": "ethereum",
    "ether": "ethereum",
    "ethereum": "ethereum",
    "base": "base",
    "bsc": "bsc",
    "bnb": "bsc",
    "arb": "arbitrum",
    "arbitrum": "arbitrum",
    "poly": "polygon",
    "matic": "polygon",
    "polygon": "polygon",
    "avax": "avalanche",
    "avalanche": "avalanche",
    "robinhood": "robinhood",
    "rhc": "robinhood",
    "4663": "robinhood",
}


def normaliseer_chain(naam: str) -> str:
    naam = (naam or "").strip().lower()
    return CHAIN_ALIASSEN.get(naam, naam)


class GeenNetwerk(Exception):
    """requests is niet geïnstalleerd."""


def _haal(url: str, limiet_ms: int = 1500) -> Any | None:
    """Haalt JSON op met een harde tijdslimiet. Geeft None bij elk probleem."""
    if requests is None:
        raise GeenNetwerk("De module 'requests' ontbreekt. Doe: pip install requests")
    try:
        antwoord = requests.get(url, headers=KOPPEN, timeout=max(0.2, limiet_ms / 1000))
    except Exception:
        return None
    if antwoord.status_code == 403:
        # Vrijwel altijd Cloudflare die de User-Agent niet vertrouwt.
        return None
    if antwoord.status_code != 200:
        return None
    try:
        return antwoord.json()
    except Exception:
        return None


# ----------------------------------------------------------- Dexscreener

def haal_token(adres: str, limiet_ms: int = 1500) -> list[dict]:
    """
    Zoekt alle handelsparen van een token op. Lege lijst = onbekend token.
    Bij een verse launch is dat normaal: die staat er nog niet in.
    """
    gegevens = _haal(f"{DEXSCREENER}/tokens/{adres}", limiet_ms)
    if not isinstance(gegevens, dict):
        return []
    paren = gegevens.get("pairs")
    return [p for p in paren if isinstance(p, dict)] if isinstance(paren, list) else []


def haal_paar(chain: str, paar_adres: str, limiet_ms: int = 1500) -> dict | None:
    """
    Zoekt één handelspaar (pool) op. Hiermee zetten we een pooladres uit een
    Dexscreener-link om naar het echte tokenadres.
    """
    chain = normaliseer_chain(chain)
    gegevens = _haal(f"{DEXSCREENER}/pairs/{chain}/{paar_adres}", limiet_ms)
    if not isinstance(gegevens, dict):
        return None
    if isinstance(gegevens.get("pair"), dict):
        return gegevens["pair"]
    paren = gegevens.get("pairs")
    if isinstance(paren, list) and paren and isinstance(paren[0], dict):
        return paren[0]
    return None


def chains_van_token(adres: str, limiet_ms: int = 1500) -> list[str]:
    """Op welke chains bestaat dit token volgens Dexscreener?"""
    chains: list[str] = []
    for paar in haal_token(adres, limiet_ms):
        chain = normaliseer_chain(str(paar.get("chainId") or ""))
        if chain and chain not in chains:
            chains.append(chain)
    return chains


def controleer_chain(
    adres: str,
    soort: str,
    verwachte_chain: str,
    stand: str = "slim",
    limiet_ms: int = 1500,
    opzoeker=None,
) -> tuple[bool, str]:
    """
    Mag dit adres doorgestuurd worden, gezien de chain waar BasedBot op staat?

    Waarom dit nodig is: een 0x-adres ziet er op élke EVM-chain hetzelfde uit.
    BasedBot koopt op de chain die op dat moment actief staat. Staat hij op
    Base en is de call op Ethereum, dan koop je iets volstrekt anders — of niets.

    Drie standen:
      slim  onbekend token = waarschijnlijk een verse launch, dus doorlaten;
            bekend token op een ANDERE chain = blokkeren
      warn  nooit blokkeren, wel melden
      off   helemaal niet opzoeken

    'slim' is de juiste standaard. Op streng blokkeer je precies de verse
    launches waar het je om te doen is.
    """
    verwacht = normaliseer_chain(verwachte_chain)
    stand = (stand or "slim").lower()

    if stand == "off":
        return True, "chaincontrole staat uit"

    if soort == "solana":
        # Een Solana-adres kan alleen Solana zijn; geen opzoeking nodig.
        if verwacht == "solana":
            return True, "solana-adres, BasedBot staat op solana"
        melding = f"solana-adres, maar BasedBot staat op {verwacht}"
        return (stand == "warn"), melding

    if soort != "evm":
        return True, "onbekend soort adres, niet gecontroleerd"

    # Een 0x-adres kan onmogelijk op Solana bestaan. Dat hoeven we niet op te
    # zoeken: dan zou een mislukte opzoeking hem alsnog doorlaten, en dan
    # stuur je een EVM-adres naar een BasedBot die op Solana staat.
    if verwacht == "solana":
        melding = "0x-adres, maar BasedBot staat op solana — dat kan nooit kloppen"
        return (stand == "warn"), melding

    zoek = opzoeker or chains_van_token
    try:
        chains = zoek(adres, limiet_ms)
    except Exception as fout:
        # Opzoeken mislukt is geen reden om een call te laten lopen.
        return True, f"chain niet op te zoeken ({fout}), doorgelaten"

    if not chains:
        return True, "token nog onbekend bij Dexscreener — waarschijnlijk verse launch"

    if verwacht in chains:
        return True, f"token staat op {verwacht}"

    melding = f"token staat op {', '.join(chains)}, maar BasedBot staat op {verwacht}"
    return (stand == "warn"), melding


def controleer_netwerk(limiet_ms: int = 5000) -> tuple[bool, str, int]:
    """
    Kijkt of Dexscreener echt bereikbaar is, met een token dat zeker bestaat.

    Waarom dit nodig is: als het opzoeken stilletjes mislukt, laat de
    chaincontrole ELK adres door met "kon niet opzoeken". De bot lijkt dan te
    werken maar controleert niets. Dit is de enige manier om dat te merken
    zonder erop te wachten dat het een keer fout gaat.

    Op macOS is de bekendste oorzaak urllib3 v2 in combinatie met LibreSSL.
    Geeft (gelukt, uitleg, milliseconden) terug.
    """
    import time as _tijd

    if requests is None:
        return False, "de module 'requests' ontbreekt (pip install -r requirements.txt)", 0

    # Waarschuw als de bekende macOS-combinatie aanwezig is.
    waarschuwing = ""
    try:
        import ssl

        import urllib3

        if urllib3.__version__.startswith("2.") and "LibreSSL" in ssl.OPENSSL_VERSION:
            waarschuwing = (
                f" LET OP: urllib3 {urllib3.__version__} met {ssl.OPENSSL_VERSION}. "
                "Die combinatie werkt niet goed. Doe: "
                "python3 -m pip install 'urllib3<2'"
            )
    except Exception:
        pass

    # USDC op Solana bestaat altijd; komt hier niets uit, dan is het netwerk stuk.
    usdc = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    begin = _tijd.time()
    try:
        paren = haal_token(usdc, limiet_ms)
    except Exception as fout:
        return False, f"opzoeken gaf een fout: {fout}.{waarschuwing}", int((_tijd.time() - begin) * 1000)
    ms = int((_tijd.time() - begin) * 1000)

    if not paren:
        return False, (
            "Dexscreener gaf geen antwoord voor USDC — dat hoort er altijd te zijn. "
            "De chaincontrole kan dus niets opzoeken en laat alles door."
            + waarschuwing
        ), ms

    chains = ", ".join(sorted({str(p.get("chainId")) for p in paren})[:5])
    return True, f"Dexscreener werkt ({len(paren)} paren gevonden, chains: {chains}).{waarschuwing}", ms


# ----------------------------------------------------------- Blockscout

def blockscout_adresveld(object_: dict) -> str:
    """
    Haalt het adres uit een Blockscout-object.

    DE VALKUIL: een ADRES-object heeft 'hash', een TOKEN-object heeft
    'address_hash'. Kijk je maar naar één van de twee, dan krijg je stilletjes
    lege adressen terug. Daarom kijken we naar allebei.
    """
    if not isinstance(object_, dict):
        return ""
    for sleutel in ("address_hash", "hash", "address"):
        waarde = object_.get(sleutel)
        if isinstance(waarde, str) and waarde:
            return waarde
        if isinstance(waarde, dict):
            # Soms zit het adres nog een laagje dieper.
            for diepere in ("hash", "address_hash"):
                if isinstance(waarde.get(diepere), str) and waarde[diepere]:
                    return waarde[diepere]
    return ""


def blockscout_transfers(
    token_adres: str,
    tot_tijdstip: float | None = None,
    maximaal: int = 2000,
    basis: str = BLOCKSCOUT_ROBINHOOD,
    limiet_ms: int = 8000,
) -> list[dict]:
    """
    Haalt tokenoverdrachten op van Blockscout, NIEUWSTE EERST.

    Wil je weten wie er vóór een bepaald moment kocht, geef dan 'tot_tijdstip'
    (Unix-tijd) mee: dan blijft hij doorbladeren tot hij voorbij dat moment is.
    Doe je dat niet, dan krijg je bij een druk token alleen het laatste half
    uur te zien en lijkt het alsof niemand vooraf kocht.

    Etherscan ondersteunt Robinhood Chain (4663) niet; daarom Blockscout.
    """
    verzameld: list[dict] = []
    volgende: dict | None = None
    basis = basis.rstrip("/")

    while len(verzameld) < maximaal:
        url = f"{basis}/tokens/{token_adres}/transfers"
        if volgende:
            paren = "&".join(f"{sleutel}={waarde}" for sleutel, waarde in volgende.items())
            url = f"{url}?{paren}"

        gegevens = _haal(url, limiet_ms)
        if not isinstance(gegevens, dict):
            break

        stuk = gegevens.get("items")
        if not isinstance(stuk, list) or not stuk:
            break
        verzameld.extend(item for item in stuk if isinstance(item, dict))

        if tot_tijdstip is not None:
            oudste = _tijd_van_transfer(stuk[-1])
            if oudste and oudste < tot_tijdstip:
                break  # we zijn voorbij het gevraagde moment: klaar

        volgende = gegevens.get("next_page_params")
        if not isinstance(volgende, dict) or not volgende:
            break
        time.sleep(0.15)  # Blockscout niet plat vragen

    return verzameld


def _tijd_van_transfer(transfer: dict) -> float | None:
    """Zet de tijdstempel van een transfer om naar Unix-tijd."""
    rauw = transfer.get("timestamp") or (transfer.get("block") or {}).get("timestamp")
    if not isinstance(rauw, str):
        return None
    tekst = rauw.replace("Z", "+00:00")
    try:
        from datetime import datetime

        return datetime.fromisoformat(tekst).timestamp()
    except Exception:
        return None
