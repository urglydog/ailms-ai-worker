from decimal import Decimal

from app.providers.edge_tts import _parse_rate_to_multiplier, compute_rate_flag


def test_compute_rate_flag_examples_from_skill():
    assert compute_rate_flag(Decimal("1.15")) == "+15%"
    assert compute_rate_flag(Decimal("1.0")) == "+0%"
    assert compute_rate_flag(Decimal("1.30")) == "+30%"


def test_parse_rate_to_multiplier_round_trip():
    assert _parse_rate_to_multiplier("+15%") == Decimal("1.15")
    assert _parse_rate_to_multiplier("+30%") == Decimal("1.30")
    assert _parse_rate_to_multiplier(None) == Decimal("1.0")
    assert _parse_rate_to_multiplier("-10%") == Decimal("0.90")
