"""Every URL must declare a permission or be explicitly public (D7)."""

from django.urls import URLPattern, URLResolver, get_resolver

from tests.testapp.urls import unmarked_urlpatterns

# Django admin enforces its own checks through User.has_perm, which uses the registry.
DELEGATED_NAMESPACES = {"admin"}


def walk(patterns, prefix="", namespaces=()):
    for entry in patterns:
        if isinstance(entry, URLResolver):
            ns = (*namespaces, entry.namespace) if entry.namespace else namespaces
            yield from walk(entry.url_patterns, prefix + str(entry.pattern), ns)
        elif isinstance(entry, URLPattern):
            yield prefix + str(entry.pattern), entry.callback, namespaces


def is_marked(callback) -> bool:
    targets = [callback, getattr(callback, "view_class", None)]
    return any(
        getattr(t, "kalvi_permission", None) or getattr(t, "kalvi_public", False)
        for t in targets
        if t is not None
    )


def unmarked_views(patterns):
    return [
        route
        for route, callback, namespaces in walk(patterns)
        if not DELEGATED_NAMESPACES.intersection(namespaces) and not is_marked(callback)
    ]


def test_every_view_declares_a_permission_or_is_public():
    assert unmarked_views(get_resolver().url_patterns) == []


def test_the_check_catches_an_unmarked_view():
    assert unmarked_views(unmarked_urlpatterns) == ["unmarked/"]
