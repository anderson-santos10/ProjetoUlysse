from django.contrib.auth.mixins import PermissionRequiredMixin as DjangoPermissionRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


class PermissionRequiredMixin(DjangoPermissionRequiredMixin):
    """
    Anônimo → login neutro.
    Autenticado sem permissão → 403.
    Autorização: user.has_perm (Groups → Permissions).
    """

    login_url = "login"
    redirect_field_name = "next"

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect_to_login(
                self.request.get_full_path(),
                self.get_login_url(),
                self.get_redirect_field_name(),
            )
        raise PermissionDenied(self.get_permission_denied_message())
