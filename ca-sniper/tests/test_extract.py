"""
Tests voor de adresherkenning.

Dit is het belangrijkste testbestand van het project: wat hier doorheen komt,
wordt straks gekocht.
"""
import unittest

from hulp import base58_codeer  # noqa: F401  (zet ook sys.path goed)

import extract


class TestSolana(unittest.TestCase):
    def test_echt_adres_wordt_herkend(self):
        # De echte mints van USDC en wrapped SOL.
        for adres in (
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "So11111111111111111111111111111111111111112",
        ):
            with self.subTest(adres=adres):
                self.assertTrue(extract.is_solana_adres(adres))

    def test_moet_naar_precies_32_bytes_decoderen(self):
        # Lengte alleen is niet genoeg: 32 bytes is de echte controle.
        van_31 = base58_codeer(b"\x01" * 31)
        van_33 = base58_codeer(b"\x01" * 33)
        self.assertFalse(extract.is_solana_adres(van_31))
        self.assertFalse(extract.is_solana_adres(van_33))
        self.assertTrue(extract.is_solana_adres(base58_codeer(b"\x07" * 32)))

    def test_handtekening_van_88_tekens_matcht_niet(self):
        """Een Solana-signature is 64 bytes -> ongeveer 88 tekens base58."""
        handtekening = base58_codeer(bytes(range(64)))
        self.assertGreaterEqual(len(handtekening), 85)
        self.assertFalse(extract.is_solana_adres(handtekening))
        gevonden = extract.zoek_adressen(f"gelukt! tx {handtekening} kijk maar")
        self.assertEqual([], [v.adres for v in gevonden.vondsten])

    def test_tekens_buiten_het_alfabet(self):
        # 0, O, I en l zitten niet in base58.
        self.assertFalse(extract.is_solana_adres("0" * 43))
        self.assertIsNone(extract.base58_decodeer("OIl0"))


class TestEvm(unittest.TestCase):
    def test_gewoon_adres(self):
        adres = "0x6B175474E89094C44Da98b954EedeAC495271d0F"
        self.assertTrue(extract.is_evm_adres(adres))
        gevonden = extract.zoek_adressen(f"CA {adres} ape")
        # Hoofdletters worden kleine letters, anders koop je hetzelfde token twee keer.
        self.assertEqual([adres.lower()], [v.adres for v in gevonden.vondsten])

    def test_transactiehash_van_64_hex_matcht_niet(self):
        hash64 = "0x" + "ab12" * 16
        self.assertEqual(66, len(hash64))
        self.assertFalse(extract.is_evm_adres(hash64))
        gevonden = extract.zoek_adressen(f"tx: {hash64} bevestigd")
        self.assertEqual([], [v.adres for v in gevonden.vondsten])

    def test_hash_zonder_0x_matcht_ook_niet_als_solana(self):
        hash64 = "ab12" * 16
        gevonden = extract.zoek_adressen(f"tx {hash64} done")
        self.assertEqual([], [v.adres for v in gevonden.vondsten])

    def test_te_kort_en_te_lang(self):
        self.assertFalse(extract.is_evm_adres("0x" + "a" * 39))
        self.assertFalse(extract.is_evm_adres("0x" + "a" * 41))


class TestLinks(unittest.TestCase):
    POOL = "0x1111111111111111111111111111111111111111"
    TOKEN = "0x6b175474e89094c44da98b954eedeac495271d0f"

    def test_dexscreener_link_is_een_pool_en_wordt_nooit_gekocht(self):
        gevonden = extract.zoek_adressen(f"https://dexscreener.com/base/{self.POOL} send it")
        self.assertEqual([], [v.adres for v in gevonden.vondsten], "pooladres mag NOOIT als token gelden")
        self.assertEqual([self.POOL], [v.adres for v in gevonden.pools])
        self.assertEqual("base", gevonden.pools[0].chain_hint)

    def test_pool_wordt_omgezet_naar_het_echte_token(self):
        def nep_ophaler(chain, paar, limiet_ms):
            return {"chainId": "base", "baseToken": {"address": self.TOKEN}}

        gevonden = extract.zoek_adressen(f"https://dexscreener.com/base/{self.POOL}")
        echt = extract.los_pool_op(gevonden.pools[0], nep_ophaler)
        self.assertIsNotNone(echt)
        self.assertEqual(self.TOKEN, echt.adres)
        self.assertEqual("pool-omgezet", echt.bron)

    def test_pool_die_niet_omgezet_kan_worden_geeft_niets(self):
        gevonden = extract.zoek_adressen(f"https://dexscreener.com/base/{self.POOL}")
        self.assertIsNone(extract.los_pool_op(gevonden.pools[0], lambda *a: None))
        self.assertIsNone(
            extract.los_pool_op(gevonden.pools[0], lambda *a: (_ for _ in ()).throw(OSError("stuk")))
        )

    def test_tokenlink_wijst_wel_naar_het_token(self):
        mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        gevonden = extract.zoek_adressen(f"https://birdeye.so/token/{mint}")
        self.assertEqual([mint], [v.adres for v in gevonden.vondsten])
        self.assertEqual("token-link", gevonden.vondsten[0].bron)

    def test_onbekende_link_wordt_overgeslagen_met_notitie(self):
        gevonden = extract.zoek_adressen("kijk op https://ietsonbekends.xyz/abc")
        self.assertEqual([], [v.adres for v in gevonden.vondsten])
        self.assertTrue(any("onbekende link" in n for n in gevonden.notities))


class TestMeerdere(unittest.TestCase):
    def test_dubbel_adres_komt_maar_een_keer_terug(self):
        adres = "0x6b175474e89094c44da98b954eedeac495271d0f"
        gevonden = extract.zoek_adressen(f"{adres} en nog eens {adres.upper()}")
        self.assertEqual(1, len(gevonden.vondsten))

    def test_twee_verschillende_adressen_worden_allebei_gezien(self):
        gevonden = extract.zoek_adressen(
            "0x6b175474e89094c44da98b954eedeac495271d0f en "
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        )
        self.assertEqual(2, len(gevonden.vondsten))


class TestNegeerwoorden(unittest.TestCase):
    def test_hele_woorden_en_niet_meer_dan_dat(self):
        """'rug' mag niet matchen in 'terug' of 'brug'."""
        self.assertIsNone(extract.bevat_negeerwoord("kijk maar terug", ["rug"]))
        self.assertIsNone(extract.bevat_negeerwoord("over de brug", ["rug"]))
        self.assertIsNone(extract.bevat_negeerwoord("terugkomen op de brug", ["rug"]))
        self.assertEqual("rug", extract.bevat_negeerwoord("dit is een rug", ["rug"]))
        self.assertEqual("rug", extract.bevat_negeerwoord("RUG!", ["rug"]))

    def test_lege_lijst_weigert_niets(self):
        self.assertIsNone(extract.bevat_negeerwoord("wat dan ook", []))

    def test_woord_met_leestekens_maakt_het_niet_stuk(self):
        self.assertIsNone(extract.bevat_negeerwoord("gewone tekst", ["(rug"]))


if __name__ == "__main__":
    unittest.main()
