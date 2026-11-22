"""Login tied to the college of the request host (D6)."""

from django.contrib.auth.backends import BaseBackend

from apps.tenancy.context import get_current_college

from .models import User


class CollegeBackend(BaseBackend):
    """Authenticate only users of the current college; platform staff only on platform hosts."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        college = get_current_college()
        user = User.objects.filter(college=college, username=username).first()
        if user is None:
            User().set_password(password)  # same cost as a real check, against timing attacks
            return None
        if user.check_password(password) and user.is_active:
            return user
        return None

    def get_user(self, user_id):
        college = get_current_college()
        user = User.objects.filter(pk=user_id, is_active=True).first()
        if user is None:
            return None
        expected = college.pk if college is not None else None
        return user if user.college_id == expected else None
