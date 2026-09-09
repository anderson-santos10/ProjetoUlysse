from datetime import timedelta
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.catalog import create_user_with_group
from alunos.matriculas import matricular
from alunos.models import Aluno, Turma
from questoes.avaliacoes import publicar
from questoes.models import Avaliacao, AvaliacaoQuestao, Questao, Resultado


def _png():
    buffer = BytesIO()
    Image.new("RGB", (8, 8), color="red").save(buffer, format="PNG")
    return SimpleUploadedFile("q.png", buffer.getvalue(), content_type="image/png")


def _questao(serie="6", enunciado="Quanto é 1+1?", correta="B"):
    return Questao.objects.create(
        serie=serie,
        dificuldade="facil",
        enunciado=enunciado,
        alternativa_a="1",
        alternativa_b="2",
        alternativa_c="3",
        alternativa_d="4",
        resposta_correta=correta,
    )


class IsolamentoPedagogicoTests(TestCase):
    password = "senha-teste-123"

    def setUp(self):
        self.prof_a = create_user_with_group("pa15", self.password, "professor")
        self.prof_b = create_user_with_group("pb15", self.password, "professor")
        self.coord = create_user_with_group("co15", self.password, "coordenador")
        self.turma_a = Turma.objects.create(
            nome="A15", serie="6", ano_letivo=2026, professor_responsavel=self.prof_a
        )
        self.turma_b = Turma.objects.create(
            nome="B15", serie="6", ano_letivo=2026, professor_responsavel=self.prof_b
        )
        self.aluno_a = Aluno.objects.create(nome="Ana Escopo", ra="ESC15A", serie="6")
        self.aluno_b = Aluno.objects.create(nome="Beto Escopo", ra="ESC15B", serie="6")
        self.mat_a = matricular(self.aluno_a, self.turma_a)
        self.mat_b = matricular(self.aluno_b, self.turma_b)
        self.res_a = Resultado.objects.create(
            aluno=self.aluno_a,
            acertos=1,
            erros=0,
            total_questoes=1,
            nota="10.00",
            xp_ganho=10,
            tempo_segundos=8,
            matricula=self.mat_a,
        )
        self.res_b = Resultado.objects.create(
            aluno=self.aluno_b,
            acertos=1,
            erros=0,
            total_questoes=1,
            nota="10.00",
            xp_ganho=10,
            tempo_segundos=8,
            matricula=self.mat_b,
        )

    def test_professor_nao_ve_aluno_nem_resultado_de_outra_turma(self):
        self.client.login(username="pa15", password=self.password)
        lista = self.client.get(reverse("alunos:lista_alunos"))
        self.assertContains(lista, "Ana Escopo")
        self.assertNotContains(lista, "Beto Escopo")
        self.assertEqual(
            self.client.get(
                reverse("desempenho_aluno", kwargs={"pk": self.aluno_b.pk})
            ).status_code,
            404,
        )
        resultados = self.client.get(reverse("questoes:resultados"))
        self.assertContains(resultados, "Ana Escopo")
        self.assertNotContains(resultados, "Beto Escopo")
        self.assertEqual(
            self.client.get(
                reverse("questoes:resultado_detalhe", kwargs={"pk": self.res_b.pk})
            ).status_code,
            404,
        )

    def test_coordenador_ve_ambos(self):
        self.client.login(username="co15", password=self.password)
        lista = self.client.get(reverse("alunos:lista_alunos"))
        self.assertContains(lista, "Ana Escopo")
        self.assertContains(lista, "Beto Escopo")

    def test_dashboard_respeita_escopo(self):
        self.client.login(username="pa15", password=self.password)
        dados = self.client.get(
            reverse("desempenho"), {"periodo": "todos"}
        ).context["indicadores"]
        self.assertEqual(dados["provas"], 1)
        self.assertEqual(dados["participantes"], 1)


class RelatorioPedagogicoTests(TestCase):
    password = "senha-teste-123"

    def setUp(self):
        self.professor = create_user_with_group("pr15", self.password, "professor")
        self.aluno_user = create_user_with_group("al15", self.password, "aluno")
        self.turma = Turma.objects.create(
            nome="R15", serie="6", ano_letivo=2026, professor_responsavel=self.professor
        )
        self.aluno = Aluno.objects.create(nome="Lia Rel", ra="REL15", serie="6")
        matricular(self.aluno, self.turma)

    def test_aluno_nao_acessa_relatorio(self):
        self.client.login(username="al15", password=self.password)
        self.assertEqual(
            self.client.get(
                reverse("relatorio_aluno", kwargs={"pk": self.aluno.pk})
            ).status_code,
            403,
        )

    def test_professor_relatorios_200(self):
        self.client.login(username="pr15", password=self.password)
        self.assertEqual(
            self.client.get(
                reverse("relatorio_aluno", kwargs={"pk": self.aluno.pk})
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse("relatorio_turma", kwargs={"pk": self.turma.pk})
            ).status_code,
            200,
        )
        self.assertContains(
            self.client.get(reverse("relatorio_questoes")),
            "Relatório de questões",
        )


class AvaliacaoFluxoTests(TestCase):
    password = "senha-teste-123"

    def setUp(self):
        self.professor = create_user_with_group("av15", self.password, "professor")
        self.outro = create_user_with_group("av15b", self.password, "professor")
        self.turma = Turma.objects.create(
            nome="AV", serie="6", ano_letivo=2026, professor_responsavel=self.professor
        )
        self.turma_outra = Turma.objects.create(
            nome="AX", serie="6", ano_letivo=2026, professor_responsavel=self.outro
        )
        self.aluno = Aluno.objects.create(nome="Aluno Av", ra="AVRA15", serie="6")
        matricular(self.aluno, self.turma)
        self.questao = _questao()
        self.v1 = self.questao.versao_atual

    def _login_prof(self):
        self.client.login(username="av15", password=self.password)

    def _sessao_aluno(self):
        session = self.client.session
        session["aluno_id"] = self.aluno.pk
        session.save()

    def test_criar_recusar_turma_alheia_e_publicar(self):
        self._login_prof()
        criar = self.client.post(
            reverse("questoes:cadastrar_avaliacao"),
            {
                "titulo": "Simulado 6A",
                "descricao": "",
                "turma": self.turma_outra.pk,
                "tentativas_maximas": 1,
                "questoes": [self.questao.pk],
            },
        )
        self.assertEqual(criar.status_code, 200)
        self.assertFalse(Avaliacao.objects.exists())

        ok = self.client.post(
            reverse("questoes:cadastrar_avaliacao"),
            {
                "titulo": "Simulado 6A",
                "descricao": "",
                "turma": self.turma.pk,
                "tentativas_maximas": 1,
                "questoes": [self.questao.pk],
            },
        )
        self.assertEqual(ok.status_code, 302)
        avaliacao = Avaliacao.objects.get()
        self.assertEqual(avaliacao.status, Avaliacao.Status.RASCUNHO)
        pub = self.client.post(
            reverse("questoes:publicar_avaliacao", kwargs={"pk": avaliacao.pk})
        )
        self.assertEqual(pub.status_code, 302)
        avaliacao.refresh_from_db()
        self.assertEqual(avaliacao.status, Avaliacao.Status.PUBLICADA)
        item = avaliacao.itens.get()
        self.assertEqual(item.questao_versao_id, self.v1.pk)

    def test_congelamento_sobrevive_edicao_e_imagem(self):
        self.questao.imagem = _png()
        self.questao.imagem_alt = "figura v1"
        self.questao.save()
        self.v1 = self.questao.versao_atual
        avaliacao = Avaliacao.objects.create(
            titulo="Congela",
            turma=self.turma,
            serie="6",
            criado_por=self.professor,
            tentativas_maximas=1,
        )
        AvaliacaoQuestao.objects.create(
            avaliacao=avaliacao, questao=self.questao, ordem=1
        )
        publicar(avaliacao)
        self.questao.enunciado = "Enunciado v2"
        self.questao.imagem = _png()
        self.questao.imagem_alt = "figura v2"
        self.questao.save()
        self.questao.refresh_from_db()
        self.assertNotEqual(self.questao.versao_atual_id, self.v1.pk)
        item = avaliacao.itens.get()
        self.assertEqual(item.questao_versao_id, self.v1.pk)
        self.assertEqual(item.questao_versao.enunciado, "Quanto é 1+1?")
        self.assertEqual(item.questao_versao.imagem_alt, "figura v1")

        self._sessao_aluno()
        self.client.post(
            reverse("questoes:aluno_avaliacao", kwargs={"pk": avaliacao.pk}),
            {"acao": "iniciar"},
        )
        pagina = self.client.get(
            reverse("questoes:aluno_avaliacao", kwargs={"pk": avaliacao.pk})
        )
        self.assertContains(pagina, "Quanto é 1+1?")
        self.assertNotContains(pagina, "Enunciado v2")
        self.client.post(
            reverse("questoes:aluno_avaliacao", kwargs={"pk": avaliacao.pk}),
            {
                "acao": "finalizar",
                "aluno_id": "999999",
                f"q_{self.questao.pk}": "B",
            },
        )
        resultado = Resultado.objects.get(avaliacao=avaliacao)
        self.assertEqual(resultado.aluno_id, self.aluno.pk)
        resp = resultado.respostas_questoes.get()
        self.assertEqual(resp.questao_versao_id, self.v1.pk)

    def test_aluno_outra_turma_nao_inicia(self):
        outro_aluno = Aluno.objects.create(nome="Fora", ra="FORA15", serie="6")
        matricular(outro_aluno, self.turma_outra)
        avaliacao = Avaliacao.objects.create(
            titulo="So A",
            turma=self.turma,
            serie="6",
            criado_por=self.professor,
            status=Avaliacao.Status.PUBLICADA,
            tentativas_maximas=1,
        )
        AvaliacaoQuestao.objects.create(
            avaliacao=avaliacao,
            questao=self.questao,
            questao_versao=self.v1,
            ordem=1,
        )
        session = self.client.session
        session["aluno_id"] = outro_aluno.pk
        session.save()
        self.client.post(
            reverse("questoes:aluno_avaliacao", kwargs={"pk": avaliacao.pk}),
            {"acao": "iniciar"},
        )
        self.assertIsNone(self.client.session.get("avaliacao_id"))
        self.assertEqual(Resultado.objects.filter(avaliacao=avaliacao).count(), 0)

    def test_tentativa_maxima_e_tempo_servidor(self):
        avaliacao = Avaliacao.objects.create(
            titulo="Uma",
            turma=self.turma,
            serie="6",
            criado_por=self.professor,
            status=Avaliacao.Status.PUBLICADA,
            tentativas_maximas=1,
            tempo_limite_minutos=1,
        )
        AvaliacaoQuestao.objects.create(
            avaliacao=avaliacao,
            questao=self.questao,
            questao_versao=self.v1,
            ordem=1,
        )
        self._sessao_aluno()
        self.client.post(
            reverse("questoes:aluno_avaliacao", kwargs={"pk": avaliacao.pk}),
            {"acao": "iniciar"},
        )
        session = self.client.session
        session["avaliacao_inicio"] = (
            timezone.now() - timedelta(minutes=5)
        ).isoformat()
        session.save()
        self.client.post(
            reverse("questoes:aluno_avaliacao", kwargs={"pk": avaliacao.pk}),
            {"acao": "finalizar", f"q_{self.questao.pk}": "B"},
        )
        resultado = Resultado.objects.get(avaliacao=avaliacao)
        self.assertLessEqual(resultado.tempo_segundos, 60)
        self._sessao_aluno()
        self.client.post(
            reverse("questoes:aluno_avaliacao", kwargs={"pk": avaliacao.pk}),
            {"acao": "iniciar"},
        )
        self.assertEqual(Resultado.objects.filter(avaliacao=avaliacao).count(), 1)

    def test_professor_b_nao_acessa_avaliacao_a(self):
        avaliacao = Avaliacao.objects.create(
            titulo="Privada",
            turma=self.turma,
            serie="6",
            criado_por=self.professor,
            tentativas_maximas=1,
        )
        self.client.login(username="av15b", password=self.password)
        self.assertEqual(
            self.client.get(
                reverse("questoes:detalhe_avaliacao", kwargs={"pk": avaliacao.pk})
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("questoes:publicar_avaliacao", kwargs={"pk": avaliacao.pk})
            ).status_code,
            403,
        )
