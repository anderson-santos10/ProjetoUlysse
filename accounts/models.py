from django.conf import settings
from django.db import models


class Role(models.TextChoices):
    ALUNO = "aluno", "Aluno"
    PROFESSOR = "professor", "Professor"
    COORDENADOR = "coordenador", "Coordenador"
    DIRETOR = "diretor", "Diretor"


class Profile(models.Model):
    """Dados complementares. Autorização: Groups → Permissions."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        blank=True,
        default="",
        verbose_name="Perfil (informativo)",
        help_text=(
            "Campo complementar. O acesso ao sistema é definido "
            "por grupos e permissões Django."
        ),
    )

    class Meta:
        verbose_name = "Perfil"
        verbose_name_plural = "Perfis"
        permissions = [
            ("access_area_aluno", "Pode acessar a área do aluno"),
            ("access_area_professor", "Pode acessar a área do professor"),
            ("access_area_coordenacao", "Pode acessar a área da coordenação"),
            ("access_area_direcao", "Pode acessar a área da direção"),
        ]

    def __str__(self):
        if self.role:
            return f"{self.user.get_username()} ({self.get_role_display()})"
        return self.user.get_username()
