from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def inr(value) -> str:
    """12345678.5 -> 1,23,45,678.50 (Indian digit grouping)."""
    if value in (None, ""):
        return ""
    amount = Decimal(value).quantize(Decimal("0.01"))
    sign = "-" if amount < 0 else ""
    rupees, paise = f"{abs(amount):.2f}".split(".")
    head, tail = rupees[:-3], rupees[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return sign + ",".join([*groups, tail]) + "." + paise
