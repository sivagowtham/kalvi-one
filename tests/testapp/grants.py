from apps.accounts.permissions import register
from apps.accounts.roles import Role

register("testapp.view_widget", [Role.FACULTY, Role.PRINCIPAL], "Test: see widgets")
register("testapp.change_widget", [Role.PRINCIPAL], "Test: edit widgets")
