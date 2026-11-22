from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from apps.accounts.permissions import public


@public
@require_GET
def health(request: HttpRequest) -> JsonResponse:
    """Liveness and database check for Docker and load balancers.

    Public on purpose: load balancers call it without logging in.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return JsonResponse({"status": "ok"})
