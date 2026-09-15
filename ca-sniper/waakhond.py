"""
waakhond.py — kijkt of alles nog draait en slaat alarm als dat niet zo is.

Het stilste soort fout is hier het gevaarlijkst: een bot die lijkt te draaien
maar niets koopt. Deze waakhond is er precies voor dat geval. Hij controleert:

  * geeft de sniper nog een teken van leven? (hartslag)
  * staat Quick Buy nog aan?
  * gaat het wegschrijven van status nog goed?
  * is het dashboard bereikbaar?

Draai hem apart, bijvoorbeeld:  nohup python3 waakhond.py &
Hij stuurt waarschuwingen naar je eigen bedieningsbot op Telegram.
"""

from __future__ import annotations

import argparse
import time

from gereedschap import maak_logboek, zet_uitvoer_op_utf8
from instellingen import laad
from staat import Staat

# Hoe lang een onderdeel mag zwijgen voordat we alarm slaan.
MAXIMALE_STILTE_S = 90
# Niet vaker dan dit hetzelfde alarm herhalen, anders word je doodgepiept.
HERHAAL_NA_S = 1800


class Waakhond:
    def __init__(self, opties, logboek) -> None:
        self.opties = opties
        self.log = logboek
        self.staat = Staat()
        self.laatste_alarm: dict[str, float] = {}
        self.vorige_schrijffouten = 0

    def _alarm(self, sleutel: str, tekst: str) -> None:
        """Slaat alarm, maar niet vaker dan eens per half uur per onderwerp."""
        nu = time.time()
        if nu - self.laatste_alarm.get(sleutel, 0) < HERHAAL_NA_S:
            return
        self.laatste_alarm[sleutel] = nu
        self.log.error("ALARM (%s): %s", sleutel, tekst.replace("\n", " "))
        try:
            import telegrambediening

            telegrambediening.stuur_naar_eigenaar(self.opties, f"WAAKHOND\n\n{tekst}")
        except Exception as fout:
            self.log.warning("kon alarm niet versturen: %s", fout)

    def _herstel(self, sleutel: str, tekst: str) -> None:
        """Meldt dat iets weer goed gaat, maar alleen als er alarm was."""
        if sleutel in self.laatste_alarm:
            del self.laatste_alarm[sleutel]
            self.log.info("hersteld: %s", tekst)
            try:
                import telegrambediening

                telegrambediening.stuur_naar_eigenaar(self.opties, f"WAAKHOND\n\nWeer in orde: {tekst}")
            except Exception:
                pass

    def controleer(self) -> dict:
        """Eén ronde. Geeft terug wat hij gezien heeft."""
        gegevens = self.staat.lees()
        bevindingen: dict[str, str] = {}

        # 1. Draait de sniper nog?
        leeftijd = self.staat.hartslag_leeftijd("sniper")
        if leeftijd is None:
            bevindingen["sniper"] = "geen hartslag gevonden — draait de sniper wel?"
            self._alarm(
                "sniper",
                "Ik zie geen enkel teken van leven van de sniper.\n"
                "Draait bot.py nog? Start hem met:\n"
                "    nohup python3 bot.py > gegevens/bot.uit 2>&1 &",
            )
        elif leeftijd > MAXIMALE_STILTE_S:
            bevindingen["sniper"] = f"stil sinds {int(leeftijd)} seconden"
            self._alarm(
                "sniper",
                f"De sniper heeft al {int(leeftijd)} seconden niets van zich laten horen.\n"
                "Waarschijnlijk is hij vastgelopen of gestopt.",
            )
        else:
            bevindingen["sniper"] = f"in orde ({int(leeftijd)}s geleden)"
            self._herstel("sniper", "de sniper geeft weer een hartslag")

        # 2. Staat Quick Buy nog aan?
        quickbuy = str(gegevens.get("quickbuy") or "")
        if quickbuy == "uit":
            bevindingen["quickbuy"] = "UIT"
            self._alarm(
                "quickbuy",
                "QUICK BUY STAAT UIT bij BasedBot.\n"
                "Adressen worden wel doorgestuurd, maar er wordt NIETS gekocht.\n"
                "Dit gebeurt vaak nadat je geld hebt gestort.",
            )
        elif quickbuy == "aan":
            bevindingen["quickbuy"] = "aan"
            self._herstel("quickbuy", "Quick Buy staat weer aan")
        else:
            bevindingen["quickbuy"] = quickbuy or "niet gecontroleerd"

        # 3. Gaat het wegschrijven van status goed?
        hartslag = gegevens.get("hartslag") or {}
        fouten = 0
        if isinstance(hartslag, dict):
            regel = hartslag.get("sniper") or {}
            if isinstance(regel, dict):
                try:
                    fouten = int(regel.get("schrijffouten") or 0)
                except Exception:
                    fouten = 0
        if fouten > self.vorige_schrijffouten:
            bevindingen["schrijffouten"] = str(fouten)
            self._alarm(
                "schrijffouten",
                f"Het wegschrijven van de status is {fouten} keer misgegaan.\n"
                "De bot draait door (zo is het gebouwd), maar het dashboard kan "
                "achterlopen. Kijk of er een programma het bestand vasthoudt.",
            )
        self.vorige_schrijffouten = max(self.vorige_schrijffouten, fouten)

        # 4. Is het dashboard bereikbaar?
        from gereedschap import draait_al

        if draait_al(self.opties.dashboard_poort):
            bevindingen["dashboard"] = "bereikbaar"
        else:
            bevindingen["dashboard"] = "niet bereikbaar"

        # 5. Draait de sniper nog volgens de poort?
        bevindingen["proces"] = (
            "draait" if draait_al(self.opties.instantie_poort) else "NIET gevonden"
        )

        self.staat.hartslag("waakhond", bevindingen)
        return bevindingen

    def draai(self, tussentijd: int = 30) -> int:
        self.log.info("Waakhond gestart, controleert elke %s seconden.", tussentijd)
        try:
            while True:
                try:
                    bevindingen = self.controleer()
                    self.log.debug("%s", bevindingen)
                except Exception as fout:
                    # De waakhond moet als laatste omvallen.
                    self.log.exception("waakhond struikelde: %s", fout)
                time.sleep(tussentijd)
        except KeyboardInterrupt:
            self.log.info("Waakhond gestopt.")
        return 0


def main(argv: list[str] | None = None) -> int:
    zet_uitvoer_op_utf8()
    ontleder = argparse.ArgumentParser(description="Bewaakt of de sniper draait")
    ontleder.add_argument("--eenmalig", action="store_true", help="één controle en klaar")
    ontleder.add_argument("--tussentijd", type=int, default=30)
    argumenten = ontleder.parse_args(argv)

    opties = laad()
    logboek = maak_logboek("waakhond", opties.logniveau)
    hond = Waakhond(opties, logboek)

    if argumenten.eenmalig:
        for naam, waarde in hond.controleer().items():
            print(f"{naam:14s}: {waarde}")
        return 0
    return hond.draai(argumenten.tussentijd)


if __name__ == "__main__":
    raise SystemExit(main())
