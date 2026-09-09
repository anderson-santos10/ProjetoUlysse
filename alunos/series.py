from django.db.models import Avg, Count
from django.http import Http404

from questoes.models import Questao, Resultado

from .models import Aluno

SERIES_MAP = dict(Aluno.SERIES)


def serie_valida(codigo):
    return codigo in SERIES_MAP


def serie_ou_404(codigo):
    if not serie_valida(codigo):
        raise Http404("Série não encontrada.")
    return codigo, SERIES_MAP[codigo]


def resumo_series(alunos_qs=None, resultados_qs=None):
    alunos_qs = alunos_qs if alunos_qs is not None else Aluno.objects.all()
    resultados_qs = resultados_qs if resultados_qs is not None else Resultado.objects.all()
    alunos = {
        item["serie"]: item["total"]
        for item in alunos_qs.values("serie").annotate(total=Count("id"))
    }
    questoes = {
        item["serie"]: item["total"]
        for item in Questao.objects.values("serie").annotate(total=Count("id"))
    }
    resultados = {
        item["aluno__serie"]: item
        for item in (
            resultados_qs
            .values("aluno__serie")
            .annotate(total=Count("id"), media=Avg("nota"))
        )
    }

    resumo = []
    for codigo, nome in Aluno.SERIES:
        dados_resultado = resultados.get(codigo) or {}
        resumo.append({
            "codigo": codigo,
            "nome": nome,
            "total_alunos": alunos.get(codigo, 0),
            "total_questoes": questoes.get(codigo, 0),
            "total_resultados": dados_resultado.get("total", 0),
            "media": dados_resultado.get("media"),
        })
    return resumo


def desempenho_serie(codigo, alunos_qs=None, resultados_qs=None):
    alunos_qs = alunos_qs if alunos_qs is not None else Aluno.objects.all()
    resultados_qs = resultados_qs if resultados_qs is not None else Resultado.objects.all()
    resultados = resultados_qs.filter(aluno__serie=codigo).aggregate(
        total=Count("id"),
        media=Avg("nota"),
    )
    return {
        "total_alunos": alunos_qs.filter(serie=codigo).count(),
        "total_questoes": Questao.objects.filter(serie=codigo).count(),
        "total_resultados": resultados["total"] or 0,
        "media": resultados["media"],
    }
