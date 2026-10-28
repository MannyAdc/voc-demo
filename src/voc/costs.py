"""B13: turn token counts into dollars with a price table that names its source and date."""
import tomllib
from decimal import Decimal

MILLION = Decimal(1_000_000)


class PriceError(ValueError):
    pass


def load_prices(path):
    with open(path, "rb") as f:
        return tomllib.load(f)["models"]


def call_cost(prices, model, input_tokens, output_tokens):
    """The dollar cost of one call. A request over the threshold pays the higher prices on all its tokens."""
    entry = prices.get(model)
    if entry is None:
        raise PriceError(f"no price for model {model!r}, so its cost is unknown")
    long = input_tokens > entry["long_context_threshold"]
    in_price = Decimal(entry["long_input_per_mtok" if long else "input_per_mtok"])
    out_price = Decimal(entry["long_output_per_mtok" if long else "output_per_mtok"])
    return (Decimal(input_tokens) * in_price + Decimal(output_tokens) * out_price) / MILLION


def run_cost(prices, model, replies):
    """Tokens and cost for a run. A replayed reply costs nothing now, but its original live cost is kept."""
    summary = {"input_tokens": 0, "output_tokens": 0, "own_cost_usd": Decimal(0), "live_cost_usd": Decimal(0)}
    for reply in replies:
        tokens_in, tokens_out = reply.input_tokens or 0, reply.output_tokens or 0
        cost = call_cost(prices, model, tokens_in, tokens_out)
        summary["input_tokens"] += tokens_in
        summary["output_tokens"] += tokens_out
        summary["live_cost_usd"] += cost
        if reply.source != "replay":
            summary["own_cost_usd"] += cost
    return summary
