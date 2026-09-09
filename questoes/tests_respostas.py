from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.catalog import create_user_with_group
from alunos.matriculas import matricular
from alunos.models import Aluno, Turma
from questoes.metrics import (
    MIN_TENTATIVAS_OBSERVADA,
    metricas_por_questao,
    metricas_questao,
)
from questoes.models import Questao, RespostaResultado, Resultado
from questoes.persistencia import persistir_respostas_resultado


def _questao(serie, correta="A", dificuldade="facil", enunciado="Pergunta"):
    return Questao.objects.create(
        serie=serie,
        dificuldade=dificuldade,
        enunciado=enunciado,
        alternativa_a="São Paulo",
        alternativa_b="Rio",
        alternativa_c="Brasília",
        alternativa_d="Recife",
        resposta_correta=correta,
    )


def _resultado(aluno, acertos=1, erros=0, total=1, nota="10.00", matricula=None):
    return Resultado.objects.create(
        aluno=aluno,
        acertos=acertos,
        erros=erros,
        total_questoes=total,
        nota=nota,
        xp_ganho=10,
        tempo_segundos=12,
        matricula=matricula,
    )


def _resposta(resultado, questao, letra):
    return RespostaResultado.objects.create(
        resultado=resultado,
        questao=questao,
        resposta=letra,
        resposta_correta=questao.resposta_correta,
        correta=bool(letra is not None and letra == questao.resposta_correta),
    )


class RespostaResultadoModelTests(TestCase):

    def setUp(self):
        self.aluno = Aluno.objects.create(nome="M", ra="RR01", serie="6")
        self.questao = _questao("6")
        self.resultado = _resultado(self.aluno)

    def test_cria_com_fk_e_letras(self):
        item = _resposta(self.resultado, self.questao, "A")
        self.assertEqual(item.resultado_id, self.resultado.id)
        self.assertEqual(item.questao_id, self.questao.id)
        self.assertTrue(item.correta)
        self.assertEqual(self.resultado.respostas_questoes.count(), 1)

    def test_unique_resultado_questao(self):
        _resposta(self.resultado, self.questao, "A")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _resposta(self.resultado, self.questao, "B")

    def test_cascade_do_resultado(self):
        _resposta(self.resultado, self.questao, "A")
        self.resultado.delete()
        self.assertEqual(RespostaResultado.objects.count(), 0)
        self.assertTrue(Questao.objects.filter(pk=self.questao.pk).exists())

    def test_protect_da_questao(self):
        _resposta(self.resultado, self.questao, "A")
        with self.assertRaises(ProtectedError):
            self.questao.delete()
        self.assertEqual(RespostaResultado.objects.count(), 1)


class PersistenciaFinalizacaoTests(TestCase):

    def setUp(self):
        self.aluno = Aluno.objects.create(nome="Prova", ra="RR02", serie="5")
        self.q1 = _questao("5", "A", enunciado="Q1")
        self.q2 = _questao("5", "C", enunciado="Q2")
        self.url = reverse("questoes:lista_questoes")

    def _sessao(self):
        session = self.client.session
        session["aluno_id"] = self.aluno.id
        session.save()

    def _iniciar(self):
        self._sessao()
        self.client.post(self.url, {"acao": "novo_questionario"})

    def test_finalizar_persiste_acerto_erro_e_em_branco(self):
        self._iniciar()
        session = self.client.session
        session["respostas"] = {str(self.q1.id): "A"}
        session.save()
        self.client.post(self.url, {"acao": "finalizar"})

        resultado = Resultado.objects.get(aluno=self.aluno)
        respostas = list(
            RespostaResultado.objects.filter(resultado=resultado).order_by("questao_id")
        )
        self.assertEqual(len(respostas), 2)
        self.assertEqual(resultado.total_questoes, 2)
        mapa = {item.questao_id: item for item in respostas}
        self.assertTrue(mapa[self.q1.id].correta)
        self.assertEqual(mapa[self.q1.id].resposta, "A")
        self.assertIsNone(mapa[self.q2.id].resposta)
        self.assertFalse(mapa[self.q2.id].correta)
        self.assertEqual(resultado.acertos, 1)
        self.assertEqual(resultado.erros, 1)
        self.assertEqual(
            resultado.acertos,
            RespostaResultado.objects.filter(resultado=resultado, correta=True).count(),
        )
        self.assertEqual(
            resultado.erros,
            RespostaResultado.objects.filter(resultado=resultado, correta=False).count(),
        )

    def test_ignora_questao_fora_da_ordem_e_letra_invalida(self):
        outra = _questao("6", "B", enunciado="outra serie")
        self._iniciar()
        session = self.client.session
        session["respostas"] = {
            str(self.q1.id): "Z",
            str(self.q2.id): "C",
            str(outra.id): "B",
            "999": "A",
        }
        session.save()
        self.client.post(
            self.url,
            {"acao": "finalizar", "correta": "true", "questao_id": str(outra.id)},
        )
        ids = set(
            RespostaResultado.objects.values_list("questao_id", flat=True)
        )
        self.assertEqual(ids, {self.q1.id, self.q2.id})
        q1 = RespostaResultado.objects.get(questao=self.q1)
        self.assertIsNone(q1.resposta)
        self.assertFalse(q1.correta)
        q2 = RespostaResultado.objects.get(questao=self.q2)
        self.assertEqual(q2.resposta, "C")
        self.assertTrue(q2.correta)

    def test_responder_nao_aceita_letra_invalida(self):
        self._iniciar()
        self.client.post(self.url, {"acao": "responder", "resposta": "Z"})
        self.assertEqual(self.client.session.get("respostas"), {})

    def test_transacao_desfaz_resultado_se_respostas_falham(self):
        self._iniciar()
        session = self.client.session
        session["respostas"] = {str(self.q1.id): "A", str(self.q2.id): "C"}
        session.save()
        with patch(
            "questoes.persistencia.RespostaResultado.objects.bulk_create",
            side_effect=RuntimeError("falha"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url, {"acao": "finalizar"})
        self.assertEqual(Resultado.objects.count(), 0)
        self.assertEqual(RespostaResultado.objects.count(), 0)
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.xp, 0)

    def test_letras_sao_originais_nao_visuais(self):
        resultado = _resultado(self.aluno, acertos=1, erros=0, total=1, nota="10.00")
        persistir_respostas_resultado(
            resultado,
            [self.q1],
            {str(self.q1.id): "A"},
            {self.q1.id: self.q1.versao_atual},
        )
        item = RespostaResultado.objects.get()
        self.assertEqual(item.resposta, "A")
        self.assertEqual(item.resposta_correta, "A")
        self.assertEqual(item.questao_versao_id, self.q1.versao_atual_id)


class MetricasQuestaoTests(TestCase):

    def setUp(self):
        self.aluno = Aluno.objects.create(nome="Ana", ra="RR03", serie="6")
        self.q1 = _questao("6", "A", enunciado="facil observada")
        self.q2 = _questao("6", "A", enunciado="dificil observada")
        self.q7 = _questao("7", "B", enunciado="outra serie")

    def _n_respostas(self, questao, acertos, erros, aluno=None):
        aluno = aluno or self.aluno
        for _ in range(acertos):
            resultado = _resultado(aluno, acertos=1, erros=0, total=1, nota="10.00")
            _resposta(resultado, questao, questao.resposta_correta)
        letra_errada = "D" if questao.resposta_correta != "D" else "C"
        for _ in range(erros):
            resultado = _resultado(aluno, acertos=0, erros=1, total=1, nota="0.00")
            _resposta(resultado, questao, letra_errada)

    def test_taxa_80_e_30_e_ordem_de_dificuldade(self):
        self._n_respostas(self.q1, 8, 2)
        self._n_respostas(self.q2, 9, 21)
        analise = metricas_por_questao(periodo="30d", serie="6")
        self.assertEqual(analise["linhas"][0]["questao"].id, self.q2.id)
        self.assertEqual(analise["linhas"][1]["questao"].id, self.q1.id)
        self.assertEqual(analise["linhas"][0]["tentativas"], 30)
        self.assertEqual(analise["linhas"][0]["acertos"], 9)
        self.assertEqual(analise["linhas"][0]["erros"], 21)
        self.assertEqual(analise["linhas"][0]["taxa"], Decimal("30"))
        self.assertEqual(analise["linhas"][1]["taxa"], Decimal("80"))
        self.assertEqual(analise["com_amostra"][0]["questao"].id, self.q2.id)

    def test_filtro_serie_nao_mistura(self):
        self._n_respostas(self.q1, 2, 0)
        self._n_respostas(self.q7, 1, 0)
        so6 = metricas_por_questao(periodo="30d", serie="6")
        ids = [item["questao"].id for item in so6["linhas"] if item["tem_dados"]]
        self.assertEqual(ids, [self.q1.id])

    def test_periodo_hoje_7d_30d_mes(self):
        agora = timezone.now()
        recente = _resultado(self.aluno)
        _resposta(recente, self.q1, "A")
        d8 = _resultado(self.aluno)
        _resposta(d8, self.q1, "A")
        Resultado.objects.filter(pk=d8.pk).update(data=agora - timedelta(days=8))
        d31 = _resultado(self.aluno)
        _resposta(d31, self.q1, "A")
        Resultado.objects.filter(pk=d31.pk).update(data=agora - timedelta(days=31))

        self.assertEqual(
            metricas_questao(self.q1, periodo="hoje")["tentativas"], 1
        )
        self.assertEqual(
            metricas_questao(self.q1, periodo="7d")["tentativas"], 1
        )
        self.assertEqual(
            metricas_questao(self.q1, periodo="30d")["tentativas"], 2
        )
        mes = metricas_questao(self.q1, periodo="mes")["tentativas"]
        self.assertGreaterEqual(mes, 1)

    def test_sem_tentativas_nao_e_zero_porcento(self):
        linha = metricas_questao(self.q1, periodo="30d")
        self.assertEqual(linha["tentativas"], 0)
        self.assertIsNone(linha["taxa"])
        self.assertFalse(linha["tem_dados"])

    def test_uma_tentativa_nao_domina_dificuldade(self):
        self._n_respostas(self.q1, 1, 4)
        isolada = _questao("6", "A", enunciado="uma tentativa")
        self._n_respostas(isolada, 0, 1)
        analise = metricas_por_questao(periodo="30d", serie="6")
        self.assertEqual(analise["min_tentativas"], MIN_TENTATIVAS_OBSERVADA)
        ids_amostra = [item["questao"].id for item in analise["com_amostra"]]
        self.assertIn(self.q1.id, ids_amostra)
        self.assertNotIn(isolada.id, ids_amostra)
        self.assertEqual(analise["com_amostra"][0]["questao"].id, self.q1.id)

    def test_resultado_antigo_sem_respostas_nao_entra_na_taxa(self):
        _resultado(self.aluno, acertos=10, erros=0, total=10, nota="10.00")
        analise = metricas_por_questao(periodo="30d")
        self.assertFalse(analise["tem_dados_persistidos"])


class DesempenhoQuestaoViewsTests(TestCase):

    def setUp(self):
        self.professor = create_user_with_group(
            "prof-q", "senha-teste-123", "professor"
        )
        self.aluno_user = create_user_with_group(
            "aluno-q", "senha-teste-123", "aluno"
        )
        self.aluno = Aluno.objects.create(nome="Bia", ra="RR04", serie="6")
        self.turma = Turma.objects.create(
            nome="Q",
            serie="6",
            ano_letivo=2026,
            professor_responsavel=self.professor,
        )
        self.matricula = matricular(self.aluno, self.turma)
        self.questao = _questao("6")
        self.url = reverse("desempenho_questoes")
        self.url_detalhe = reverse(
            "desempenho_questao", kwargs={"pk": self.questao.pk}
        )

    def test_anonimo_login_aluno_403(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.client.get(self.url_detalhe).status_code, 302)
        self.client.login(username="aluno-q", password="senha-teste-123")
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.get(self.url_detalhe).status_code, 403)

    def test_professor_200_e_404(self):
        self.client.login(username="prof-q", password="senha-teste-123")
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertContains(
            self.client.get(self.url),
            "Ainda não há dados suficientes para análise por questão",
        )
        self.assertEqual(self.client.get(self.url_detalhe).status_code, 200)
        self.assertEqual(
            self.client.get(
                reverse("desempenho_questao", kwargs={"pk": 999999})
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(self.url, {"serie": "99"}).status_code,
            404,
        )

    def test_pagina_nao_expoe_ra_e_agrega(self):
        resultado = _resultado(self.aluno, matricula=self.matricula)
        _resposta(resultado, self.questao, "A")
        self.client.login(username="prof-q", password="senha-teste-123")
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(self.url, {"periodo": "30d", "serie": "6"})
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(ctx.captured_queries), 20)
        self.assertContains(response, "Questão #")
        self.assertNotContains(response, "RR04")
        self.assertContains(response, "Poucos dados")
        detalhe = self.client.get(self.url_detalhe)
        self.assertContains(detalhe, "Distribuição das respostas")
        self.assertNotContains(detalhe, "RR04")

    def test_resultado_antigo_e_novo_nas_telas(self):
        antigo = _resultado(self.aluno, acertos=1, erros=0, total=1, nota="10.00", matricula=self.matricula)
        novo = _resultado(self.aluno, acertos=1, erros=0, total=1, nota="10.00", matricula=self.matricula)
        _resposta(novo, self.questao, "A")
        self.client.login(username="prof-q", password="senha-teste-123")
        historico = self.client.get(
            reverse("desempenho_aluno", kwargs={"pk": self.aluno.pk})
        )
        self.assertContains(
            historico,
            "Este resultado foi registrado antes da coleta detalhada por questão",
        )
        self.assertContains(historico, "Acertou")
        velho = self.client.get(
            reverse("questoes:resultado_detalhe", kwargs={"pk": antigo.pk})
        )
        self.assertContains(
            velho,
            "Este resultado foi registrado antes da coleta detalhada por questão",
        )
        fresco = self.client.get(
            reverse("questoes:resultado_detalhe", kwargs={"pk": novo.pk})
        )
        self.assertContains(fresco, "Desempenho por questão")
        self.assertContains(fresco, "Acertou")
        self.assertNotContains(
            fresco,
            "Este resultado foi registrado antes da coleta detalhada por questão",
        )
