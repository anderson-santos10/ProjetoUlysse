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