from datetime import datetime

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from accounts.mixins import PermissionRequiredMixin
from alunos.matriculas import matricula_ativa_em
from alunos.session import aluno_session_exists

from .avaliacoes import (
    avaliacao_disponivel_para_aluno,
    avaliacoes_visiveis,
    encerrar,
    publicar,
    tempo_esgotado,
    tentativas_do_aluno,
    usuario_pode_acessar_avaliacao,
)
from .forms_avaliacao import AvaliacaoForm
from .models import Avaliacao, AvaliacaoQuestao, Resultado
from .persistencia import persistir_respostas_resultado
from .scoring import calcular_xp


class ListaAvaliacoesView(PermissionRequiredMixin, ListView):
    permission_required = "questoes.view_avaliacao"
    template_name = "avaliacao_list.html"
    context_object_name = "avaliacoes"
    paginate_by = 20

    def get_queryset(self):
        return avaliacoes_visiveis(self.request.user).order_by("-criado_em")


class AvaliacaoFormMixin:
    model = Avaliacao
    form_class = AvaliacaoForm
    template_name = "avaliacao_form.html"
    success_url = reverse_lazy("questoes:lista_avaliacoes")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        criando = not form.instance.pk
        if not criando and form.instance.status != Avaliacao.Status.RASCUNHO:
            messages.error(
                self.request,
                "Avaliação publicada não pode ter o conjunto de questões alterado.",
            )
            return redirect("questoes:detalhe_avaliacao", pk=form.instance.pk)
        if criando:
            form.instance.criado_por = self.request.user
            form.instance.status = Avaliacao.Status.RASCUNHO
        form.instance.serie = form.cleaned_data["turma"].serie
        response = super().form_valid(form)
        self._salvar_itens(form)
        messages.success(self.request, "Avaliação salva como rascunho.")
        return response

    def _salvar_itens(self, form):
        if self.object.status != Avaliacao.Status.RASCUNHO:
            return
        escolhidas = list(form.cleaned_data.get("questoes") or [])
        AvaliacaoQuestao.objects.filter(avaliacao=self.object).exclude(
            questao__in=escolhidas
        ).delete()
        existentes = {
            item.questao_id: item
            for item in AvaliacaoQuestao.objects.filter(avaliacao=self.object)
        }
        for ordem, questao in enumerate(escolhidas, start=1):
            item = existentes.get(questao.pk)
            if item:
                if item.ordem != ordem:
                    item.ordem = ordem
                    item.save(update_fields=["ordem"])
            else:
                AvaliacaoQuestao.objects.create(
                    avaliacao=self.object,
                    questao=questao,
                    ordem=ordem,
                )


class CadastrarAvaliacaoView(PermissionRequiredMixin, AvaliacaoFormMixin, CreateView):
    permission_required = "questoes.add_avaliacao"


class EditarAvaliacaoView(PermissionRequiredMixin, AvaliacaoFormMixin, UpdateView):
    permission_required = "questoes.change_avaliacao"

    def get_queryset(self):
        return avaliacoes_visiveis(self.request.user)

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not usuario_pode_acessar_avaliacao(self.request.user, obj):
            raise PermissionDenied
        return obj

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.status != Avaliacao.Status.RASCUNHO:
            messages.error(
                request,
                "Somente rascunhos podem ser editados. A avaliação publicada preserva as versões congeladas.",
            )
            return redirect("questoes:detalhe_avaliacao", pk=self.object.pk)
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.status != Avaliacao.Status.RASCUNHO:
            messages.error(
                request,
                "Somente rascunhos podem ser editados. A avaliação publicada preserva as versões congeladas.",
            )
            return redirect("questoes:detalhe_avaliacao", pk=self.object.pk)
        return super().post(request, *args, **kwargs)


class DetalheAvaliacaoView(PermissionRequiredMixin, DetailView):
    permission_required = "questoes.view_avaliacao"
    template_name = "avaliacao_detail.html"
    context_object_name = "avaliacao"

    def get_queryset(self):
        return avaliacoes_visiveis(self.request.user).prefetch_related(
            "itens__questao",
            "itens__questao_versao",
        )

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not usuario_pode_acessar_avaliacao(self.request.user, obj):
            raise PermissionDenied
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        resultados = (
            Resultado.objects.filter(avaliacao=self.object)
            .select_related("aluno")
            .order_by("-nota", "tempo_segundos", "aluno__nome")
        )
        context["resultados"] = resultados
        context["itens"] = self.object.itens.all()
        return context


class PublicarAvaliacaoView(PermissionRequiredMixin, View):
    permission_required = "questoes.change_avaliacao"

    def post(self, request, pk):
        avaliacao = get_object_or_404(Avaliacao.objects.select_related("turma"), pk=pk)
        if not usuario_pode_acessar_avaliacao(request.user, avaliacao):
            raise PermissionDenied
        try:
            publicar(avaliacao)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(
                request,
                "Avaliação publicada. As versões das questões foram congeladas.",
            )
        return redirect("questoes:detalhe_avaliacao", pk=pk)

    def get(self, request, pk):
        return redirect("questoes:detalhe_avaliacao", pk=pk)


class EncerrarAvaliacaoView(PermissionRequiredMixin, View):
    permission_required = "questoes.change_avaliacao"

    def post(self, request, pk):
        avaliacao = get_object_or_404(Avaliacao.objects.select_related("turma"), pk=pk)
        if not usuario_pode_acessar_avaliacao(request.user, avaliacao):
            raise PermissionDenied
        try:
            encerrar(avaliacao)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Avaliação encerrada.")
        return redirect("questoes:detalhe_avaliacao", pk=pk)

    def get(self, request, pk):
        return redirect("questoes:detalhe_avaliacao", pk=pk)


def _aluno_da_sessao(request):
    aluno_id = request.session.get("aluno_id")
    if not aluno_id or not aluno_session_exists(aluno_id):
        return None
    from alunos.models import Aluno
    return Aluno.objects.filter(pk=aluno_id).first()


class AlunoAvaliacaoView(View):
    template_name = "avaliacao_aluno.html"

    def dispatch(self, request, *args, **kwargs):
        self.aluno = _aluno_da_sessao(request)
        if self.aluno is None:
            messages.error(request, "Entre com o RA para acessar a avaliação.")
            return redirect("alunos:acesso_aluno")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, pk):
        avaliacao = get_object_or_404(
            Avaliacao.objects.select_related("turma"),
            pk=pk,
        )
        ok, motivo = avaliacao_disponivel_para_aluno(avaliacao, self.aluno)
        em_andamento = request.session.get("avaliacao_id") == avaliacao.pk
        itens = []
        if em_andamento:
            itens = list(
                avaliacao.itens.select_related("questao", "questao_versao").order_by("ordem")
            )
            if tempo_esgotado(
                request.session.get("avaliacao_inicio"),
                avaliacao.tempo_limite_minutos,
            ):
                messages.error(request, "O tempo desta avaliação esgotou.")
                return self._finalizar(request, avaliacao, itens, request.session.get("avaliacao_respostas") or {})
        context = {
            "avaliacao": avaliacao,
            "aluno": self.aluno,
            "disponivel": ok,
            "motivo": motivo,
            "em_andamento": em_andamento,
            "itens": itens,
            "tentativas": tentativas_do_aluno(self.aluno, avaliacao),
        }
        return render(request, self.template_name, context)

    def post(self, request, pk):
        avaliacao = get_object_or_404(
            Avaliacao.objects.select_related("turma"),
            pk=pk,
        )
        acao = request.POST.get("acao")
        if acao == "iniciar":
            ok, motivo = avaliacao_disponivel_para_aluno(avaliacao, self.aluno)
            if not ok:
                messages.error(request, motivo)
                return redirect("questoes:aluno_avaliacao", pk=pk)
            request.session["avaliacao_id"] = avaliacao.pk
            request.session["avaliacao_inicio"] = timezone.now().isoformat()
            request.session["avaliacao_respostas"] = {}
            request.session.pop("aluno_id_avaliacao", None)
            return redirect("questoes:aluno_avaliacao", pk=pk)

        if acao == "finalizar":
            if request.session.get("avaliacao_id") != avaliacao.pk:
                messages.error(request, "Não há tentativa em andamento.")
                return redirect("questoes:aluno_avaliacao", pk=pk)
            itens = list(
                avaliacao.itens.select_related("questao", "questao_versao").order_by("ordem")
            )
            respostas = {
                str(item.questao_id): request.POST.get(f"q_{item.questao_id}")
                for item in itens
            }
            return self._finalizar(request, avaliacao, itens, respostas)

        return redirect("questoes:aluno_avaliacao", pk=pk)

    def _finalizar(self, request, avaliacao, itens, respostas):
        questoes = [item.questao for item in itens]
        versoes = {
            item.questao_id: item.questao_versao
            for item in itens
        }
        if any(versao is None for versao in versoes.values()):
            messages.error(request, "Avaliação inconsistente: faltam versões congeladas.")
            self._limpar_sessao(request)
            return redirect("alunos:aluno_logado")
        inicio = request.session.get("avaliacao_inicio")
        tempo_segundos = 0
        if inicio:
            try:
                inicio_dt = datetime.fromisoformat(inicio)
                if timezone.is_naive(inicio_dt):
                    inicio_dt = timezone.make_aware(inicio_dt)
                tempo_segundos = max(0, int((timezone.now() - inicio_dt).total_seconds()))
            except (TypeError, ValueError):
                tempo_segundos = 0
        if avaliacao.tempo_limite_minutos:
            teto = avaliacao.tempo_limite_minutos * 60
            tempo_segundos = min(tempo_segundos, teto)

        acertos = sum(
            1
            for q in questoes
            if respostas.get(str(q.id)) == versoes[q.id].resposta_correta
        )
        total = len(questoes)
        erros = total - acertos
        nota = round((acertos / total) * 10, 2) if total else 0
        xp_ganho = calcular_xp(questoes, respostas, versoes)

        with transaction.atomic():
            from alunos.models import Aluno
            aluno = Aluno.objects.select_for_update().get(pk=self.aluno.pk)
            ja_feitas = Resultado.objects.filter(
                aluno=aluno, avaliacao=avaliacao
            ).count()
            if ja_feitas >= avaliacao.tentativas_maximas:
                messages.error(request, "Você já utilizou o número máximo de tentativas.")
                self._limpar_sessao(request)
                return redirect("alunos:aluno_logado")
            aluno.xp += xp_ganho
            aluno.save(update_fields=["xp"])
            resultado = Resultado.objects.create(
                aluno=aluno,
                acertos=acertos,
                erros=erros,
                total_questoes=total,
                nota=nota,
                xp_ganho=xp_ganho,
                tempo_segundos=tempo_segundos,
                matricula=matricula_ativa_em(aluno),
                avaliacao=avaliacao,
            )
            persistir_respostas_resultado(resultado, questoes, respostas, versoes)

        self._limpar_sessao(request)
        messages.success(request, "Avaliação enviada.")
        return redirect("alunos:aluno_logado")

    def _limpar_sessao(self, request):
        for chave in ("avaliacao_id", "avaliacao_inicio", "avaliacao_respostas"):
            request.session.pop(chave, None)
