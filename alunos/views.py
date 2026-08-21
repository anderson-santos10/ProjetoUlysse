from django.contrib import messages
from django.shortcuts import redirect
from django.views.generic import ListView, CreateView, TemplateView
from django.urls import reverse_lazy
from django.views.generic import TemplateView
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
    success_url = reverse_lazy('alunos:lista_alunos')


class AcessoAlunoView(TemplateView):

    template_name = 'acesso_aluno.html'

    def post(self, request, *args, **kwargs):

        ra = request.POST.get('ra', '').strip()

        try:

            aluno = Aluno.objects.get(ra=ra)

            # ==========================================
            # LOGIN DO ALUNO
            # ==========================================

            request.session['aluno_id'] = aluno.id

            # ==========================================
            # LIMPA O QUESTIONÁRIO ANTERIOR
            # ==========================================

            request.session['questao_atual'] = 0
            request.session['respostas'] = {}
            request.session['questionario_finalizado'] = False
            request.session['acertos'] = 0
            request.session['total_questoes'] = 0

            # ==========================================
            # REDIRECIONA PARA ÁREA DO ALUNO
            # ==========================================

            return redirect('alunos:aluno_logado')

        except Aluno.DoesNotExist:

            messages.error(
                request,
                'RA não encontrado. Verifique o número informado.'
            )

            return self.get(request, *args, **kwargs)


class AlunoLogadoView(TemplateView):

    template_name = 'aluno_logado.html'

    def get(self, request, *args, **kwargs):

        # Verifica se existe aluno logado
        aluno_id = request.session.get('aluno_id')

        if not aluno_id:
            return redirect('alunos:acesso_aluno')

        try:

            aluno = Aluno.objects.get(id=aluno_id)

        except Aluno.DoesNotExist:

            # Remove sessão inválida
            request.session.pop('aluno_id', None)

            messages.error(
                request,
                'Aluno não encontrado. Faça o acesso novamente.'
            )

            return redirect('questoes:lista_questoes')

        return self.render_to_response({
            'aluno': aluno
        })
        
        
class RankingView(TemplateView):

    template_name = 'ranking.html'

    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        # ==========================================
        # RANKING DOS ALUNOS
        # ==========================================

        alunos = (
            Aluno.objects
            .annotate(
                pontos=Avg('resultados__nota'),
                tentativas=Count('resultados'),
                total_acertos=Sum('resultados__acertos'),
            )
            .filter(
                tentativas__gt=0
            )
            .order_by(
                '-pontos',
                '-total_acertos',
                'nome'
            )[:20]
        )

        alunos_ranking = list(alunos)

        # Adiciona posição
        for posicao, aluno in enumerate(
            alunos_ranking,
            start=1
        ):
            aluno.posicao = posicao

        context['alunos'] = alunos_ranking

        # ==========================================
        # ALUNO LOGADO
        # ==========================================

        aluno_id = self.request.session.get('aluno_id')

        usuario_logado = None

        if aluno_id:

            try:

                resultado_aluno = (
                    Aluno.objects
                    .filter(id=aluno_id)
                    .annotate(
                        pontos=Avg('resultados__nota'),
                        tentativas=Count('resultados'),
                        total_acertos=Sum(
                            'resultados__acertos'
                        ),
                    )
                    .first()
                )

                if (
                    resultado_aluno
                    and resultado_aluno.tentativas > 0
                ):

                    # Busca todos os alunos para descobrir
                    # a posição real do aluno
                    todos_alunos = list(
                        Aluno.objects
                        .annotate(
                            pontos=Avg(
                                'resultados__nota'
                            ),
                            tentativas=Count(
                                'resultados'
                            ),
                            total_acertos=Sum(
                                'resultados__acertos'
                            ),
                        )
                        .filter(
                            tentativas__gt=0
                        )
                        .order_by(
                            '-pontos',
                            '-total_acertos',
                            'nome'
                        )
                    )

                    for posicao, aluno in enumerate(
                        todos_alunos,
                        start=1
                    ):

                        if aluno.id == aluno_id:

                            resultado_aluno.posicao = posicao

                            break

                    usuario_logado = resultado_aluno

            except Aluno.DoesNotExist:

                usuario_logado = None

        context['usuario_logado'] = usuario_logado

        return context