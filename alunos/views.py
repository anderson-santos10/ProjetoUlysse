from django.contrib import messages
from django.shortcuts import redirect
from django.views.generic import (
    ListView,
    CreateView,
    TemplateView
)
from django.urls import reverse_lazy
from django.db.models import Avg, Count, Sum

from .models import Aluno
from .forms import AlunoForm


class ListaAlunosView(ListView):

    model = Aluno
    template_name = 'aluno_list.html'
    context_object_name = 'alunos'
    ordering = ['nome']


class CadastrarAlunoView(CreateView):

    model = Aluno
    form_class = AlunoForm
    template_name = 'aluno_form.html'

    def get_success_url(self):
        return reverse_lazy(
            'alunos:alunos_por_serie',
            kwargs={
                'serie': self.object.serie
            }
        )


class AcessoAlunoView(TemplateView):

    template_name = 'acesso_aluno.html'

    def post(self, request, *args, **kwargs):

        ra = request.POST.get(
            'ra',
            ''
        ).strip()

        try:

            aluno = Aluno.objects.get(
                ra=ra
            )

            request.session['aluno_id'] = aluno.id
            request.session['questao_atual'] = 0
            request.session['respostas'] = {}
            request.session['questionario_finalizado'] = False
            request.session['acertos'] = 0
            request.session['total_questoes'] = 0

            request.session.pop(
                'questoes_ordem',
                None
            )

            request.session.pop(
                'alternativas_ordem',
                None
            )

            request.session.pop(
                'inicio_questionario',
                None
            )

            request.session.pop(
                'resposta_mostrada',
                None
            )

            request.session.pop(
                'resposta_escolhida',
                None
            )

            request.session.pop(
                'resposta_correta',
                None
            )

            request.session.pop(
                'acertou',
                None
            )

            return redirect(
                'alunos:aluno_logado'
            )

        except Aluno.DoesNotExist:

            messages.error(
                request,
                'RA não encontrado. Verifique o número informado.'
            )

            return self.get(
                request,
                *args,
                **kwargs
            )


class AlunoLogadoView(TemplateView):

    template_name = 'aluno_logado.html'

    def get(self, request, *args, **kwargs):

        aluno_id = request.session.get(
            'aluno_id'
        )

        if not aluno_id:

            return redirect(
                'alunos:acesso_aluno'
            )

        try:

            aluno = Aluno.objects.get(
                id=aluno_id
            )

        except Aluno.DoesNotExist:

            request.session.pop(
                'aluno_id',
                None
            )

            messages.error(
                request,
                'Aluno não encontrado. Faça o acesso novamente.'
            )

            return redirect(
                'questoes:lista_questoes'
            )

        return self.render_to_response({
            'aluno': aluno
        })


# =========================================================
# RANKING
# =========================================================

class RankingView(TemplateView):

    template_name = 'ranking.html'

    def formatar_tempo(self, segundos):

        segundos = segundos or 0

        horas = segundos // 3600

        minutos = (
            segundos % 3600
        ) // 60

        segundos_restantes = (
            segundos % 60
        )

        if horas > 0:

            return (
                f'{horas}h '
                f'{minutos:02d}min '
                f'{segundos_restantes:02d}s'
            )

        return (
            f'{minutos:02d}min '
            f'{segundos_restantes:02d}s'
        )

    def get_context_data(self, **kwargs):

        context = super().get_context_data(
            **kwargs
        )

        rankings = {}

        # =====================================================
        # RANKING POR SÉRIE
        # =====================================================

        for codigo, nome in Aluno.SERIES:

            alunos = (
                Aluno.objects
                .filter(
                    serie=codigo
                )
                .annotate(
                    pontos=Avg(
                        'resultados__nota'
                    ),

                    tentativas=Count(
                        'resultados',
                        distinct=True
                    ),

                    total_acertos=Sum(
                        'resultados__acertos'
                    ),

                    tempo_total=Sum(
                        'resultados__tempo_segundos'
                    ),
                )
                .order_by(
                    '-xp',
                    '-pontos',
                    '-total_acertos',
                    'nome'
                )[:20]
            )

            alunos_ranking = list(
                alunos
            )

            for posicao, aluno in enumerate(
                alunos_ranking,
                start=1
            ):

                aluno.posicao = posicao

                # =================================================
                # XP
                # =================================================

                aluno.xp = aluno.xp or 0

                # =================================================
                # ESTATÍSTICAS
                # =================================================

                aluno.pontos = (
                    aluno.pontos or 0
                )

                aluno.tentativas = (
                    aluno.tentativas or 0
                )

                aluno.total_acertos = (
                    aluno.total_acertos or 0
                )

                aluno.tempo_total = (
                    aluno.tempo_total or 0
                )

                # =================================================
                # TEMPO FORMATADO
                # =================================================

                aluno.tempo_formatado = (
                    self.formatar_tempo(
                        aluno.tempo_total
                    )
                )

            rankings[codigo] = {
                'nome': nome,
                'alunos': alunos_ranking,
            }

        context['rankings'] = rankings

        # =====================================================
        # ALUNO LOGADO
        # =====================================================

        aluno_id = self.request.session.get(
            'aluno_id'
        )

        usuario_logado = None

        if aluno_id:

            resultado_aluno = (
                Aluno.objects
                .filter(
                    id=aluno_id
                )
                .annotate(
                    pontos=Avg(
                        'resultados__nota'
                    ),

                    tentativas=Count(
                        'resultados',
                        distinct=True
                    ),

                    total_acertos=Sum(
                        'resultados__acertos'
                    ),

                    tempo_total=Sum(
                        'resultados__tempo_segundos'
                    ),
                )
                .first()
            )

            if resultado_aluno:

                # =================================================
                # XP
                # =================================================

                resultado_aluno.xp = (
                    resultado_aluno.xp or 0
                )

                # =================================================
                # ESTATÍSTICAS
                # =================================================

                resultado_aluno.pontos = (
                    resultado_aluno.pontos or 0
                )

                resultado_aluno.tentativas = (
                    resultado_aluno.tentativas or 0
                )

                resultado_aluno.total_acertos = (
                    resultado_aluno.total_acertos or 0
                )

                resultado_aluno.tempo_total = (
                    resultado_aluno.tempo_total or 0
                )

                # =================================================
                # TEMPO FORMATADO
                # =================================================

                resultado_aluno.tempo_formatado = (
                    self.formatar_tempo(
                        resultado_aluno.tempo_total
                    )
                )

                # =================================================
                # POSIÇÃO DO ALUNO NA SUA SÉRIE
                # =================================================

                alunos_da_serie = list(
                    Aluno.objects
                    .filter(
                        serie=resultado_aluno.serie
                    )
                    .annotate(
                        pontos=Avg(
                            'resultados__nota'
                        ),

                        tentativas=Count(
                            'resultados',
                            distinct=True
                        ),

                        total_acertos=Sum(
                            'resultados__acertos'
                        ),

                        tempo_total=Sum(
                            'resultados__tempo_segundos'
                        ),
                    )
                    .order_by(
                        '-xp',
                        '-pontos',
                        '-total_acertos',
                        'nome'
                    )
                )

                for posicao, aluno in enumerate(
                    alunos_da_serie,
                    start=1
                ):

                    if aluno.id == aluno_id:

                        resultado_aluno.posicao = (
                            posicao
                        )

                        break

                usuario_logado = (
                    resultado_aluno
                )

        context['usuario_logado'] = (
            usuario_logado
        )

        return context

# =========================================================
# LISTA DE SÉRIES
# =========================================================

class ListaSeriesView(TemplateView):

    template_name = 'series.html'

    def get_context_data(
        self,
        **kwargs
    ):

        context = super().get_context_data(
            **kwargs
        )

        context['series'] = (
            Aluno.SERIES
        )

        return context


# =========================================================
# ALUNOS POR SÉRIE
# =========================================================

class AlunosPorSerieView(ListView):

    model = Aluno

    template_name = ('alunos_por_serie.html')

    context_object_name = 'alunos'

    def get_queryset(self):

        serie = self.kwargs['serie']

        return (
            Aluno.objects
            .filter(
                serie=serie
            )
            .order_by('nome')
        )

    def get_context_data(
        self,
        **kwargs
    ):

        context = super().get_context_data(
            **kwargs
        )

        serie = self.kwargs['serie']

        series = dict(
            Aluno.SERIES
        )

        context['nome_serie'] = (
            series.get(
                serie,
                'Série não encontrada'
            )
        )

        return context