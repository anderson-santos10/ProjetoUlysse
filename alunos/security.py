from django.utils import timezone


def mascarar_ra(ra):
    texto = str(ra or "").strip()
    if not texto:
        return ""
    if len(texto) <= 4:
        return "*" * len(texto)
    return texto[:4] + ("*" * (len(texto) - 4))


RA_MAX_FALHAS = 8
RA_JANELA_SEGUNDOS = 600
RA_FALHAS_SESSION_KEY = "ra_falhas"


def _agora():
    return timezone.now().timestamp()


def falhas_recentes(session):
    agora = _agora()
    brutas = session.get(RA_FALHAS_SESSION_KEY) or []
    return [
        marca
        for marca in brutas
        if isinstance(marca, (int, float))
        and agora - marca < RA_JANELA_SEGUNDOS
    ]


def ra_acesso_limitado(session):
    recentes = falhas_recentes(session)
    session[RA_FALHAS_SESSION_KEY] = recentes
    return len(recentes) >= RA_MAX_FALHAS


def registrar_falha_ra(session):
    recentes = falhas_recentes(session)
    recentes.append(_agora())
    session[RA_FALHAS_SESSION_KEY] = recentes


def limpar_falhas_ra(session):
    session.pop(RA_FALHAS_SESSION_KEY, None)


def formatar_tempo(segundos):
    segundos = segundos or 0
    horas = segundos // 3600
    minutos = (segundos % 3600) // 60
    segundos_restantes = segundos % 60
    if horas > 0:
        return (
            f"{horas}h "
            f"{minutos:02d}min "
            f"{segundos_restantes:02d}s"
        )
    return f"{minutos:02d}min {segundos_restantes:02d}s"
