from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.catalog import create_user_with_group
from alunos.models import Aluno
from questoes.models import Questao, RespostaResultado, Resultado


User = get_user_model()


class CadastroQuestaoAuthTests(TestCase):

    def setUp(self):
        self.url = reverse("questoes:cadastrar")
        self.professor = create_user_with_group(
            "professor1",
            "senha-teste-123",
            "professor",
        )

    def test_anonimo_nao_acessa_cadastro_de_questao(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

        post = self.client.post(
            self.url,
            {
                "serie": "5",
                "dificuldade": "facil",
                "enunciado": "Quanto é 1+1?",
                "alternativa_a": "1",
                "alternativa_b": "2",
                "alternativa_c": "3",
                "alternativa_d": "4",
                "resposta_correta": "B",
            },
        )
        self.assertEqual(post.status_code, 302)
        self.assertEqual(Questao.objects.count(), 0)

    def test_professor_acessa_cadastro_de_questao(self):
        self.client.login(
            username="professor1",
            password="senha-teste-123",
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)


class CooldownPostTests(TestCase):

    def setUp(self):
        self.aluno = Aluno.objects.create(
            nome="João Cooldown",
            ra="20260001",
            serie="5",
        )
        self.questao = Questao.objects.create(
            serie="5",
            dificuldade="facil",
            enunciado="Pergunta de teste",
            alternativa_a="A",
            alternativa_b="B",
            alternativa_c="C",
            alternativa_d="D",
            resposta_correta="A",
        )
        self.url = reverse("questoes:lista_questoes")

    def _entrar_como_aluno(self):
        session = self.client.session
        session["aluno_id"] = self.aluno.id
        session.save()

    def _criar_resultado(self, horas_atras):
        resultado = Resultado.objects.create(
            aluno=self.aluno,
            acertos=1,
            erros=0,
            total_questoes=1,
            nota=10,
            xp_ganho=10,
            tempo_segundos=30,
        )
        Resultado.objects.filter(pk=resultado.pk).update(
            data=timezone.now() - timedelta(hours=horas_atras)
        )
        return resultado

    def test_post_novo_questionario_bloqueado_dentro_de_8_horas(self):
        self._entrar_como_aluno()
        self._criar_resultado(horas_atras=1)

        response = self.client.post(
            self.url,
            {"acao": "novo_questionario"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.client.session.get("questoes_ordem"))
        self.assertTrue(
            self.client.session.get("questionario_bloqueado")
        )

    def test_post_responder_bloqueado_dentro_de_8_horas(self):
        self._entrar_como_aluno()
        self._criar_resultado(horas_atras=2)

        response = self.client.post(
            self.url,
            {
                "acao": "responder",
                "resposta": "A",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get("respostas") or {}, {})
        self.assertTrue(
            self.client.session.get("questionario_bloqueado")
        )

    def test_post_finalizar_bloqueado_nao_cria_resultado(self):
        self._entrar_como_aluno()
        self._criar_resultado(horas_atras=3)
        total_antes = Resultado.objects.filter(aluno=self.aluno).count()

        self.client.post(
            self.url,
            {"acao": "finalizar"},
        )
        self.assertEqual(
            Resultado.objects.filter(aluno=self.aluno).count(),
            total_antes,
        )

    def test_post_novo_questionario_liberado_apos_8_horas(self):
        self._entrar_como_aluno()
        self._criar_resultado(horas_atras=9)

        response = self.client.post(
            self.url,
            {"acao": "novo_questionario"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.client.session.get("questoes_ordem"),
            [self.questao.id],
        )
        self.assertFalse(
            self.client.session.get("questionario_bloqueado")
        )


class AlunoSessionInvalidaQuestoesTests(TestCase):

    def test_get_questoes_com_aluno_id_inexistente_nao_gera_500(self):
        session = self.client.session
        session["aluno_id"] = 999999
        session.save()

        response = self.client.get(reverse("questoes:lista_questoes"))
        self.assertNotEqual(response.status_code, 500)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("alunos:acesso_aluno"),
        )
        self.assertNotIn("aluno_id", self.client.session)


class CalcularXpTests(TestCase):

    def test_xp_por_dificuldade_e_bonus_de_sequencia(self):
        from questoes.scoring import calcular_xp

        class Item:
            def __init__(self, pk, dificuldade, correta):
                self.id = pk
                self.dificuldade = dificuldade
                self.resposta_correta = correta

        facil, medio, dificil = (
            Item(1, "facil", "A"),
            Item(2, "medio", "B"),
            Item(3, "dificil", "C"),
        )
        self.assertEqual(
            calcular_xp([facil], {"1": "A"}),
            10,
        )
        self.assertEqual(
            calcular_xp([medio], {"2": "B"}),
            15,
        )
        self.assertEqual(
            calcular_xp([dificil], {"3": "C"}),
            20,
        )

        tres_faceis = [
            Item(10, "facil", "A"),
            Item(11, "facil", "A"),
            Item(12, "facil", "A"),
        ]
        self.assertEqual(
            calcular_xp(
                tres_faceis,
                {"10": "A", "11": "A", "12": "A"},
            ),
            10 + 10 + 15,
        )

    def test_erro_zera_sequencia_e_combina_acertos(self):
        from questoes.scoring import calcular_xp

        class Item:
            def __init__(self, pk, correta):
                self.id = pk
                self.dificuldade = "facil"
                self.resposta_correta = correta

        questoes = [
            Item(1, "A"),
            Item(2, "A"),
            Item(3, "A"),
            Item(4, "A"),
            Item(5, "A"),
        ]
        respostas = {
            "1": "A",
            "2": "A",
            "3": "B",
            "4": "A",
            "5": "A",
        }
        self.assertEqual(calcular_xp(questoes, respostas), 10 + 10 + 0 + 10 + 10)


class ProvaSessaoEFinalizarTests(TestCase):

    def setUp(self):
        self.aluno = Aluno.objects.create(
            nome="Aluno Prova",
            ra="20261111",
            serie="5",
        )
        self.questao = Questao.objects.create(
            serie="5",
            dificuldade="facil",
            enunciado="Pergunta",
            alternativa_a="A",
            alternativa_b="B",
            alternativa_c="C",
            alternativa_d="D",
            resposta_correta="A",
        )
        self.url = reverse("questoes:lista_questoes")

    def _sessao_aluno(self):
        session = self.client.session
        session["aluno_id"] = self.aluno.id
        session.save()

    def test_get_questoes_sem_sessao_redireciona(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("alunos:acesso_aluno"))

    def test_get_questoes_com_aluno_valido(self):
        self._sessao_aluno()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_post_sem_sessao_nao_processa_prova(self):
        response = self.client.post(
            self.url,
            {"acao": "novo_questionario"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("alunos:acesso_aluno"))
        self.assertIsNone(self.client.session.get("questoes_ordem"))

        self.client.post(self.url, {"acao": "responder", "resposta": "A"})
        self.assertEqual(self.client.session.get("respostas") or {}, {})

        self.client.post(self.url, {"acao": "finalizar"})
        self.assertEqual(Resultado.objects.count(), 0)

    def test_post_nao_troca_identidade_via_aluno_id(self):
        outro = Aluno.objects.create(
            nome="Outro",
            ra="20262222",
            serie="6",
        )
        self._sessao_aluno()
        self.client.post(
            self.url,
            {
                "acao": "novo_questionario",
                "aluno_id": str(outro.id),
            },
        )
        self.assertEqual(self.client.session.get("aluno_id"), self.aluno.id)

    def test_get_cooldown_dentro_de_8_horas(self):
        self._sessao_aluno()
        resultado = Resultado.objects.create(
            aluno=self.aluno,
            acertos=1,
            erros=0,
            total_questoes=1,
            nota=10,
            xp_ganho=10,
            tempo_segundos=10,
        )
        Resultado.objects.filter(pk=resultado.pk).update(
            data=timezone.now() - timedelta(hours=1)
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "já realizou um simulado")

    def test_finalizar_uma_vez_e_double_submit(self):
        self._sessao_aluno()
        self.client.post(self.url, {"acao": "novo_questionario"})
        session = self.client.session
        session["respostas"] = {str(self.questao.id): "A"}
        session.save()

        primeiro = self.client.post(self.url, {"acao": "finalizar"})
        self.assertEqual(primeiro.status_code, 302)
        self.assertEqual(Resultado.objects.filter(aluno=self.aluno).count(), 1)
        self.aluno.refresh_from_db()
        xp_depois = self.aluno.xp
        self.assertEqual(xp_depois, 10)
        self.assertTrue(self.client.session.get("questionario_finalizado"))

        self.client.post(self.url, {"acao": "finalizar"})
        self.assertEqual(Resultado.objects.filter(aluno=self.aluno).count(), 1)
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.xp, xp_depois)
        self.assertEqual(RespostaResultado.objects.count(), 1)
        unica = RespostaResultado.objects.get()
        self.assertEqual(unica.questao_id, self.questao.id)
        self.assertEqual(unica.resposta, "A")
        self.assertTrue(unica.correta)
        self.assertEqual(unica.questao_versao_id, self.questao.versao_atual_id)
        self.assertEqual(unica.resposta_correta, "A")

    def test_get_finalizar_nao_cria_resultado(self):
        self._sessao_aluno()
        self.client.get(self.url, {"acao": "finalizar"})
        self.assertEqual(Resultado.objects.count(), 0)

    def test_resultado_apos_finalizar_mostra_nota_e_xp(self):
        self._sessao_aluno()
        self.client.post(self.url, {"acao": "novo_questionario"})
        session = self.client.session
        session["respostas"] = {str(self.questao.id): "A"}
        session.save()
        self.client.post(self.url, {"acao": "finalizar"})
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Simulado concluído")
        self.assertContains(response, "Ver ranking")
        self.assertContains(response, "Voltar para meu painel")
        self.assertContains(response, "+10 XP")


