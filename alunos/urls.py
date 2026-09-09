from django.urls import path
from .views import (
    AlunosPorSerieView,
    ListaAlunosView,
    CadastrarAlunoView,
    EditarAlunoView,
    AcessoAlunoView,
    AlunoLogadoView,
    ListaSeriesView,
    RankingView,
    RegrasView,
    SairAlunoView,
)
from .views_turmas import (
    AlternarTurmaView,
    CadastrarTurmaView,
    DesempenhoTurmaView,
    DetalheTurmaView,
    EditarTurmaView,
    EncerrarMatriculaView,
    ListaTurmasView,
    MatricularAlunoView,
    RankingTurmaView,
    TransferirAlunoView,
)

app_name = 'alunos'


urlpatterns = [
    path('', ListaAlunosView.as_view(), name='lista_alunos'),
    path('cadastrar/', CadastrarAlunoView.as_view(), name='cadastrar'),
    path('turmas/', ListaTurmasView.as_view(), name='lista_turmas'),
    path('turmas/cadastrar/', CadastrarTurmaView.as_view(), name='cadastrar_turma'),
    path('turmas/<int:pk>/', DetalheTurmaView.as_view(), name='detalhe_turma'),
    path('turmas/<int:pk>/editar/', EditarTurmaView.as_view(), name='editar_turma'),
    path('turmas/<int:pk>/alternar/', AlternarTurmaView.as_view(), name='alternar_turma'),
    path('turmas/<int:pk>/matricular/', MatricularAlunoView.as_view(), name='matricular_aluno'),
    path('turmas/<int:pk>/transferir/', TransferirAlunoView.as_view(), name='transferir_aluno'),
    path('turmas/<int:pk>/desempenho/', DesempenhoTurmaView.as_view(), name='desempenho_turma'),
    path('turmas/<int:pk>/ranking/', RankingTurmaView.as_view(), name='ranking_turma'),
    path('matriculas/<int:pk>/encerrar/', EncerrarMatriculaView.as_view(), name='encerrar_matricula'),
    path('<int:pk>/editar/', EditarAlunoView.as_view(), name='editar_aluno'),
    path('acesso/', AcessoAlunoView.as_view(), name='acesso_aluno'),
    path('sair/', SairAlunoView.as_view(), name='sair_aluno'),
    path('logado/', AlunoLogadoView.as_view(), name='aluno_logado'),
    path('ranking/', RankingView.as_view(), name='ranking'),
    path('series/', ListaSeriesView.as_view(), name='series'),
    path('series/<str:serie>/', AlunosPorSerieView.as_view(), name='alunos_por_serie'),
    path('regras/', RegrasView.as_view(), name='regras'),
]