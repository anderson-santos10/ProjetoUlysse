from django.urls import path
from . import views
from . import views_avaliacao

app_name = 'questoes'

urlpatterns = [

    path(
        '',
        views.ListaQuestoesView.as_view(),
        name='lista_questoes'
    ),

    path(
        'cadastrar/',
        views.CadastrarQuestaoView.as_view(),
        name='cadastrar'
    ),

    path(
        'gestao/',
        views.GestaoQuestoesView.as_view(),
        name='gestao'
    ),

    path(
        '<int:pk>/editar/',
        views.EditarQuestaoView.as_view(),
        name='editar_questao'
    ),

    path(
        'resultados/',
        views.ListaResultadosView.as_view(),
        name='resultados'
    ),

    path(
        'resultados/<int:pk>/',
        views.DetalheResultadoView.as_view(),
        name='resultado_detalhe'
    ),
    path(
        'avaliacoes/',
        views_avaliacao.ListaAvaliacoesView.as_view(),
        name='lista_avaliacoes',
    ),
    path(
        'avaliacoes/cadastrar/',
        views_avaliacao.CadastrarAvaliacaoView.as_view(),
        name='cadastrar_avaliacao',
    ),
    path(
        'avaliacoes/<int:pk>/',
        views_avaliacao.DetalheAvaliacaoView.as_view(),
        name='detalhe_avaliacao',
    ),
    path(
        'avaliacoes/<int:pk>/editar/',
        views_avaliacao.EditarAvaliacaoView.as_view(),
        name='editar_avaliacao',
    ),
    path(
        'avaliacoes/<int:pk>/publicar/',
        views_avaliacao.PublicarAvaliacaoView.as_view(),
        name='publicar_avaliacao',
    ),
    path(
        'avaliacoes/<int:pk>/encerrar/',
        views_avaliacao.EncerrarAvaliacaoView.as_view(),
        name='encerrar_avaliacao',
    ),
    path(
        'avaliacoes/<int:pk>/realizar/',
        views_avaliacao.AlunoAvaliacaoView.as_view(),
        name='aluno_avaliacao',
    ),
]