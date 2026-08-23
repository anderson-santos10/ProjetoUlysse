from django.db import models


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

    def __str__(self):
        return f"{self.nome} - RA: {self.ra}"