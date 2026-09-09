import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Profile, Role
from accounts.permissions import user_has_staff_access


User = get_user_model()

PROJECT_ROOT = Path(settings.BASE_DIR)


class SettingsSecurityTests(TestCase):

    def test_debug_nao_e_true_por_padrao_no_codigo(self):
        source = (PROJECT_ROOT / "saresp" / "settings.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(
            'os.environ.get("DEBUG", "True")',
            source,
        )
        self.assertIn(
            '_env_bool("DEBUG", default=False)',
            source,
        )

    def test_secret_key_antiga_nao_esta_no_codigo(self):
        source = (PROJECT_ROOT / "saresp" / "settings.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(
            "django-insecure-e6go^1$c2p3^mcm",
            source,
        )

    def test_debug_em_testes_nao_fica_true_sem_env(self):
        self.assertFalse(settings.DEBUG)

    def test_settings_exige_secret_key_por_variavel_de_ambiente(self):
        source = (PROJECT_ROOT / "saresp" / "settings.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('os.environ.get("SECRET_KEY"', source)
        self.assertIn("ImproperlyConfigured", source)
        self.assertNotIn(
            'SECRET_KEY = "django-insecure-e6go^1$c2p3^mcm"',
            source,
        )

    def _settings_subprocess(self, extra_env, expect_success):
        env = os.environ.copy()
        env.pop("SECRET_KEY", None)
        env["DEBUG"] = "False"
        env["SARESP_IGNORE_DOTENV"] = "1"
        env["DJANGO_SETTINGS_MODULE"] = "saresp.settings"
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        env.update(extra_env)
        script = (
            "import os\n"
            "os.environ['DJANGO_SETTINGS_MODULE'] = 'saresp.settings'\n"
            "from django.core.exceptions import ImproperlyConfigured\n"
            "try:\n"
            "    import django\n"
            "    django.setup()\n"
            "except ImproperlyConfigured as exc:\n"
            "    texto = str(exc)\n"
            "    assert 'SECRET_KEY' in texto\n"
            "    print('SECRET_KEY configurada: NAO')\n"
            "    raise SystemExit(2)\n"
            "print('SECRET_KEY configurada: SIM')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        combined = (result.stdout or "") + (result.stderr or "")
        self.assertNotIn("django-insecure-e6go^1$c2p3^mcm", combined)
        if expect_success:
            self.assertEqual(result.returncode, 0, combined)
            self.assertIn("SECRET_KEY configurada: SIM", result.stdout)
            self.assertNotIn(extra_env.get("SECRET_KEY", ""), result.stdout)
        else:
            self.assertEqual(result.returncode, 2, combined)
            self.assertIn("SECRET_KEY configurada: NAO", result.stdout)
        return result

    def test_django_inicializa_quando_secret_key_existe(self):
        self._settings_subprocess(
            {"SECRET_KEY": "chave-de-teste-nao-usar-em-producao"},
            expect_success=True,
        )

    def test_producao_sem_secret_key_falha_com_mensagem_clara(self):
        self._settings_subprocess({}, expect_success=False)

    def test_base_css_existe_e_esta_no_staticfiles_dirs(self):
        css_path = PROJECT_ROOT / "static" / "css" / "base.css"
        self.assertTrue(css_path.is_file())
        self.assertIn(PROJECT_ROOT / "static", settings.STATICFILES_DIRS)


class PermissionsTests(TestCase):

    def test_is_staff_sozinho_nao_libera_area_professor(self):
        user = User.objects.create_user(
            username="apenas-staff",
            password="senha-teste-123",
            is_staff=True,
        )
        self.assertFalse(user_has_staff_access(user))

    def test_grupo_professor_tem_acesso(self):
        from accounts.catalog import create_user_with_group

        user = create_user_with_group(
            "prof",
            "senha-teste-123",
            "professor",
        )
        self.assertTrue(user_has_staff_access(user))

    def test_usuario_comum_nao_tem_acesso(self):
        user = User.objects.create_user(
            username="comum",
            password="senha-teste-123",
        )
        self.assertFalse(user_has_staff_access(user))

    def test_profile_role_nao_concede_permissao(self):
        user = User.objects.create_user(
            username="com-role",
            password="senha-teste-123",
        )
        Profile.objects.create(user=user, role=Role.PROFESSOR)
        user.refresh_from_db()
        self.assertFalse(user_has_staff_access(user))

    def test_usuario_autenticado_sem_permissao_ve_403_claro(self):
        from accounts.catalog import create_user_with_group

        create_user_with_group("aluno-403", "senha-teste-123", "aluno")
        self.client.login(username="aluno-403", password="senha-teste-123")
        response = self.client.get(reverse("area_professor"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(
            response,
            "Você está autenticado, mas não possui permissão",
            status_code=403,
        )
