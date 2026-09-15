"""
Tests voor het opzoekwerk (Dexscreener / Blockscout).

Deze tests raken het internet NIET: de opzoeker wordt nagebootst.
"""
import unittest

import hulp  # noqa: F401

import markt


class TestBlockscoutAdresveld(unittest.TestCase):
    """
    De valkuil die 16.254 transfers met een leeg tokenveld opleverde:
    een ADRES-object gebruikt 'hash', een TOKEN-object 'address_hash'.
    """

    def test_adresobject_gebruikt_hash(self):
        self.assertEqual("0xaaa", markt.blockscout_adresveld({"hash": "0xaaa"}))

    def test_tokenobject_gebruikt_address_hash(self):
        self.assertEqual("0xbbb", markt.blockscout_adresveld({"address_hash": "0xbbb"}))

    def test_allebei_werken_dus_geen_leeg_veld(self):
        for object_ in ({"hash": "0x1"}, {"address_hash": "0x2"}, {"address": "0x3"}):
            with self.subTest(object_=object_):
                self.assertNotEqual("", markt.blockscout_adresveld(object_))

    def test_een_laagje_dieper(self):
        self.assertEqual("0xccc", markt.blockscout_adresveld({"address": {"hash": "0xccc"}}))

    def test_rommel_geeft_een_lege_tekst_en_geen_crash(self):
        for object_ in ({}, None, [], {"iets": "anders"}, {"hash": None}):
            with self.subTest(object_=object_):
                self.assertEqual("", markt.blockscout_adresveld(object_))


class TestUserAgent(unittest.TestCase):
    def test_er_gaat_een_echte_browserkop_mee(self):
        """Blockscout zit achter Cloudflare en geeft 403 op python-requests."""
        agent = markt.KOPPEN["User-Agent"]
        self.assertIn("Mozilla", agent)
        self.assertNotIn("python", agent.lower())


class TestChainnamen(unittest.TestCase):
    def test_afkortingen(self):
        self.assertEqual("solana", markt.normaliseer_chain("SOL"))
        self.assertEqual("ethereum", markt.normaliseer_chain("eth"))
        self.assertEqual("bsc", markt.normaliseer_chain("BNB"))

    def test_robinhood(self):
        """Etherscan kent chain 4663 niet; Dexscreener noemt hem 'robinhood'."""
        self.assertEqual("robinhood", markt.normaliseer_chain("4663"))
        self.assertIn("robinhoodchain.blockscout.com", markt.BLOCKSCOUT_ROBINHOOD)

    def test_onbekende_naam_blijft_zoals_hij_is(self):
        self.assertEqual("ietsnieuws", markt.normaliseer_chain("IetsNieuws"))


class TestChaincontrole(unittest.TestCase):
    EVM = "0x6b175474e89094c44da98b954eedeac495271d0f"
    MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

    def test_slim_laat_een_onbekend_token_door(self):
        """
        Een verse launch staat nog niet op Dexscreener. Precies daar is het je
        om te doen, dus doorlaten.
        """
        mag, reden = markt.controleer_chain(
            self.EVM, "evm", "base", "slim", opzoeker=lambda *a: []
        )
        self.assertTrue(mag)
        self.assertIn("verse launch", reden)

    def test_slim_blokkeert_een_bekende_mismatch(self):
        mag, reden = markt.controleer_chain(
            self.EVM, "evm", "base", "slim", opzoeker=lambda *a: ["ethereum"]
        )
        self.assertFalse(mag)
        self.assertIn("ethereum", reden)

    def test_slim_laat_de_juiste_chain_door(self):
        mag, _ = markt.controleer_chain(
            self.EVM, "evm", "base", "slim", opzoeker=lambda *a: ["base", "ethereum"]
        )
        self.assertTrue(mag)

    def test_warn_blokkeert_nooit(self):
        mag, reden = markt.controleer_chain(
            self.EVM, "evm", "base", "warn", opzoeker=lambda *a: ["ethereum"]
        )
        self.assertTrue(mag)
        self.assertIn("ethereum", reden)

    def test_off_zoekt_niets_op(self):
        def mag_niet_aangeroepen(*argumenten):
            raise AssertionError("bij 'off' hoort er niets opgezocht te worden")

        mag, _ = markt.controleer_chain(
            self.EVM, "evm", "base", "off", opzoeker=mag_niet_aangeroepen
        )
        self.assertTrue(mag)

    def test_solana_hoeft_niet_opgezocht_te_worden(self):
        def mag_niet_aangeroepen(*argumenten):
            raise AssertionError("een solana-adres kan alleen solana zijn")

        mag, _ = markt.controleer_chain(
            self.MINT, "solana", "solana", "slim", opzoeker=mag_niet_aangeroepen
        )
        self.assertTrue(mag)

    def test_solana_adres_terwijl_basedbot_op_base_staat(self):
        mag, reden = markt.controleer_chain(self.MINT, "solana", "base", "slim")
        self.assertFalse(mag)
        self.assertIn("base", reden)

    def test_mislukte_opzoeking_laat_de_call_niet_lopen(self):
        def stuk(*argumenten):
            raise OSError("geen internet")

        mag, reden = markt.controleer_chain(
            self.EVM, "evm", "base", "slim", opzoeker=stuk
        )
        self.assertTrue(mag)
        self.assertIn("niet op te zoeken", reden)


if __name__ == "__main__":
    unittest.main()


class TestOnmogelijkeCombinatie(unittest.TestCase):
    """Een 0x-adres kan nooit op Solana staan, en andersom ook niet."""

    EVM = "0x6b175474e89094c44da98b954eedeac495271d0f"
    MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

    def test_evm_adres_terwijl_basedbot_op_solana_staat(self):
        def mag_niet_aangeroepen(*argumenten):
            raise AssertionError("hier hoort geen opzoeking bij nodig te zijn")

        mag, reden = markt.controleer_chain(
            self.EVM, "evm", "solana", "slim", opzoeker=mag_niet_aangeroepen
        )
        self.assertFalse(mag)
        self.assertIn("nooit kloppen", reden)

    def test_ook_als_de_opzoeking_stuk_is(self):
        """
        Zou dit wél opgezocht worden, dan laat een mislukte opzoeking hem
        alsnog door — en dat is precies de stille fout die we niet willen.
        """
        mag, _ = markt.controleer_chain(
            self.EVM, "evm", "solana", "slim",
            opzoeker=lambda *a: (_ for _ in ()).throw(OSError("geen internet")),
        )
        self.assertFalse(mag)

    def test_warn_waarschuwt_maar_blokkeert_niet(self):
        mag, reden = markt.controleer_chain(self.EVM, "evm", "solana", "warn")
        self.assertTrue(mag)
        self.assertIn("solana", reden)
