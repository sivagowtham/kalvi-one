from django.http import HttpResponse

from apps.accounts.permissions import public, require_perm


@require_perm("testapp.view_widget")
def widget_list(request):
    return HttpResponse("widgets")


@public
def open_page(request):
    return HttpResponse("open")


def unmarked(request):  # deliberately missing a permission mark
    return HttpResponse("oops")
