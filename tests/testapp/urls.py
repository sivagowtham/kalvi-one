from django.urls import path

from . import views

urlpatterns = [
    path("widgets/", views.widget_list, name="widget-list"),
    path("open/", views.open_page, name="open"),
]

# Used only by the default-deny test to prove it catches unmarked views.
unmarked_urlpatterns = [path("unmarked/", views.unmarked)]
