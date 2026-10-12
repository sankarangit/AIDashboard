"""Reference prices are intentionally absent.

Historical provider responses that do not include a monetary amount are not
priced from a local catalog.
"""


def reference_unit_prices() -> dict:
    return {}
