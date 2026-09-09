from datetime import timedelta
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.catalog import create_user_with_group
from alunos.matriculas import matricular
from alunos.models import Aluno, Turma
from questoes.metrics import indicadores, taxa_percentual
from questoes.models import Resultado


class MetricasDesempenhoTests(TestCase):

    def test_taxa_ponderada_nao_e_media_das_porcentagens(self):
        self.assertEqual(
            taxa_percentual(14, 30),
            (Decimal("14") / Decimal("30")) * Decimal("100"),
        )
        a = Aluno.objects.create(nome="A", ra="TAXA01", serie="6")
        b = Aluno.objects.create(nome="B", ra="TAXA02", serie="6")
        Resultado.objects.create(
            aluno=a, acertos=9, erros=1, total_questoes=10,
            nota="9.00", xp_ganho=20, tempo_segundos=30,
        )
        Resultado.objects.create(
            aluno=b, acertos=5, erros=15, total_questoes=20,
            nota="2.50", xp_ganho=5, tempo_segundos=40,
        )
        dados = indicadores(Resultado.objects.all())
        self.assertEqual(dados["acertos"], 14)
        self.assertEqual(dados["questoes"], 30)
        self.assertEqual(dados["provas"], 2)
        self.assertEqual(dados["participantes"], 2)
        self.assertAlmostEqual(float(dados["taxa"]), 46.6666, places=2)
        media_simples = (90 + 25) / 2
        self.assertNotAlmostEqual(float(dados["taxa"]), media_simples, places=1)

    def test_sem_resultados_nao_divide_por_zero(self):
        dados = indicadores(Resultado.objects.none())
        self.assertFalse(dados["tem_dados"])
        self.assertIsNone(dados["taxa"])
        self.assertIsNone(dados["media"])
        self.assertEqual(dados["provas"], 0)


class DesempenhoAcessoTests(TestCase):

    def setUp(self):
        self.professor = create_user_with_group(
            "prof-d", "senha-teste-123", "professor"
        )
        self.coordenador = create_user_with_group(
            "coord-d", "senha-teste-123", "coordenador"
        )
        self.diretor = create_user_with_group(
            "dir-d", "senha-teste-123", "diretor"
        )
        self.aluno_user = create_user_with_group(
            "aluno-d", "senha-teste-123", "aluno"
        )
        self.aluno = Aluno.objects.create(
            nome="Dora Relatorio",
            ra="DES001",
            serie="6",
            xp=12,
        )
        self.turma = Turma.objects.create(
            nome="D",
            serie="6",
            ano_letivo=2026,
            professor_responsavel=self.professor,
        )
        matricular(self.aluno, self.turma)
        self.url = reverse("desempenho")
        self.url_aluno = reverse(
            "desempenho_aluno",
            kwargs={"pk": self.aluno.pk},
        )

    def test_anonimo_vai_para_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)
        response = self.client.get(self.url_aluno)
        self.assertEqual(response.status_code, 302)

    def test_aluno_recebe_403(self):
        self.client.login(username="aluno-d", password="senha-teste-123")
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.get(self.url_aluno).status_code, 403)

    def test_perfis_pedagogicos_acessam(self):
        for username in ("prof-d", "coord-d", "dir-d"):
            self.client.logout()
            self.client.login(username=username, password="senha-teste-123")
            self.assertEqual(self.client.get(self.url).status_code, 200, username)
            self.assertEqual(
                self.client.get(self.url_aluno).status_code, 200, username
            )

    def test_aluno_inexistente_404(self):
        self.client.login(username="prof-d", password="senha-teste-123")
        response = self.client.get(
            reverse("desempenho_aluno", kwargs={"pk": 999999})
        )
        self.assertEqual(response.status_code, 404)

    def test_serie_invalida_404(self):
        self.client.login(username="prof-d", password="senha-teste-123")
        response = self.client.get(self.url, {"serie": "99"})
        self.assertEqual(response.status_code, 404)


class DesempenhoFiltrosTests(TestCase):

    def setUp(self):
        self.professor = create_user_with_group(
            "prof-f", "senha-teste-123", "professor"
        )
        self.coordenador = create_user_with_group(
            "coord-f", "senha-teste-123", "coordenador"
        )
        self.aluno6 = Aluno.objects.create(nome="Seis", ra="F6", serie="6")
        self.aluno7 = Aluno.objects.create(nome="Sete", ra="F7", serie="7")
        agora = timezone.now()
        self.recente6 = Resultado.objects.create(
            aluno=self.aluno6, acertos=8, erros=2, total_questoes=10,
            nota="8.00", xp_ganho=15, tempo_segundos=20,
        )
        self.recente7 = Resultado.objects.create(
            aluno=self.aluno7, acertos=4, erros=6, total_questoes=10,
            nota="4.00", xp_ganho=5, tempo_segundos=25,
        )
        self.antigo = Resultado.objects.create(
            aluno=self.aluno6, acertos=10, erros=0, total_questoes=10,
            nota="10.00", xp_ganho=30, tempo_segundos=15,
        )
        Resultado.objects.filter(pk=self.antigo.pk).update(
            data=agora - timedelta(days=40)
        )
        self.url = reverse("desempenho")

    def test_periodo_30d_exclui_resultado_antigo(self):
        self.client.login(username="coord-f", password="senha-teste-123")
        response = self.client.get(self.url, {"periodo": "30d"})
        dados = response.context["indicadores"]
        self.assertEqual(dados["provas"], 2)
        self.assertEqual(dados["xp"], 20)

    def test_filtro_serie_nao_mistura(self):
        self.client.login(username="coord-f", password="senha-teste-123")
        response = self.client.get(
            self.url, {"periodo": "30d", "serie": "7"}
        )
        dados = response.context["indicadores"]
        self.assertEqual(dados["provas"], 1)
        self.assertEqual(dados["acertos"], 4)
        self.assertContains(response, "7º Ano")

    def test_hoje_nao_inclui_ontem(self):
        ontem = timezone.now() - timedelta(days=1)
        Resultado.objects.filter(pk=self.recente7.pk).update(data=ontem)
        self.client.login(username="coord-f", password="senha-teste-123")
        response = self.client.get(self.url, {"periodo": "hoje"})
        self.assertEqual(response.context["indicadores"]["provas"], 1)

    def test_periodo_sem_resultados(self):
        Resultado.objects.filter(pk=self.recente6.pk).update(
            data=timezone.now() - timedelta(days=2)
        )
        Resultado.objects.filter(pk=self.recente7.pk).update(
            data=timezone.now() - timedelta(days=2)
        )
        self.client.login(username="coord-f", password="senha-teste-123")
        response = self.client.get(self.url, {"periodo": "hoje"})
        self.assertFalse(response.context["indicadores"]["tem_dados"])
        self.assertContains(
            response,
            "Nenhum resultado encontrado para os filtros selecionados",
        )

    def test_dashboard_nao_explode_queries(self):
        self.client.login(username="coord-f", password="senha-teste-123")
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(self.url, {"periodo": "30d"})
        self.assertLessEqual(len(ctx.captured_queries), 40)


class DesempenhoAlunoHistoricoTests(TestCase):

    def setUp(self):
        self.professor = create_user_with_group(
            "prof-h", "senha-teste-123", "professor"
        )
        self.aluno = Aluno.objects.create(
            nome="Heloisa", ra="H001", serie="8", xp=0
        )
        self.turma = Turma.objects.create(
            nome="H",
            serie="8",
            ano_letivo=2026,
            professor_responsavel=self.professor,
        )
        self.matricula = matricular(self.aluno, self.turma)
        self.url = reverse("desempenho_aluno", kwargs={"pk": self.aluno.pk})

    def test_aluno_sem_resultados(self):
        self.client.login(username="prof-h", password="senha-teste-123")
        response = self.client.get(self.url)
        self.assertContains(response, "Ainda não há resultados para este aluno")
        self.assertNotContains(response, "Média")
        self.assertFalse(response.context["indicadores"]["tem_dados"])

    def test_historico_e_paginacao(self):
        for i in range(25):
            Resultado.objects.create(
                aluno=self.aluno,
                acertos=1,
                erros=0,
                total_questoes=1,
                nota="10.00",
                xp_ganho=10,
                tempo_segundos=8,
                matricula=self.matricula,
            )
        self.client.login(username="prof-h", password="senha-teste-123")
        page2 = self.client.get(self.url, {"page": "2"})
        self.assertEqual(page2.status_code, 200)
        self.assertEqual(len(page2.context["historico"]), 5)
        self.assertContains(page2, "page=1")
