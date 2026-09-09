from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect
from django.views import View
from django.views.generic import (
    ListView,
    CreateView,
    UpdateView,
    TemplateView
)
from django.urls import reverse_lazy
from django.db.models import Avg, Count, Sum

from accounts.mixins import PermissionRequiredMixin
from accounts.querystring import without_page
from questoes.cooldown import verificar_bloqueio
from questoes.models import Avaliacao, Questao
from questoes.avaliacoes import avaliacao_disponivel_para_aluno

from .escopo import queryset_alunos_visiveis, queryset_resultados_visiveis
from .forms import AlunoForm
from .matriculas import matricula_ativa_em
from .models import Aluno
from .series import desempenho_serie, resumo_series, serie_ou_404
from .security import (
    limpar_falhas_ra,
    mascarar_ra,
    ra_acesso_limitado,
    registrar_falha_ra,
    formatar_tempo,
)
from .session import (
    aluno_session_exists,
    bind_linked_aluno_session,
    clear_aluno_session,
)


class ListaAlunosView(PermissionRequiredMixin, ListView):

    permission_required = "alunos.view_aluno"
    model = Aluno
    template_name = 'aluno_list.html'
    context_object_name = 'alunos'
    ordering = ['nome']
    paginate_by = 20

    def get_queryset(self):
        queryset = queryset_alunos_visiveis(self.request.user).order_by('nome')
        busca = self.request.GET.get('q', '').strip()
        serie = self.request.GET.get('serie', '').strip()
        if busca:
            queryset = queryset.filter(
                Q(nome__icontains=busca) | Q(ra__icontains=busca)
            )
        if serie:
            queryset = queryset.filter(serie=serie)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['busca'] = self.request.GET.get('q', '').strip()
        context['serie_filtro'] = self.request.GET.get('serie', '').strip()
        context['series'] = Aluno.SERIES
        context['querystring'] = without_page(self.request)
        return context


class CadastrarAlunoView(PermissionRequiredMixin, CreateView):

    permission_required = "alunos.add_aluno"

    model = Aluno
    form_class = AlunoForm
    template_name = 'aluno_form.html'

    def form_valid(self, form):
        messages.success(
            self.request,
            'Aluno cadastrado com sucesso.',
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy(
            'alunos:alunos_por_serie',
            kwargs={
                'serie': self.object.serie
            }
        )


class EditarAlunoView(PermissionRequiredMixin, UpdateView):

    permission_required = "alunos.change_aluno"
    model = Aluno
    form_class = AlunoForm
    template_name = 'aluno_form.html'
    pk_url_kwarg = 'pk'

    def get_queryset(self):
        return queryset_alunos_visiveis(self.request.user)

    def form_valid(self, form):
        messages.success(
            self.request,
            'Aluno atualizado com sucesso.',
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('alunos:lista_alunos')


class AcessoAlunoView(TemplateView):

    template_name = 'acesso_aluno.html'

    def post(self, request, *args, **kwargs):

        if ra_acesso_limitado(request.session):
            messages.error(
                request,
                'Muitas tentativas. Aguarde alguns minutos e tente novamente.',
            )
            return self.get(request, *args, **kwargs)

        ra = request.POST.get(
            'ra',
            ''
        ).strip()

        try:

            aluno = Aluno.objects.get(
                ra=ra
            )

            limpar_falhas_ra(request.session)
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
                'questoes_versoes',
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

            registrar_falha_ra(request.session)
            messages.error(
                request,
                'Não foi possível acessar com os dados informados. Tente novamente.'
            )

            return self.get(
                request,
                *args,
                **kwargs
            )


class SairAlunoView(View):
    """Encerra só a sessão pedagógica (RA). Não faz logout Django."""

    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        clear_aluno_session(request.session)
        messages.info(
            request,
            'Acesso do aluno encerrado.',
        )
        return redirect('alunos:acesso_aluno')


class AlunoLogadoView(TemplateView):

    template_name = 'aluno_logado.html'

    def get(self, request, *args, **kwargs):

        bind_linked_aluno_session(request)

        aluno_id = request.session.get(
            'aluno_id'
        )

        if not aluno_id or not aluno_session_exists(aluno_id):

            if aluno_id:
                clear_aluno_session(
                    request.session
                )

                messages.error(
                    request,
                    'Aluno não encontrado. Faça o acesso novamente.'
                )

            return redirect(
                'alunos:acesso_aluno'
            )

        aluno = Aluno.objects.get(
            id=aluno_id
        )

        bloqueado, _proxima, segundos_restantes = verificar_bloqueio(aluno)
        total_questoes_serie = Questao.objects.filter(serie=aluno.serie).count()

        posicao = None
        for indice, candidato in enumerate(queryset_ranking(aluno.serie), start=1):
            if candidato.id == aluno.id:
                posicao = indice
                break

        avaliacoes_abertas = []
        matricula = matricula_ativa_em(aluno)
        if matricula:
            for item in (
                Avaliacao.objects
                .filter(turma=matricula.turma, status=Avaliacao.Status.PUBLICADA)
                .order_by("data_fim", "titulo")
            ):
                ok, _motivo = avaliacao_disponivel_para_aluno(item, aluno)
                if ok:
                    avaliacoes_abertas.append(item)

        return self.render_to_response({
            'aluno': aluno,
            'questionario_bloqueado': bloqueado,
            'segundos_restantes': segundos_restantes,
            'tempo_bloqueio_formatado': formatar_tempo(segundos_restantes),
            'total_questoes_serie': total_questoes_serie,
            'posicao': posicao,
            'avaliacoes_abertas': avaliacoes_abertas,
        })


def queryset_ranking(serie):
    return (
        Aluno.objects
        .filter(serie=serie)
        .annotate(
            pontos=Avg('resultados__nota'),
            tentativas=Count('resultados', distinct=True),
            total_acertos=Sum('resultados__acertos'),
            tempo_total=Sum('resultados__tempo_segundos'),
        )
        .order_by(
            '-xp',
            '-pontos',
            '-total_acertos',
            'tempo_total',
            'nome',
        )
    )


class RegrasView(TemplateView):

    template_name = 'regras.html'
# =========================================================
# RANKING
# =========================================================

class RankingView(TemplateView):

    template_name = 'ranking.html'

    def formatar_tempo(self, segundos):
        return formatar_tempo(segundos)

    def get_context_data(self, **kwargs):

        context = super().get_context_data(
            **kwargs
        )

        rankings = {}

        # =====================================================
        # RANKING POR SÉRIE
        # =====================================================

        for codigo, nome in Aluno.SERIES:

            alunos = queryset_ranking(codigo)[:20]

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

                aluno.ra_mascarado = mascarar_ra(aluno.ra)

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

        if aluno_id and not aluno_session_exists(aluno_id):

            clear_aluno_session(
                self.request.session
            )

            aluno_id = None

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

                resultado_aluno.ra_mascarado = mascarar_ra(
                    resultado_aluno.ra
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

                    # =================================================
                    # MESMA REGRA DO RANKING
                    # =================================================
                    .order_by(

                        # 1º - Maior XP
                        '-xp',

                        # 2º - Maior média
                        '-pontos',

                        # 3º - Maior número de acertos
                        '-total_acertos',

                        # 4º - MENOR TEMPO
                        'tempo_total',

                        # 5º - Nome
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

class ListaSeriesView(PermissionRequiredMixin, TemplateView):

    permission_required = "alunos.view_aluno"

    template_name = 'series.html'

    def get_context_data(
        self,
        **kwargs
    ):

        context = super().get_context_data(
            **kwargs
        )

        context['series'] = resumo_series(
            alunos_qs=queryset_alunos_visiveis(self.request.user),
            resultados_qs=queryset_resultados_visiveis(self.request.user),
        )
        return context


# =========================================================
# ALUNOS POR SÉRIE
# =========================================================

class AlunosPorSerieView(PermissionRequiredMixin, ListView):

    permission_required = "alunos.view_aluno"

    model = Aluno

    template_name = 'alunos_por_serie.html'
    context_object_name = 'alunos'
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        self.codigo_serie, self.nome_serie = serie_ou_404(
            kwargs.get('serie')
        )
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        queryset = (
            queryset_alunos_visiveis(self.request.user)
            .filter(serie=self.codigo_serie)
            .order_by('nome')
        )
        busca = self.request.GET.get('q', '').strip()
        if busca:
            queryset = queryset.filter(
                Q(nome__icontains=busca) | Q(ra__icontains=busca)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['codigo_serie'] = self.codigo_serie
        context['nome_serie'] = self.nome_serie
        context['busca'] = self.request.GET.get('q', '').strip()
        context['querystring'] = without_page(self.request)
        context.update(
            desempenho_serie(
                self.codigo_serie,
                alunos_qs=queryset_alunos_visiveis(self.request.user),
                resultados_qs=queryset_resultados_visiveis(self.request.user),
            )
        )
        return context
