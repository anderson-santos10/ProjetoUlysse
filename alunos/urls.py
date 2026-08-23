from django.urls import path
from .views import (
    ListaAlunosView,
    CadastrarAlunoView,
    AcessoAlunoView,
    AlunoLogadoView,
    RankingView,
)

app_name = 'alunos'


urlpatterns = [
    path('', ListaAlunosView.as_view(), name='lista_alunos'),
    path('cadastrar/', CadastrarAlunoView.as_view(), name='cadastrar'),
    path('acesso/', AcessoAlunoView.as_view(), name='acesso_aluno'),
    path('logado/', AlunoLogadoView.as_view(), name='aluno_logado'),
    path('ranking/', RankingView.as_view(), name='ranking'),
]