from django.urls import path

from . import views

app_name = "fees"

urlpatterns = [
    path("collect/", views.collect_search, name="collect"),
    path("collect/<int:pk>/", views.collect_student, name="collect_student"),
    path("receipts/<int:pk>/", views.receipt_view, name="receipt"),
    path("receipts/<int:pk>/cancel/", views.cancel_receipt, name="cancel_receipt"),
    path("reports/dues/", views.dues_report, name="dues_report"),
    path("reports/collections/", views.collections_report, name="collections_report"),
    path("reports/ask/", views.ask_question, name="ask"),
    path("reports/at-risk/", views.at_risk, name="at_risk"),
    path("reminders/<int:pk>/", views.reminder, name="reminder"),
    path("tally/", views.tally_home, name="tally"),
    path("tally/<int:pk>/download/", views.tally_download, name="tally_download"),
    path("tally/ledgers.xml", views.tally_ledgers, name="tally_ledgers"),
]
