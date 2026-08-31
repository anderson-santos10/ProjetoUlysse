from django.views.generic import TemplateView
from django.shortcuts import render, redirect

class HomeView(TemplateView):
    template_name = 'home.html'


class TurmaView(TemplateView):
    template_name = 'turma.html'


class AreaProfessorView(TemplateView):
    template_name = 'area_professor.html'

class AcessoProfessorView(TemplateView):
    template_name = "acesso_professor.html"

    def post(self, request, *args, **kwargs):
        senha = request.POST.get("senha")

        if senha == "UL824695.":
            request.session["professor_autenticado"] = True
            return redirect("area_professor")

        return render(
            request,
            self.template_name,
            {
                "erro": "Senha incorreta. Tente novamente."
            }
        )