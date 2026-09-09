from django.contrib.auth import get_user_model
from django.template.exceptions import TemplateDoesNotExist
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.catalog import create_user_with_group
from alunos.matriculas import matricular
from alunos.models import Aluno, Turma
from alunos.security import mascarar_ra
from questoes.models import Questao, Resultado


User = get_user_model()


class CadastroAlunoAuthTests(TestCase):

    def setUp(self):
        self.url = reverse("alunos:cadastrar")
        self.professor = create_user_with_group(
            "professor1",
            "senha-teste-123",
            "professor",
        )

    def test_anonimo_nao_acessa_cadastro_de_aluno(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

        post = self.client.post(
            self.url,
            {
                "nome": "Aluno Invasor",
                "ra": "999999",
                "serie": "5",
            },
        )
        self.assertEqual(post.status_code, 302)
        self.assertFalse(
            Aluno.objects.filter(ra="999999").exists()
        )

    def test_professor_acessa_cadastro_de_aluno(self):
        self.client.login(
            username="professor1",
            password="senha-teste-123",
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)


class ListaAlunosViewTests(TestCase):

    def setUp(self):
        self.url = reverse("alunos:lista_alunos")
        self.professor = create_user_with_group(
            "professor1",
            "senha-teste-123",
            "professor",
        )
        self.aluno = Aluno.objects.create(
            nome="Ana Lista",
            ra="20260002",
            serie="6",
        )
        self.turma = Turma.objects.create(
            nome="A",
            serie="6",
            ano_letivo=2026,
            professor_responsavel=self.professor,
        )
        matricular(self.aluno, self.turma)

    def test_anonimo_nao_acessa_lista_de_alunos(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_professor_acessa_lista_sem_template_ausente(self):
        self.client.login(
            username="professor1",
            password="senha-teste-123",
        )
        try:
            response = self.client.get(self.url)
        except TemplateDoesNotExist:
            self.fail("templates/aluno_list.html não encontrado")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "aluno_list.html")
        self.assertContains(response, "Ana Lista")
        self.assertContains(response, "20260002")

    def test_busca_por_nome_e_ra(self):
        bruno = Aluno.objects.create(nome="Bruno Outro", ra="20261111", serie="5")
        turma5 = Turma.objects.create(
            nome="B",
            serie="5",
            ano_letivo=2026,
            professor_responsavel=self.professor,
        )
        matricular(bruno, turma5)
        self.client.login(username="professor1", password="senha-teste-123")
        por_nome = self.client.get(self.url, {"q": "Ana"})
        self.assertContains(por_nome, "Ana Lista")
        self.assertNotContains(por_nome, "Bruno Outro")
        por_ra = self.client.get(self.url, {"q": "20261111"})
        self.assertContains(por_ra, "Bruno Outro")
        self.assertNotContains(por_ra, "Ana Lista")

    def test_filtro_por_serie(self):
        cinco = Aluno.objects.create(nome="Cinco Ano", ra="20265555", serie="5")
        turma5 = Turma.objects.create(
            nome="C",
            serie="5",
            ano_letivo=2026,
            professor_responsavel=self.professor,
        )
        matricular(cinco, turma5)
        self.client.login(username="professor1", password="senha-teste-123")
        response = self.client.get(self.url, {"serie": "6"})
        self.assertContains(response, "Ana Lista")
        self.assertNotContains(response, "Cinco Ano")

    def test_professor_nao_ve_botao_editar(self):
        self.client.login(username="professor1", password="senha-teste-123")
        response = self.client.get(self.url)
        self.assertNotContains(response, "Editar")
        self.assertContains(response, "Cadastrar aluno")

    def test_painel_mostra_contagens(self):
        self.client.login(username="professor1", password="senha-teste-123")
        response = self.client.get(reverse("area_professor"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alunos")
        self.assertContains(response, reverse("alunos:lista_alunos"))
        self.assertContains(response, reverse("questoes:resultados"))
        self.assertNotContains(response, 'href="#"')


class AcessoAlunoSessionTests(TestCase):

    def setUp(self):
        self.aluno = Aluno.objects.create(
            nome="Maria Teste",
            ra="20261234",
            serie="5",
        )

    def test_acesso_por_ra_grava_aluno_id_na_sessao(self):
        response = self.client.post(
            reverse("alunos:acesso_aluno"),
            {"ra": "20261234"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("alunos:aluno_logado"),
        )
        self.assertEqual(
            self.client.session.get("aluno_id"),
            self.aluno.id,
        )

    def test_aluno_logado_usa_sessao(self):
        session = self.client.session
        session["aluno_id"] = self.aluno.id
        session.save()

        response = self.client.get(reverse("alunos:aluno_logado"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Maria Teste")
        self.assertContains(response, "Simulado indisponível")

    def test_acesso_ra_invalido_usa_mensagem_generica(self):
        response = self.client.post(
            reverse("alunos:acesso_aluno"),
            {"ra": "00000000"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Não foi possível acessar com os dados informados",
        )
        self.assertNotContains(response, "RA não encontrado")
        self.assertNotContains(response, "não existe")
        self.assertIsNone(self.client.session.get("aluno_id"))

    def test_turma_e_acesso_aluno_exibem_entrada_oficial(self):
        for nome in ("turma", "alunos:acesso_aluno"):
            response = self.client.get(reverse(nome))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Digite seu RA")

    def test_aluno_logado_sem_sessao_redireciona(self):
        response = self.client.get(reverse("alunos:aluno_logado"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("alunos:acesso_aluno"))

    def test_painel_mostra_iniciar_quando_ha_questoes(self):
        from questoes.models import Questao

        Questao.objects.create(
            serie="5",
            dificuldade="facil",
            enunciado="Quanto é 2+2?",
            alternativa_a="1",
            alternativa_b="4",
            alternativa_c="3",
            alternativa_d="5",
            resposta_correta="B",
        )
        session = self.client.session
        session["aluno_id"] = self.aluno.id
        session.save()
        response = self.client.get(reverse("alunos:aluno_logado"))
        self.assertContains(response, "Iniciar simulado")
        self.assertNotContains(response, "Simulado indisponível")

    def test_painel_mostra_cooldown_apos_resultado_recente(self):
        Resultado.objects.create(
            aluno=self.aluno,
            acertos=1,
            erros=0,
            total_questoes=1,
            nota=10,
            xp_ganho=10,
            tempo_segundos=8,
        )
        session = self.client.session
        session["aluno_id"] = self.aluno.id
        session.save()
        response = self.client.get(reverse("alunos:aluno_logado"))
        self.assertContains(response, "já realizou um simulado")
        self.assertContains(response, "Sair do aluno")

    def test_aluno_id_inexistente_nao_gera_500(self):
        session = self.client.session
        session["aluno_id"] = 999999
        session["questao_atual"] = 3
        session["respostas"] = {"1": "A"}
        session.save()

        response = self.client.get(reverse("alunos:aluno_logado"))
        self.assertNotEqual(response.status_code, 500)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("alunos:acesso_aluno"),
        )

        for key in ("aluno_id", "questao_atual", "respostas"):
            self.assertNotIn(key, self.client.session)

    def test_aluno_id_invalido_nao_remove_auth_django(self):
        User.objects.create_user(
            username="professor1",
            password="senha-teste-123",
            is_staff=True,
        )
        self.client.login(
            username="professor1",
            password="senha-teste-123",
        )
        session = self.client.session
        session["aluno_id"] = 888888
        session.save()

        self.client.get(reverse("alunos:aluno_logado"))
        self.assertIn("_auth_user_id", self.client.session)
        self.assertNotIn("aluno_id", self.client.session)

    def test_ranking_com_aluno_id_inexistente_nao_gera_500(self):
        session = self.client.session
        session["aluno_id"] = 777777
        session.save()

        response = self.client.get(reverse("alunos:ranking"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("aluno_id", self.client.session)

    def test_ranking_permanece_publico(self):
        response = self.client.get(reverse("alunos:ranking"))
        self.assertEqual(response.status_code, 200)


class UrlSmokeTests(TestCase):

    def test_reverses_principais(self):
        nomes = [
            "home",
            "turma",
            "login",
            "logout",
            "area_aluno",
            "acesso_professor",
            "area_professor",
            "logout_professor",
            "alunos:lista_alunos",
            "alunos:acesso_aluno",
            "alunos:aluno_logado",
            "alunos:ranking",
            "alunos:series",
            "alunos:sair_aluno",
            "questoes:lista_questoes",
            "questoes:gestao",
            "questoes:resultados",
            "desempenho",
        ]
        for nome in nomes:
            reverse(nome)

    def test_rotas_publicas_principais_respondem(self):
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("acesso_professor")).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("alunos:acesso_aluno")).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("alunos:ranking")).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("questoes:lista_questoes")).status_code,
            302,
        )


class SairAlunoEPrivacidadeTests(TestCase):

    def setUp(self):
        self.aluno = Aluno.objects.create(
            nome="Maria Sessao",
            ra="SEGREDO99RA",
            serie="5",
            xp=50,
        )

    def test_sair_aluno_limpa_sessao_e_nao_acessa_prova(self):
        session = self.client.session
        session["aluno_id"] = self.aluno.id
        session["questao_atual"] = 1
        session.save()

        get_sair = self.client.get(reverse("alunos:sair_aluno"))
        self.assertEqual(get_sair.status_code, 405)

        response = self.client.post(reverse("alunos:sair_aluno"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("alunos:acesso_aluno"))
        self.assertNotIn("aluno_id", self.client.session)
        self.assertTrue(Aluno.objects.filter(pk=self.aluno.pk).exists())

        self.assertEqual(
            self.client.get(reverse("alunos:aluno_logado")).status_code,
            302,
        )
        self.assertEqual(
            self.client.get(reverse("questoes:lista_questoes")).status_code,
            302,
        )

    def test_ranking_publico_nao_expoe_ra_completo(self):
        self.assertEqual(mascarar_ra("12345678"), "1234****")
        response = self.client.get(reverse("alunos:ranking"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Maria Sessao")
        self.assertNotContains(response, "SEGREDO99RA")

    def test_ranking_ordena_xp_depois_desempates_e_top_20(self):
        serie = "6"
        Aluno.objects.create(nome="ZetaXP10", ra="R006A", serie=serie, xp=10)
        Aluno.objects.create(nome="AlfaXP30", ra="R006B", serie=serie, xp=30)
        medio = Aluno.objects.create(nome="MeioXP20", ra="R006C", serie=serie, xp=20)
        Resultado.objects.create(
            aluno=medio,
            acertos=1,
            erros=0,
            total_questoes=1,
            nota=10,
            xp_ganho=10,
            tempo_segundos=5,
        )
        empate_xp_a = Aluno.objects.create(
            nome="BrunoEmpate", ra="R006D", serie=serie, xp=15
        )
        empate_xp_b = Aluno.objects.create(
            nome="AnaEmpate", ra="R006E", serie=serie, xp=15
        )
        Resultado.objects.create(
            aluno=empate_xp_a,
            acertos=2,
            erros=0,
            total_questoes=2,
            nota=5,
            xp_ganho=0,
            tempo_segundos=40,
        )
        Resultado.objects.create(
            aluno=empate_xp_b,
            acertos=1,
            erros=1,
            total_questoes=2,
            nota=8,
            xp_ganho=0,
            tempo_segundos=40,
        )

        for i in range(21):
            Aluno.objects.create(
                nome=f"Lote {i:02d}",
                ra=f"L6{i:03d}",
                serie="7",
                xp=100 - i,
            )
        Aluno.objects.create(
            nome="Fora do topo",
            ra="L7FORA",
            serie="7",
            xp=0,
        )

        response = self.client.get(reverse("alunos:ranking"))
        rankings = response.context["rankings"]
        nomes_6 = [aluno.nome for aluno in rankings["6"]["alunos"]]
        self.assertEqual(
            nomes_6[:3],
            ["AlfaXP30", "MeioXP20", "AnaEmpate"],
        )
        self.assertLess(
            nomes_6.index("AnaEmpate"),
            nomes_6.index("BrunoEmpate"),
        )
        self.assertLess(
            nomes_6.index("BrunoEmpate"),
            nomes_6.index("ZetaXP10"),
        )

        nomes_7 = [aluno.nome for aluno in rankings["7"]["alunos"]]
        self.assertEqual(len(nomes_7), 20)
        self.assertIn("Lote 00", nomes_7)
        self.assertNotIn("Fora do topo", nomes_7)

    def test_ranking_desempate_por_tempo(self):
        lento = Aluno.objects.create(nome="LentoT", ra="T008A", serie="8", xp=7)
        rapido = Aluno.objects.create(nome="RapidoT", ra="T008B", serie="8", xp=7)
        Resultado.objects.create(
            aluno=lento,
            acertos=1,
            erros=0,
            total_questoes=1,
            nota=10,
            xp_ganho=0,
            tempo_segundos=120,
        )
        Resultado.objects.create(
            aluno=rapido,
            acertos=1,
            erros=0,
            total_questoes=1,
            nota=10,
            xp_ganho=0,
            tempo_segundos=20,
        )
        response = self.client.get(reverse("alunos:ranking"))
        nomes = [aluno.nome for aluno in response.context["rankings"]["8"]["alunos"]]
        self.assertLess(nomes.index("RapidoT"), nomes.index("LentoT"))

    def test_rate_limit_de_ra(self):
        from alunos.security import RA_MAX_FALHAS

        url = reverse("alunos:acesso_aluno")
        for _ in range(RA_MAX_FALHAS):
            self.client.post(url, {"ra": "nao-existe"})
        limitado = self.client.post(url, {"ra": self.aluno.ra})
        self.assertEqual(limitado.status_code, 200)
        self.assertNotIn("aluno_id", limitado.wsgi_request.session)
        self.assertContains(limitado, "Muitas tentativas")

    def test_csrf_obrigatorio_no_acesso_ra_e_sair(self):
        csrf_client = Client(enforce_csrf_checks=True)
        sem_token = csrf_client.post(
            reverse("alunos:acesso_aluno"),
            {"ra": self.aluno.ra},
        )
        self.assertEqual(sem_token.status_code, 403)

        csrf_client.get(reverse("alunos:acesso_aluno"))
        # cookie csrf existe após GET, mas POST ainda precisa do token no body
        sem_campo = csrf_client.post(
            reverse("alunos:acesso_aluno"),
            {"ra": self.aluno.ra},
        )
        self.assertEqual(sem_campo.status_code, 403)


class ExperienciaAlunoEtapa6Tests(TestCase):

    def test_ranking_vazio_explica_ausencia_de_resultados(self):
        response = self.client.get(reverse("alunos:ranking"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ainda não há resultados neste ranking")
        self.assertContains(response, "Faça seu primeiro simulado")

    def test_regras_refletem_xp_e_cooldown_reais(self):
        response = self.client.get(reverse("alunos:regras"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "8 horas")
        self.assertContains(response, "+10 XP")
        self.assertContains(response, "+5 XP")
        self.assertNotContains(response, "+100 XP")
        self.assertNotContains(response, "Conclusão da rodada")


class GestaoAlunosEtapa7Tests(TestCase):

    def setUp(self):
        self.aluno = Aluno.objects.create(
            nome="Carla Editavel",
            ra="20267777",
            serie="5",
        )
        self.professor = create_user_with_group(
            "prof-gestao", "senha-teste-123", "professor"
        )
        self.coordenador = create_user_with_group(
            "coord-gestao", "senha-teste-123", "coordenador"
        )
        self.turma = Turma.objects.create(
            nome="G",
            serie="5",
            ano_letivo=2026,
            professor_responsavel=self.professor,
        )
        matricular(self.aluno, self.turma)
        self.url_editar = reverse(
            "alunos:editar_aluno",
            kwargs={"pk": self.aluno.pk},
        )

    def test_professor_nao_edita_aluno(self):
        self.client.login(username="prof-gestao", password="senha-teste-123")
        self.assertEqual(self.client.get(self.url_editar).status_code, 403)
        post = self.client.post(
            self.url_editar,
            {"nome": "Hack", "ra": "20267777", "serie": "6"},
        )
        self.assertEqual(post.status_code, 403)
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.nome, "Carla Editavel")

    def test_coordenador_edita_aluno_via_post(self):
        self.client.login(username="coord-gestao", password="senha-teste-123")
        get = self.client.get(self.url_editar)
        self.assertEqual(get.status_code, 200)
        post = self.client.post(
            self.url_editar,
            {"nome": "Carla Atualizada", "ra": "20267777", "serie": "6"},
        )
        self.assertEqual(post.status_code, 302)
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.nome, "Carla Atualizada")
        self.assertEqual(self.aluno.serie, "6")

    def test_get_nao_altera_aluno(self):
        self.client.login(username="coord-gestao", password="senha-teste-123")
        self.client.get(self.url_editar)
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.nome, "Carla Editavel")

    def test_csrf_obrigatorio_na_edicao(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.login(username="coord-gestao", password="senha-teste-123")
        response = csrf_client.post(
            self.url_editar,
            {"nome": "Sem CSRF", "ra": "20267777", "serie": "5"},
        )
        self.assertEqual(response.status_code, 403)

    def test_editar_aluno_inexistente(self):
        self.client.login(username="coord-gestao", password="senha-teste-123")
        response = self.client.get(
            reverse("alunos:editar_aluno", kwargs={"pk": 999999})
        )
        self.assertEqual(response.status_code, 404)

    def test_paginacao_preserva_filtro(self):
        turma8 = Turma.objects.create(
            nome="P",
            serie="8",
            ano_letivo=2026,
            professor_responsavel=self.professor,
        )
        for i in range(25):
            aluno = Aluno.objects.create(
                nome=f"Pagina {i:02d}",
                ra=f"PG{i:04d}",
                serie="8",
            )
            matricular(aluno, turma8)
        self.client.login(username="prof-gestao", password="senha-teste-123")
        page2 = self.client.get(
            reverse("alunos:lista_alunos"),
            {"serie": "8", "page": "2"},
        )
        self.assertEqual(page2.status_code, 200)
        self.assertContains(page2, "serie=8")


class SeriePedagogicaEtapa8Tests(TestCase):

    def setUp(self):
        self.professor = create_user_with_group(
            "prof-serie", "senha-teste-123", "professor"
        )
        self.aluno_user = create_user_with_group(
            "aluno-serie", "senha-teste-123", "aluno"
        )
        self.aluno = Aluno.objects.create(
            nome="Elena Serie",
            ra="SERIE001",
            serie="6",
            xp=40,
        )
        self.turma = Turma.objects.create(
            nome="S",
            serie="6",
            ano_letivo=2026,
            professor_responsavel=self.professor,
        )
        self.matricula = matricular(self.aluno, self.turma)
        Questao.objects.create(
            serie="6",
            dificuldade="facil",
            enunciado="Pergunta da sexta",
            alternativa_a="A",
            alternativa_b="B",
            alternativa_c="C",
            alternativa_d="D",
            resposta_correta="A",
        )
        Resultado.objects.create(
            aluno=self.aluno,
            acertos=8,
            erros=2,
            total_questoes=10,
            nota="8.00",
            xp_ganho=20,
            tempo_segundos=50,
            matricula=self.matricula,
        )
        self.url_series = reverse("alunos:series")
        self.url_serie_6 = reverse(
            "alunos:alunos_por_serie",
            kwargs={"serie": "6"},
        )

    def test_anonimo_nao_acessa_series(self):
        self.assertEqual(self.client.get(self.url_series).status_code, 302)
        self.assertEqual(self.client.get(self.url_serie_6).status_code, 302)

    def test_aluno_nao_acessa_series_admin(self):
        self.client.login(username="aluno-serie", password="senha-teste-123")
        self.assertEqual(self.client.get(self.url_series).status_code, 403)
        self.assertEqual(self.client.get(self.url_serie_6).status_code, 403)

    def test_listagem_de_series_mostra_contagens(self):
        self.client.login(username="prof-serie", password="senha-teste-123")
        response = self.client.get(self.url_series)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "6º Ano")
        self.assertContains(response, "1 aluno")
        self.assertContains(response, "1 questão")
        self.assertContains(response, "1 resultado")
        self.assertContains(response, self.url_serie_6)
        self.assertContains(response, reverse("questoes:resultados") + "?serie=6")
        self.assertContains(response, reverse("questoes:gestao") + "?serie=6")

    def test_serie_sem_alunos_tem_estado_vazio(self):
        self.client.login(username="prof-serie", password="senha-teste-123")
        url = reverse("alunos:alunos_por_serie", kwargs={"serie": "5"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nenhum aluno cadastrado nesta série")
        self.assertContains(response, "Ainda não há questões para esta série")
        self.assertContains(response, "Ainda não há resultados para esta série")

    def test_alunos_por_serie_busca_e_desempenho(self):
        outra = Aluno.objects.create(nome="Outra Aluna", ra="SERIE002", serie="6")
        matricular(outra, self.turma)
        self.client.login(username="prof-serie", password="senha-teste-123")
        response = self.client.get(self.url_serie_6, {"q": "Elena"})
        self.assertContains(response, "Elena Serie")
        self.assertNotContains(response, "Outra Aluna")
        self.assertContains(response, "SERIE001")
        self.assertContains(response, "40")

    def test_serie_invalida_retorna_404(self):
        self.client.login(username="prof-serie", password="senha-teste-123")
        response = self.client.get(
            reverse("alunos:alunos_por_serie", kwargs={"serie": "99"})
        )
        self.assertEqual(response.status_code, 404)

    def test_paginacao_por_serie_preserva_busca(self):
        for i in range(25):
            aluno = Aluno.objects.create(
                nome=f"Lote Serie {i:02d}",
                ra=f"LS{i:04d}",
                serie="6",
            )
            matricular(aluno, self.turma)
        self.client.login(username="prof-serie", password="senha-teste-123")
        page2 = self.client.get(self.url_serie_6, {"q": "Lote", "page": "2"})
        self.assertEqual(page2.status_code, 200)
        self.assertContains(page2, "q=Lote")


