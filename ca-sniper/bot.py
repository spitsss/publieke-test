"""
bot.py — de sniper: melding -> contractadres -> BasedBot.

DE KETEN
    macOS Berichtencentrum  ->  filter  ->  adres eruit  ->  chaincontrole
    ->  bericht naar BasedBot  ->  antwoord beoordelen  ->  logboek

WEES EERLIJK OVER DE SNELHEID
Een melding komt een halve tot enkele seconden na het bericht binnen. Je
verslaat hiermee de mensen die het kanaal zitten te verversen. Je verslaat
NIET een bot die op de gateway van Discord meeluistert. "Eerste zijn" beloven
we dus niet.

DE HOOFDLUS BLIJFT VRIJ
De lus die meldingen ophaalt doet alleen goedkoop werk: filteren en het adres
eruit halen. Alles wat traag is (Dexscreener opzoeken, naar Telegram sturen,
op antwoord wachten) gaat naar een aparte draad. Zou je dat in de hoofdlus
doen, dan ziet de bot ondertussen géén nieuwe meldingen.

DRY RUN STAAT STANDAARD AAN
Hij logt wat hij zou kopen en koopt niets. Pas als jij in config.ini
'dryrun = nee' zet, gaat er echt geld weg.
"""

from __future__ import annotations

import argparse
import queue
import sys
import threading
import time

import extract
import filters
from gereedschap import EnkeleInstantie, kort, maak_logboek, nu_ms, zet_uitvoer_op_utf8
from instellingen import Instellingen, laad
from meldingen import Melding, Meldingenlezer, MeldingFout
from staat import DRYRUN, GEKOCHT, MISLUKT, ONBEKEND, Staat, VERSTUURD


class Sniper:
    def __init__(self, opties: Instellingen, logboek=None, staat: Staat | None = None) -> None:
        self.opties = opties
        self.log = logboek or maak_logboek("sniper", opties.logniveau)
        # 'staat' is los mee te geven zodat de tests niet in je echte
        # gegevensmap rommelen.
        self.staat = staat or Staat()
        self.lezer: Meldingenlezer | None = None
        self.brug = None
        self.werk: queue.Queue = queue.Queue(maxsize=100)
        self.stoppen = threading.Event()
        self.laatste_rec_id = 0
        self.tellers = {"gezien": 0, "gefilterd": 0, "verstuurd": 0, "gekocht": 0, "mislukt": 0}
        self.laatste_ms = 0

    # ------------------------------------------------------------- opstarten

    def verbind_telegram(self) -> bool:
        """Verbindt met Telegram. In dryrun mag dit mislukken; live niet."""
        from telegram_brug import TelegramBrug

        try:
            self.brug = TelegramBrug(
                self.opties.api_id,
                self.opties.api_hash,
                self.opties.sessienaam,
                self.opties.basedbot,
                self.opties.antwoord_wacht_s,
                self.log,
            )
            self.brug.start()
            self.log.info("Telegram verbonden met %s", self.opties.basedbot)
            return True
        except Exception as fout:
            if self.opties.dryrun:
                self.log.warning(
                    "Geen Telegram-verbinding (%s). In dryrun gaat de bot door; "
                    "hij laat alleen zien wat hij zou sturen.", fout
                )
                self.brug = None
                return False
            self.log.error("Telegram-verbinding mislukt: %s", fout)
            raise

    # ------------------------------------------------------------- hoofdlus

    def draai(self) -> int:
        opties = self.opties

        problemen = opties.controleer_voor_sniper()
        if problemen:
            self.log.error("De instellingen kloppen nog niet:")
            for probleem in problemen:
                self.log.error("  - %s", probleem)
            return 2

        try:
            self.lezer = Meldingenlezer(opties.db_pad, opties.bundle_ids, opties.leesmodus)
        except MeldingFout as fout:
            self.log.error("%s", fout)
            return 1

        for waarschuwing in self.lezer.waarschuwingen:
            self.log.warning("%s", waarschuwing)

        # HET HOOGSTE rec_id ONTHOUDEN VOORDAT WE BEGINNEN.
        # Zonder deze regel verwerkt de bot bij elke herstart alle oude
        # meldingen die nog in het Berichtencentrum staan — en koopt dus
        # alles opnieuw. Dit ging op de Windows-versie bijna mis.
        self.laatste_rec_id = self.lezer.hoogste_rec_id()
        self.log.info(
            "Start bij rec_id %s — alles daarvóór wordt genegeerd.", self.laatste_rec_id
        )

        self.verbind_telegram()

        stand = "DRY RUN (er wordt niets gekocht)" if opties.dryrun else "LIVE — ER GAAT ECHT GELD WEG"
        self.log.info("=" * 60)
        self.log.info("Stand         : %s", stand)
        self.log.info("Bedrag/call   : %s %s", opties.bedrag, opties.valuta)
        self.log.info("BasedBot chain: %s (controle: %s)", opties.basedbot_chain, opties.chaincontrole)
        self.log.info("Kanalen       : %s", ", ".join(opties.kanalen) or "(geen!)")
        self.log.info("Apps          : %s", ", ".join(opties.bundle_ids))
        self.log.info("Database      : %s (stand %s)", self.lezer.pad, self.lezer.modus)
        self.log.info("Zelf verkopen : %s", "aan" if opties.zelf_verkopen else "uit")
        self.log.info("=" * 60)

        werker = threading.Thread(target=self._werkdraad, name="koper", daemon=True)
        werker.start()

        if not opties.dryrun and self.brug is not None:
            import quickbuy_wacht

            threading.Thread(
                target=quickbuy_wacht.draai_wachter,
                args=(self.brug, self.opties, self.staat, self.log, self.stoppen),
                name="quickbuy",
                daemon=True,
            ).start()

        self.staat.werk_bij(
            gestart_op=time.time(),
            dryrun=opties.dryrun,  # startstand; de bediening kan dit omzetten
            gepauzeerd=False,
            db_pad=str(self.lezer.pad),
            leesmodus=self.lezer.modus,
            bedrag=opties.bedrag,
            valuta=opties.valuta,
            chain=opties.basedbot_chain,
        )

        wacht = opties.poll_ms / 1000
        laatste_hartslag = 0.0

        try:
            while not self.stoppen.is_set():
                try:
                    nieuw = self.lezer.nieuwe_meldingen(self.laatste_rec_id)
                except MeldingFout as fout:
                    # Database even bezet: overslaan, niet stoppen.
                    self.log.debug("database even niet leesbaar: %s", fout)
                    nieuw = []

                for melding in nieuw:
                    self.laatste_rec_id = max(self.laatste_rec_id, melding.rec_id)
                    try:
                        self._bekijk(melding)
                    except Exception as fout:
                        # Eén rare melding mag de bot nooit omleggen.
                        self.log.exception("fout bij melding %s: %s", melding.rec_id, fout)

                if time.time() - laatste_hartslag > 2:
                    laatste_hartslag = time.time()
                    self._schrijf_status()
                    try:
                        self._doe_opdrachten()
                    except Exception as fout:
                        self.log.exception("opdracht mislukte: %s", fout)

                time.sleep(wacht)
        except KeyboardInterrupt:
            self.log.info("Gestopt met ctrl-C.")
        finally:
            self.stoppen.set()
            if self.brug:
                self.brug.stop()
            self._schrijf_status()
        return 0

    def _schrijf_status(self) -> None:
        """Status wegschrijven mag NOOIT de bot omleggen — vandaar het vangnet."""
        try:
            self.staat.hartslag(
                "sniper",
                {
                    "rec_id": self.laatste_rec_id,
                    "tellers": dict(self.tellers),
                    "laatste_ms": self.laatste_ms,
                    "dryrun": self.opties.dryrun,
                    "schrijffouten": self.staat.schrijffouten,
                },
            )
        except Exception:
            pass

    def _dryrun_nu(self) -> bool:
        """
        De dry-run-stand kan tijdens het draaien omgezet worden met de
        bedieningsbot (/dryrun aan|uit). De gedeelde toestand is dus leidend;
        config.ini is alleen het startpunt. Bij twijfel: dry run AAN.
        """
        waarde = self.staat.lees().get("dryrun")
        if isinstance(waarde, bool):
            return waarde
        return self.opties.dryrun

    def _doe_opdrachten(self) -> None:
        """Voert opdrachten uit die de bedieningsbot heeft klaargezet."""
        for opdracht in self.staat.neem_opdrachten():
            soort = str(opdracht.get("soort") or "")
            if soort != "verkoop":
                self.log.warning("onbekende opdracht overgeslagen: %s", opdracht)
                continue
            adres = str(opdracht.get("adres") or "")
            deel = str(opdracht.get("deel") or "initials")
            if not adres:
                continue
            if self.brug is None:
                self._alarm("Kan niet verkopen: geen Telegram-verbinding.")
                continue
            self.log.info("opdracht van de bediening: %s van %s verkopen", deel, adres)
            import verkoop as verkoopmodule

            uitkomst = verkoopmodule.verkoop(self.brug, adres, deel, self.log)
            self.staat.noteer_handel({
                "adres": adres, "resultaat": f"verkoop-{uitkomst.resultaat}",
                "uitleg": uitkomst.uitleg, "deel": deel, "bron": "bediening",
            })
            self._alarm(
                f"Verkoop {deel} van {adres[:16]}…\n"
                f"Resultaat: {uitkomst.resultaat}\n{uitkomst.uitleg}"
            )

    # ------------------------------------------------- goedkope beoordeling

    def _bekijk(self, melding: Melding) -> None:
        """
        Draait in de hoofdlus, dus alleen snel werk: filteren en het adres
        eruit halen. Al het trage werk gaat naar de werkdraad.
        """
        self.tellers["gezien"] += 1
        self.log.debug("melding %s: %s", melding.rec_id, kort(melding.tekst, 160))

        if self.staat.lees().get("gepauzeerd"):
            self.log.info("gepauzeerd — melding %s overgeslagen", melding.rec_id)
            return

        mag, reden = filters.kanaal_toegestaan(
            melding.titel, melding.ondertitel, self.opties.kanalen, self.opties.sta_dm_toe
        )
        if not mag:
            self.tellers["gefilterd"] += 1
            self.log.debug("melding %s geweigerd: %s", melding.rec_id, reden)
            return

        negeerwoord = extract.bevat_negeerwoord(melding.tekst, self.opties.negeerwoorden)
        if negeerwoord:
            self.tellers["gefilterd"] += 1
            self.log.info(
                "melding %s overgeslagen: negeerwoord '%s' in '%s'",
                melding.rec_id, negeerwoord, kort(melding.body, 100),
            )
            return

        # Verkoopsignaal? Alleen relevant als zelf verkopen aan staat.
        if self.opties.zelf_verkopen:
            self._bekijk_exit(melding)

        gevonden = extract.zoek_adressen(melding.tekst)
        for notitie in gevonden.notities:
            self.log.info("melding %s: %s", melding.rec_id, notitie)

        vondsten = list(gevonden.vondsten)

        if not vondsten and gevonden.pools:
            # Alleen een poollink. Die moet omgezet worden naar het echte
            # token — dat kost een opzoeking, dus dat doet de werkdraad.
            self.werk.put(("pool", melding, gevonden.pools[0]))
            return

        if not vondsten:
            self.log.debug("melding %s: geen adres gevonden", melding.rec_id)
            return

        if len(vondsten) > 1:
            if self.opties.meerdere_adressen == "weiger":
                self.tellers["gefilterd"] += 1
                self.log.warning(
                    "melding %s bevat %d adressen — overgeslagen. Welke van de %s "
                    "bedoelde hij? Zet meerdere_adressen=eerste als je toch de "
                    "eerste wilt.",
                    melding.rec_id, len(vondsten), [v.adres[:10] + "…" for v in vondsten],
                )
                return
            self.log.warning(
                "melding %s bevat %d adressen — ik neem de eerste (%s)",
                melding.rec_id, len(vondsten), vondsten[0].adres,
            )

        vondst = vondsten[0]

        # Al eens doorgestuurd? Dan nooit nog een keer. Dit staat bewust hier,
        # in de hoofdlus, zodat twee meldingen vlak na elkaar niet allebei
        # door de werkdraad glippen.
        if self.staat.is_verstuurd(vondst.adres):
            self.log.info("melding %s: %s is al eens verstuurd — overgeslagen", melding.rec_id, vondst.adres)
            return
        self.staat.noteer_verstuurd(vondst.adres, f"rec_id={melding.rec_id}")

        self.log.info(
            "GEVONDEN in %.0fms na bezorging | %s | %s",
            (melding.gezien_op - melding.bezorgd_op) * 1000 if melding.bezorgd_op else -1,
            vondst.adres,
            kort(melding.titel, 50),
        )
        self.werk.put(("koop", melding, vondst))

    def _bekijk_exit(self, melding: Melding) -> None:
        import exits

        signaal = exits.zoek_exit(melding.body or melding.tekst)
        if not signaal:
            return
        if not signaal.zeker:
            self.log.warning("mogelijk verkoopsignaal (onduidelijk hoeveel): %s", signaal.zin)
            self._alarm(f"Mogelijk verkoopsignaal, maar onduidelijk hoeveel:\n{signaal.zin}")
            return
        self.log.info("verkoopsignaal: %s (%s)", signaal.zin, signaal.deel)
        self.werk.put(("verkoop", melding, signaal))

    # ------------------------------------------------------- de werkdraad

    def _werkdraad(self) -> None:
        while not self.stoppen.is_set():
            try:
                soort, melding, lading = self.werk.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                if soort == "koop":
                    self._koop(melding, lading)
                elif soort == "pool":
                    self._pool(melding, lading)
                elif soort == "verkoop":
                    self._verkoop(melding, lading)
            except Exception as fout:
                self.log.exception("werkdraad struikelde: %s", fout)
            finally:
                self.werk.task_done()

    def _pool(self, melding: Melding, pool) -> None:
        """Zet een pooladres om naar het echte token. Koop nooit de pool."""
        self.log.info("poollink omzetten: %s op %s", pool.adres, pool.chain_hint)
        echt = extract.los_pool_op(pool, limiet_ms=self.opties.dexscreener_limiet_ms)
        if echt is None:
            self.log.warning(
                "pool %s kon ik niet omzetten naar een token — OVERGESLAGEN. "
                "Nooit het pooladres kopen.", pool.adres,
            )
            return
        if self.staat.is_verstuurd(echt.adres):
            self.log.info("%s is al eens verstuurd — overgeslagen", echt.adres)
            return
        self.staat.noteer_verstuurd(echt.adres, f"rec_id={melding.rec_id} via pool")
        self.log.info("pool %s -> token %s", pool.adres, echt.adres)
        self._koop(melding, echt)

    def _koop(self, melding: Melding, vondst) -> None:
        begin = nu_ms()
        opties = self.opties

        # Chaincontrole. Voor Solana-adressen is dit gratis; voor 0x-adressen
        # kost het een opzoeking van maximaal anderhalve seconde. Dat is de
        # prijs van niet op de verkeerde chain kopen.
        import markt

        mag, reden = markt.controleer_chain(
            vondst.adres,
            vondst.soort,
            opties.basedbot_chain,
            opties.chaincontrole,
            opties.dexscreener_limiet_ms,
        )
        if not mag:
            self.log.error("GEBLOKKEERD door chaincontrole: %s (%s)", vondst.adres, reden)
            self.staat.noteer_handel({
                "adres": vondst.adres, "resultaat": "geblokkeerd", "uitleg": reden,
                "kanaal": melding.titel, "rec_id": melding.rec_id,
            })
            self._alarm(f"Niet gekocht: {vondst.adres}\nReden: {reden}")
            return
        if opties.chaincontrole == "warn" and "maar BasedBot staat op" in reden:
            self.log.warning("chainwaarschuwing: %s", reden)

        if self._dryrun_nu():
            ms = nu_ms() - begin
            self.laatste_ms = ms
            self.tellers["verstuurd"] += 1
            self.log.info(
                "[DRY RUN] zou %s %s kopen van %s — niets verstuurd (%d ms). %s",
                opties.bedrag, opties.valuta, vondst.adres, ms, reden,
            )
            self.staat.noteer_handel({
                "adres": vondst.adres, "resultaat": DRYRUN, "uitleg": reden,
                "kanaal": melding.titel, "rec_id": melding.rec_id, "ms": ms,
                "bedrag": opties.bedrag, "valuta": opties.valuta,
            })
            self._schrijf_status()
            return

        if self.brug is None:
            self.log.error("Geen Telegram-verbinding — %s NIET verstuurd.", vondst.adres)
            return

        # Met Quick Buy aan betekent een kaal adres: KOPEN.
        antwoord = self.brug.stuur_en_lees(vondst.adres)
        ms = nu_ms() - begin
        self.laatste_ms = ms
        self.tellers["verstuurd"] += 1

        if antwoord.resultaat == GEKOCHT:
            self.tellers["gekocht"] += 1
            self.log.info("GEKOCHT %s in %d ms — %s", vondst.adres, ms, antwoord.uitleg)
        elif antwoord.resultaat == MISLUKT:
            self.tellers["mislukt"] += 1
            self.log.error("NIET gekocht %s — %s", vondst.adres, antwoord.uitleg)
            self._alarm(f"Aankoop MISLUKT\n{vondst.adres}\n{antwoord.uitleg}")
        else:
            # Verstuurd is niet gekocht. Dit onderscheid is het hele punt.
            self.log.warning(
                "VERSTUURD maar NIET BEVESTIGD: %s (%d ms). BasedBot zei: %s",
                vondst.adres, ms, kort(" | ".join(antwoord.teksten), 200) or "(niets)",
            )
            self._alarm(
                f"Adres verstuurd, maar GEEN bevestiging van een aankoop:\n"
                f"{vondst.adres}\nAntwoord: {kort(' | '.join(antwoord.teksten), 300) or '(niets)'}\n"
                f"Staat Quick Buy nog aan?"
            )

        self.staat.noteer_handel({
            "adres": vondst.adres,
            "resultaat": antwoord.resultaat,
            "uitleg": antwoord.uitleg,
            "antwoord": kort(" | ".join(antwoord.teksten), 500),
            "kanaal": melding.titel,
            "rec_id": melding.rec_id,
            "ms": ms,
            "bedrag": opties.bedrag,
            "valuta": opties.valuta,
        })
        self._schrijf_status()

    def _verkoop(self, melding: Melding, signaal) -> None:
        """Verkoopt via het menu van BasedBot. Nooit door een adres te sturen."""
        import verkoop as verkoopmodule

        gevonden = extract.zoek_adressen(melding.tekst)
        if not gevonden.vondsten:
            self.log.warning(
                "verkoopsignaal zonder adres in hetzelfde bericht: '%s' — niets gedaan. "
                "Verkoop met de hand via de bedieningsbot.", signaal.zin,
            )
            self._alarm(f"Verkoopsignaal zonder adres:\n{signaal.zin}")
            return

        adres = gevonden.vondsten[0].adres
        if self._dryrun_nu():
            self.log.info("[DRY RUN] zou %s van %s verkopen", signaal.deel, adres)
            return
        if self.brug is None:
            self.log.error("Geen Telegram-verbinding — niet verkocht.")
            return

        uitkomst = verkoopmodule.verkoop(self.brug, adres, signaal.deel, self.log)
        self.log.info("verkoop %s: %s (%s)", adres, uitkomst.resultaat, uitkomst.uitleg)
        self.staat.noteer_handel({
            "adres": adres, "resultaat": f"verkoop-{uitkomst.resultaat}",
            "uitleg": uitkomst.uitleg, "deel": signaal.deel, "rec_id": melding.rec_id,
        })
        self._alarm(f"Verkoop {signaal.deel} van {adres}: {uitkomst.resultaat}\n{uitkomst.uitleg}")

    # ------------------------------------------------------------- alarm

    def _alarm(self, tekst: str) -> None:
        """Stuurt een waarschuwing naar je eigen bedieningsbot. Faalt stil."""
        try:
            import telegrambediening

            telegrambediening.stuur_naar_eigenaar(self.opties, tekst)
        except Exception as fout:
            self.log.debug("alarm kon niet verstuurd worden: %s", fout)


# ----------------------------------------------------------------- opstarten

def main(argv: list[str] | None = None) -> int:
    zet_uitvoer_op_utf8()
    ontleder = argparse.ArgumentParser(description="CA-sniper via macOS-meldingen")
    ontleder.add_argument("--diag", action="store_true", help="controleer de opstelling en stop")
    ontleder.add_argument("--live", action="store_true", help="ECHT kopen (overschrijft dryrun)")
    ontleder.add_argument("--dryrun", action="store_true", help="niets kopen (standaard)")
    ontleder.add_argument("--config", default=None, help="ander config-bestand")
    ontleder.add_argument(
        "--test-melding",
        default=None,
        help="voer zelf een neptekst door de keten, zonder Discord en zonder te kopen",
    )
    argumenten = ontleder.parse_args(argv)

    opties = laad(argumenten.config)
    logboek = maak_logboek("sniper", opties.logniveau)

    if argumenten.diag:
        import meldingen as meldingenmodule

        code = meldingenmodule.diagnose(opties.db_pad, opties.bundle_ids)
        print("\n--- instellingen ---")
        problemen = opties.controleer_voor_sniper()
        if problemen:
            for probleem in problemen:
                print(f"  !! {probleem}")
        else:
            print("  instellingen zien er goed uit")
        print(f"  dryrun: {'AAN (er wordt niets gekocht)' if opties.dryrun else 'UIT — LIVE'}")
        return code

    if argumenten.test_melding:
        return _test_melding(opties, logboek, argumenten.test_melding)

    if argumenten.live and argumenten.dryrun:
        print("Kies er één: --live of --dryrun.")
        return 2

    # Eén exemplaar tegelijk. Twee snipers sturen hetzelfde adres twee keer door.
    slot = EnkeleInstantie(opties.instantie_poort)
    if not slot.neem():
        logboek.error(
            "Er draait al een sniper (poort %s bezet). Twee exemplaren sturen "
            "hetzelfde adres twee keer door. Ik stop.", opties.instantie_poort,
        )
        return 3

    if argumenten.live:
        # Handmatig omzetten vergt een bewuste handeling.
        opties.zet("algemeen", "dryrun", "nee")
        logboek.warning("LIVE-stand via --live. Er gaat nu echt geld weg.")

    try:
        return Sniper(opties, logboek).draai()
    finally:
        slot.geef_vrij()


def _test_melding(opties: Instellingen, logboek, tekst: str) -> int:
    """
    Duwt een verzonnen melding door het filter en de adresherkenning, zonder
    Discord, zonder Telegram en zonder te kopen. Handig om je kanaalfilter te
    controleren. Gebruik: --test-melding "#calls (Alpha)|| CA: <adres>"
    """
    delen = tekst.split("||")
    titel = delen[0].strip() if len(delen) > 1 else "#test (Test)"
    body = delen[-1].strip()

    print(f"titel : {titel}")
    print(f"tekst : {body}\n")

    mag, reden = filters.kanaal_toegestaan(titel, "", opties.kanalen, opties.sta_dm_toe)
    print(f"kanaalfilter : {'DOOR' if mag else 'GEWEIGERD'} — {reden}")
    if not mag:
        return 1

    woord = extract.bevat_negeerwoord(f"{titel}\n{body}", opties.negeerwoorden)
    print(f"negeerwoorden: {'geweigerd op ' + woord if woord else 'geen'}")
    if woord:
        return 1

    gevonden = extract.zoek_adressen(f"{titel}\n{body}")
    for notitie in gevonden.notities:
        print(f"  notitie: {notitie}")
    print(f"adressen     : {[v.adres for v in gevonden.vondsten] or '(geen)'}")
    print(f"pools        : {[v.adres for v in gevonden.pools] or '(geen)'}")

    if not gevonden.vondsten:
        return 1
    if len(gevonden.vondsten) > 1 and opties.meerdere_adressen == "weiger":
        print("MEERDERE adressen -> geweigerd (zo staat het ingesteld)")
        return 1

    vondst = gevonden.vondsten[0]
    print(f"\nZou versturen: {vondst.adres} ({vondst.soort}, via {vondst.bron})")
    print(f"Al eerder verstuurd: {'JA — zou overgeslagen worden' if Staat().is_verstuurd(vondst.adres) else 'nee'}")
    print("Er is niets verstuurd en niets gekocht; dit was alleen een test.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
