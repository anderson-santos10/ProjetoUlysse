from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from alunos.models import Aluno
from alunos.series import serie_ou_404

from .models import Questao, RespostaResultado, Resultado

DIFICULDADE_NOMES = dict(Questao.DIFICULDADE_CHOICES)
DIFICULDADES_VALIDAS = {codigo for codigo, _ in Questao.DIFICULDADE_CHOICES}

PERIODOS = (
    ("hoje", "Hoje"),
    ("7d", "Últimos 7 dias"),
    ("30d", "Últimos 30 dias"),
    ("mes", "Este mês"),
)

PERIODOS_ANALISE = PERIODOS + (
    ("todos", "Todos"),
    ("personalizado", "Período personalizado"),
)

PERIODOS_VALIDOS = {codigo for codigo, _ in PERIODOS_ANALISE}

TAXA_FAIXAS = (
    ("", "Todas"),
    ("lt40", "< 40%"),
    ("40_59", "40%–59%"),
    ("60_79", "60%–79%"),
    ("gte80", "≥ 80%"),
)

VOLUME_MINIMOS = (
    ("", "Todas"),
    ("5", "≥ 5 tentativas"),
    ("10", "≥ 10 tentativas"),
    ("30", "≥ 30 tentativas"),
)

# Indicador estatístico, não afirma erro de gabarito.
REVISAR_TAXA = Decimal("40")
REVISAR_MIN_TENTATIVAS = 5

ORDENS = {
    "-media": ("media", True),
    "media": ("media", False),
    "-taxa": ("taxa", True),
    "taxa": ("taxa", False),
    "-provas": ("provas", True),
    "provas": ("provas", False),
}


def normalizar_periodo(codigo):
    if codigo in PERIODOS_VALIDOS:
        return codigo
    return "30d"


def parse_data_iso(valor):
    if not valor:
        return None
    try:
        return datetime.strptime(str(valor).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def inicio_periodo(codigo, agora=None):
    codigo = normalizar_periodo(codigo)
    agora = agora or timezone.now()
    local = timezone.localtime(agora)
    tz = local.tzinfo

    if codigo in {"todos", "personalizado"}:
        return None
    if codigo == "hoje":
        inicio = datetime.combine(local.date(), time.min)
        return timezone.make_aware(inicio, tz)
    if codigo == "7d":
        return agora - timedelta(days=7)
    if codigo == "mes":
        inicio = datetime.combine(local.date().replace(day=1), time.min)
        return timezone.make_aware(inicio, tz)
    return agora - timedelta(days=30)


def limites_periodo(periodo="30d", agora=None, data_de=None, data_ate=None):
    agora = agora or timezone.now()
    periodo = normalizar_periodo(periodo)
    if periodo == "todos":
        return None, None
    if periodo == "personalizado":
        local = timezone.localtime(agora)
        tz = local.tzinfo
        inicio = None
        fim = None
        if data_de:
            inicio = timezone.make_aware(datetime.combine(data_de, time.min), tz)
        if data_ate:
            seguinte = data_ate + timedelta(days=1)
            fim = timezone.make_aware(datetime.combine(seguinte, time.min), tz)
        return inicio, fim
    return inicio_periodo(periodo, agora=agora), None


def aplicar_intervalo(queryset, campo, inicio, fim):
    if inicio is not None:
        queryset = queryset.filter(**{f"{campo}__gte": inicio})
    if fim is not None:
        queryset = queryset.filter(**{f"{campo}__lt": fim})
    return queryset


def q_intervalo_respostas(inicio, fim):
    condicao = Q()
    if inicio is not None:
        condicao &= Q(respostas_resultados__resultado__data__gte=inicio)
    if fim is not None:
        condicao &= Q(respostas_resultados__resultado__data__lt=fim)
    return condicao


def q_intervalo_direto(inicio, fim):
    condicao = Q()
    if inicio is not None:
        condicao &= Q(resultado__data__gte=inicio)
    if fim is not None:
        condicao &= Q(resultado__data__lt=fim)
    return condicao


def taxa_percentual(acertos, total):
    if not total:
        return None
    return (Decimal(acertos) / Decimal(total)) * Decimal("100")


def queryset_resultados(
    periodo="30d",
    serie="",
    agora=None,
    data_de=None,
    data_ate=None,
    turma_id=None,
    turma_ids=None,
):
    queryset = Resultado.objects.select_related(
        "aluno", "matricula", "matricula__turma", "avaliacao"
    )
    inicio, fim = limites_periodo(
        periodo, agora=agora, data_de=data_de, data_ate=data_ate
    )
    queryset = aplicar_intervalo(queryset, "data", inicio, fim)
    serie = (serie or "").strip()
    if serie:
        serie_ou_404(serie)
        queryset = queryset.filter(aluno__serie=serie)
    if turma_id:
        queryset = queryset.filter(matricula__turma_id=turma_id)
    elif turma_ids is not None:
        queryset = queryset.filter(matricula__turma_id__in=turma_ids)
    return queryset


def indicadores(queryset):
    dados = queryset.aggregate(
        provas=Count("id"),
        participantes=Count("aluno", distinct=True),
        media=Avg("nota"),
        acertos=Sum("acertos"),
        erros=Sum("erros"),
        questoes=Sum("total_questoes"),
        xp=Sum("xp_ganho"),
    )
    provas = dados["provas"] or 0
    acertos = dados["acertos"] or 0
    erros = dados["erros"] or 0
    questoes = dados["questoes"] or 0
    return {
        "provas": provas,
        "participantes": dados["participantes"] or 0,
        "media": dados["media"],
        "acertos": acertos,
        "erros": erros,
        "questoes": questoes,
        "xp": dados["xp"] or 0,
        "taxa": taxa_percentual(acertos, questoes),
        "tem_dados": provas > 0,
    }


def desempenho_por_serie(queryset, ordem="-media"):
    agregados = {
        item["aluno__serie"]: item
        for item in queryset.values("aluno__serie").annotate(
            provas=Count("id"),
            alunos=Count("aluno", distinct=True),
            media=Avg("nota"),
            acertos=Sum("acertos"),
            erros=Sum("erros"),
            questoes=Sum("total_questoes"),
        )
    }
    linhas = []
    for codigo, nome in Aluno.SERIES:
        item = agregados.get(codigo)
        if item:
            linhas.append({
                "codigo": codigo,
                "nome": nome,
                "alunos": item["alunos"] or 0,
                "provas": item["provas"] or 0,
                "media": item["media"],
                "acertos": item["acertos"] or 0,
                "erros": item["erros"] or 0,
                "questoes": item["questoes"] or 0,
                "taxa": taxa_percentual(
                    item["acertos"] or 0,
                    item["questoes"] or 0,
                ),
                "tem_dados": True,
            })
        else:
            linhas.append({
                "codigo": codigo,
                "nome": nome,
                "alunos": 0,
                "provas": 0,
                "media": None,
                "acertos": 0,
                "erros": 0,
                "questoes": 0,
                "taxa": None,
                "tem_dados": False,
            })

    campo, reverso = ORDENS.get(ordem, ORDENS["-media"])
    com_dados = [linha for linha in linhas if linha["tem_dados"]]
    sem_dados = [linha for linha in linhas if not linha["tem_dados"]]
    com_dados.sort(key=lambda linha: linha.get(campo) or 0, reverse=reverso)
    return com_dados + sem_dados


def indicadores_aluno(aluno):
    queryset = Resultado.objects.filter(aluno=aluno)
    return indicadores(queryset)


# Amostra mínima para classificar dificuldade observada.
# Com menos tentativas a questão aparece em "Poucos dados".
MIN_TENTATIVAS_OBSERVADA = 5


def queryset_respostas(
    periodo="30d",
    serie="",
    agora=None,
    data_de=None,
    data_ate=None,
    turma_id=None,
    turma_ids=None,
    aluno_id=None,
):
    queryset = RespostaResultado.objects.select_related(
        "questao", "questao_versao", "resultado", "resultado__matricula"
    )
    inicio, fim = limites_periodo(
        periodo, agora=agora, data_de=data_de, data_ate=data_ate
    )
    queryset = aplicar_intervalo(queryset, "resultado__data", inicio, fim)
    serie = (serie or "").strip()
    if serie:
        serie_ou_404(serie)
        queryset = queryset.filter(questao__serie=serie)
    if turma_id:
        queryset = queryset.filter(resultado__matricula__turma_id=turma_id)
    elif turma_ids is not None:
        queryset = queryset.filter(resultado__matricula__turma_id__in=turma_ids)
    if aluno_id:
        queryset = queryset.filter(resultado__aluno_id=aluno_id)
    return queryset


def _linha_questao(questao, tentativas, acertos, min_tentativas):
    tentativas = tentativas or 0
    acertos = acertos or 0
    erros = tentativas - acertos
    taxa = taxa_percentual(acertos, tentativas)
    taxa_erro = taxa_percentual(erros, tentativas)
    revisar = (
        taxa is not None
        and taxa < REVISAR_TAXA
        and tentativas >= REVISAR_MIN_TENTATIVAS
    )
    return {
        "questao": questao,
        "tentativas": tentativas,
        "acertos": acertos,
        "erros": erros,
        "taxa": taxa,
        "taxa_erro": taxa_erro,
        "tem_dados": tentativas > 0,
        "tem_amostra": tentativas >= min_tentativas,
        "taxa_baixa": taxa is not None and taxa < 50,
        "revisar": revisar,
    }


def _ordenar_por_dificuldade(linhas):
    def chave(linha):
        taxa = linha["taxa"]
        taxa_ord = float(taxa) if taxa is not None else 101
        return (taxa_ord, -linha["tentativas"], linha["questao"].serie, linha["questao"].numero)

    return sorted(linhas, key=chave)


def _passa_faixa_taxa(taxa, faixa):
    if not faixa:
        return True
    if taxa is None:
        return False
    if faixa == "lt40":
        return taxa < 40
    if faixa == "40_59":
        return Decimal("40") <= taxa < Decimal("60")
    if faixa == "60_79":
        return Decimal("60") <= taxa < Decimal("80")
    if faixa == "gte80":
        return taxa >= 80
    return True


def metricas_por_questao(
    periodo="30d",
    serie="",
    agora=None,
    min_tentativas=MIN_TENTATIVAS_OBSERVADA,
    dificuldade="",
    faixa_taxa="",
    volume_minimo="",
    data_de=None,
    data_ate=None,
    turma_id=None,
    turma_ids=None,
    aluno_id=None,
):
    inicio, fim = limites_periodo(
        periodo, agora=agora, data_de=data_de, data_ate=data_ate
    )
    filtro_periodo = q_intervalo_respostas(inicio, fim)
    if turma_id:
        filtro_periodo &= Q(
            respostas_resultados__resultado__matricula__turma_id=turma_id
        )
    elif turma_ids is not None:
        filtro_periodo &= Q(
            respostas_resultados__resultado__matricula__turma_id__in=turma_ids
        )
    if aluno_id:
        filtro_periodo &= Q(respostas_resultados__resultado__aluno_id=aluno_id)
    serie = (serie or "").strip()
    if serie:
        serie_ou_404(serie)
    dificuldade = (dificuldade or "").strip()
    if dificuldade and dificuldade not in DIFICULDADES_VALIDAS:
        dificuldade = ""

    queryset = Questao.objects.select_related("versao_atual")
    if serie:
        queryset = queryset.filter(serie=serie)
    if dificuldade:
        queryset = queryset.filter(dificuldade=dificuldade)

    queryset = queryset.annotate(
        tentativas=Count("respostas_resultados", filter=filtro_periodo),
        acertos_obs=Count(
            "respostas_resultados",
            filter=filtro_periodo & Q(respostas_resultados__correta=True),
        ),
    )

    linhas = [
        _linha_questao(questao, questao.tentativas, questao.acertos_obs, min_tentativas)
        for questao in queryset
    ]
    com_dados_brutos = any(linha["tem_dados"] for linha in linhas)
    try:
        minimo = int(volume_minimo) if str(volume_minimo).strip() else 0
    except (TypeError, ValueError):
        minimo = 0
    if minimo:
        linhas = [linha for linha in linhas if linha["tentativas"] >= minimo]
    if faixa_taxa:
        linhas = [
            linha for linha in linhas if _passa_faixa_taxa(linha["taxa"], faixa_taxa)
        ]
    com_dados = _ordenar_por_dificuldade([linha for linha in linhas if linha["tem_dados"]])
    sem_dados = [linha for linha in linhas if not linha["tem_dados"]]
    com_amostra = [linha for linha in com_dados if linha["tem_amostra"]]
    poucos_dados = [linha for linha in com_dados if not linha["tem_amostra"]]
    revisar = [linha for linha in com_dados if linha["revisar"]]

    filtros_restritivos = bool(minimo or faixa_taxa)
    if serie and not filtros_restritivos:
        visiveis = com_dados + sem_dados
    else:
        visiveis = com_dados

    return {
        "linhas": visiveis,
        "com_amostra": com_amostra,
        "poucos_dados": poucos_dados,
        "sem_tentativas": sem_dados if serie and not filtros_restritivos else [],
        "tem_dados_persistidos": com_dados_brutos,
        "tem_resultados_filtrados": bool(com_dados),
        "min_tentativas": min_tentativas,
        "revisar": revisar,
        "mais_faceis": list(reversed(com_amostra[-8:])) if com_amostra else [],
        "mais_tentadas": sorted(
            com_dados, key=lambda linha: (-linha["tentativas"], linha["questao"].numero)
        )[:8],
    }


def metricas_questao(
    questao,
    periodo="30d",
    agora=None,
    min_tentativas=MIN_TENTATIVAS_OBSERVADA,
    data_de=None,
    data_ate=None,
    turma_id=None,
    turma_ids=None,
):
    inicio, fim = limites_periodo(
        periodo, agora=agora, data_de=data_de, data_ate=data_ate
    )
    queryset = RespostaResultado.objects.filter(questao=questao)
    queryset = aplicar_intervalo(queryset, "resultado__data", inicio, fim)
    if turma_id:
        queryset = queryset.filter(resultado__matricula__turma_id=turma_id)
    elif turma_ids is not None:
        queryset = queryset.filter(resultado__matricula__turma_id__in=turma_ids)
    dados = queryset.aggregate(
        tentativas=Count("id"),
        acertos=Count("id", filter=Q(correta=True)),
        a=Count("id", filter=Q(resposta="A")),
        b=Count("id", filter=Q(resposta="B")),
        c=Count("id", filter=Q(resposta="C")),
        d=Count("id", filter=Q(resposta="D")),
        em_branco=Count("id", filter=Q(resposta__isnull=True)),
        gabarito_a=Count("id", filter=Q(resposta_correta="A")),
        gabarito_b=Count("id", filter=Q(resposta_correta="B")),
        gabarito_c=Count("id", filter=Q(resposta_correta="C")),
        gabarito_d=Count("id", filter=Q(resposta_correta="D")),
        sem_versao=Count("id", filter=Q(questao_versao__isnull=True)),
    )
    linha = _linha_questao(
        questao,
        dados["tentativas"],
        dados["acertos"],
        min_tentativas,
    )
    total = dados["tentativas"] or 0
    validas = total - (dados["em_branco"] or 0)
    gabaritos = [
        letra
        for letra, campo in (("A", "gabarito_a"), ("B", "gabarito_b"), ("C", "gabarito_c"), ("D", "gabarito_d"))
        if (dados[campo] or 0) > 0
    ]
    gabarito_historico = gabaritos[0] if len(gabaritos) == 1 else None
    gabarito_misto = len(gabaritos) > 1
    distribuicao = []
    for letra, campo in (("A", "a"), ("B", "b"), ("C", "c"), ("D", "d")):
        quantidade = dados[campo] or 0
        distribuicao.append({
            "letra": letra,
            "quantidade": quantidade,
            "pct": float(taxa_percentual(quantidade, validas) or 0) if validas else 0,
            "gabarito": bool(gabarito_historico and letra == gabarito_historico),
        })
    erradas = [
        item for item in distribuicao
        if not item["gabarito"] and item["quantidade"] > 0
    ]
    distrator = None
    if erradas and not gabarito_misto:
        distrator = max(erradas, key=lambda item: item["quantidade"])
        for item in distribuicao:
            item["distrator"] = distrator["letra"] == item["letra"]
    else:
        for item in distribuicao:
            item["distrator"] = False
    em_branco = dados["em_branco"] or 0
    linha.update({
        "distribuicao": distribuicao,
        "em_branco": em_branco,
        "em_branco_pct": float(taxa_percentual(em_branco, total) or 0) if total else 0,
        "respostas_validas": validas,
        "gabarito_historico": gabarito_historico,
        "gabarito_misto": gabarito_misto,
        "gabarito_atual": questao.resposta_correta,
        "distrator": distrator,
        "sem_versao": dados["sem_versao"] or 0,
    })
    return linha


def metricas_versoes_questao(
    questao,
    periodo="30d",
    agora=None,
    data_de=None,
    data_ate=None,
    turma_id=None,
    turma_ids=None,
):
    inicio, fim = limites_periodo(
        periodo, agora=agora, data_de=data_de, data_ate=data_ate
    )
    linhas = []
    queryset = RespostaResultado.objects.filter(questao=questao)
    if turma_id:
        queryset = queryset.filter(resultado__matricula__turma_id=turma_id)
    elif turma_ids is not None:
        queryset = queryset.filter(resultado__matricula__turma_id__in=turma_ids)
    queryset = aplicar_intervalo(queryset, "resultado__data", inicio, fim)
    agregados = (
        queryset
        .values(
            "questao_versao_id",
            "questao_versao__versao",
            "questao_versao__dificuldade",
            "questao_versao__resposta_correta",
            "questao_versao__criado_em",
            "questao_versao__imagem",
        )
        .annotate(
            tentativas=Count("id"),
            acertos=Count("id", filter=Q(correta=True)),
        )
        .order_by("questao_versao__versao")
    )
    for item in agregados:
        tentativas = item["tentativas"] or 0
        acertos = item["acertos"] or 0
        codigo_dif = item["questao_versao__dificuldade"]
        linhas.append({
            "versao": item["questao_versao__versao"],
            "versao_id": item["questao_versao_id"],
            "criado_em": item["questao_versao__criado_em"],
            "dificuldade": codigo_dif,
            "dificuldade_nome": DIFICULDADE_NOMES.get(codigo_dif, "—"),
            "gabarito": item["questao_versao__resposta_correta"],
            "tentativas": tentativas,
            "acertos": acertos,
            "erros": tentativas - acertos,
            "taxa": taxa_percentual(acertos, tentativas),
            "anterior_ao_versionamento": item["questao_versao_id"] is None,
            "tem_imagem": bool(item["questao_versao__imagem"]),
        })
    return linhas


def desempenho_por_dificuldade(
    periodo="30d",
    serie="",
    agora=None,
    data_de=None,
    data_ate=None,
    turma_id=None,
    turma_ids=None,
):
    queryset = queryset_respostas(
        periodo=periodo,
        serie=serie,
        agora=agora,
        data_de=data_de,
        data_ate=data_ate,
        turma_id=turma_id,
        turma_ids=turma_ids,
    ).annotate(
        dificuldade_hist=Coalesce(
            "questao_versao__dificuldade",
            "questao__dificuldade",
        )
    )
    agregados = {
        item["dificuldade_hist"]: item
        for item in queryset.values("dificuldade_hist").annotate(
            tentativas=Count("id"),
            acertos=Count("id", filter=Q(correta=True)),
        )
    }
    linhas = []
    for codigo, nome in Questao.DIFICULDADE_CHOICES:
        item = agregados.get(codigo)
        tentativas = (item["tentativas"] if item else 0) or 0
        acertos = (item["acertos"] if item else 0) or 0
        linhas.append({
            "codigo": codigo,
            "nome": nome,
            "tentativas": tentativas,
            "acertos": acertos,
            "erros": tentativas - acertos,
            "taxa": taxa_percentual(acertos, tentativas),
        })
    return linhas


def escopo_turma_ids(user):
    """None = sem recorte (coordenação). Lista (mesmo vazia) = professor."""
    from alunos.escopo import gerencia_todas_turmas, ids_turmas_visiveis

    if gerencia_todas_turmas(user):
        return None
    return ids_turmas_visiveis(user)


def evolucao_media_por_dia(queryset, limite=30):
    from django.db.models.functions import TruncDate

    return list(
        queryset.annotate(dia=TruncDate("data"))
        .values("dia")
        .annotate(provas=Count("id"), media=Avg("nota"))
        .order_by("dia")[:limite]
    )


def indicadores_por_turma(queryset, turmas):
    agregados = {
        item["matricula__turma_id"]: item
        for item in queryset.filter(matricula__isnull=False).values(
            "matricula__turma_id"
        ).annotate(
            provas=Count("id"),
            participantes=Count("aluno", distinct=True),
            media=Avg("nota"),
            acertos=Sum("acertos"),
            erros=Sum("erros"),
            questoes=Sum("total_questoes"),
        )
    }
    linhas = []
    for turma in turmas:
        item = agregados.get(turma.pk) or {}
        acertos = item.get("acertos") or 0
        questoes = item.get("questoes") or 0
        provas = item.get("provas") or 0
        linhas.append({
            "turma": turma,
            "provas": provas,
            "participantes": item.get("participantes") or 0,
            "media": item.get("media"),
            "acertos": acertos,
            "erros": item.get("erros") or 0,
            "questoes": questoes,
            "taxa": taxa_percentual(acertos, questoes),
            "tem_dados": provas > 0,
        })
    return linhas
