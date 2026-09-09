from django.conf import settings
from django.db import models

from alunos.models import Aluno
from .media import upload_imagem_questao


CAMPOS_CONTEUDO_QUESTAO = frozenset({
    'numero',
    'serie',
    'dificuldade',
    'enunciado',
    'alternativa_a',
    'alternativa_b',
    'alternativa_c',
    'alternativa_d',
    'resposta_correta',
    'imagem',
    'imagem_alt',
})

MENSAGEM_ALTERACAO_DIRETA = (
    'Questao deve ser alterada através do fluxo de versionamento.'
)


class QuestaoQuerySet(models.QuerySet):

    def update(self, **kwargs):
        if set(kwargs) & CAMPOS_CONTEUDO_QUESTAO:
            raise ValueError(MENSAGEM_ALTERACAO_DIRETA)
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        if set(fields) & CAMPOS_CONTEUDO_QUESTAO:
            raise ValueError(MENSAGEM_ALTERACAO_DIRETA)
        return super().bulk_update(objs, fields, batch_size=batch_size)


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

    imagem = models.ImageField(
        upload_to=upload_imagem_questao,
        blank=True,
        null=True,
        verbose_name='Imagem da questão',
    )

    imagem_alt = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Texto alternativo da imagem',
        help_text='Descrição para leitores de tela. Opcional, mas recomendado se houver imagem.',
    )

    criado_em = models.DateTimeField(
        auto_now_add=True
    )

    versao_atual = models.ForeignKey(
        'QuestaoVersao',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='+',
        verbose_name='Versão atual',
    )

    class Meta:

        constraints = [
            models.UniqueConstraint(
                fields=['serie', 'numero'],
                name='unique_numero_por_serie'
            )
        ]

        ordering = ['serie', 'numero']

    objects = QuestaoQuerySet.as_manager()

    def save(self, *args, **kwargs):

        from .versionamento import (
            criar_versao,
            garantir_primeira_versao,
            questao_diverge_da_versao_atual,
        )

        criando = self._state.adding
        deve_versionar = False
        if not criando:
            deve_versionar = questao_diverge_da_versao_atual(self)

        # Só gera o número quando a questão é nova
        if criando:

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

        if criando:
            garantir_primeira_versao(self)
        elif deve_versionar:
            criar_versao(self)
        elif not self.versao_atual_id:
            garantir_primeira_versao(self)

    def __str__(self):

        return f'Questão {self.numero} - {self.get_serie_display()}'


class QuestaoVersaoQuerySet(models.QuerySet):

    def update(self, **kwargs):
        raise ValueError('QuestaoVersao é imutável depois de criada.')

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValueError('QuestaoVersao é imutável depois de criada.')


class QuestaoVersao(models.Model):
    """
    Instantâneo imutável do conteúdo pedagógico de uma Questao.
    A identidade continua em Questao; o histórico aponta para esta versão.
    """

    questao = models.ForeignKey(
        Questao,
        on_delete=models.CASCADE,
        related_name='versoes',
        verbose_name='Questão',
    )

    versao = models.PositiveIntegerField(
        verbose_name='Número da versão',
    )

    numero = models.PositiveIntegerField(
        verbose_name='Número da questão na época',
    )

    serie = models.CharField(
        max_length=2,
        choices=Questao.SERIE_CHOICES,
        verbose_name='Série',
    )

    dificuldade = models.CharField(
        max_length=10,
        choices=Questao.DIFICULDADE_CHOICES,
        verbose_name='Grau de dificuldade',
    )

    enunciado = models.TextField(
        verbose_name='Enunciado',
    )

    alternativa_a = models.CharField(
        max_length=500,
        verbose_name='Alternativa A',
    )

    alternativa_b = models.CharField(
        max_length=500,
        verbose_name='Alternativa B',
    )

    alternativa_c = models.CharField(
        max_length=500,
        verbose_name='Alternativa C',
    )

    alternativa_d = models.CharField(
        max_length=500,
        verbose_name='Alternativa D',
    )

    resposta_correta = models.CharField(
        max_length=1,
        choices=Questao.RESPOSTA_CHOICES,
        verbose_name='Resposta correta',
    )

    imagem = models.ImageField(
        upload_to=upload_imagem_questao,
        blank=True,
        null=True,
        verbose_name='Imagem da questão',
    )

    imagem_alt = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Texto alternativo da imagem',
    )

    criado_em = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Criada em',
    )

    class Meta:
        verbose_name = 'Versão da questão'
        verbose_name_plural = 'Versões das questões'
        ordering = ['questao', 'versao']
        constraints = [
            models.UniqueConstraint(
                fields=['questao', 'versao'],
                name='unique_versao_por_questao',
            )
        ]

    objects = QuestaoVersaoQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError('QuestaoVersao é imutável depois de criada.')
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Questão {self.numero} v{self.versao}'


class Avaliacao(models.Model):
    """
    Atividade configurada (simulado dirigido a uma turma).
    O questionário livre por série continua em ListaQuestoesView.
    Questões históricas ficam em AvaliacaoQuestao.questao_versao.
    """

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", "Rascunho"
        PUBLICADA = "publicada", "Publicada"
        ENCERRADA = "encerrada", "Encerrada"

    titulo = models.CharField(max_length=180)
    descricao = models.TextField(blank=True)
    turma = models.ForeignKey(
        "alunos.Turma",
        on_delete=models.PROTECT,
        related_name="avaliacoes",
    )
    serie = models.CharField(max_length=10, choices=Questao.SERIE_CHOICES)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="avaliacoes_criadas",
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.RASCUNHO,
    )
    data_inicio = models.DateTimeField(null=True, blank=True)
    data_fim = models.DateTimeField(null=True, blank=True)
    tempo_limite_minutos = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Tempo limite (minutos)",
        help_text="Vazio = sem limite. Validado no servidor.",
    )
    tentativas_maximas = models.PositiveIntegerField(default=1)
    publicado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Avaliação"
        verbose_name_plural = "Avaliações"
        ordering = ["-criado_em"]
        permissions = [
            ("view_relatorio_pedagogico", "Pode ver relatórios pedagógicos"),
        ]

    def __str__(self):
        return self.titulo


class AvaliacaoQuestao(models.Model):
    avaliacao = models.ForeignKey(
        Avaliacao,
        on_delete=models.CASCADE,
        related_name="itens",
    )
    questao = models.ForeignKey(
        Questao,
        on_delete=models.PROTECT,
        related_name="itens_avaliacao",
    )
    questao_versao = models.ForeignKey(
        QuestaoVersao,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="itens_avaliacao",
        verbose_name="Versão congelada",
    )
    ordem = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Questão da avaliação"
        ordering = ["ordem", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["avaliacao", "questao"],
                name="unique_questao_por_avaliacao",
            ),
        ]

    def __str__(self):
        return f"{self.avaliacao} · Q{self.questao.numero}"


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

    matricula = models.ForeignKey(
        'alunos.Matricula',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='resultados',
        verbose_name='Matrícula no momento da prova',
        help_text=(
            'Vínculo turma–aluno vigente quando a prova foi finalizada. '
            'Nulo em tentativas anteriores às turmas.'
        ),
    )

    avaliacao = models.ForeignKey(
        "Avaliacao",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="resultados",
        verbose_name="Avaliação",
        help_text="Nulo no simulado livre por série.",
    )

    def __str__(self):

        return f'{self.aluno.nome} - Nota {self.nota}'


class RespostaResultado(models.Model):
    """
    Resposta individual de uma tentativa.

    A letra armazenada é a alternativa original da Questao (A–D),
    não a letra visual após o embaralhamento na tela.

    Se a Questao for editada depois, o histórico usa QuestaoVersao quando
    existir. Resultados antigos podem não ter linhas aqui.
    Respostas anteriores ao versionamento podem ter questao_versao nulo.
    """

    resultado = models.ForeignKey(
        Resultado,
        on_delete=models.CASCADE,
        related_name='respostas_questoes',
        verbose_name='Resultado',
    )

    questao = models.ForeignKey(
        Questao,
        on_delete=models.PROTECT,
        related_name='respostas_resultados',
        verbose_name='Questão',
    )

    resposta = models.CharField(
        max_length=1,
        choices=Questao.RESPOSTA_CHOICES,
        null=True,
        blank=True,
        verbose_name='Resposta do aluno',
    )

    resposta_correta = models.CharField(
        max_length=1,
        choices=Questao.RESPOSTA_CHOICES,
        verbose_name='Gabarito na prova',
    )

    questao_versao = models.ForeignKey(
        'QuestaoVersao',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='respostas',
        verbose_name='Versão utilizada',
    )

    correta = models.BooleanField(
        verbose_name='Acertou',
    )

    class Meta:
        verbose_name = 'Resposta do resultado'
        verbose_name_plural = 'Respostas dos resultados'
        constraints = [
            models.UniqueConstraint(
                fields=['resultado', 'questao'],
                name='unique_resposta_por_questao_no_resultado',
            )
        ]

    def clean(self):
        from .integridade import validar_par_questao_versao

        super().clean()
        if self.questao_id and self.questao_versao_id:
            validar_par_questao_versao(
                self.questao,
                self.questao_versao,
                obrigatorio=True,
            )

    def save(self, *args, **kwargs):
        if self.questao_versao_id:
            self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        letra = self.resposta or '—'
        return f'{self.resultado_id} / Q{self.questao_id}: {letra}'