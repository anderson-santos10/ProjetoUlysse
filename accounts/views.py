from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.views import View
from django.views.generic import TemplateView

from .catalog import (
    PERM_AREA_ALUNO,
    PERM_AREA_COORDENACAO,
    PERM_AREA_DIRECAO,
    post_login_url_name,
)
from .mixins import PermissionRequiredMixin


def _bind_aluno_session(request, user):
    from alunos.session import bind_linked_aluno_session

    bind_linked_aluno_session(request)


class LoginView(View):
    template_name = "login.html"

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(post_login_url_name(request.user))
        return render(request, self.template_name)

    def post(self, request, *args, **kwargs):
        username = request.POST.get("username", "").strip()
        password = request.POST.get("senha") or request.POST.get("password") or ""

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is None:
            return render(
                request,
                self.template_name,
                {"erro": "Usuário ou senha inválidos. Tente novamente."},
            )

        login(request, user)
        request.session.pop("professor_autenticado", None)
        _bind_aluno_session(request, user)
        return redirect(post_login_url_name(user))


class LogoutView(View):
    def post(self, request, *args, **kwargs):
        logout(request)
        return redirect("home")


class AreaAlunoView(PermissionRequiredMixin, TemplateView):
    permission_required = PERM_AREA_ALUNO
    template_name = "area_aluno.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from alunos.models import Aluno

        context["aluno"] = Aluno.objects.filter(
            user=self.request.user
        ).first()
        return context


class AreaCoordenacaoView(PermissionRequiredMixin, TemplateView):
    permission_required = PERM_AREA_COORDENACAO
    template_name = "area_coordenacao.html"


class AreaDirecaoView(PermissionRequiredMixin, TemplateView):
    permission_required = PERM_AREA_DIRECAO
    template_name = "area_direcao.html"


def permission_denied(request, exception=None):
    return render(request, "403.html", status=403)
