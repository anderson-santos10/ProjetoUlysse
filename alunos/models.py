from django.conf import settings
from django.db import models

from .media import upload_foto_aluno


class Aluno(models.Model):

    SERIES = [
        ('5', '5º Ano'),
        ('6', '6º Ano'),
        ('7', '7º Ano'),
        ('8', '8º Ano'),
        ('9', '9º Ano'),
        ('1S', '1ª Série'),
        ('2S', '2ª Série'),
        ('3S', '3ª Série'),
    ]

    nome = models.CharField(
        max_length=150
    )

    ra = models.CharField(
        max_length=30,
        unique=True
    )

    serie = models.CharField(
        max_length=10,
        choices=SERIES
    )

    xp = models.PositiveIntegerField(
        default=0,
        verbose_name='XP'
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='aluno',
        verbose_name='Usuário',
    )

    foto = models.ImageField(
        upload_to=upload_foto_aluno,
        blank=True,
        null=True,
        verbose_name='Foto',
    )

    mostrar_foto_ranking = models.BooleanField(
        default=False,
        verbose_name='Mostrar foto no ranking',
        help_text='Somente com esta opção marcada a foto aparece no ranking público.',
    )

    def inicial_nome(self):
        nome = (self.nome or '').strip()
        return nome[:1].upper() if nome else '?'

    def exibe_foto_no_ranking(self):
        return bool(self.mostrar_foto_ranking and self.foto)

    def matricula_ativa(self):
        """Vínculo vigente. Não usar Aluno.serie como se fosse turma."""
        return (
            self.matriculas
            .select_related("turma", "turma__professor_responsavel")
            .filter(ativa=True)
            .first()
        )

    def __str__(self):
        return f"{self.nome} - RA: {self.ra}"


class Turma(models.Model):
    """
    Agrupamento pedagógico (ex.: 6º A em 2026) com um professor responsável.

    Não substitui Aluno.serie: o quiz e o ranking público continuam
    pela série do cadastro. A turma organiza gestão e análise.
    """

    nome = models.CharField(
        max_length=80,
        verbose_name="Nome",
        help_text="Identificação da turma na série, por exemplo A ou Integral.",
    )
    serie = models.CharField(
        max_length=10,
        choices=Aluno.SERIES,
        verbose_name="Série",
    )
    ano_letivo = models.PositiveIntegerField(
        verbose_name="Ano letivo",
    )
    ativa = models.BooleanField(
        default=True,
        verbose_name="Ativa",
    )
    professor_responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="turmas_responsaveis",
        verbose_name="Professor responsável",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Turma"
        verbose_name_plural = "Turmas"
        ordering = ["-ano_letivo", "serie", "nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["nome", "serie", "ano_letivo"],
                name="unique_turma_nome_serie_ano",
            ),
        ]

    def __str__(self):
        return f"{self.get_serie_display()} {self.nome} ({self.ano_letivo})"


class Matricula(models.Model):
    """
    Histórico de vínculo aluno–turma.

    A turma atual do aluno é a matrícula com ativa=True.
    Encerrar ou transferir não apaga este registro. Resultados
    apontam para a matrícula vigente no momento da prova.
    """

    aluno = models.ForeignKey(
        Aluno,
        on_delete=models.CASCADE,
        related_name="matriculas",
        verbose_name="Aluno",
    )
    turma = models.ForeignKey(
        Turma,
        on_delete=models.PROTECT,
        related_name="matriculas",
        verbose_name="Turma",
    )
    data_inicio = models.DateField(verbose_name="Início")
    data_fim = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fim",
    )
    ativa = models.BooleanField(
        default=True,
        verbose_name="Ativa",
    )

    class Meta:
        verbose_name = "Matrícula"
        verbose_name_plural = "Matrículas"
        ordering = ["-data_inicio", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["aluno"],
                condition=models.Q(ativa=True),
                name="unique_matricula_ativa_por_aluno",
            ),
        ]

    def __str__(self):
        estado = "ativa" if self.ativa else "encerrada"
        return f"{self.aluno.nome} em {self.turma} ({estado})"
