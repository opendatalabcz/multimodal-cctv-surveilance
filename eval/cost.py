"""Turn Azure token usage into a dollar cost.

Prices are Azure OpenAI Global standard, USD per 1M tokens. Cached input is the
prompt-cache rate: half of the input price for gpt-4o, one tenth for the GPT-5
deployments. Reasoning tokens are already included in the output count.
"""

from __future__ import annotations

PRICES_PER_MILLION = {
    "gpt-4o": {"input": 2.50, "cached_input": 1.25, "output": 10.0},
    "gpt-5.6-luna": {"input": 0.20, "cached_input": 0.02, "output": 1.20},
    "gpt-6-astra": {"input": 10.0, "cached_input": 1.0, "output": 50.0},
}


def token_counts(usage: dict | None) -> dict[str, int]:
    """Normalize Chat Completions and Responses API usage objects."""
    usage = usage or {}
    input_tokens = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
    output_tokens = int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
    input_details = usage.get("input_tokens_details") or usage.get("prompt_tokens_details") or {}
    output_details = usage.get("output_tokens_details") or usage.get("completion_tokens_details") or {}
    cached = int(input_details.get("cached_tokens") or 0)
    reasoning = int(output_details.get("reasoning_tokens") or 0)
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": min(cached, input_tokens),
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning,
    }


def cost_usd(model: str, usage: dict | None) -> dict | None:
    prices = PRICES_PER_MILLION.get(model)
    if prices is None:
        return None
    counts = token_counts(usage)
    uncached = counts["input_tokens"] - counts["cached_input_tokens"]
    input_cost = uncached * prices["input"] / 1_000_000
    cached_cost = counts["cached_input_tokens"] * prices["cached_input"] / 1_000_000
    output_cost = counts["output_tokens"] * prices["output"] / 1_000_000
    return {
        "input": round(input_cost, 6),
        "cached_input": round(cached_cost, 6),
        "output": round(output_cost, 6),
        "total": round(input_cost + cached_cost + output_cost, 6),
        "prices_per_million": prices,
    }


def summarize_usage(model: str, records: list[dict]) -> dict:
    """Cost of the stored answers. Each record is one scored frame."""
    totals = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "frames": len(records),
        "frames_with_usage": 0,
        "frames_missing_usage": 0,
    }
    for record in records:
        counts = token_counts(record.get("usage"))
        if not record.get("usage"):
            totals["frames_missing_usage"] += 1
            continue
        totals["frames_with_usage"] += 1
        for key in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens"):
            totals[key] += counts[key]
    priced = cost_usd(model, _usage_from_totals(totals))
    return {"usage": totals, "cost_usd": priced}


def _usage_from_totals(totals: dict) -> dict:
    return {
        "input_tokens": totals["input_tokens"],
        "output_tokens": totals["output_tokens"],
        "input_tokens_details": {"cached_tokens": totals["cached_input_tokens"]},
        "output_tokens_details": {"reasoning_tokens": totals["reasoning_tokens"]},
    }
