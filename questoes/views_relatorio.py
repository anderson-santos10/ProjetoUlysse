from django.core.exceptions import PermissionDenied
from django.views.generic import DetailView, TemplateView

from accounts.mixins import PermissionRequiredMixin
from alunos.escopo import (
    queryset_alunos_visiveis,
    queryset_turmas_visiveis,
    usuario_pode_acessar_aluno,
    usuario_pode_acessar_turma,
)
from alunos.models import Aluno, Turma
from alunos.series import SERIES_MAP

from .desempenho import _recorte_temporal, _turma_filtro
from .metrics import (
    REVISAR_MIN_TENTATIVAS,
    REVISAR_TAXA,
    evolucao_media_por_dia,
    indicadores,
    metricas_por_questao,
    metricas_questao,
    queryset_resultados,
    escopo_turma_ids,
)
from .models import Resultado


class RelatorioMixin:
    permission_required = "questoes.view_relatorio_pedagogico"
    extra_context = {"modo_impressao": True}


class RelatorioAlunoView(RelatorioMixin, PermissionRequiredMixin, DetailView):
    model = Aluno
    template_name = "relatorio_aluno.html"
    context_object_name = "aluno"

    def get_queryset(self):
        return queryset_alunos_visiveis(self.request.user)

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not usuario_pode_acessar_aluno(self.request.user, obj):
            raise PermissionDenied
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        periodo, data_de, data_ate = _recorte_temporal(self.request)
        turma_ids = escopo_turma_ids(self.request.user)
        historico = (
            Resultado.objects.filter(aluno=self.object)
            .select_related("avaliacao", "matricula__turma")
            .order_by("data")
        )
        if turma_ids is not None:
            historico = historico.filter(matricula__turma_id__in=turma_ids)
        historico = list(historico)
        indicadores_dados = indicadores(
            Resultado.objects.filter(pk__in=[item.pk for item in historico])
        )
        analise = metricas_por_questao(
            periodo="todos",
            turma_ids=turma_ids,
            aluno_id=self.object.pk,
        )
        dificeis = [
            linha for linha in analise["com_amostra"]
            if linha["taxa"] is not None and linha["taxa"] < REVISAR_TAXA
        ][:8]
        fortes = [
            linha for linha in analise["com_amostra"]
            if linha["taxa"] is not None and linha["taxa"] >= 80
        ][:8]
        evidencia = any(linha["revisar"] for linha in analise["revisar"])
        context.update({
            "periodo": periodo,
            "indicadores": indicadores_dados,
            "historico": historico,
            "evolucao": evolucao_media_por_dia(
                Resultado.objects.filter(pk__in=[item.pk for item in historico])
            ),
            "questoes_dificeis": dificeis,
            "pontos_fortes": fortes,
            "evidencia_abaixo": evidencia,
            "matricula_ativa": self.object.matricula_ativa(),
            "amostra_minima": REVISAR_MIN_TENTATIVAS,
        })
        return context


class RelatorioTurmaView(RelatorioMixin, PermissionRequiredMixin, DetailView):
    model = Turma
    template_name = "relatorio_turma.html"
    context_object_name = "turma"

    def get_queryset(self):
        return queryset_turmas_visiveis(self.request.user)

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not usuario_pode_acessar_turma(self.request.user, obj):
            raise PermissionDenied
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        periodo, data_de, data_ate = _recorte_temporal(self.request)
        resultados = queryset_resultados(
            periodo=periodo,
            data_de=data_de,
            data_ate=data_ate,
            turma_id=self.object.pk,
        )
        alunos = queryset_alunos_visiveis(self.request.user).filter(
            matriculas__turma=self.object, matriculas__ativa=True
        ).distinct()
        analise = metricas_por_questao(periodo=periodo, turma_id=self.object.pk)
        context.update({
            "periodo": periodo,
            "indicadores": indicadores(resultados),
            "alunos_ativos": alunos.count(),
            "evolucao": evolucao_media_por_dia(resultados),
            "questoes_dificeis": analise["com_amostra"][:8],
            "revisar": analise["revisar"][:8],
        })
        return context


class RelatorioQuestoesView(RelatorioMixin, PermissionRequiredMixin, TemplateView):
    template_name = "relatorio_questoes.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        periodo, data_de, data_ate = _recorte_temporal(self.request)
        turma = _turma_filtro(self.request)
        serie = self.request.GET.get("serie", "").strip()
        turma_ids = escopo_turma_ids(self.request.user)
        analise = metricas_por_questao(
            periodo=periodo,
            serie=serie,
            data_de=data_de,
            data_ate=data_ate,
            turma_id=turma.pk if turma else None,
            turma_ids=None if turma else turma_ids,
        )
        linhas = []
        detalhadas = 0
        for linha in analise["linhas"][:80]:
            detalhe = None
            if linha["tem_dados"] and detalhadas < 15:
                detalhe = metricas_questao(
                    linha["questao"],
                    periodo=periodo,
                    data_de=data_de,
                    data_ate=data_ate,
                    turma_id=turma.pk if turma else None,
                    turma_ids=None if turma else turma_ids,
                )
                detalhadas += 1
            linhas.append({**linha, "detalhe": detalhe})
        context.update({
            "periodo": periodo,
            "serie_filtro": serie,
            "turma_filtro": turma,
            "nome_serie": SERIES_MAP.get(serie, serie) if serie else "",
            "analise": analise,
            "linhas": linhas,
        })
        return context
