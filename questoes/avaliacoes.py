"""Regras de avaliação dirigida. Versões congelam na publicação."""

from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from alunos.escopo import usuario_pode_acessar_turma
from alunos.matriculas import matricula_ativa_em

from .models import Avaliacao, AvaliacaoQuestao, Resultado


def agora():
    return timezone.now()


def avaliacoes_visiveis(user):
    from alunos.escopo import gerencia_todas_turmas, queryset_turmas_visiveis

    qs = Avaliacao.objects.select_related("turma", "criado_por")
    if gerencia_todas_turmas(user):
        return qs
    return qs.filter(turma__in=queryset_turmas_visiveis(user))


def usuario_pode_acessar_avaliacao(user, avaliacao):
    return usuario_pode_acessar_turma(user, getattr(avaliacao, "turma", None))


def validar_datas_avaliacao(data_inicio, data_fim):
    if data_inicio and data_fim and data_fim < data_inicio:
        raise ValidationError("A data de término não pode ser anterior ao início.")


def publicar(avaliacao):
    if avaliacao.status != Avaliacao.Status.RASCUNHO:
        raise ValidationError("Somente rascunhos podem ser publicados.")
    itens = list(avaliacao.itens.select_related("questao", "questao__versao_atual"))
    if not itens:
        raise ValidationError("Inclua ao menos uma questão antes de publicar.")
    validar_datas_avaliacao(avaliacao.data_inicio, avaliacao.data_fim)
    with transaction.atomic():
        for item in itens:
            versao = item.questao.versao_atual
            if versao is None:
                raise ValidationError(
                    f"A questão {item.questao.numero} não possui versão para congelar."
                )
            if item.questao.serie != avaliacao.serie:
                raise ValidationError("Há questão de série diferente da avaliação.")
            item.questao_versao = versao
            item.save(update_fields=["questao_versao"])
        avaliacao.status = Avaliacao.Status.PUBLICADA
        avaliacao.publicado_em = agora()
        avaliacao.save(update_fields=["status", "publicado_em", "atualizado_em"])
    return avaliacao


def encerrar(avaliacao):
    if avaliacao.status != Avaliacao.Status.PUBLICADA:
        raise ValidationError("Somente avaliações publicadas podem ser encerradas.")
    avaliacao.status = Avaliacao.Status.ENCERRADA
    avaliacao.save(update_fields=["status", "atualizado_em"])
    return avaliacao


def avaliacao_disponivel_para_aluno(avaliacao, aluno, momento=None):
    momento = momento or agora()
    if avaliacao.status != Avaliacao.Status.PUBLICADA:
        return False, "Esta avaliação não está disponível."
    matricula = matricula_ativa_em(aluno)
    if matricula is None or matricula.turma_id != avaliacao.turma_id:
        return False, "Esta avaliação não pertence à sua turma."
    if avaliacao.data_inicio and momento < avaliacao.data_inicio:
        return False, "Esta avaliação ainda não começou."
    if avaliacao.data_fim and momento > avaliacao.data_fim:
        return False, "O prazo desta avaliação encerrou."
    feitas = Resultado.objects.filter(aluno=aluno, avaliacao=avaliacao).count()
    if feitas >= avaliacao.tentativas_maximas:
        return False, "Você já utilizou o número máximo de tentativas."
    return True, ""


def tentativas_do_aluno(aluno, avaliacao):
    return Resultado.objects.filter(aluno=aluno, avaliacao=avaliacao).count()


def tempo_esgotado(inicio_iso, minutos, momento=None):
    if not minutos or not inicio_iso:
        return False
    momento = momento or agora()
    inicio = datetime.fromisoformat(inicio_iso)
    if timezone.is_naive(inicio):
        inicio = timezone.make_aware(inicio, timezone.get_current_timezone())
    limite = inicio + timedelta(minutes=minutos)
    return momento > limite
