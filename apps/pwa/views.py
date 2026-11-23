"""Files that make KalviOne installable on phones as an app (D33).

All of these are public: the browser fetches them before anyone signs in. None of them
contains college data beyond the college's name, which the login page already shows.
"""

from pathlib import Path

from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET

from apps.accounts.permissions import public

ICON_DIR = Path(__file__).resolve().parent / "icons"
ICONS = {
    "icon-192.png",
    "icon-512.png",
    "icon-maskable-512.png",
    "apple-touch-icon.png",
}
THEME_COLOR = "#1f5fbf"
BACKGROUND_COLOR = "#f5f6f8"
# Bump when sw.js or the offline page changes, so phones drop the old cache.
CACHE_VERSION = "kalvione-v1"


@public
@require_GET
def manifest(request: HttpRequest) -> JsonResponse:
    """Web app manifest. Each college installs as its own app with its own name."""
    college = getattr(request, "college", None)
    name = college.name if college else "KalviOne"
    short_name = college.code if college else "KalviOne"
    data = {
        "id": "/",
        "name": name,
        "short_name": short_name,
        "description": "College ERP for staff, students and parents.",
        "start_url": "/?source=app",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "theme_color": THEME_COLOR,
        "background_color": BACKGROUND_COLOR,
        "icons": [
            {"src": "/app/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/app/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
            {
                "src": "/app/icons/icon-maskable-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
        ],
    }
    response = JsonResponse(data, json_dumps_params={"indent": 2})
    response["Content-Type"] = "application/manifest+json"
    response["Cache-Control"] = "public, max-age=3600"
    # The Android app's college picker reads this from its own origin to check the code.
    # Safe to share: it only holds the college's public name.
    response["Access-Control-Allow-Origin"] = "*"
    return response


@public
@require_GET
def service_worker(request: HttpRequest) -> HttpResponse:
    """Service worker, served from the site root so it can control every page."""
    body = render_to_string("pwa/sw.js", {"cache_version": CACHE_VERSION})
    response = HttpResponse(body, content_type="application/javascript")
    # Phones must always check for a newer worker.
    response["Cache-Control"] = "no-cache"
    response["Service-Worker-Allowed"] = "/"
    return response


@public
@require_GET
def offline(request: HttpRequest) -> HttpResponse:
    """Shown by the service worker when the phone has no network."""
    return render(request, "pwa/offline.html", {"college": getattr(request, "college", None)})


@public
@require_GET
def icon(request: HttpRequest, name: str) -> FileResponse:
    if name not in ICONS:
        raise Http404("No such icon")
    response = FileResponse((ICON_DIR / name).open("rb"), content_type="image/png")
    response["Cache-Control"] = "public, max-age=604800"
    return response
