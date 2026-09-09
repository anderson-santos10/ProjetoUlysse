from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from accounts.mixins import PermissionRequiredMixin
from alunos.security import formatar_tempo, mascarar_ra
from questoes.metrics import indicadores, metricas_por_questao, queryset_resultados

from .escopo import queryset_turmas_visiveis, usuario_pode_acessar_turma
from .forms_turma import MatricularAlunoForm, TransferirAlunoForm, TurmaForm
from .matriculas import encerrar_matricula, matricular, transferir
from .models import Aluno, Matricula, Turma
from .views import queryset_ranking


class TurmasQuerysetMixin:
    def get_queryset(self):
        return queryset_turmas_visiveis(self.request.user)

    def get_object(self, queryset=None):
        turma = get_object_or_404(
            Turma.objects.select_related("professor_responsavel"),
            pk=self.kwargs["pk"],
        )
        if not usuario_pode_acessar_turma(self.request.user, turma):
            raise PermissionDenied
        return turma


class ListaTurmasView(PermissionRequiredMixin, TurmasQuerysetMixin, ListView):
    permission_required = "alunos.view_turma"
    model = Turma
    template_name = "turma_list.html"
    context_object_name = "turmas"
    paginate_by = 20

    def get_queryset(self):
        return (
            super().get_queryset()
            .annotate(
                total_alunos=Count(
                    "matriculas",
                    filter=Q(matriculas__ativa=True),
                    distinct=True,
                )
            )
            .order_by("-ano_letivo", "serie", "nome")
        )


class CadastrarTurmaView(PermissionRequiredMixin, CreateView):
    permission_required = "alunos.add_turma"
    model = Turma
    form_class = TurmaForm
    template_name = "turma_form.html"
    success_url = reverse_lazy("alunos:lista_turmas")

    def get_initial(self):
        inicial = super().get_initial()
        inicial.setdefault("ano_letivo", timezone.localdate().year)
        inicial.setdefault("ativa", True)
        return inicial

    def form_valid(self, form):
        messages.success(self.request, "Turma cadastrada com sucesso.")
        return super().form_valid(form)


class EditarTurmaView(PermissionRequiredMixin, TurmasQuerysetMixin, UpdateView):
    permission_required = "alunos.change_turma"
    model = Turma
    form_class = TurmaForm
    template_name = "turma_form.html"
    success_url = reverse_lazy("alunos:lista_turmas")

    def form_valid(self, form):
        messages.success(self.request, "Turma atualizada com sucesso.")
        return super().form_valid(form)


class AlternarTurmaView(PermissionRequiredMixin, View):
    permission_required = "alunos.change_turma"

    def post(self, request, pk):
        turma = get_object_or_404(Turma, pk=pk)
        if not usuario_pode_acessar_turma(request.user, turma):
            raise PermissionDenied
        turma.ativa = not turma.ativa
        turma.save(update_fields=["ativa", "atualizado_em"])
        if turma.ativa:
            messages.success(request, "Turma reativada.")
        else:
            messages.success(request, "Turma desativada. O histórico de vínculos foi preservado.")
        return redirect("alunos:detalhe_turma", pk=turma.pk)

    def get(self, request, pk):
        return redirect("alunos:detalhe_turma", pk=pk)


class DetalheTurmaView(PermissionRequiredMixin, TurmasQuerysetMixin, DetailView):
    permission_required = "alunos.view_turma"
    model = Turma
    template_name = "turma_detail.html"
    context_object_name = "turma"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        turma = self.object
        alunos = list(
            Aluno.objects
            .filter(matriculas__turma=turma, matriculas__ativa=True)
            .annotate(
                total_resultados=Count("resultados", distinct=True),
                media_nota=Avg("resultados__nota"),
            )
            .order_by("nome")
        )
        vinculos = {
            item.aluno_id: item
            for item in (
                Matricula.objects
                .filter(turma=turma, ativa=True, aluno_id__in=[a.pk for a in alunos])
                .select_related("aluno")
            )
        }
        for aluno in alunos:
            aluno.vinculo = vinculos.get(aluno.pk)
        historico = (
            Matricula.objects
            .filter(turma=turma, ativa=False)
            .select_related("aluno")
            .order_by("-data_fim", "-id")[:20]
        )
        context.update({
            "alunos_turma": alunos,
            "historico_vinculos": historico,
            "form_matricular": MatricularAlunoForm(turma=turma),
            "form_transferir": TransferirAlunoForm(
                turma_origem=turma,
                turmas_destino=queryset_turmas_visiveis(self.request.user),
            ),
        })
        return context


class MatricularAlunoView(PermissionRequiredMixin, View):
    permission_required = "alunos.add_matricula"

    def post(self, request, pk):
        turma = get_object_or_404(Turma.objects.select_related("professor_responsavel"), pk=pk)
        if not usuario_pode_acessar_turma(request.user, turma):
            raise PermissionDenied
        form = MatricularAlunoForm(request.POST, turma=turma)
        if not form.is_valid():
            messages.error(request, "Selecione um aluno disponível da mesma série.")
            return redirect("alunos:detalhe_turma", pk=turma.pk)
        try:
            matricular(form.cleaned_data["aluno"], turma)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Aluno vinculado à turma.")
        return redirect("alunos:detalhe_turma", pk=turma.pk)

    def get(self, request, pk):
        return redirect("alunos:detalhe_turma", pk=pk)


class TransferirAlunoView(PermissionRequiredMixin, View):
    permission_required = "alunos.change_matricula"

    def post(self, request, pk):
        turma = get_object_or_404(Turma.objects.select_related("professor_responsavel"), pk=pk)
        if not usuario_pode_acessar_turma(request.user, turma):
            raise PermissionDenied
        form = TransferirAlunoForm(
            request.POST,
            turma_origem=turma,
            turmas_destino=queryset_turmas_visiveis(request.user),
        )
        if not form.is_valid():
            messages.error(request, "Informe aluno e turma de destino válidos.")
            return redirect("alunos:detalhe_turma", pk=turma.pk)
        destino = form.cleaned_data["turma_destino"]
        if not usuario_pode_acessar_turma(request.user, destino):
            raise PermissionDenied
        try:
            transferir(form.cleaned_data["aluno"], destino)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Aluno transferido. O vínculo anterior foi encerrado.")
        return redirect("alunos:detalhe_turma", pk=turma.pk)

    def get(self, request, pk):
        return redirect("alunos:detalhe_turma", pk=pk)


class EncerrarMatriculaView(PermissionRequiredMixin, View):
    permission_required = "alunos.change_matricula"

    def post(self, request, pk):
        matricula = get_object_or_404(
            Matricula.objects.select_related("turma", "turma__professor_responsavel"),
            pk=pk,
        )
        if not usuario_pode_acessar_turma(request.user, matricula.turma):
            raise PermissionDenied
        try:
            encerrar_matricula(matricula)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Vínculo encerrado. O histórico foi preservado.")
        return redirect("alunos:detalhe_turma", pk=matricula.turma_id)

    def get(self, request, pk):
        matricula = get_object_or_404(Matricula, pk=pk)
        return redirect("alunos:detalhe_turma", pk=matricula.turma_id)


class DesempenhoTurmaView(PermissionRequiredMixin, TurmasQuerysetMixin, DetailView):
    permission_required = ("alunos.view_turma", "questoes.view_resultado")
    model = Turma
    template_name = "turma_desempenho.html"
    context_object_name = "turma"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        turma = self.object
        resultados = queryset_resultados(periodo="todos", turma_id=turma.pk)
        alunos_ativos = Aluno.objects.filter(
            matriculas__turma=turma, matriculas__ativa=True
        ).count()
        analise = metricas_por_questao(periodo="todos", turma_id=turma.pk)
        context.update({
            "indicadores": indicadores(resultados),
            "alunos_ativos": alunos_ativos,
            "questoes_dificuldade": analise["com_amostra"][:8],
        })
        return context


class RankingTurmaView(PermissionRequiredMixin, TurmasQuerysetMixin, DetailView):
    permission_required = "alunos.view_turma"
    model = Turma
    template_name = "turma_ranking.html"
    context_object_name = "turma"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        turma = self.object
        ids = list(
            Matricula.objects.filter(turma=turma, ativa=True).values_list("aluno_id", flat=True)
        )
        alunos = list(queryset_ranking(turma.serie).filter(pk__in=ids)[:20])
        for posicao, aluno in enumerate(alunos, start=1):
            aluno.posicao = posicao
            aluno.xp = aluno.xp or 0
            aluno.tentativas = aluno.tentativas or 0
            aluno.tempo_formatado = formatar_tempo(aluno.tempo_total or 0)
            aluno.ra_mascarado = mascarar_ra(aluno.ra)
        context["alunos_ranking"] = alunos
        return context
