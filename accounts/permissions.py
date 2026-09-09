"""Compatibilidade. A autorização real é Group → Permission → has_perm."""

from .catalog import PERM_AREA_PROFESSOR


def user_has_staff_access(user):
    """
    Deprecated: equivalente a accounts.access_area_professor.

    Não usa is_staff nem Profile.role. Superuser continua
    passando porque User.has_perm retorna True.
    """
    return bool(
        getattr(user, "is_authenticated", False)
        and user.has_perm(PERM_AREA_PROFESSOR)
    )
