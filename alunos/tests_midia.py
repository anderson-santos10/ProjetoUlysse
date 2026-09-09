import tempfile
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from accounts.catalog import create_user_with_group
from alunos.models import Aluno
from questoes.models import Resultado


def _foto(nome="foto.png"):
    buffer = BytesIO()
    Image.new("RGB", (12, 12), color=(80, 20, 20)).save(buffer, format="PNG")
    return SimpleUploadedFile(nome, buffer.getvalue(), content_type="image/png")


MEDIA_ROOT_TESTE = tempfile.mkdtemp(prefix="provas-media-a-")


@override_settings(MEDIA_ROOT=MEDIA_ROOT_TESTE)
class FotoAlunoERankingTests(TestCase):

    def setUp(self):
        self.coordenador = create_user_with_group(
            "coord-foto", "senha-teste-123", "coordenador"
        )
        self.aluno = Aluno.objects.create(
            nome="Marina Ranking",
            ra="FOTO01",
            serie="6",
            xp=40,
        )
        Resultado.objects.create(
            aluno=self.aluno,
            acertos=1,
            erros=0,
            total_questoes=1,
            nota="10.00",
            xp_ganho=10,
            tempo_segundos=5,
        )

    def test_aluno_sem_foto_e_opt_in_padrao_falso(self):
        self.assertFalse(self.aluno.foto)
        self.assertFalse(self.aluno.mostrar_foto_ranking)
        self.assertFalse(self.aluno.exibe_foto_no_ranking())
        self.assertEqual(self.aluno.inicial_nome(), "M")

    def test_foto_sem_permissao_nao_aparece_no_ranking(self):
        self.aluno.foto = _foto()
        self.aluno.mostrar_foto_ranking = False
        self.aluno.save()
        response = self.client.get(reverse("alunos:ranking"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "M")
        self.assertNotContains(response, self.aluno.foto.url)
        self.assertNotContains(response, "FOTO01")

    def test_foto_com_permissao_aparece_no_ranking(self):
        self.aluno.foto = _foto()
        self.aluno.mostrar_foto_ranking = True
        self.aluno.save()
        response = self.client.get(reverse("alunos:ranking"))
        self.assertContains(response, self.aluno.foto.url)
        self.assertContains(response, 'class="avatar-img"')
        self.assertNotContains(response, "FOTO01")

    def test_sem_foto_mesmo_com_opt_in_usa_inicial(self):
        self.aluno.mostrar_foto_ranking = True
        self.aluno.save()
        response = self.client.get(reverse("alunos:ranking"))
        self.assertContains(response, "M")
        self.assertNotContains(response, 'class="avatar-img"')

    def test_coordenador_atualiza_foto_e_opt_in(self):
        url = reverse("alunos:editar_aluno", kwargs={"pk": self.aluno.pk})
        self.client.login(username="coord-foto", password="senha-teste-123")
        response = self.client.post(
            url,
            {
                "nome": self.aluno.nome,
                "ra": self.aluno.ra,
                "serie": self.aluno.serie,
                "foto": _foto("nova.png"),
                "mostrar_foto_ranking": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.aluno.refresh_from_db()
        self.assertTrue(self.aluno.foto)
        self.assertTrue(self.aluno.mostrar_foto_ranking)

    def test_professor_nao_altera_foto_de_aluno_existente(self):
        create_user_with_group("prof-foto", "senha-teste-123", "professor")
        url = reverse("alunos:editar_aluno", kwargs={"pk": self.aluno.pk})
        self.client.login(username="prof-foto", password="senha-teste-123")
        response = self.client.post(
            url,
            {
                "nome": "Hack",
                "ra": self.aluno.ra,
                "serie": self.aluno.serie,
                "foto": _foto(),
                "mostrar_foto_ranking": "on",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.nome, "Marina Ranking")
        self.assertFalse(self.aluno.foto)
        self.assertFalse(self.aluno.mostrar_foto_ranking)

    def test_sessao_de_aluno_nao_edita_outro_aluno(self):
        outro = Aluno.objects.create(nome="Outro", ra="FOTO02", serie="6")
        session = self.client.session
        session["aluno_id"] = self.aluno.pk
        session.save()
        response = self.client.post(
            reverse("alunos:editar_aluno", kwargs={"pk": outro.pk}),
            {
                "nome": "Invadido",
                "ra": outro.ra,
                "serie": "6",
                "mostrar_foto_ranking": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)
        outro.refresh_from_db()
        self.assertEqual(outro.nome, "Outro")
        self.assertFalse(outro.mostrar_foto_ranking)

    def test_usuario_aluno_autenticado_nao_edita_cadastro(self):
        create_user_with_group("aluno-foto", "senha-teste-123", "aluno")
        self.client.login(username="aluno-foto", password="senha-teste-123")
        response = self.client.post(
            reverse("alunos:editar_aluno", kwargs={"pk": self.aluno.pk}),
            {
                "nome": "Hack",
                "ra": self.aluno.ra,
                "serie": "6",
                "mostrar_foto_ranking": "on",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.nome, "Marina Ranking")
