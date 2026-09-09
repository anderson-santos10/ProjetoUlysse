import tempfile
from io import BytesIO
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from accounts.catalog import create_user_with_group
from alunos.models import Aluno
from questoes.forms import QuestaoForm
from questoes.media import (
    MENSAGEM_TAMANHO,
    MENSAGEM_TIPO,
    TAMANHO_MAXIMO_BYTES,
    validar_imagem_enviada,
)
from questoes.metrics import metricas_versoes_questao
from questoes.models import Questao, RespostaResultado, Resultado


def _bytes_imagem(formato="PNG", tamanho=(8, 8), cor=(20, 40, 80)):
    buffer = BytesIO()
    Image.new("RGB", tamanho, color=cor).save(buffer, format=formato)
    return buffer.getvalue()


def _arquivo(nome="figura.png", formato="PNG", content_type="image/png", **kwargs):
    return SimpleUploadedFile(
        nome,
        _bytes_imagem(formato=formato, **kwargs),
        content_type=content_type,
    )


def _questao(**kwargs):
    dados = {
        "serie": "5",
        "dificuldade": "facil",
        "enunciado": "Enunciado sem figura",
        "alternativa_a": "A",
        "alternativa_b": "B",
        "alternativa_c": "C",
        "alternativa_d": "D",
        "resposta_correta": "A",
    }
    dados.update(kwargs)
    return Questao.objects.create(**dados)


def _payload(questao, **overrides):
    dados = {
        "serie": questao.serie,
        "dificuldade": questao.dificuldade,
        "enunciado": questao.enunciado,
        "alternativa_a": questao.alternativa_a,
        "alternativa_b": questao.alternativa_b,
        "alternativa_c": questao.alternativa_c,
        "alternativa_d": questao.alternativa_d,
        "resposta_correta": questao.resposta_correta,
        "imagem_alt": questao.imagem_alt,
    }
    dados.update(overrides)
    return dados


MEDIA_ROOT_TESTE = tempfile.mkdtemp(prefix="provas-media-q-")


@override_settings(MEDIA_ROOT=MEDIA_ROOT_TESTE)
class QuestaoImagemTests(TestCase):

    def test_criar_sem_imagem(self):
        questao = _questao()
        self.assertFalse(questao.imagem)
        self.assertFalse(questao.versao_atual.imagem)
        self.assertEqual(questao.imagem_alt, "")
        self.assertEqual(questao.versao_atual.imagem_alt, "")

    def test_criar_com_imagem_e_alt(self):
        questao = _questao(
            imagem=_arquivo(),
            imagem_alt="Mapa da região Sudeste",
        )
        self.assertTrue(questao.imagem)
        self.assertTrue(questao.versao_atual.imagem)
        self.assertEqual(questao.imagem.name, questao.versao_atual.imagem.name)
        self.assertEqual(questao.versao_atual.imagem_alt, "Mapa da região Sudeste")
        self.assertEqual(questao.versoes.count(), 1)

    def test_editar_texto_sem_mudar_imagem_cria_versao_e_preserva_arquivo(self):
        questao = _questao(imagem=_arquivo("v1.png"), imagem_alt="Figura V1")
        nome_v1 = questao.versao_atual.imagem.name
        questao.enunciado = "Enunciado atualizado"
        questao.save()
        self.assertEqual(questao.versoes.count(), 2)
        v1 = questao.versoes.get(versao=1)
        v2 = questao.versoes.get(versao=2)
        self.assertEqual(v1.imagem.name, nome_v1)
        self.assertEqual(v2.imagem.name, nome_v1)
        self.assertEqual(v1.enunciado, "Enunciado sem figura")
        self.assertEqual(v2.enunciado, "Enunciado atualizado")

    def test_trocar_imagem_cria_versao_e_preserva_v1(self):
        questao = _questao(imagem=_arquivo("a.png", cor=(1, 2, 3)))
        nome_a = questao.versao_atual.imagem.name
        questao.imagem = _arquivo("b.png", cor=(200, 10, 10))
        questao.imagem_alt = "Gráfico novo"
        questao.save()
        v1 = questao.versoes.get(versao=1)
        v2 = questao.versoes.get(versao=2)
        self.assertEqual(v1.imagem.name, nome_a)
        self.assertNotEqual(v2.imagem.name, nome_a)
        self.assertTrue(v2.imagem)
        self.assertEqual(v2.imagem_alt, "Gráfico novo")
        self.assertTrue(Path(v1.imagem.path).exists())

    def test_remover_imagem_cria_versao_sem_arquivo_e_mantem_v1(self):
        questao = _questao(imagem=_arquivo("permanece.png"))
        nome_a = questao.versao_atual.imagem.name
        questao.imagem = None
        questao.imagem_alt = ""
        questao.save()
        v1 = questao.versoes.get(versao=1)
        v2 = questao.versoes.get(versao=2)
        self.assertEqual(v1.imagem.name, nome_a)
        self.assertFalse(v2.imagem)
        self.assertTrue(Path(v1.imagem.path).exists())

    def test_salvar_sem_mudanca_nao_cria_versao(self):
        questao = _questao(imagem=_arquivo())
        questao.save()
        self.assertEqual(questao.versoes.count(), 1)

    def test_historico_do_resultado_usa_imagem_da_versao_respondida(self):
        questao = _questao(imagem=_arquivo("hist-a.png", cor=(9, 9, 9)))
        v1 = questao.versao_atual
        aluno = Aluno.objects.create(nome="Histórico", ra="MID01", serie="5")
        resultado = Resultado.objects.create(
            aluno=aluno,
            acertos=1,
            erros=0,
            total_questoes=1,
            nota="10.00",
            xp_ganho=10,
            tempo_segundos=8,
        )
        RespostaResultado.objects.create(
            resultado=resultado,
            questao=questao,
            questao_versao=v1,
            resposta="A",
            resposta_correta="A",
            correta=True,
        )
        questao.imagem = _arquivo("hist-b.png", cor=(90, 90, 90))
        questao.save()
        resposta = resultado.respostas_questoes.get()
        self.assertEqual(resposta.questao_versao_id, v1.id)
        self.assertEqual(resposta.questao_versao.imagem.name, v1.imagem.name)
        self.assertNotEqual(
            resposta.questao_versao.imagem.name,
            questao.versao_atual.imagem.name,
        )

    def test_analise_indica_se_a_versao_tem_imagem(self):
        questao = _questao(imagem=_arquivo())
        aluno = Aluno.objects.create(nome="Métrica", ra="MID02", serie="5")
        resultado = Resultado.objects.create(
            aluno=aluno,
            acertos=1,
            erros=0,
            total_questoes=1,
            nota="10.00",
        )
        RespostaResultado.objects.create(
            resultado=resultado,
            questao=questao,
            questao_versao=questao.versao_atual,
            resposta="A",
            resposta_correta="A",
            correta=True,
        )
        questao.imagem = None
        questao.save()
        resultado2 = Resultado.objects.create(
            aluno=aluno,
            acertos=0,
            erros=1,
            total_questoes=1,
            nota="0.00",
        )
        RespostaResultado.objects.create(
            resultado=resultado2,
            questao=questao,
            questao_versao=questao.versao_atual,
            resposta="B",
            resposta_correta="A",
            correta=False,
        )
        linhas = metricas_versoes_questao(questao)
        por_versao = {item["versao"]: item for item in linhas}
        self.assertTrue(por_versao[1]["tem_imagem"])
        self.assertFalse(por_versao[2]["tem_imagem"])


@override_settings(MEDIA_ROOT=MEDIA_ROOT_TESTE)
class UploadImagemQuestaoTests(TestCase):

    def setUp(self):
        self.coordenador = create_user_with_group(
            "coord-midia", "senha-teste-123", "coordenador"
        )
        self.questao = _questao()
        self.url = reverse("questoes:editar_questao", kwargs={"pk": self.questao.pk})

    def test_jpeg_png_webp_aceitam(self):
        for nome, formato, mime in (
            ("ok.jpg", "JPEG", "image/jpeg"),
            ("ok.png", "PNG", "image/png"),
            ("ok.webp", "WEBP", "image/webp"),
        ):
            form = QuestaoForm(
                _payload(self.questao),
                {"imagem": _arquivo(nome, formato=formato, content_type=mime)},
                instance=self.questao,
            )
            self.assertTrue(form.is_valid(), form.errors)

    def test_extensao_svg_rejeitada(self):
        form = QuestaoForm(
            _payload(self.questao),
            {
                "imagem": SimpleUploadedFile(
                    "figura.svg",
                    b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
                    content_type="image/svg+xml",
                )
            },
            instance=self.questao,
        )
        self.assertFalse(form.is_valid())
        self.assertTrue(form.errors.get("imagem"))

    def test_validacao_interna_rejeita_svg_e_tamanho(self):
        with self.assertRaises(Exception) as ctx:
            validar_imagem_enviada(
                SimpleUploadedFile(
                    "figura.svg",
                    b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
                    content_type="image/svg+xml",
                )
            )
        self.assertIn(MENSAGEM_TIPO, str(ctx.exception))
        grande = SimpleUploadedFile(
            "grande.png",
            b"x" * (TAMANHO_MAXIMO_BYTES + 1),
            content_type="image/png",
        )
        with self.assertRaises(Exception) as ctx_tam:
            validar_imagem_enviada(grande)
        self.assertIn(MENSAGEM_TAMANHO, str(ctx_tam.exception))

    def test_gif_rejeitado(self):
        form = QuestaoForm(
            _payload(self.questao),
            {"imagem": _arquivo("anima.gif", formato="GIF", content_type="image/gif")},
            instance=self.questao,
        )
        self.assertFalse(form.is_valid())

    def test_arquivo_invalido_rejeitado(self):
        form = QuestaoForm(
            _payload(self.questao, enunciado="Texto preservado"),
            {
                "imagem": SimpleUploadedFile(
                    "falso.png",
                    b"isto nao e uma imagem",
                    content_type="image/png",
                )
            },
            instance=self.questao,
        )
        self.assertFalse(form.is_valid())
        self.assertEqual(form["enunciado"].value(), "Texto preservado")

    def test_arquivo_acima_do_limite(self):
        grande = SimpleUploadedFile(
            "grande.png",
            b"x" * (TAMANHO_MAXIMO_BYTES + 1),
            content_type="image/png",
        )
        form = QuestaoForm(
            _payload(self.questao),
            {"imagem": grande},
            instance=self.questao,
        )
        self.assertFalse(form.is_valid())
        self.assertTrue(form.errors.get("imagem"))

    def test_coordenador_envia_imagem_pela_view(self):
        self.client.login(username="coord-midia", password="senha-teste-123")
        response = self.client.post(
            self.url,
            _payload(
                self.questao,
                imagem=_arquivo("via-view.png"),
                imagem_alt="Charge da questão",
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.questao.refresh_from_db()
        self.assertTrue(self.questao.imagem)
        self.assertEqual(self.questao.versoes.count(), 2)
        self.assertEqual(self.questao.versao_atual.imagem_alt, "Charge da questão")

    def test_remover_imagem_pela_view(self):
        self.questao.imagem = _arquivo("sair.png")
        self.questao.save()
        nome_v1 = self.questao.versoes.get(versao=1).imagem.name
        self.client.login(username="coord-midia", password="senha-teste-123")
        response = self.client.post(
            self.url,
            _payload(self.questao, remover_imagem="on"),
        )
        self.assertEqual(response.status_code, 302)
        self.questao.refresh_from_db()
        self.assertFalse(self.questao.imagem)
        self.assertFalse(self.questao.versao_atual.imagem)
        self.assertEqual(self.questao.versoes.get(versao=1).imagem.name, nome_v1)

    def test_alt_vazio_e_template_usa_fallback_neutro(self):
        self.questao.imagem = _arquivo("sem-alt.png")
        self.questao.imagem_alt = ""
        self.questao.save()
        aluno = Aluno.objects.create(nome="Alt", ra="MID03", serie="5")
        resultado = Resultado.objects.create(
            aluno=aluno,
            acertos=1,
            erros=0,
            total_questoes=1,
            nota="10.00",
        )
        RespostaResultado.objects.create(
            resultado=resultado,
            questao=self.questao,
            questao_versao=self.questao.versao_atual,
            resposta="A",
            resposta_correta="A",
            correta=True,
        )
        create_user_with_group("dir-midia", "senha-teste-123", "diretor")
        self.client.login(username="dir-midia", password="senha-teste-123")
        response = self.client.get(
            reverse("questoes:resultado_detalhe", kwargs={"pk": resultado.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'alt="Figura desta questão"')
        self.assertContains(response, self.questao.versao_atual.imagem.url)

    def test_alt_informado_aparece_no_historico(self):
        self.questao.imagem = _arquivo("com-alt.png")
        self.questao.imagem_alt = "Tabela de conversão"
        self.questao.save()
        aluno = Aluno.objects.create(nome="Alt2", ra="MID04", serie="5")
        resultado = Resultado.objects.create(
            aluno=aluno,
            acertos=1,
            erros=0,
            total_questoes=1,
            nota="10.00",
        )
        RespostaResultado.objects.create(
            resultado=resultado,
            questao=self.questao,
            questao_versao=self.questao.versao_atual,
            resposta="A",
            resposta_correta="A",
            correta=True,
        )
        create_user_with_group("dir-midia2", "senha-teste-123", "diretor")
        self.client.login(username="dir-midia2", password="senha-teste-123")
        response = self.client.get(
            reverse("questoes:resultado_detalhe", kwargs={"pk": resultado.pk})
        )
        self.assertContains(response, 'alt="Tabela de conversão"')

    def test_professor_nao_edita_imagem(self):
        create_user_with_group("prof-midia", "senha-teste-123", "professor")
        self.client.login(username="prof-midia", password="senha-teste-123")
        response = self.client.post(
            self.url,
            _payload(self.questao, imagem=_arquivo("proibido.png")),
        )
        self.assertEqual(response.status_code, 403)
        self.questao.refresh_from_db()
        self.assertFalse(self.questao.imagem)

    def test_anonimo_nao_edita_imagem(self):
        response = self.client.post(
            self.url,
            _payload(self.questao, imagem=_arquivo("anon.png")),
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)
