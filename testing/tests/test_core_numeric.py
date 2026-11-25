from decimal import Decimal
from unittest import TestCase

from core.verifier import compare_numbers, extract_normalized_numbers, normalized_quote


class NumericVerificationTests(TestCase):
    def test_normalized_quote_ignores_typographic_quotes_and_spacing(self):
        self.assertEqual(normalized_quote(" „A   citace“ "), '"A citace"')

    def test_decimal_locale_parsing_matches_equivalent_czech_and_english_amounts(self):
        czech, uncertain_cs = extract_normalized_numbers("1 234,50 Kč a 7,5 %", "cs")
        english, uncertain_en = extract_normalized_numbers("1,234.50 CZK and 7.5 %", "en")
        self.assertFalse(uncertain_cs)
        self.assertFalse(uncertain_en)
        self.assertEqual(czech, {
            (Decimal("1234.50"), "CZK"),
            (Decimal("7.5"), "%"),
        })
        self.assertEqual(english, czech)

    def test_compare_numbers_flags_unmatched_values_and_units(self):
        missing, uncertain = compare_numbers(
            "Celkem 12 EUR", ["Celkem 12 CZK"],
            {"source_number_locale": "cs", "output_number_locale": "cs"},
        )
        self.assertEqual(missing, {(Decimal("12"), "EUR")})
        self.assertFalse(uncertain)

    def test_unsupported_number_locale_is_rejected(self):
        with self.assertRaises(ValueError):
            extract_normalized_numbers("10", "de")
