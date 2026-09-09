ALUNO_SESSION_KEYS = (
    "aluno_id",
    "questao_atual",
    "respostas",
    "questionario_finalizado",
    "acertos",
    "total_questoes",
    "questoes_ordem",
    "alternativas_ordem",
    "questoes_versoes",
    "inicio_questionario",
    "resposta_mostrada",
    "resposta_escolhida",
    "resposta_correta",
    "acertou",
    "questionario_bloqueado",
    "segundos_restantes",
    "xp_ganho",
    "tempo_segundos",
)


def clear_aluno_session(session):
    """Remove só o estado do aluno/prova. Não altera autenticação Django."""
    for key in ALUNO_SESSION_KEYS:
        session.pop(key, None)


def bind_linked_aluno_session(request):
    """
    Se o User autenticado estiver ligado a um Aluno, a sessão
    passa a ser desse aluno (impede impersonar outro via aluno_id).
    Sem vínculo, o fluxo por RA permanece.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None

    from .models import Aluno

    aluno = Aluno.objects.filter(user_id=user.pk).first()
    if aluno is not None:
        request.session["aluno_id"] = aluno.id
    return aluno


def aluno_session_exists(aluno_id):
    from django.core.exceptions import ValidationError

    from .models import Aluno

    if not aluno_id:
        return False

    try:
        return Aluno.objects.filter(pk=aluno_id).exists()
    except (ValueError, TypeError, ValidationError):
        return False
