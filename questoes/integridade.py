from django.core.exceptions import ValidationError
from django.db.models import Count, F

from .models import Questao, QuestaoVersao, RespostaResultado
from .versionamento import CAMPOS_CONTEUDO


def validar_par_questao_versao(questao, versao, obrigatorio=True):
    if versao is None:
        if obrigatorio:
            raise ValidationError(
                "Resposta nova precisa da versão histórica da questão."
            )
        return
    if versao.questao_id != questao.id:
        raise ValidationError(
            "A versão histórica não pertence à questão da resposta."
        )


def auditar_integridade():
    questoes = list(Questao.objects.select_related("versao_atual"))
    total_questoes = len(questoes)
    total_versoes = QuestaoVersao.objects.count()

    sem_versao_atual = 0
    versao_atual_incompativel = 0
    conteudo_divergente = 0
    for questao in questoes:
        atual = questao.versao_atual
        if atual is None:
            sem_versao_atual += 1
            continue
        if atual.questao_id != questao.id:
            versao_atual_incompativel += 1
            continue
        if any(
            getattr(questao, campo) != getattr(atual, campo)
            for campo in CAMPOS_CONTEUDO
        ) or atual.numero != questao.numero:
            conteudo_divergente += 1

    orfas = QuestaoVersao.objects.filter(questao__isnull=True).count()
    duplicadas = (
        QuestaoVersao.objects
        .values("questao_id", "versao")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
        .count()
    )
    respostas = RespostaResultado.objects.all()
    sem_versao = respostas.filter(questao_versao__isnull=True).count()
    inconsistentes = (
        respostas
        .exclude(questao_versao__isnull=True)
        .exclude(questao_versao__questao_id=F("questao_id"))
        .count()
    )

    ok = (
        sem_versao_atual == 0
        and versao_atual_incompativel == 0
        and orfas == 0
        and duplicadas == 0
        and inconsistentes == 0
    )
    return {
        "questoes": total_questoes,
        "versoes": total_versoes,
        "sem_versao_atual": sem_versao_atual,
        "orfas": orfas,
        "duplicadas": duplicadas,
        "versao_atual_incompativel": versao_atual_incompativel,
        "conteudo_divergente": conteudo_divergente,
        "respostas_sem_versao": sem_versao,
        "respostas_inconsistentes": inconsistentes,
        "ok": ok,
    }


def formatar_relatorio(dados):
    status = "OK" if dados["ok"] else "FALHAS ENCONTRADAS"
    return (
        "AUDITORIA DE QUESTÕES\n"
        "\n"
        f"Questões: {dados['questoes']}\n"
        f"Versões: {dados['versoes']}\n"
        f"Questões sem versão atual: {dados['sem_versao_atual']}\n"
        f"Versões órfãs: {dados['orfas']}\n"
        f"Versões duplicadas: {dados['duplicadas']}\n"
        f"Questões com versão atual incompatível: {dados['versao_atual_incompativel']}\n"
        f"Questões com conteúdo divergente da versão atual: {dados['conteudo_divergente']}\n"
        f"Respostas sem versão: {dados['respostas_sem_versao']}\n"
        f"Respostas inconsistentes: {dados['respostas_inconsistentes']}\n"
        "\n"
        f"STATUS: {status}\n"
    )
