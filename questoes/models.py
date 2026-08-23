from django.db import models

from alunos.models import Aluno


class Questao(models.Model):

    SERIE_CHOICES = [
        ('5', '5º Ano'),
        ('6', '6º Ano'),
        ('7', '7º Ano'),
        ('8', '8º Ano'),
        ('9', '9º Ano'),
        ('1S', '1ª Série'),
        ('2S', '2ª Série'),
        ('3S', '3ª Série'),
    ]

    DIFICULDADE_CHOICES = [
        ('facil', 'Fácil'),
        ('medio', 'Médio'),
        ('dificil', 'Difícil'),
    ]

    RESPOSTA_CHOICES = [
        ('A', 'A'),
        ('B', 'B'),
        ('C', 'C'),
        ('D', 'D'),
    ]

    # Número gerado automaticamente
    numero = models.PositiveIntegerField(
        verbose_name='Número da questão',
        editable=False
    )

    serie = models.CharField(
        max_length=2,
        choices=SERIE_CHOICES,
        verbose_name='Série'
    )

    dificuldade = models.CharField(
        max_length=10,
        choices=DIFICULDADE_CHOICES,
        verbose_name='Grau de dificuldade'
    )

    enunciado = models.TextField(
        verbose_name='Enunciado'
    )

    alternativa_a = models.CharField(
        max_length=500,
        verbose_name='Alternativa A'
    )

    alternativa_b = models.CharField(
        max_length=500,
        verbose_name='Alternativa B'
    )

    alternativa_c = models.CharField(
        max_length=500,
        verbose_name='Alternativa C'
    )

    alternativa_d = models.CharField(
        max_length=500,
        verbose_name='Alternativa D'
    )

    resposta_correta = models.CharField(
        max_length=1,
        choices=RESPOSTA_CHOICES,
        verbose_name='Resposta correta'
    )

    criado_em = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:

        constraints = [
            models.UniqueConstraint(
                fields=['serie', 'numero'],
                name='unique_numero_por_serie'
            )
        ]

        ordering = ['serie', 'numero']

    def save(self, *args, **kwargs):

        # Só gera o número quando a questão é nova
        if self._state.adding:

            ultimo_numero = (
                Questao.objects
                .filter(serie=self.serie)
                .order_by('-numero')
                .values_list('numero', flat=True)
                .first()
            )

            if ultimo_numero is None:
                self.numero = 1
            else:
                self.numero = ultimo_numero + 1

        super().save(*args, **kwargs)

    def __str__(self):

        return (
            f'Questão {self.numero} - '
            f'{self.get_serie_display()}'
        )


class Resultado(models.Model):

    aluno = models.ForeignKey(
        Aluno,
        on_delete=models.CASCADE,
        related_name='resultados'
    )

    acertos = models.IntegerField()

    erros = models.IntegerField()

    total_questoes = models.IntegerField()

    nota = models.DecimalField(
        max_digits=4,
        decimal_places=2
    )

    xp_ganho = models.PositiveIntegerField(
        default=0
    )

    tempo_segundos = models.PositiveIntegerField(
        default=0
    )

    data = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):

        return f'{self.aluno.nome} - Nota {self.nota}'