from django.urls import path
from .views import (
    AlunosPorSerieView,
    ListaAlunosView,
    CadastrarAlunoView,
    AcessoAlunoView,
    AlunoLogadoView,
    ListaSeriesView,
    RankingView,
)

app_name = 'alunos'


urlpatterns = [
    path('', ListaAlunosView.as_view(), name='lista_alunos'),
    path('cadastrar/', CadastrarAlunoView.as_view(), name='cadastrar'),
    path('acesso/', AcessoAlunoView.as_view(), name='acesso_aluno'),
    path('logado/', AlunoLogadoView.as_view(), name='aluno_logado'),
    path('ranking/', RankingView.as_view(), name='ranking'),
    path('series/', ListaSeriesView.as_view(), name='series'),
    path('series/<str:serie>/', AlunosPorSerieView.as_view(), name='alunos_por_serie'),
]