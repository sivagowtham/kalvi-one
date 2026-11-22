from django.urls import path

from . import views

app_name = "fees"

urlpatterns = [
    path("collect/", views.collect_search, name="collect"),
    path("collect/<int:pk>/", views.collect_student, name="collect_student"),
    path("receipts/<int:pk>/", views.receipt_view, name="receipt"),
    path("receipts/<int:pk>/cancel/", views.cancel_receipt, name="cancel_receipt"),
]
