"""
Este URLconf NÃO é usado pelo projeto.

ROOT_URLCONF aponta para saresp.urls. As rotas reais (incluindo
login do professor, painel, logout e questões) estão lá.

Não incluir este módulo em include() sem revisar: ele mapeia
/professor/ para o painel (sem tela de login) e duplica admin/.
"""

from django.contrib import admin
from django.urls import include, path
from . import views


urlpatterns = [

    path(
        'admin/',
        admin.site.urls
    ),

    path(
        '',
        views.HomeView.as_view(),
        name='home'
    ),

    path(
        'turma/',
        views.TurmaView.as_view(),
        name='turma'
    ),

    path(
        'professor/',
        views.AreaProfessorView.as_view(),
        name='area_professor'
    ),

    path(
        'alunos/',
        include('alunos.urls')
    ),

]