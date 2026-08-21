from django.db.models import Avg, Count, Sum
from django.views.generic import TemplateView
from django.db.models.functions import Round
from alunos.models import Aluno


class HomeView(TemplateView):
    template_name = 'home.html'


class TurmaView(TemplateView):
    template_name = 'turma.html'


class AreaProfessorView(TemplateView):
    template_name = 'area_professor.html'


from django.views.generic import TemplateView
from django.db.models import Avg, Count, Sum
from django.db.models.functions import Round

from alunos.models import Aluno


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
                pontos=Round(
                    Avg('resultados__nota'),
                    precision=2
                ),
                tentativas=Count('resultados'),
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
            )[:20]
        )

        alunos_ranking = list(alunos)

        # Define a posição de cada aluno
        for posicao, aluno in enumerate(
            alunos_ranking,
            start=1
        ):
            aluno.posicao = posicao

        context['alunos'] = alunos_ranking

        # ==========================================
        # ALUNO ATUALMENTE LOGADO
        # ==========================================

        aluno_id = self.request.session.get(
            'aluno_id'
        )

        usuario_logado = None

        if aluno_id:

            try:

                resultado_aluno = (
                    Aluno.objects
                    .filter(
                        id=aluno_id
                    )
                    .annotate(
                        pontos=Round(
                            Avg(
                                'resultados__nota'
                            ),
                            precision=2
                        ),
                        tentativas=Count(
                            'resultados'
                        ),
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

                    # ==========================================
                    # DESCOBRE A POSIÇÃO REAL DO ALUNO
                    # ==========================================

                    todos_alunos = list(
                        Aluno.objects
                        .annotate(
                            pontos=Round(
                                Avg(
                                    'resultados__nota'
                                ),
                                precision=2
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