from django.urls import path
from . import views

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
]