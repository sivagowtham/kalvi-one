"""Resolve the current college from the request host (D2, D12)."""

from __future__ import annotations

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse

from .context import college_context
from .models import College


def college_slug_for_host(host: str) -> str | None:
    """Return the college subdomain for ``host``, or None for platform hosts.

    Raises Http404 for hosts that are neither a college nor a platform host.
    """
    host = host.split(":", 1)[0].lower().rstrip(".")
    if host in settings.TENANT_PLATFORM_HOSTS:
        return None
    for base in settings.TENANT_BASE_DOMAINS:
        suffix = "." + base
        if host.endswith(suffix):
            label = host[: -len(suffix)]
            if label and "." not in label:
                return label
    raise Http404("Unknown host")


class TenantMiddleware:
    """Set ``request.college`` and the current-college context for the whole request.

    - ``<slug>.<base domain>`` serves that college; unknown or inactive slugs get 404.
    - Hosts in TENANT_PLATFORM_HOSTS serve the platform (no college).
    - TENANT_DEDICATED_COLLEGE_SLUG, when set, serves one college on every host
      (dedicated deployment, D2).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        dedicated = settings.TENANT_DEDICATED_COLLEGE_SLUG
        slug = dedicated or college_slug_for_host(request.get_host())
        college = None
        if slug is not None:
            college = College.objects.filter(slug=slug, is_active=True).first()
            if college is None:
                raise Http404("No such college")
        request.college = college
        with college_context(college):
            return self.get_response(request)
