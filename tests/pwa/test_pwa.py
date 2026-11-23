"""KalviOne installs on phones as an app (D26)."""

import pytest

pytestmark = pytest.mark.django_db

ALPHA = "alpha.localhost"


def test_manifest_names_the_college(client, college_a):
    response = client.get("/manifest.webmanifest", HTTP_HOST=ALPHA)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/manifest+json"
    data = response.json()
    assert data["name"] == "Alpha College of Engineering"
    assert data["short_name"] == "ACE"
    assert data["display"] == "standalone"
    assert data["scope"] == "/"
    sizes = {icon["sizes"] for icon in data["icons"]}
    assert {"192x192", "512x512"} <= sizes
    assert any(icon.get("purpose") == "maskable" for icon in data["icons"])


def test_manifest_on_platform_host_uses_product_name(client):
    assert client.get("/manifest.webmanifest").json()["name"] == "KalviOne"


def test_each_college_gets_its_own_manifest(client, college_a, college_b):
    alpha = client.get("/manifest.webmanifest", HTTP_HOST=ALPHA).json()
    beta = client.get("/manifest.webmanifest", HTTP_HOST="beta.localhost").json()
    assert alpha["name"] != beta["name"]


def test_manifest_icons_are_served(client, college_a):
    for icon in client.get("/manifest.webmanifest", HTTP_HOST=ALPHA).json()["icons"]:
        response = client.get(icon["src"], HTTP_HOST=ALPHA)
        assert response.status_code == 200
        assert response["Content-Type"] == "image/png"
        assert b"".join(response.streaming_content).startswith(b"\x89PNG")


def test_unknown_icon_is_404(client):
    assert client.get("/app/icons/../views.py").status_code == 404
    assert client.get("/app/icons/secret.png").status_code == 404


def test_service_worker_controls_whole_site_and_is_never_cached(client, college_a):
    response = client.get("/sw.js", HTTP_HOST=ALPHA)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/javascript"
    assert response["Service-Worker-Allowed"] == "/"
    assert response["Cache-Control"] == "no-cache"
    body = response.content.decode()
    assert "/offline/" in body
    # Pages hold personal data: the worker only caches the offline page and icons.
    assert "cache.put" not in body


def test_offline_page(client, college_a):
    response = client.get("/offline/", HTTP_HOST=ALPHA)
    assert response.status_code == 200
    page = response.content.decode()
    assert "offline" in page
    assert "Alpha College of Engineering" in page


def test_pages_link_the_manifest_and_register_the_worker(client, college_a):
    page = client.get("/login/", HTTP_HOST=ALPHA).content.decode()
    assert 'rel="manifest" href="/manifest.webmanifest"' in page
    assert 'serviceWorker.register("/sw.js"' in page


def test_pwa_files_are_get_only(client):
    assert client.post("/manifest.webmanifest").status_code == 405
    assert client.post("/sw.js").status_code == 405
