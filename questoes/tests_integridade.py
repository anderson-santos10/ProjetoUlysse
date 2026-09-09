from io import StringIO
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from alunos.models import Aluno
from questoes.forms import QuestaoForm
from questoes.integridade import auditar_integridade
from questoes.models import (
    MENSAGEM_ALTERACAO_DIRETA,
    Questao,
    QuestaoVersao,
    RespostaResultado,
    Resultado,
)
from questoes.persistencia import persistir_respostas_resultado
from questoes.versionamento import (
    VersaoTentativaInvalida,
    aplicar_edicao_com_versao,
    resolver_versoes_tentativa,
)


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


class IntegridadeDominioTests(TestCase):

    def test_save_sem_mudanca_nao_cria_versao(self):
        questao = _questao()
        questao.save()
        self.assertEqual(questao.versoes.count(), 1)

    def test_save_com_conteudo_novo_cria_uma_versao(self):
        questao = _questao()
        questao.enunciado = "Novo"
        questao.alternativa_c = "Gama 2"
        questao.save()
        self.assertEqual(questao.versoes.count(), 2)
        self.assertEqual(questao.versao_atual.versao, 2)

    def test_queryset_update_nao_altera_conteudo_da_questao(self):
        questao = _questao()
        versao_id = questao.versao_atual_id
        with self.assertRaisesMessage(ValueError, MENSAGEM_ALTERACAO_DIRETA):
            Questao.objects.filter(pk=questao.pk).update(
                enunciado="alteração direta"
            )
        questao.refresh_from_db()
        self.assertEqual(questao.enunciado, "Enunciado original")
        self.assertEqual(questao.versoes.count(), 1)
        self.assertEqual(questao.versao_atual_id, versao_id)

    def test_bulk_update_nao_altera_conteudo_da_questao(self):
        questao = _questao()
        questao.enunciado = "alteração em memória"
        with self.assertRaisesMessage(ValueError, MENSAGEM_ALTERACAO_DIRETA):
            Questao.objects.bulk_update([questao], ["enunciado"])
        questao.refresh_from_db()
        self.assertEqual(questao.enunciado, "Enunciado original")
        self.assertEqual(questao.versoes.count(), 1)

    def test_queryset_update_nao_altera_versao_historica(self):
        questao = _questao()
        with self.assertRaises(ValueError):
            QuestaoVersao.objects.filter(pk=questao.versao_atual_id).update(
                enunciado="hack"
            )
        questao = _questao()
        atual = questao.versao_atual
        atualizados = Questao.objects.filter(pk=questao.pk).update(
            versao_atual=atual
        )
        self.assertEqual(atualizados, 1)

    def test_aplicar_edicao_com_versao_por_campo(self):
        questao = _questao()

        def _editar(**overrides):
            dados = {
                "serie": questao.serie,
                "dificuldade": questao.dificuldade,
                "enunciado": questao.enunciado,
                "alternativa_a": questao.alternativa_a,
                "alternativa_b": questao.alternativa_b,
                "alternativa_c": questao.alternativa_c,
                "alternativa_d": questao.alternativa_d,
                "resposta_correta": questao.resposta_correta,
            }
            dados.update(overrides)
            form = QuestaoForm(dados, instance=questao)
            self.assertTrue(form.is_valid(), form.errors)
            return aplicar_edicao_com_versao(form)

        _editar(enunciado="Enunciado v2")
        self.assertEqual(questao.versoes.count(), 2)
        _editar(alternativa_a="Alpha 2")
        self.assertEqual(questao.versoes.count(), 3)
        _editar(resposta_correta="C")
        self.assertEqual(questao.versoes.count(), 4)
        _editar(dificuldade="dificil")
        self.assertEqual(questao.versoes.count(), 5)
        _editar(serie="6")
        self.assertEqual(questao.versoes.count(), 6)
        _editar(
            enunciado="Tudo",
            alternativa_b="Beta 2",
            dificuldade="medio",
        )
        self.assertEqual(questao.versoes.count(), 7)
        _editar()
        self.assertEqual(questao.versoes.count(), 7)


class ProvaAposEdicaoTests(TestCase):

    def test_prova_antiga_fica_em_v1_e_nova_usa_v2(self):
        aluno = Aluno.objects.create(nome="Hist", ra="INT03", serie="5")
        questao = _questao()
        v1 = questao.versao_atual
        url = reverse("questoes:lista_questoes")
        session = self.client.session
        session["aluno_id"] = aluno.id
        session.save()
        self.client.post(url, {"acao": "novo_questionario"})
        session = self.client.session
        session["respostas"] = {str(questao.id): "B"}
        session.save()
        self.client.post(url, {"acao": "finalizar"})
        antigo = RespostaResultado.objects.get()
        self.assertEqual(antigo.questao_versao_id, v1.id)
        self.assertEqual(antigo.questao_versao.enunciado, "Enunciado original")
        self.assertEqual(antigo.questao_versao.resposta_correta, "B")
        self.assertEqual(antigo.questao_versao.dificuldade, "facil")

        questao.enunciado = "Enunciado v2"
        questao.resposta_correta = "C"
        questao.dificuldade = "dificil"
        questao.save()
        v2 = questao.versao_atual
        self.assertEqual(v2.versao, 2)
        self.assertEqual(v1.enunciado, "Enunciado original")

        Resultado.objects.filter(pk=antigo.resultado_id).update(
            data=timezone.now() - timedelta(hours=9)
        )

        self.client.post(url, {"acao": "novo_questionario"})
        session = self.client.session
        self.assertEqual(session.get("questoes_versoes"), {str(questao.id): v2.id})
        session["respostas"] = {str(questao.id): "C"}
        session.save()
        self.client.post(url, {"acao": "finalizar"})
        novo = RespostaResultado.objects.exclude(pk=antigo.pk).get()
        self.assertEqual(novo.questao_versao_id, v2.id)
        self.assertEqual(novo.resposta_correta, "C")
        self.assertTrue(novo.correta)
        questao = _questao()
        with self.assertRaises(ValueError):
            QuestaoVersao.objects.filter(pk=questao.versao_atual_id).update(
                enunciado="hack"
            )

    def test_resposta_com_versao_de_outra_questao_e_rejeitada(self):
        q1 = _questao()
        q2 = _questao(enunciado="Outra")
        aluno = Aluno.objects.create(nome="I", ra="INT01", serie="5")
        resultado = Resultado.objects.create(
            aluno=aluno, acertos=0, erros=1, total_questoes=1,
            nota="0.00", xp_ganho=0, tempo_segundos=1,
        )
        with self.assertRaises(ValidationError):
            RespostaResultado.objects.create(
                resultado=resultado,
                questao=q1,
                questao_versao=q2.versao_atual,
                resposta="B",
                resposta_correta="B",
                correta=True,
            )
        with self.assertRaises(ValidationError):
            persistir_respostas_resultado(
                resultado,
                [q1],
                {str(q1.id): "B"},
                {q1.id: q2.versao_atual},
            )


class SessaoVersoesTests(TestCase):

    def setUp(self):
        self.aluno = Aluno.objects.create(nome="Sessao", ra="INT02", serie="5")
        self.questao = _questao()
        self.url = reverse("questoes:lista_questoes")
        session = self.client.session
        session["aluno_id"] = self.aluno.id
        session.save()

    def _iniciar_e_responder(self):
        self.client.post(self.url, {"acao": "novo_questionario"})
        session = self.client.session
        session["respostas"] = {str(self.questao.id): "B"}
        session.save()

    def test_mapa_ausente_usa_versao_atual_legado(self):
        self._iniciar_e_responder()
        session = self.client.session
        session.pop("questoes_versoes", None)
        session.save()
        self.client.post(self.url, {"acao": "finalizar"})
        item = RespostaResultado.objects.get()
        self.assertEqual(item.questao_versao_id, self.questao.versao_atual_id)
        self.assertTrue(item.correta)

    def test_versao_inexistente_nao_cria_resultado(self):
        self._iniciar_e_responder()
        session = self.client.session
        session["questoes_versoes"] = {str(self.questao.id): 999999}
        session.save()
        self.client.post(self.url, {"acao": "finalizar"})
        self.assertEqual(Resultado.objects.count(), 0)

    def test_id_invalido_nao_cria_resultado(self):
        self._iniciar_e_responder()
        session = self.client.session
        session["questoes_versoes"] = {str(self.questao.id): "abc"}
        session.save()
        self.client.post(self.url, {"acao": "finalizar"})
        self.assertEqual(Resultado.objects.count(), 0)

    def test_id_negativo_nao_cria_resultado(self):
        self._iniciar_e_responder()
        session = self.client.session
        session["questoes_versoes"] = {str(self.questao.id): -3}
        session.save()
        self.client.post(self.url, {"acao": "finalizar"})
        self.assertEqual(Resultado.objects.count(), 0)

    def test_resolver_estrito_rejeita_versao_alheia(self):
        outra = _questao(enunciado="Alheia")
        session = {"questoes_versoes": {str(self.questao.id): outra.versao_atual_id}}
        with self.assertRaises(VersaoTentativaInvalida):
            resolver_versoes_tentativa([self.questao], session, estrito=True)


class ComandoAuditoriaTests(TestCase):

    def test_comando_somente_leitura_ok(self):
        _questao()
        dados = auditar_integridade()
        self.assertTrue(dados["ok"])
        self.assertEqual(dados["sem_versao_atual"], 0)
        saida = StringIO()
        call_command("audit_question_integrity", stdout=saida)
        self.assertIn("STATUS: OK", saida.getvalue())
        self.assertIn("Questões sem versão atual: 0", saida.getvalue())
