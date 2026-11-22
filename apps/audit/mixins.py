"""The Audited mixin. Kept free of model imports so any app can use it."""


class AuditBypassError(RuntimeError):
    """A bulk operation that would change audited rows without an audit record."""


class Audited:
    """Mix into a model to record every create, update and delete (D8).

    audit_exclude: fields never recorded (e.g. timestamps that change on every save).
    audit_mask:    fields recorded only as "changed", never with their values.
    """

    audit_exclude: tuple[str, ...] = ()
    audit_mask: tuple[str, ...] = ()
