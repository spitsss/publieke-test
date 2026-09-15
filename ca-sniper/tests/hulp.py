"""Kleine hulpjes voor de tests."""
import sys
from pathlib import Path

# De tests draaien vanuit tests/, de code staat er een map boven.
MAP = Path(__file__).resolve().parent.parent
if str(MAP) not in sys.path:
    sys.path.insert(0, str(MAP))

from extract import BASE58_ALFABET  # noqa: E402


def base58_codeer(rauw: bytes) -> str:
    """Zet bytes om naar base58 — nodig om echte testadressen te maken."""
    getal = int.from_bytes(rauw, "big")
    uit = ""
    while getal > 0:
        getal, rest = divmod(getal, 58)
        uit = BASE58_ALFABET[rest] + uit
    nullen = len(rauw) - len(rauw.lstrip(b"\x00"))
    return "1" * nullen + uit
