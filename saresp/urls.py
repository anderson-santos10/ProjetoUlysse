from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from accounts.views import (
    AreaAlunoView,
    AreaCoordenacaoView,
    AreaDirecaoView,
    LoginView,
    LogoutView,
)
from prova import views
from questoes.desempenho import (
    DesempenhoAlunoView,
    DesempenhoQuestaoView,
    DesempenhoQuestoesView,
    DesempenhoView,
)
from questoes.views_relatorio import (
    RelatorioAlunoView,
    RelatorioQuestoesView,
    RelatorioTurmaView,
)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.HomeView.as_view(), name="home"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("aluno/", AreaAlunoView.as_view(), name="area_aluno"),
    path("coordenacao/", AreaCoordenacaoView.as_view(), name="area_coordenacao"),
    path("direcao/", AreaDirecaoView.as_view(), name="area_direcao"),
    path("turma/", views.TurmaView.as_view(), name="turma"),
    path("professor/", LoginView.as_view(), name="acesso_professor"),
    path("professor/painel/", views.AreaProfessorView.as_view(), name="area_professor"),
    path("professor/sair/", LogoutView.as_view(), name="logout_professor"),
    path("alunos/", include("alunos.urls")),
    path("questoes/", include("questoes.urls")),
    path("desempenho/", DesempenhoView.as_view(), name="desempenho"),
    path(
        "desempenho/questoes/",
        DesempenhoQuestoesView.as_view(),
        name="desempenho_questoes",
    ),
    path(
        "desempenho/questoes/<int:pk>/",
        DesempenhoQuestaoView.as_view(),
        name="desempenho_questao",
    ),
    path(
        "desempenho/aluno/<int:pk>/",
        DesempenhoAlunoView.as_view(),
        name="desempenho_aluno",
    ),
    path(
        "desempenho/relatorios/aluno/<int:pk>/",
        RelatorioAlunoView.as_view(),
        name="relatorio_aluno",
    ),
    path(
        "desempenho/relatorios/turma/<int:pk>/",
        RelatorioTurmaView.as_view(),
        name="relatorio_turma",
    ),
    path(
        "desempenho/relatorios/questoes/",
        RelatorioQuestoesView.as_view(),
        name="relatorio_questoes",
    ),
]

handler403 = "accounts.views.permission_denied"

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
