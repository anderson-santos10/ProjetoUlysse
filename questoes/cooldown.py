from datetime import timedelta

from django.utils import timezone

from .models import Resultado

COOLDOWN_HOURS = 8


def verificar_bloqueio(aluno):
    if not aluno:
        return False, None, 0

    ultima_tentativa = (
        Resultado.objects
        .filter(aluno=aluno)
        .order_by("-data")
        .first()
    )

    if not ultima_tentativa:
        return False, None, 0

    agora = timezone.now()
    proxima_tentativa = ultima_tentativa.data + timedelta(hours=COOLDOWN_HOURS)

    if agora < proxima_tentativa:
        segundos_restantes = int((proxima_tentativa - agora).total_seconds())
        return True, proxima_tentativa, segundos_restantes

    return False, None, 0
