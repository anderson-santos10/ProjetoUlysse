from django.db.models import Avg, Sum
from django.views.generic import TemplateView

from accounts.catalog import PERM_AREA_PROFESSOR
from accounts.mixins import PermissionRequiredMixin
from accounts.views import LoginView
from alunos.escopo import queryset_alunos_visiveis, queryset_resultados_visiveis, queryset_turmas_visiveis
from questoes.models import Questao


class HomeView(TemplateView):
    template_name = "home.html"


class TurmaView(TemplateView):
    template_name = "turma.html"


class AreaProfessorView(PermissionRequiredMixin, TemplateView):
    permission_required = PERM_AREA_PROFESSOR
    template_name = "area_professor.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        visiveis_alunos = queryset_alunos_visiveis(self.request.user)
        visiveis_resultados = queryset_resultados_visiveis(self.request.user)
        context["total_alunos"] = visiveis_alunos.count()
        context["total_questoes"] = Questao.objects.count()
        context["total_resultados"] = visiveis_resultados.count()
        context["total_turmas"] = queryset_turmas_visiveis(self.request.user).count()
        agreg = visiveis_resultados.aggregate(
            media=Avg("nota"),
            acertos=Sum("acertos"),
            questoes=Sum("total_questoes"),
        )
        context["media_geral"] = agreg["media"]
        total_q = agreg["questoes"] or 0
        context["acuracia"] = (
            (agreg["acertos"] or 0) / total_q * 100 if total_q else None
        )
        context["resultados_recentes"] = (
            visiveis_resultados
            .select_related("aluno", "matricula", "matricula__turma")
            .order_by("-data")[:5]
        )
        return context


# Alias de compatibilidade: /professor/ usa o login único.
AcessoProfessorView = LoginView
