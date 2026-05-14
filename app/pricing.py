"""Derive-on-read runtime cost computation."""

MODEL_RATES: dict[str, dict[str, float]] = {
    "claude-opus-4-7": {"input": 5.0, "output": 25.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
}


def compute_cost(
    model: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
) -> float | None:
    """Return USD cost, or None when a row cannot be priced."""
    if model is None or input_tokens is None or output_tokens is None:
        return None
    rate = MODEL_RATES.get(model)
    if rate is None:
        return None
    return (input_tokens / 1_000_000) * rate["input"] + (
        output_tokens / 1_000_000
    ) * rate["output"]
