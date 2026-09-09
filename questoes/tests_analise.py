from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from accounts.catalog import create_user_with_group
from alunos.matriculas import matricular
from alunos.models import Aluno, Turma
from questoes.metrics import (
    desempenho_por_dificuldade,
    metricas_por_questao,
    metricas_questao,
    metricas_versoes_questao,
)
from questoes.models import Questao, RespostaResultado, Resultado


def _questao(serie="6", correta="A", dificuldade="facil", enunciado="Pergunta"):
    return Questao.objects.create(
        serie=serie,
        dificuldade=dificuldade,
        enunciado=enunciado,
        alternativa_a="A1",
        alternativa_b="B1",
        alternativa_c="C1",
        alternativa_d="D1",
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


def _resposta(resultado, questao, letra, versao=None, gabarito=None, correta=None):
    gabarito = gabarito if gabarito is not None else questao.resposta_correta
    if correta is None:
        correta = bool(letra is not None and letra == gabarito)
    return RespostaResultado.objects.create(
        resultado=resultado,
        questao=questao,
        questao_versao=versao if versao is not None else questao.versao_atual,
        resposta=letra,
        resposta_correta=gabarito,
        correta=correta,
    )


class MetricasAnalisePedagogicaTests(TestCase):

    def setUp(self):
        self.aluno = Aluno.objects.create(nome="Ana", ra="AN12", serie="6")
        self.questao = _questao()

    def test_zero_tentativas(self):
        linha = metricas_questao(self.questao)
        self.assertEqual(linha["tentativas"], 0)
        self.assertEqual(linha["acertos"], 0)
        self.assertEqual(linha["erros"], 0)
        self.assertIsNone(linha["taxa"])
        self.assertFalse(linha["revisar"])

    def test_uma_correta_e_uma_errada(self):
        _resposta(_resultado(self.aluno), self.questao, "A")
        _resposta(_resultado(self.aluno, acertos=0, erros=1, nota="0.00"), self.questao, "B")
        linha = metricas_questao(self.questao)
        self.assertEqual(linha["tentativas"], 2)
        self.assertEqual(linha["acertos"], 1)
        self.assertEqual(linha["erros"], 1)
        self.assertEqual(linha["taxa"], Decimal("50"))
        self.assertEqual(linha["taxa_erro"], Decimal("50"))

    def test_taxa_0_e_100(self):
        _resposta(_resultado(self.aluno, acertos=0, erros=1, nota="0.00"), self.questao, "D")
        self.assertEqual(metricas_questao(self.questao)["taxa"], Decimal("0"))
        outra = _questao(enunciado="cem")
        _resposta(_resultado(self.aluno), outra, "A")
        self.assertEqual(metricas_questao(outra)["taxa"], Decimal("100"))

    def test_em_branco_nao_some_da_distribuicao(self):
        _resposta(
            _resultado(self.aluno, acertos=0, erros=1, nota="0.00"),
            self.questao,
            None,
            correta=False,
        )
        linha = metricas_questao(self.questao)
        self.assertEqual(linha["em_branco"], 1)
        self.assertEqual(linha["respostas_validas"], 0)
        self.assertEqual(linha["erros"], 1)
        self.assertEqual(linha["distribuicao"][0]["quantidade"], 0)

    def test_alternativas_e_distrator(self):
        for _ in range(3):
            _resposta(_resultado(self.aluno), self.questao, "A")
        for _ in range(5):
            _resposta(
                _resultado(self.aluno, acertos=0, erros=1, nota="0.00"),
                self.questao,
                "C",
            )
        _resposta(
            _resultado(self.aluno, acertos=0, erros=1, nota="0.00"),
            self.questao,
            "B",
        )
        linha = metricas_questao(self.questao)
        mapa = {item["letra"]: item for item in linha["distribuicao"]}
        self.assertTrue(mapa["A"]["gabarito"])
        self.assertFalse(mapa["C"]["gabarito"])
        self.assertTrue(mapa["C"]["distrator"])
        self.assertEqual(linha["distrator"]["letra"], "C")
        self.assertEqual(mapa["C"]["quantidade"], 5)
        self.assertEqual(mapa["A"]["quantidade"], 3)
        self.assertAlmostEqual(mapa["C"]["pct"], 5 / 9 * 100, places=5)

    def test_revisar_exige_amostra_e_taxa_baixa(self):
        for _ in range(4):
            _resposta(
                _resultado(self.aluno, acertos=0, erros=1, nota="0.00"),
                self.questao,
                "D",
            )
        self.assertFalse(metricas_questao(self.questao)["revisar"])
        _resposta(
            _resultado(self.aluno, acertos=0, erros=1, nota="0.00"),
            self.questao,
            "D",
        )
        linha = metricas_questao(self.questao)
        self.assertTrue(linha["revisar"])
        self.assertEqual(linha["taxa"], Decimal("0"))

    def test_filtros_serie_dificuldade_taxa_volume_periodo(self):
        facil = _questao(serie="6", dificuldade="facil", enunciado="f")
        dificil = _questao(serie="6", dificuldade="dificil", enunciado="d")
        outra = _questao(serie="7", dificuldade="facil", enunciado="7")
        for _ in range(10):
            _resposta(_resultado(self.aluno), facil, "A")
        for _ in range(8):
            _resposta(
                _resultado(self.aluno, acertos=0, erros=1, nota="0.00"),
                dificil,
                "B",
            )
        _resposta(_resultado(self.aluno), outra, "A")
        antigo = _resultado(self.aluno)
        _resposta(antigo, facil, "A")
        Resultado.objects.filter(pk=antigo.pk).update(
            data=timezone.now() - timedelta(days=40)
        )

        so6 = metricas_por_questao(periodo="30d", serie="6")
        ids6 = {item["questao"].id for item in so6["linhas"] if item["tem_dados"]}
        self.assertEqual(ids6, {facil.id, dificil.id})

        so_dif = metricas_por_questao(periodo="30d", serie="6", dificuldade="dificil")
        self.assertEqual([item["questao"].id for item in so_dif["linhas"] if item["tem_dados"]], [dificil.id])

        baixa = metricas_por_questao(periodo="30d", serie="6", faixa_taxa="lt40")
        self.assertEqual([item["questao"].id for item in baixa["linhas"]], [dificil.id])

        volume = metricas_por_questao(periodo="30d", serie="6", volume_minimo="10")
        self.assertEqual([item["questao"].id for item in volume["linhas"]], [facil.id])

        hoje = metricas_por_questao(periodo="hoje", serie="6")
        self.assertTrue(hoje["tem_dados_persistidos"])
        todos = metricas_por_questao(periodo="todos", serie="6")
        mapa = {item["questao"].id: item for item in todos["linhas"]}
        self.assertEqual(mapa[facil.id]["tentativas"], 11)

    def test_versoes_permanecem_separadas(self):
        v1 = self.questao.versao_atual
        _resposta(_resultado(self.aluno), self.questao, "A", versao=v1, gabarito="A")
        self.questao.enunciado = "v2"
        self.questao.resposta_correta = "C"
        self.questao.save()
        v2 = self.questao.versao_atual
        _resposta(
            _resultado(self.aluno, acertos=0, erros=1, nota="0.00"),
            self.questao,
            "A",
            versao=v2,
            gabarito="C",
            correta=False,
        )
        geral = metricas_questao(self.questao)
        self.assertTrue(geral["gabarito_misto"])
        self.assertIsNone(geral["gabarito_historico"])
        por_versao = metricas_versoes_questao(self.questao)
        mapa = {item["versao"]: item for item in por_versao}
        self.assertEqual(mapa[1]["gabarito"], "A")
        self.assertEqual(mapa[2]["gabarito"], "C")
        self.assertEqual(mapa[1]["acertos"], 1)
        self.assertEqual(mapa[2]["acertos"], 0)
        self.assertEqual(RespostaResultado.objects.get(questao_versao=v1).resposta, "A")
        self.assertEqual(RespostaResultado.objects.get(questao_versao=v2).questao_versao_id, v2.id)

    def test_desempenho_por_dificuldade(self):
        facil = _questao(dificuldade="facil", enunciado="f2")
        media = _questao(dificuldade="medio", enunciado="m2")
        _resposta(_resultado(self.aluno), facil, "A")
        _resposta(
            _resultado(self.aluno, acertos=0, erros=1, nota="0.00"),
            media,
            "B",
        )
        linhas = {item["codigo"]: item for item in desempenho_por_dificuldade(periodo="30d")}
        self.assertEqual(linhas["facil"]["tentativas"], 1)
        self.assertEqual(linhas["medio"]["acertos"], 0)
        self.assertEqual(linhas["dificil"]["tentativas"], 0)


class AnalisePedagogicaViewsTests(TestCase):

    password = "senha-teste-123"

    def setUp(self):
        self.professor = create_user_with_group("prof-a", self.password, "professor")
        self.coordenador = create_user_with_group("coord-a", self.password, "coordenador")
        self.diretor = create_user_with_group("dir-a", self.password, "diretor")
        self.aluno_user = create_user_with_group("aluno-a", self.password, "aluno")
        self.aluno = Aluno.objects.create(nome="Bia", ra="BX99", serie="6")
        self.turma = Turma.objects.create(
            nome="AN",
            serie="6",
            ano_letivo=2026,
            professor_responsavel=self.professor,
        )
        self.matricula = matricular(self.aluno, self.turma)
        self.questao = _questao()
        self.url = reverse("desempenho_questoes")
        self.detalhe = reverse("desempenho_questao", kwargs={"pk": self.questao.pk})

    def test_permissoes(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertIn("/login/", self.client.get(self.url).url)
        self.client.login(username="aluno-a", password=self.password)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.get(self.detalhe).status_code, 403)
        for username in ("prof-a", "coord-a", "dir-a"):
            self.client.logout()
            self.client.login(username=username, password=self.password)
            self.assertEqual(self.client.get(self.url).status_code, 200, username)
            self.assertEqual(self.client.get(self.detalhe).status_code, 200, username)

    def test_filtros_na_pagina_e_indicador(self):
        for _ in range(5):
            _resposta(
                _resultado(self.aluno, acertos=0, erros=1, nota="0.00", matricula=self.matricula),
                self.questao,
                "D",
            )
        self.client.login(username="prof-a", password=self.password)
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(
                self.url,
                {"periodo": "30d", "serie": "6", "taxa": "lt40", "volume": "5"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(ctx.captured_queries), 40)
        self.assertContains(response, "Baixo desempenho")
        self.assertContains(response, "Questão com desempenho abaixo do esperado")
        self.assertNotContains(response, "Questão errada")
        self.assertNotContains(response, "BX99")
        detalhe = self.client.get(self.detalhe, {"periodo": "todos"})
        self.assertContains(detalhe, "Mais escolhida entre as erradas")
        self.assertContains(detalhe, "V1")

    def test_dificuldade_invalida_404(self):
        self.client.login(username="prof-a", password=self.password)
        self.assertEqual(self.client.get(self.url, {"dificuldade": "x"}).status_code, 404)
