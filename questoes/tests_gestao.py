from django.test import Client, TestCase
from django.urls import reverse

from accounts.catalog import create_user_with_group
from alunos.matriculas import matricular
from alunos.models import Aluno, Turma
from questoes.models import Questao, Resultado


class GestaoQuestoesEtapa7Tests(TestCase):

    def setUp(self):
        self.professor = create_user_with_group(
            "prof-q", "senha-teste-123", "professor"
        )
        self.coordenador = create_user_with_group(
            "coord-q", "senha-teste-123", "coordenador"
        )
        self.aluno_user = create_user_with_group(
            "aluno-q", "senha-teste-123", "aluno"
        )
        self.questao = Questao.objects.create(
            serie="5",
            dificuldade="facil",
            enunciado="Quanto é 2 + 2?",
            alternativa_a="1",
            alternativa_b="4",
            alternativa_c="3",
            alternativa_d="5",
            resposta_correta="B",
        )
        self.outra = Questao.objects.create(
            serie="6",
            dificuldade="dificil",
            enunciado="Capital do Brasil",
            alternativa_a="SP",
            alternativa_b="RJ",
            alternativa_c="Brasília",
            alternativa_d="BH",
            resposta_correta="C",
        )
        self.url_gestao = reverse("questoes:gestao")
        self.url_editar = reverse(
            "questoes:editar_questao",
            kwargs={"pk": self.questao.pk},
        )

    def test_anonimo_nao_acessa_gestao(self):
        response = self.client.get(self.url_gestao)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_aluno_nao_acessa_gestao(self):
        self.client.login(username="aluno-q", password="senha-teste-123")
        self.assertEqual(self.client.get(self.url_gestao).status_code, 403)
        self.assertEqual(self.client.get(self.url_editar).status_code, 403)

    def test_professor_lista_e_busca(self):
        self.client.login(username="prof-q", password="senha-teste-123")
        lista = self.client.get(self.url_gestao)
        self.assertEqual(lista.status_code, 200)
        self.assertContains(lista, "Quanto é 2 + 2?")
        self.assertNotContains(lista, "Editar")
        busca = self.client.get(self.url_gestao, {"q": "Capital"})
        self.assertContains(busca, "Capital do Brasil")
        self.assertNotContains(busca, "Quanto é 2 + 2?")
        numero = self.client.get(self.url_gestao, {"q": str(self.questao.numero)})
        self.assertContains(numero, "Quanto é 2 + 2?")
        serie = self.client.get(self.url_gestao, {"serie": "6"})
        self.assertContains(serie, "Capital do Brasil")
        self.assertNotContains(serie, "Quanto é 2 + 2?")
        dificil = self.client.get(self.url_gestao, {"dificuldade": "dificil"})
        self.assertContains(dificil, "Capital do Brasil")

    def test_professor_nao_edita_questao(self):
        self.client.login(username="prof-q", password="senha-teste-123")
        self.assertEqual(self.client.get(self.url_editar).status_code, 403)
        post = self.client.post(
            self.url_editar,
            {
                "serie": "5",
                "dificuldade": "facil",
                "enunciado": "Alterado",
                "alternativa_a": "1",
                "alternativa_b": "4",
                "alternativa_c": "3",
                "alternativa_d": "5",
                "resposta_correta": "B",
            },
        )
        self.assertEqual(post.status_code, 403)
        self.questao.refresh_from_db()
        self.assertEqual(self.questao.enunciado, "Quanto é 2 + 2?")

    def test_coordenador_edita_questao(self):
        self.client.login(username="coord-q", password="senha-teste-123")
        self.assertEqual(self.client.get(self.url_editar).status_code, 200)
        post = self.client.post(
            self.url_editar,
            {
                "serie": "5",
                "dificuldade": "medio",
                "enunciado": "Quanto é 3 + 1?",
                "alternativa_a": "1",
                "alternativa_b": "4",
                "alternativa_c": "3",
                "alternativa_d": "5",
                "resposta_correta": "B",
            },
        )
        self.assertEqual(post.status_code, 302)
        self.questao.refresh_from_db()
        self.assertEqual(self.questao.enunciado, "Quanto é 3 + 1?")
        self.assertEqual(self.questao.dificuldade, "medio")
        self.assertEqual(self.questao.numero, 1)
        self.assertEqual(self.questao.versoes.count(), 2)
        v1 = self.questao.versoes.get(versao=1)
        self.assertEqual(v1.enunciado, "Quanto é 2 + 2?")
        self.assertEqual(v1.dificuldade, "facil")
        self.assertEqual(self.questao.versao_atual.versao, 2)

    def test_csrf_na_edicao_de_questao(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.login(username="coord-q", password="senha-teste-123")
        response = csrf_client.post(
            self.url_editar,
            {
                "serie": "5",
                "dificuldade": "facil",
                "enunciado": "Sem token",
                "alternativa_a": "1",
                "alternativa_b": "4",
                "alternativa_c": "3",
                "alternativa_d": "5",
                "resposta_correta": "B",
            },
        )
        self.assertEqual(response.status_code, 403)


class ResultadosAdminEtapa7Tests(TestCase):

    def setUp(self):
        self.professor = create_user_with_group(
            "prof-r", "senha-teste-123", "professor"
        )
        self.aluno_user = create_user_with_group(
            "aluno-r", "senha-teste-123", "aluno"
        )
        self.aluno = Aluno.objects.create(
            nome="Lia Resultado",
            ra="RA-LIA-01",
            serie="5",
        )
        self.turma = Turma.objects.create(
            nome="R",
            serie="5",
            ano_letivo=2026,
            professor_responsavel=self.professor,
        )
        self.matricula = matricular(self.aluno, self.turma)
        self.resultado = Resultado.objects.create(
            aluno=self.aluno,
            acertos=8,
            erros=2,
            total_questoes=10,
            nota="8.00",
            xp_ganho=35,
            tempo_segundos=120,
            matricula=self.matricula,
        )
        self.url_lista = reverse("questoes:resultados")
        self.url_detalhe = reverse(
            "questoes:resultado_detalhe",
            kwargs={"pk": self.resultado.pk},
        )

    def test_anonimo_nao_acessa_resultados(self):
        self.assertEqual(self.client.get(self.url_lista).status_code, 302)
        self.assertEqual(self.client.get(self.url_detalhe).status_code, 302)

    def test_aluno_nao_acessa_resultados_admin(self):
        self.client.login(username="aluno-r", password="senha-teste-123")
        self.assertEqual(self.client.get(self.url_lista).status_code, 403)
        self.assertEqual(self.client.get(self.url_detalhe).status_code, 403)

    def test_professor_lista_e_detalha(self):
        self.client.login(username="prof-r", password="senha-teste-123")
        lista = self.client.get(self.url_lista)
        self.assertEqual(lista.status_code, 200)
        self.assertContains(lista, "Lia Resultado")
        self.assertNotContains(lista, "RA-LIA-01")
        detalhe = self.client.get(self.url_detalhe)
        self.assertEqual(detalhe.status_code, 200)
        self.assertContains(detalhe, "Lia Resultado")
        self.assertContains(detalhe, "8,00")
        self.assertContains(detalhe, "35")
        self.assertNotContains(detalhe, "RA-LIA-01")

    def test_filtros_de_resultado(self):
        outro = Aluno.objects.create(nome="Outro R", ra="RA-OUT-02", serie="6")
        turma6 = Turma.objects.create(
            nome="R6",
            serie="6",
            ano_letivo=2026,
            professor_responsavel=self.professor,
        )
        mat_outro = matricular(outro, turma6)
        Resultado.objects.create(
            aluno=outro,
            acertos=1,
            erros=0,
            total_questoes=1,
            nota="10.00",
            xp_ganho=10,
            tempo_segundos=10,
            matricula=mat_outro,
        )
        self.client.login(username="prof-r", password="senha-teste-123")
        por_aluno = self.client.get(self.url_lista, {"q": "Lia"})
        self.assertContains(por_aluno, "Lia Resultado")
        self.assertNotContains(por_aluno, "Outro R")
        por_serie = self.client.get(self.url_lista, {"serie": "6"})
        self.assertContains(por_serie, "Outro R")
        self.assertNotContains(por_serie, "Lia Resultado")
        por_nota = self.client.get(self.url_lista, {"nota": "8.00"})
        self.assertContains(por_nota, "Lia Resultado")
        self.assertNotContains(por_nota, "Outro R")

    def test_resultado_inexistente(self):
        self.client.login(username="prof-r", password="senha-teste-123")
        response = self.client.get(
            reverse("questoes:resultado_detalhe", kwargs={"pk": 999999})
        )
        self.assertEqual(response.status_code, 404)

    def test_lista_vazia(self):
        Resultado.objects.all().delete()
        self.client.login(username="prof-r", password="senha-teste-123")
        response = self.client.get(self.url_lista)
        self.assertContains(response, "Ainda não há resultados")
