from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("password/change/", views.password_change_view, name="password_change"),
    path("password/forgot/", views.forgot_password_view, name="forgot_password"),
    path("password/forgot/sent/", views.forgot_password_sent_view, name="forgot_password_sent"),
    path("password/reset/<uidb64>/<token>/", views.reset_confirm_view, name="reset_confirm"),
    path("welcome/<uidb64>/<token>/", views.invite_accept_view, name="invite_accept"),
]
