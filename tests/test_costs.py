"""B13: cost in dollars, from a price table that names its source and the date checked."""
from decimal import Decimal
from pathlib import Path

import pytest

from voc.costs import PriceError, call_cost, load_prices, run_cost
from voc.replay import Reply

PRICES = Path(__file__).resolve().parent.parent / "config" / "prices.toml"


def _reply(source, tokens_in, tokens_out):
    charged = 0 if source == "replay" else tokens_in + tokens_out
    return Reply(text="x", source=source, input_tokens=tokens_in, output_tokens=tokens_out,
                 charged_tokens=charged, live_cost_tokens=tokens_in + tokens_out, attempts=1)


def test_B13_tokens_convert_to_dollars_with_the_price_table():
    prices = load_prices(PRICES)
    # 50,000 input tokens is under the long-prompt threshold, so the normal prices apply.
    assert call_cost(prices, "claude-haiku-5-5", 50_000, 10_000) == Decimal("0.010")
    assert call_cost(prices, "claude-haiku-5-5", 1_000, 200) == Decimal("0.0002")


def test_B13_a_prompt_over_the_long_context_threshold_uses_the_higher_price():
    prices = load_prices(PRICES)
    assert call_cost(prices, "claude-haiku-5-5", 150_000, 0) == Decimal("0.075")


def test_B13_the_price_table_names_its_source_and_the_date_checked():
    for model, entry in load_prices(PRICES).items():
        assert entry["source"].startswith("https://"), model
        assert len(entry["checked"]) == 10, model


def test_B13_a_model_missing_from_the_price_table_is_an_error_not_zero_cost():
    with pytest.raises(PriceError):
        call_cost(load_prices(PRICES), "claude-unknown-model", 10, 10)


def test_B13_each_run_records_its_tokens_and_cost():
    summary = run_cost(load_prices(PRICES), "claude-haiku-5-5",
                       [_reply("live", 1_000, 200), _reply("live", 2_000, 300)])
    assert summary["input_tokens"] == 3_000 and summary["output_tokens"] == 500
    assert summary["own_cost_usd"] == summary["live_cost_usd"] == Decimal("0.00055")


def test_B13_a_replayed_run_reports_zero_own_cost_and_the_original_live_cost():
    summary = run_cost(load_prices(PRICES), "claude-haiku-5-5",
                       [_reply("replay", 1_000, 200), _reply("live", 2_000, 300)])
    assert summary["own_cost_usd"] == Decimal("0.00035")
    assert summary["live_cost_usd"] == Decimal("0.00055")


# Review of pull request #14


def test_B13_a_prompt_of_exactly_the_threshold_uses_the_normal_price():
    assert call_cost(load_prices(PRICES), "claude-haiku-5-5", 100_000, 0) == Decimal("0.01")


def test_B13_a_long_prompt_pays_the_higher_output_price_too():
    assert call_cost(load_prices(PRICES), "claude-haiku-5-5", 100_001, 1_000) == Decimal("0.0525005")


def test_B13_a_live_reply_with_no_usage_is_costed_as_what_the_ledger_charged_and_flagged():
    reply = Reply(text="x", source="live", input_tokens=None, output_tokens=None,
                  charged_tokens=4_000, live_cost_tokens=4_000, attempts=1)
    summary = run_cost(load_prices(PRICES), "claude-haiku-5-5", [reply])
    assert summary["calls_without_usage"] == 1
    # Priced as if every charged token were output, the dearest kind, so it is never too low.
    assert summary["own_cost_usd"] == Decimal("0.002")
