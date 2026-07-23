BASE_PRICE_VND = 150_000
PRIVATE_MULTIPLIER = 4


def price_for(is_private: bool) -> int:
    return BASE_PRICE_VND * PRIVATE_MULTIPLIER if is_private else BASE_PRICE_VND
