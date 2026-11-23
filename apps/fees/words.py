"""Rupee amounts in words, the Indian way (lakh and crore), for printed receipts."""

from decimal import ROUND_HALF_UP, Decimal

ONES = (
    *("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"),
    *("ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen"),
    *("seventeen", "eighteen", "nineteen"),
)
TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")


def _below_hundred(n: int) -> str:
    if n < 20:
        return ONES[n]
    tens, ones = divmod(n, 10)
    return TENS[tens] + (f"-{ONES[ones]}" if ones else "")


def _below_thousand(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    parts = []
    if hundreds:
        parts.append(f"{ONES[hundreds]} hundred")
    if rest:
        parts.append(_below_hundred(rest))
    return " ".join(parts)


def number_in_words(n: int) -> str:
    if n == 0:
        return "zero"
    parts = []
    crores, n = divmod(n, 10_000_000)
    lakhs, n = divmod(n, 100_000)
    thousands, n = divmod(n, 1000)
    if crores:
        parts.append(f"{number_in_words(crores)} crore")
    if lakhs:
        parts.append(f"{_below_hundred(lakhs)} lakh")
    if thousands:
        parts.append(f"{_below_hundred(thousands)} thousand")
    if n:
        parts.append(_below_thousand(n))
    return " ".join(parts)


def rupees_in_words(amount: Decimal) -> str:
    """e.g. 26500.50 -> 'Rupees twenty-six thousand five hundred and fifty paise only'."""
    amount = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    rupees = int(amount)
    paise = int((amount - rupees) * 100)
    text = f"Rupees {number_in_words(rupees)}"
    if paise:
        text += f" and {number_in_words(paise)} paise"
    return text + " only"
