"""Small Python sample demonstrating a successful SpotAI Quality Gate."""


def add(first: float, second: float) -> float:
    """Return the sum of two numbers."""
    return first + second


def average(values: list[float]) -> float:
    """Return the arithmetic mean, or zero for an empty list."""
    if not values:
        return 0.0
    return sum(values) / len(values)
