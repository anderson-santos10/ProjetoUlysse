from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from accounts.catalog import create_user_with_group
from alunos.matriculas import matricular
from alunos.models import Aluno, Turma
from questoes.metrics import metricas_questao, metricas_versoes_questao
from questoes.models import Questao, QuestaoVersao, RespostaResultado, Resultado


def _questao(**kwargs):
    dados = {
        "serie": "5",
        "dificuldade": "facil",
        "enunciado": "Enunciado original",
        "alternativa_a": "Alpha",
        "alternativa_b": "Beta",
        "alternativa_c": "Gama",
        "alternativa_d": "Delta",
        "resposta_correta": "B",
    }
    dados.update(kwargs)
    return Questao.objects.create(**dados)


class QuestaoVersaoModelTests(TestCase):

    def test_create_gera_versao_1(self):
        questao = _questao()
        self.assertEqual(questao.versoes.count(), 1)
        versao = questao.versao_atual
        self.assertEqual(versao.versao, 1)
        self.assertEqual(versao.enunciado, "Enunciado original")
        self.assertEqual(versao.resposta_correta, "B")
        self.assertEqual(versao.dificuldade, "facil")
        self.assertEqual(versao.serie, "5")
        self.assertEqual(versao.numero, questao.numero)
        self.assertEqual(questao.versao_atual.questao_id, questao.id)

    def test_unicidade_questao_versao(self):
        questao = _questao()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                QuestaoVersao.objects.create(
                    questao=questao,
                    versao=1,
                    numero=questao.numero,
                    serie=questao.serie,
                    dificuldade=questao.dificuldade,
                    enunciado="dup",
                    alternativa_a="A",
                    alternativa_b="B",
                    alternativa_c="C",
                    alternativa_d="D",
                    resposta_correta="A",
                )

    def test_versao_e_imutavel(self):
        questao = _questao()
        versao = questao.versao_atual
        versao.enunciado = "hack"
        with self.assertRaises(ValueError):
            versao.save()
        versao.refresh_from_db()
        self.assertEqual(versao.enunciado, "Enunciado original")


class EdicaoCriaVersaoTests(TestCase):

    def setUp(self):
        self.coordenador = create_user_with_group(
            "coord-v", "senha-teste-123", "coordenador"
        )
        self.questao = _questao()
        self.url = reverse(
            "questoes:editar_questao", kwargs={"pk": self.questao.pk}
        )

    def _post(self, **overrides):
        payload = {
            "serie": self.questao.serie,
            "dificuldade": self.questao.dificuldade,
            "enunciado": self.questao.enunciado,
            "alternativa_a": self.questao.alternativa_a,
            "alternativa_b": self.questao.alternativa_b,
            "alternativa_c": self.questao.alternativa_c,
            "alternativa_d": self.questao.alternativa_d,
            "resposta_correta": self.questao.resposta_correta,
        }
        payload.update(overrides)
        self.client.login(username="coord-v", password="senha-teste-123")
        return self.client.post(self.url, payload)

    def test_salvar_sem_mudanca_nao_cria_versao(self):
        self._post()
        self.assertEqual(self.questao.versoes.count(), 1)

    def test_editar_alternativa_cria_versao(self):
        self._post(alternativa_a="Alpha novo")
        self.assertEqual(self.questao.versoes.count(), 2)
        self.assertEqual(self.questao.versoes.get(versao=1).alternativa_a, "Alpha")

    def test_editar_varios_campos_cria_uma_versao(self):
        self._post(
            enunciado="Tudo novo",
            alternativa_b="Beta novo",
            resposta_correta="C",
            dificuldade="medio",
        )
        self.assertEqual(self.questao.versoes.count(), 2)

    def test_editar_enunciado_cria_versao(self):
        self._post(enunciado="Enunciado novo")
        self.assertEqual(self.questao.versoes.count(), 2)
        v1 = self.questao.versoes.get(versao=1)
        self.assertEqual(v1.enunciado, "Enunciado original")

    def test_editar_gabarito_cria_versao(self):
        self._post(resposta_correta="C")
        self.questao.refresh_from_db()
        self.assertEqual(self.questao.versao_atual.resposta_correta, "C")
        self.assertEqual(self.questao.versoes.get(versao=1).resposta_correta, "B")

    def test_editar_dificuldade_cria_versao(self):
        self._post(dificuldade="dificil")
        self.assertEqual(self.questao.versoes.get(versao=2).dificuldade, "dificil")
        self.assertEqual(self.questao.versoes.get(versao=1).dificuldade, "facil")

    def test_editar_serie_cria_versao(self):
        self._post(serie="6")
        self.questao.refresh_from_db()
        self.assertEqual(self.questao.serie, "6")
        self.assertEqual(self.questao.versoes.get(versao=1).serie, "5")
        self.assertEqual(self.questao.numero, 1)


class ProvaUsaVersaoHistoricaTests(TestCase):

    def setUp(self):
        self.professor = create_user_with_group(
            "prof-v", "senha-teste-123", "professor"
        )
        self.aluno = Aluno.objects.create(nome="Vera", ra="VER001", serie="5")
        self.turma = Turma.objects.create(
            nome="V",
            serie="5",
            ano_letivo=2026,
            professor_responsavel=self.professor,
        )
        matricular(self.aluno, self.turma)
        self.questao = _questao()
        self.url = reverse("questoes:lista_questoes")
        session = self.client.session
        session["aluno_id"] = self.aluno.id
        session.save()

    def test_prova_congela_versao_e_ignora_post_adulterado(self):
        self.client.post(self.url, {"acao": "novo_questionario"})
        v1_id = self.questao.versao_atual_id
        self.assertEqual(
            self.client.session.get("questoes_versoes"),
            {str(self.questao.id): v1_id},
        )

        criar_versao_atual = self.questao
        criar_versao_atual.enunciado = "Enunciado v2"
        criar_versao_atual.resposta_correta = "C"
        criar_versao_atual.save()
        self.questao.refresh_from_db()

        session = self.client.session
        session["respostas"] = {str(self.questao.id): "B"}
        session.save()
        self.client.post(
            self.url,
            {
                "acao": "finalizar",
                "questao_versao": str(self.questao.versao_atual_id),
                "correta": "false",
            },
        )

        item = RespostaResultado.objects.get()
        self.assertEqual(item.questao_versao_id, v1_id)
        self.assertEqual(item.resposta_correta, "B")
        self.assertTrue(item.correta)
        resultado = Resultado.objects.get()
        self.assertEqual(resultado.acertos, 1)

        self.client.login(username="prof-v", password="senha-teste-123")
        detalhe = self.client.get(
            reverse("questoes:resultado_detalhe", kwargs={"pk": resultado.pk})
        )
        self.assertContains(detalhe, "Enunciado original")
        self.assertContains(detalhe, "Gabarito daquela prova")
        self.assertContains(detalhe, "Acertou")
        self.assertNotContains(detalhe, "Enunciado v2")

    def test_sessao_nao_troca_versao_de_outra_questao(self):
        outra = _questao(enunciado="Outra", resposta_correta="A")
        self.client.post(self.url, {"acao": "novo_questionario"})
        session = self.client.session
        session["questoes_versoes"] = {
            str(self.questao.id): outra.versao_atual_id,
        }
        session["respostas"] = {str(self.questao.id): "B"}
        session.save()
        self.client.post(self.url, {"acao": "finalizar"})
        self.assertEqual(Resultado.objects.count(), 0)
        self.assertEqual(RespostaResultado.objects.count(), 0)


class AnalisePorVersaoTests(TestCase):

    def test_agrega_identidade_e_separa_versoes(self):
        aluno = Aluno.objects.create(nome="Ana V", ra="ANV01", serie="5")
        questao = _questao()
        v1 = questao.versao_atual
        r1 = Resultado.objects.create(
            aluno=aluno, acertos=1, erros=0, total_questoes=1,
            nota="10.00", xp_ganho=10, tempo_segundos=8,
        )
        RespostaResultado.objects.create(
            resultado=r1,
            questao=questao,
            questao_versao=v1,
            resposta="B",
            resposta_correta="B",
            correta=True,
        )
        questao.enunciado = "v2"
        questao.resposta_correta = "C"
        questao.save()
        v2 = questao.versao_atual
        r2 = Resultado.objects.create(
            aluno=aluno, acertos=0, erros=1, total_questoes=1,
            nota="0.00", xp_ganho=0, tempo_segundos=8,
        )
        RespostaResultado.objects.create(
            resultado=r2,
            questao=questao,
            questao_versao=v2,
            resposta="B",
            resposta_correta="C",
            correta=False,
        )
        geral = metricas_questao(questao, periodo="30d")
        self.assertEqual(geral["tentativas"], 2)
        self.assertEqual(geral["acertos"], 1)
        por_versao = metricas_versoes_questao(questao, periodo="30d")
        self.assertEqual(len(por_versao), 2)
        mapa = {item["versao"]: item for item in por_versao}
        self.assertEqual(mapa[1]["acertos"], 1)
        self.assertEqual(mapa[2]["acertos"], 0)
        self.assertEqual(mapa[1]["gabarito"], "B")
        self.assertEqual(mapa[2]["gabarito"], "C")
