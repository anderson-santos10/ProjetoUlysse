"""Escopo de turmas: Groups → Permissions, nunca is_staff."""

from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import Aluno, Turma


def gerencia_todas_turmas(user):
    return bool(
        getattr(user, "is_authenticated", False)
        and user.has_perm("alunos.change_turma")
    )


def queryset_turmas_visiveis(user):
    queryset = Turma.objects.select_related("professor_responsavel")
    if not getattr(user, "is_authenticated", False):
        return queryset.none()
    if gerencia_todas_turmas(user):
        return queryset
    if user.has_perm("alunos.view_turma"):
        return queryset.filter(professor_responsavel=user)
    return queryset.none()


def ids_turmas_visiveis(user):
    return list(queryset_turmas_visiveis(user).values_list("pk", flat=True))


def usuario_pode_acessar_turma(user, turma):
    if not turma or not getattr(user, "is_authenticated", False):
        return False
    if gerencia_todas_turmas(user):
        return True
    return (
        user.has_perm("alunos.view_turma")
        and turma.professor_responsavel_id == user.pk
    )


def queryset_alunos_visiveis(user):
    if gerencia_todas_turmas(user):
        return Aluno.objects.all()
    ids = ids_turmas_visiveis(user)
    if not ids:
        return Aluno.objects.none()
    return Aluno.objects.filter(matriculas__turma_id__in=ids).distinct()


def usuario_pode_acessar_aluno(user, aluno):
    if not aluno or not getattr(user, "is_authenticated", False):
        return False
    if gerencia_todas_turmas(user):
        return True
    return queryset_alunos_visiveis(user).filter(pk=aluno.pk).exists()


def queryset_resultados_visiveis(user, queryset=None):
    from questoes.models import Resultado

    qs = queryset if queryset is not None else Resultado.objects.all()
    if gerencia_todas_turmas(user):
        return qs
    ids = ids_turmas_visiveis(user)
    if not ids:
        return qs.none()
    return qs.filter(matricula__turma_id__in=ids)


def usuario_pode_acessar_resultado(user, resultado):
    if not resultado or not getattr(user, "is_authenticated", False):
        return False
    if gerencia_todas_turmas(user):
        return True
    turma = getattr(getattr(resultado, "matricula", None), "turma", None)
    return usuario_pode_acessar_turma(user, turma)


def usuarios_podem_ser_responsaveis():
    User = get_user_model()
    return (
        User.objects
        .filter(
            Q(is_superuser=True)
            | Q(groups__name__in=["professor", "coordenador", "diretor"])
        )
        .distinct()
        .order_by("username")
    )
