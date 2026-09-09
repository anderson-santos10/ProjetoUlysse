"""Regras de vínculo. A turma atual nunca é um FK direto em Aluno."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Matricula, Turma


def hoje():
    return timezone.localdate()


def matricula_ativa_em(aluno):
    if aluno is None:
        return None
    if getattr(aluno, "_state", None) and not aluno.pk:
        return None
    return (
        Matricula.objects
        .select_related("turma", "turma__professor_responsavel")
        .filter(aluno=aluno, ativa=True)
        .first()
    )


def _validar_datas(data_inicio, data_fim):
    if data_fim and data_inicio and data_fim < data_inicio:
        raise ValidationError("A data de término não pode ser anterior ao início.")


def matricular(aluno, turma, data_inicio=None):
    if not isinstance(turma, Turma):
        raise ValidationError("Turma inválida.")
    if not turma.ativa:
        raise ValidationError("Não é possível matricular em uma turma inativa.")
    data_inicio = data_inicio or hoje()
    atual = matricula_ativa_em(aluno)
    if atual:
        if atual.turma_id == turma.pk:
            raise ValidationError("O aluno já está vinculado a esta turma.")
        raise ValidationError(
            "O aluno já possui um vínculo ativo. Encerre ou transfira antes."
        )
    with transaction.atomic():
        if aluno.serie != turma.serie:
            aluno.serie = turma.serie
            aluno.save(update_fields=["serie"])
        return Matricula.objects.create(
            aluno=aluno,
            turma=turma,
            data_inicio=data_inicio,
            data_fim=None,
            ativa=True,
        )


def encerrar_matricula(matricula, data_fim=None):
    if matricula is None:
        raise ValidationError("Não há vínculo para encerrar.")
    if not matricula.ativa:
        raise ValidationError("Este vínculo já está encerrado.")
    data_fim = data_fim or hoje()
    _validar_datas(matricula.data_inicio, data_fim)
    matricula.ativa = False
    matricula.data_fim = data_fim
    matricula.save(update_fields=["ativa", "data_fim"])
    return matricula


def transferir(aluno, turma_destino, data=None):
    data = data or hoje()
    atual = matricula_ativa_em(aluno)
    if atual is None:
        raise ValidationError("O aluno não possui vínculo ativo para transferir.")
    if atual.turma_id == turma_destino.pk:
        raise ValidationError("O aluno já está nesta turma.")
    if not turma_destino.ativa:
        raise ValidationError("Não é possível transferir para uma turma inativa.")
    with transaction.atomic():
        encerrar_matricula(atual, data_fim=data)
        return matricular(aluno, turma_destino, data_inicio=data)
