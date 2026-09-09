"""Catálogo idempotente de grupos e permissões reais do sistema."""

from django.contrib.auth.models import Group, Permission


GROUP_ALUNO = "aluno"
GROUP_PROFESSOR = "professor"
GROUP_COORDENADOR = "coordenador"
GROUP_DIRETOR = "diretor"

GROUPS = (
    GROUP_ALUNO,
    GROUP_PROFESSOR,
    GROUP_COORDENADOR,
    GROUP_DIRETOR,
)

PERM_AREA_ALUNO = "accounts.access_area_aluno"
PERM_AREA_PROFESSOR = "accounts.access_area_professor"
PERM_AREA_COORDENACAO = "accounts.access_area_coordenacao"
PERM_AREA_DIRECAO = "accounts.access_area_direcao"


def _perm(codename, app_label):
    return Permission.objects.get(
        content_type__app_label=app_label,
        codename=codename,
    )


def _permissions_for_group(group_name):
    perms = []

    if group_name == GROUP_ALUNO:
        perms = [
            _perm("access_area_aluno", "accounts"),
        ]

    elif group_name == GROUP_PROFESSOR:
        perms = [
            _perm("access_area_professor", "accounts"),
            _perm("view_aluno", "alunos"),
            _perm("add_aluno", "alunos"),
            _perm("view_turma", "alunos"),
            _perm("view_matricula", "alunos"),
            _perm("add_matricula", "alunos"),
            _perm("change_matricula", "alunos"),
            _perm("view_questao", "questoes"),
            _perm("add_questao", "questoes"),
            _perm("view_resultado", "questoes"),
            _perm("view_avaliacao", "questoes"),
            _perm("add_avaliacao", "questoes"),
            _perm("change_avaliacao", "questoes"),
            _perm("view_relatorio_pedagogico", "questoes"),
        ]

    elif group_name == GROUP_COORDENADOR:
        perms = _permissions_for_group(GROUP_PROFESSOR) + [
            _perm("access_area_coordenacao", "accounts"),
            _perm("change_aluno", "alunos"),
            _perm("add_turma", "alunos"),
            _perm("change_turma", "alunos"),
            _perm("change_questao", "questoes"),
            _perm("change_resultado", "questoes"),
        ]

    elif group_name == GROUP_DIRETOR:
        perms = _permissions_for_group(GROUP_COORDENADOR) + [
            _perm("access_area_direcao", "accounts"),
            _perm("delete_aluno", "alunos"),
            _perm("delete_turma", "alunos"),
            _perm("delete_matricula", "alunos"),
            _perm("delete_questao", "questoes"),
            _perm("delete_resultado", "questoes"),
            _perm("delete_avaliacao", "questoes"),
        ]

    return perms


def seed_auth_catalog():
    """Cria grupos e associa permissões. Pode rodar quantas vezes for preciso."""
    for name in GROUPS:
        group, _created = Group.objects.get_or_create(name=name)
        group.permissions.set(_permissions_for_group(name))

    return Group.objects.filter(name__in=GROUPS)


def assign_group(user, group_name):
    seed_auth_catalog()
    group = Group.objects.get(name=group_name)
    user.groups.add(group)
    if hasattr(user, "_perm_cache"):
        del user._perm_cache
    if hasattr(user, "_user_perm_cache"):
        del user._user_perm_cache
    if hasattr(user, "_group_perm_cache"):
        del user._group_perm_cache
    return user


def create_user_with_group(username, password, group_name, **extra):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.create_user(
        username=username,
        password=password,
        **extra,
    )
    return assign_group(user, group_name)


def post_login_url_name(user):
    if user.has_perm(PERM_AREA_DIRECAO):
        return "area_direcao"
    if user.has_perm(PERM_AREA_COORDENACAO):
        return "area_coordenacao"
    if user.has_perm(PERM_AREA_PROFESSOR):
        return "area_professor"
    if user.has_perm(PERM_AREA_ALUNO):
        return "area_aluno"
    return "home"
