from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch
from django.http import Http404
from django.views.generic import DetailView, TemplateView

from accounts.mixins import PermissionRequiredMixin
from accounts.querystring import without_page
from alunos.escopo import (
    queryset_alunos_visiveis,
    queryset_resultados_visiveis,
    queryset_turmas_visiveis,
    usuario_pode_acessar_aluno,
    usuario_pode_acessar_turma,
)
from alunos.models import Aluno, Turma
from alunos.security import formatar_tempo
from alunos.series import SERIES_MAP

from .metrics import (
    DIFICULDADES_VALIDAS,
    PERIODOS,
    PERIODOS_ANALISE,
    TAXA_FAIXAS,
    VOLUME_MINIMOS,
    desempenho_por_dificuldade,
    desempenho_por_serie,
    escopo_turma_ids,
    evolucao_media_por_dia,
    indicadores,
    indicadores_por_turma,
    metricas_por_questao,
    metricas_questao,
    metricas_versoes_questao,
    normalizar_periodo,
    parse_data_iso,
    queryset_resultados,
)
from .models import Questao, RespostaResultado, Resultado


def _recorte_temporal(request):
    periodo = normalizar_periodo(request.GET.get("periodo", "30d"))
    data_de = parse_data_iso(request.GET.get("de"))
    data_ate = parse_data_iso(request.GET.get("ate"))
    if periodo == "personalizado" and data_de is None and data_ate is None:
        periodo = "30d"
    return periodo, data_de, data_ate


def _dificuldade_filtro(request):
    dificuldade = request.GET.get("dificuldade", "").strip()
    if dificuldade and dificuldade not in DIFICULDADES_VALIDAS:
        raise Http404("Dificuldade inválida.")
    return dificuldade



def _turma_filtro(request):
    bruto = (request.GET.get("turma") or "").strip()
    if not bruto:
        return None
    try:
        pk = int(bruto)
    except (TypeError, ValueError):
        raise Http404("Turma inválida.")
    turma = (
        Turma.objects
        .select_related("professor_responsavel")
        .filter(pk=pk)
        .first()
    )
    if turma is None:
        raise Http404("Turma não encontrada.")
    if not usuario_pode_acessar_turma(request.user, turma):
        raise PermissionDenied
    return turma


def _turmas_filtro_context(request):
    return queryset_turmas_visiveis(request.user).order_by(
        "-ano_letivo", "serie", "nome"
    )



class DesempenhoView(PermissionRequiredMixin, TemplateView):

    permission_required = "questoes.view_resultado"
    template_name = "desempenho.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        periodo = normalizar_periodo(self.request.GET.get("periodo", "30d"))
        serie = self.request.GET.get("serie", "").strip()
        ordem = self.request.GET.get("ordem", "-media")
        turma = _turma_filtro(self.request)
        turma_ids = None if turma else escopo_turma_ids(self.request.user)
        queryset = queryset_resultados(
            periodo=periodo,
            serie=serie,
            turma_id=turma.pk if turma else None,
            turma_ids=turma_ids,
        )
        turmas = list(_turmas_filtro_context(self.request))
        analise = metricas_por_questao(
            periodo=periodo,
            serie=serie,
            turma_id=turma.pk if turma else None,
            turma_ids=turma_ids,
        )

        context.update({
            "periodo": periodo,
            "serie_filtro": serie,
            "turma_filtro": turma,
            "turmas": turmas,
            "ordem": ordem,
            "periodos": PERIODOS,
            "series": Aluno.SERIES,
            "indicadores": indicadores(queryset),
            "series_desempenho": desempenho_por_serie(queryset, ordem=ordem),
            "turmas_desempenho": indicadores_por_turma(queryset, turmas),
            "evolucao": evolucao_media_por_dia(queryset),
            "revisar": analise["revisar"][:8],
            "mais_erros": analise["com_amostra"][:8],
            "querystring": without_page(self.request),
        })
        if serie:
            context["nome_serie"] = SERIES_MAP.get(serie, serie)
        return context


class DesempenhoAlunoView(PermissionRequiredMixin, DetailView):

    permission_required = "questoes.view_resultado"
    model = Aluno
    template_name = "desempenho_aluno.html"
    context_object_name = "aluno"
    paginate_by = 20

    def get_queryset(self):
        return queryset_alunos_visiveis(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        historico = (
            queryset_resultados_visiveis(self.request.user)
            .filter(aluno=self.object)
            .order_by("-data")
            .prefetch_related(
                Prefetch(
                    "respostas_questoes",
                    queryset=(
                        RespostaResultado.objects
                        .select_related("questao", "questao_versao")
                        .order_by("questao__numero")
                    ),
                )
            )
        )
        paginator = Paginator(historico, self.paginate_by)
        page = paginator.get_page(self.request.GET.get("page"))
        for item in page.object_list:
            item.tempo_formatado = formatar_tempo(item.tempo_segundos)

        evolucao = list(reversed(list(historico[:10])))
        for item in evolucao:
            nota = float(item.nota or 0)
            item.barra_pct = min(100, max(0, (nota / 10) * 100))

        context.update({
            "indicadores": indicadores(historico),
            "page_obj": page,
            "historico": page.object_list,
            "evolucao": evolucao,
            "querystring": without_page(self.request),
        })
        return context


class DesempenhoQuestoesView(PermissionRequiredMixin, TemplateView):

    permission_required = "questoes.view_resultado"
    template_name = "desempenho_questoes.html"
    paginate_by = 50

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        periodo, data_de, data_ate = _recorte_temporal(self.request)
        serie = self.request.GET.get("serie", "").strip()
        dificuldade = _dificuldade_filtro(self.request)
        faixa_taxa = self.request.GET.get("taxa", "").strip()
        volume = self.request.GET.get("volume", "").strip()
        turma = _turma_filtro(self.request)
        turma_ids = None if turma else escopo_turma_ids(self.request.user)
        analise = metricas_por_questao(
            periodo=periodo,
            serie=serie,
            dificuldade=dificuldade,
            faixa_taxa=faixa_taxa,
            volume_minimo=volume,
            data_de=data_de,
            data_ate=data_ate,
            turma_id=turma.pk if turma else None,
            turma_ids=turma_ids,
        )
        paginator = Paginator(analise["linhas"], self.paginate_by)
        page = paginator.get_page(self.request.GET.get("page"))

        context.update({
            "periodo": periodo,
            "serie_filtro": serie,
            "turma_filtro": turma,
            "turmas": _turmas_filtro_context(self.request),
            "dificuldade_filtro": dificuldade,
            "faixa_taxa": faixa_taxa,
            "volume_filtro": volume,
            "data_de": data_de.isoformat() if data_de else "",
            "data_ate": data_ate.isoformat() if data_ate else "",
            "periodos": PERIODOS_ANALISE,
            "series": Aluno.SERIES,
            "dificuldades": Questao.DIFICULDADE_CHOICES,
            "faixas_taxa": TAXA_FAIXAS,
            "volumes": VOLUME_MINIMOS,
            "analise": analise,
            "page_obj": page,
            "por_dificuldade": desempenho_por_dificuldade(
                periodo=periodo,
                serie=serie,
                data_de=data_de,
                data_ate=data_ate,
                turma_id=turma.pk if turma else None,
                turma_ids=None if turma else escopo_turma_ids(self.request.user),
            ),
            "querystring": without_page(self.request),
        })
        if serie:
            context["nome_serie"] = SERIES_MAP.get(serie, serie)
        return context


class DesempenhoQuestaoView(PermissionRequiredMixin, DetailView):

    permission_required = "questoes.view_resultado"
    model = Questao
    template_name = "desempenho_questao.html"
    context_object_name = "questao"

    def get_queryset(self):
        return (
            Questao.objects
            .select_related("versao_atual")
            .annotate(total_versoes=Count("versoes"))
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        periodo, data_de, data_ate = _recorte_temporal(self.request)
        turma = _turma_filtro(self.request)
        turma_ids = None if turma else escopo_turma_ids(self.request.user)
        context.update({
            "periodo": periodo,
            "data_de": data_de.isoformat() if data_de else "",
            "data_ate": data_ate.isoformat() if data_ate else "",
            "periodos": PERIODOS_ANALISE,
            "turma_filtro": turma,
            "turmas": _turmas_filtro_context(self.request),
            "serie_filtro": self.request.GET.get("serie", "").strip(),
            "metrica": metricas_questao(
                self.object,
                periodo=periodo,
                data_de=data_de,
                data_ate=data_ate,
                turma_id=turma.pk if turma else None,
                turma_ids=turma_ids,
            ),
            "versoes_metricas": metricas_versoes_questao(
                self.object,
                periodo=periodo,
                data_de=data_de,
                data_ate=data_ate,
                turma_id=turma.pk if turma else None,
                turma_ids=turma_ids,
            ),
            "querystring": without_page(self.request),
            "titulo_pagina": f"Questão #{self.object.numero}",
        })
        return context
