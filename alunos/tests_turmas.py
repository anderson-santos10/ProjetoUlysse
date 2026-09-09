from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from accounts.catalog import create_user_with_group
from alunos.matriculas import encerrar_matricula, matricular, transferir
from alunos.models import Aluno, Matricula, Turma
from questoes.metrics import queryset_resultados
from questoes.models import Questao, RespostaResultado, Resultado


def _aluno(nome="Ana", ra="TURA01", serie="6", **kwargs):
    return Aluno.objects.create(nome=nome, ra=ra, serie=serie, **kwargs)


def _turma(responsavel, nome="A", serie="6", ano=2026, **kwargs):
    return Turma.objects.create(
        nome=nome,
        serie=serie,
        ano_letivo=ano,
        professor_responsavel=responsavel,
        **kwargs,
    )


def _questao(serie="6"):
    return Questao.objects.create(
        serie=serie,
        dificuldade="facil",
        enunciado="Pergunta turma",
        alternativa_a="A1",
        alternativa_b="B1",
        alternativa_c="C1",
        alternativa_d="D1",
        resposta_correta="A",
    )


class TurmaModelTests(TestCase):

    def setUp(self):
        self.professor = create_user_with_group("prof-t", "senha-teste-123", "professor")

    def test_criar_turma(self):
        turma = _turma(self.professor)
        self.assertTrue(turma.ativa)
        self.assertEqual(turma.ano_letivo, 2026)
        self.assertEqual(turma.professor_responsavel_id, self.professor.pk)
        self.assertEqual(str(turma), "6º Ano A (2026)")

    def test_unicidade_nome_serie_ano(self):
        _turma(self.professor)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _turma(self.professor)


class MatriculaTests(TestCase):

    def setUp(self):
        self.professor = create_user_with_group("prof-m", "senha-teste-123", "professor")
        self.turma = _turma(self.professor)
        self.aluno = _aluno()

    def test_matricular_e_impedir_duplicidade(self):
        vinculo = matricular(self.aluno, self.turma)
        self.assertTrue(vinculo.ativa)
        self.assertIsNone(vinculo.data_fim)
        with self.assertRaises(ValidationError):
            matricular(self.aluno, self.turma)

    def test_nao_matricula_em_turma_inativa(self):
        self.turma.ativa = False
        self.turma.save(update_fields=["ativa"])
        with self.assertRaises(ValidationError):
            matricular(self.aluno, self.turma)

    def test_encerrar_preserva_registro(self):
        vinculo = matricular(self.aluno, self.turma)
        pk = vinculo.pk
        encerrar_matricula(vinculo)
        vinculo.refresh_from_db()
        self.assertFalse(vinculo.ativa)
        self.assertIsNotNone(vinculo.data_fim)
        self.assertTrue(Matricula.objects.filter(pk=pk).exists())

    def test_transferir_preserva_historico(self):
        outra = _turma(self.professor, nome="B")
        primeiro = matricular(self.aluno, self.turma)
        segundo = transferir(self.aluno, outra)
        primeiro.refresh_from_db()
        self.assertFalse(primeiro.ativa)
        self.assertTrue(segundo.ativa)
        self.assertEqual(segundo.turma_id, outra.pk)
        self.assertEqual(Matricula.objects.filter(aluno=self.aluno).count(), 2)

    def test_alinha_serie_do_aluno_com_a_turma(self):
        self.aluno.serie = "5"
        self.aluno.save(update_fields=["serie"])
        matricular(self.aluno, self.turma)
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.serie, "6")


class ResultadoHistoricoTurmaTests(TestCase):

    def setUp(self):
        self.professor = create_user_with_group("prof-r", "senha-teste-123", "professor")
        self.turma_a = _turma(self.professor, nome="A")
        self.turma_b = _turma(self.professor, nome="B")
        self.aluno = _aluno()

    def test_resultado_novo_guarda_matricula_e_nao_segue_transferencia(self):
        vinculo_a = matricular(self.aluno, self.turma_a)
        resultado = Resultado.objects.create(
            aluno=self.aluno,
            acertos=1,
            erros=0,
            total_questoes=1,
            nota="10.00",
            matricula=vinculo_a,
        )
        transferir(self.aluno, self.turma_b)
        resultado.refresh_from_db()
        self.assertEqual(resultado.matricula_id, vinculo_a.pk)
        self.assertEqual(resultado.matricula.turma_id, self.turma_a.pk)

    def test_resultado_antigo_sem_turma_continua_valido(self):
        resultado = Resultado.objects.create(
            aluno=self.aluno,
            acertos=0,
            erros=1,
            total_questoes=1,
            nota="0.00",
        )
        self.assertIsNone(resultado.matricula_id)
        self.assertEqual(list(queryset_resultados(periodo="todos")), [resultado])
        self.assertEqual(
            queryset_resultados(periodo="todos", turma_id=self.turma_a.pk).count(),
            0,
        )


class TurmaPermissoesTests(TestCase):

    password = "senha-teste-123"

    def setUp(self):
        self.professor_a = create_user_with_group("pa", self.password, "professor")
        self.professor_b = create_user_with_group("pb", self.password, "professor")
        self.coordenador = create_user_with_group("ca", self.password, "coordenador")
        self.diretor = create_user_with_group("da", self.password, "diretor")
        self.aluno_user = create_user_with_group("aa", self.password, "aluno")
        self.turma_a = _turma(self.professor_a, nome="A")
        self.turma_b = _turma(self.professor_b, nome="B")
        self.aluno = _aluno()
        self.vinculo = matricular(self.aluno, self.turma_a)

    def test_anonimo_vai_para_login(self):
        response = self.client.get(reverse("alunos:lista_turmas"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_aluno_autenticado_nao_acessa_turmas(self):
        self.client.login(username="aa", password=self.password)
        self.assertEqual(
            self.client.get(reverse("alunos:lista_turmas")).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                reverse("alunos:detalhe_turma", kwargs={"pk": self.turma_a.pk})
            ).status_code,
            403,
        )

    def test_professor_ve_so_a_sua_turma(self):
        self.client.login(username="pa", password=self.password)
        lista = self.client.get(reverse("alunos:lista_turmas"))
        self.assertEqual(lista.status_code, 200)
        self.assertContains(lista, "A")
        self.assertNotContains(lista, "6º Ano B")
        self.assertEqual(
            self.client.get(
                reverse("alunos:detalhe_turma", kwargs={"pk": self.turma_a.pk})
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse("alunos:detalhe_turma", kwargs={"pk": self.turma_b.pk})
            ).status_code,
            403,
        )

    def test_professor_nao_cria_turma(self):
        self.client.login(username="pa", password=self.password)
        self.assertEqual(
            self.client.get(reverse("alunos:cadastrar_turma")).status_code,
            403,
        )

    def test_coordenador_cria_e_ve_todas(self):
        self.client.login(username="ca", password=self.password)
        lista = self.client.get(reverse("alunos:lista_turmas"))
        self.assertEqual(lista.status_code, 200)
        self.assertContains(lista, "A")
        self.assertContains(lista, "B")
        post = self.client.post(
            reverse("alunos:cadastrar_turma"),
            {
                "nome": "C",
                "serie": "6",
                "ano_letivo": 2026,
                "professor_responsavel": self.professor_a.pk,
                "ativa": "on",
            },
        )
        self.assertEqual(post.status_code, 302)
        self.assertTrue(Turma.objects.filter(nome="C", serie="6").exists())

    def test_diretor_acessa_turma_alheia(self):
        self.client.login(username="da", password=self.password)
        self.assertEqual(
            self.client.get(
                reverse("alunos:detalhe_turma", kwargs={"pk": self.turma_b.pk})
            ).status_code,
            200,
        )

    def test_professor_nao_altera_vinculo_de_outra_turma(self):
        self.client.login(username="pb", password=self.password)
        response = self.client.post(
            reverse("alunos:encerrar_matricula", kwargs={"pk": self.vinculo.pk}),
        )
        self.assertEqual(response.status_code, 403)
        self.vinculo.refresh_from_db()
        self.assertTrue(self.vinculo.ativa)

    def test_sessao_de_aluno_nao_altera_vinculo(self):
        session = self.client.session
        session["aluno_id"] = self.aluno.pk
        session.save()
        response = self.client.post(
            reverse("alunos:matricular_aluno", kwargs={"pk": self.turma_a.pk}),
            {"aluno": self.aluno.pk},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_desempenho_filtro_turma_isolamento(self):
        self.client.login(username="pa", password=self.password)
        ok = self.client.get(reverse("desempenho"), {"turma": self.turma_a.pk})
        self.assertEqual(ok.status_code, 200)
        bloqueado = self.client.get(reverse("desempenho"), {"turma": self.turma_b.pk})
        self.assertEqual(bloqueado.status_code, 403)


class AnaliseTurmaTests(TestCase):

    def setUp(self):
        self.coord = create_user_with_group("coord-an", "senha-teste-123", "coordenador")
        self.turma = _turma(self.coord, nome="AN")
        self.aluno = _aluno(ra="ANL01")
        self.vinculo = matricular(self.aluno, self.turma)
        questao = _questao()
        resultado = Resultado.objects.create(
            aluno=self.aluno,
            acertos=1,
            erros=0,
            total_questoes=1,
            nota="10.00",
            matricula=self.vinculo,
        )
        RespostaResultado.objects.create(
            resultado=resultado,
            questao=questao,
            questao_versao=questao.versao_atual,
            resposta="A",
            resposta_correta="A",
            correta=True,
        )
        Resultado.objects.create(
            aluno=self.aluno,
            acertos=0,
            erros=1,
            total_questoes=1,
            nota="0.00",
        )

    def test_filtro_turma_nao_inclui_resultado_sem_historico(self):
        todos = queryset_resultados(periodo="todos")
        da_turma = queryset_resultados(periodo="todos", turma_id=self.turma.pk)
        self.assertEqual(todos.count(), 2)
        self.assertEqual(da_turma.count(), 1)

    def test_pagina_analise_filtra_no_backend(self):
        self.client.login(username="coord-an", password="senha-teste-123")
        response = self.client.get(
            reverse("desempenho_questoes"),
            {"turma": self.turma.pk, "periodo": "todos"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.turma.nome)


class RankingTurmaPrivacidadeTests(TestCase):

    def setUp(self):
        self.professor = create_user_with_group("prof-rk", "senha-teste-123", "professor")
        self.turma = _turma(self.professor, nome="RK")
        self.aluno = _aluno(nome="Carla Rank", ra="RANK99", xp=15)
        matricular(self.aluno, self.turma)

    def test_ranking_interno_mascara_ra_e_usa_inicial_sem_opt_in(self):
        self.client.login(username="prof-rk", password="senha-teste-123")
        response = self.client.get(
            reverse("alunos:ranking_turma", kwargs={"pk": self.turma.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Carla Rank")
        self.assertNotContains(response, "RANK99")
        self.assertContains(response, "C")

    def test_lista_turmas_nao_faz_query_por_linha(self):
        for i in range(3):
            _turma(self.professor, nome=f"X{i}", ano=2025)
        self.client.login(username="prof-rk", password="senha-teste-123")
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(reverse("alunos:lista_turmas"))
        self.assertLess(len(ctx), 20)
