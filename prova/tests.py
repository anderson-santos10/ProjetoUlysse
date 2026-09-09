from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse


from accounts.catalog import create_user_with_group


User = get_user_model()


class ProfessorAuthTests(TestCase):

    def setUp(self):
        self.password = "senha-teste-123"
        self.professor = create_user_with_group(
            "professor1",
            self.password,
            "professor",
        )
        self.aluno_user = User.objects.create_user(
            username="nao-professor",
            password=self.password,
            is_staff=False,
        )

    def test_anonimo_nao_acessa_painel(self):
        response = self.client.get(reverse("area_professor"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_usuario_autenticado_staff_acessa_painel(self):
        self.client.login(
            username="professor1",
            password=self.password,
        )
        response = self.client.get(reverse("area_professor"))
        self.assertEqual(response.status_code, 200)

    def test_usuario_sem_permissao_nao_acessa_painel(self):
        self.client.login(
            username="nao-professor",
            password=self.password,
        )
        response = self.client.get(reverse("area_professor"))
        self.assertEqual(response.status_code, 403)

    def test_login_com_usuario_e_senha_django(self):
        response = self.client.post(
            reverse("acesso_professor"),
            {
                "username": "professor1",
                "senha": self.password,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("area_professor"))

        painel = self.client.get(reverse("area_professor"))
        self.assertEqual(painel.status_code, 200)

    def test_logout_invalida_sessao(self):
        self.client.login(
            username="professor1",
            password=self.password,
        )
        session = self.client.session
        session["professor_autenticado"] = True
        session["aluno_id"] = 99
        session.save()

        response = self.client.post(reverse("logout_professor"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotIn("professor_autenticado", self.client.session)
        self.assertNotIn("aluno_id", self.client.session)

        painel = self.client.get(reverse("area_professor"))
        self.assertEqual(painel.status_code, 302)

    def test_logout_get_nao_invalida_sessao(self):
        self.client.login(
            username="professor1",
            password=self.password,
        )
        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_exige_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        response = csrf_client.post(
            reverse("login"),
            {"username": "professor1", "senha": self.password},
        )
        self.assertEqual(response.status_code, 403)

    def test_senha_nao_esta_hardcoded(self):
        views_source = (
            Path(settings.BASE_DIR) / "prova" / "views.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("UL824695", views_source)
        self.assertNotIn(
            'request.session["professor_autenticado"] = True',
            views_source,
        )

        templates_dir = Path(settings.BASE_DIR) / "templates"
        for path in templates_dir.glob("*.html"):
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("UL824695", content)
