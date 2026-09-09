from django.test import TestCase
from django.urls import reverse

from accounts.catalog import create_user_with_group
from alunos.models import Aluno


class RolesAccessTests(TestCase):

    password = "senha-teste-123"

    def setUp(self):
        self.aluno_user = create_user_with_group(
            "aluno1", self.password, "aluno"
        )
        self.professor = create_user_with_group(
            "professor1", self.password, "professor"
        )
        self.coordenador = create_user_with_group(
            "coord1", self.password, "coordenador"
        )
        self.diretor = create_user_with_group(
            "dir1", self.password, "diretor"
        )
        self.aluno = Aluno.objects.create(
            nome="Aluno Vinculado",
            ra="20269999",
            serie="5",
            user=self.aluno_user,
        )

    def test_anonimo_nao_acessa_areas_protegidas(self):
        for name in (
            "area_professor",
            "area_aluno",
            "area_coordenacao",
            "area_direcao",
            "alunos:lista_alunos",
            "alunos:cadastrar",
            "alunos:series",
            "alunos:lista_turmas",
            "questoes:cadastrar",
            "questoes:gestao",
            "questoes:resultados",
            "desempenho",
        ):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn("/login/", response.url)

    def test_login_unico_redireciona_por_perfil(self):
        casos = [
            ("aluno1", "area_aluno"),
            ("professor1", "area_professor"),
            ("coord1", "area_coordenacao"),
            ("dir1", "area_direcao"),
        ]
        for username, destino in casos:
            self.client.logout()
            response = self.client.post(
                reverse("login"),
                {"username": username, "senha": self.password},
            )
            self.assertEqual(response.status_code, 302, username)
            self.assertEqual(response.url, reverse(destino), username)

    def test_aluno_nao_acessa_area_administrativa(self):
        self.client.login(username="aluno1", password=self.password)
        for name in (
            "area_professor",
            "area_coordenacao",
            "area_direcao",
            "alunos:cadastrar",
            "alunos:lista_alunos",
            "questoes:cadastrar",
            "questoes:gestao",
            "questoes:resultados",
            "desempenho",
            "alunos:lista_turmas",
        ):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 403, name)

    def test_aluno_acessa_sua_area_e_nao_a_de_outro_via_sessao(self):
        outro = Aluno.objects.create(
            nome="Outro",
            ra="20268888",
            serie="6",
        )
        self.client.login(username="aluno1", password=self.password)
        session = self.client.session
        session["aluno_id"] = outro.id
        session.save()

        response = self.client.get(reverse("questoes:lista_questoes"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.client.session.get("aluno_id"),
            self.aluno.id,
        )

    def test_professor_nao_acessa_coordenacao_nem_direcao(self):
        self.client.login(username="professor1", password=self.password)
        self.assertEqual(
            self.client.get(reverse("area_professor")).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("area_coordenacao")).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse("area_direcao")).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse("alunos:cadastrar")).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("questoes:cadastrar")).status_code,
            200,
        )

    def test_coordenador_acessa_mais_que_professor(self):
        self.client.login(username="coord1", password=self.password)
        self.assertEqual(
            self.client.get(reverse("area_coordenacao")).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("area_professor")).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("area_direcao")).status_code,
            403,
        )
        self.assertTrue(
            self.coordenador.has_perm("alunos.change_aluno")
        )
        self.assertFalse(
            self.professor.has_perm("alunos.change_aluno")
        )

    def test_diretor_acessa_mais_que_coordenador(self):
        self.client.login(username="dir1", password=self.password)
        self.assertEqual(
            self.client.get(reverse("area_direcao")).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("area_coordenacao")).status_code,
            200,
        )
        self.assertTrue(self.diretor.has_perm("alunos.delete_aluno"))
        self.assertFalse(
            self.coordenador.has_perm("alunos.delete_aluno")
        )

    def test_alterar_url_ou_get_nao_eleva_permissao(self):
        self.client.login(username="aluno1", password=self.password)
        response = self.client.get(
            reverse("alunos:alunos_por_serie", kwargs={"serie": "5"}),
            {"id": self.aluno.id},
        )
        self.assertEqual(response.status_code, 403)

    def test_acesso_por_ra_continua_funcionando(self):
        self.client.logout()
        response = self.client.post(
            reverse("alunos:acesso_aluno"),
            {"ra": "20269999"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.client.session.get("aluno_id"),
            self.aluno.id,
        )
