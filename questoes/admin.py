from django.contrib import admin
from django.db import transaction

from .models import Avaliacao, AvaliacaoQuestao, Questao, QuestaoVersao, RespostaResultado, Resultado


@admin.register(Questao)
class QuestaoAdmin(admin.ModelAdmin):

    list_display = (
        'numero',
        'serie',
        'dificuldade',
        'resposta_correta',
        'versao_atual',
    )

    list_filter = (
        'serie',
        'dificuldade',
    )

    search_fields = (
        'enunciado',
    )

    raw_id_fields = (
        'versao_atual',
    )

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            super().save_model(request, obj, form, change)


@admin.register(QuestaoVersao)
class QuestaoVersaoAdmin(admin.ModelAdmin):

    list_display = (
        'questao',
        'versao',
        'serie',
        'dificuldade',
        'resposta_correta',
        'criado_em',
    )

    list_filter = (
        'serie',
        'dificuldade',
    )

    search_fields = (
        'enunciado',
        'questao__numero',
    )

    readonly_fields = (
        'questao',
        'versao',
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
        'criado_em',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Resultado)
class ResultadoAdmin(admin.ModelAdmin):

    list_display = (
        'aluno',
        'nota',
        'acertos',
        'erros',
        'total_questoes',
        'matricula',
        'avaliacao',
        'data',
    )

    list_filter = (
        'nota',
        'data',
    )

    search_fields = (
        'aluno__nome',
        'aluno__ra',
    )

    ordering = (
        '-nota',
        '-data',
    )


@admin.register(RespostaResultado)
class RespostaResultadoAdmin(admin.ModelAdmin):

    list_display = (
        'resultado',
        'questao',
        'questao_versao',
        'resposta',
        'resposta_correta',
        'correta',
    )

    list_filter = (
        'correta',
    )

    search_fields = (
        'resultado__aluno__nome',
        'questao__numero',
    )


class AvaliacaoQuestaoInline(admin.TabularInline):
    model = AvaliacaoQuestao
    extra = 0
    raw_id_fields = ("questao", "questao_versao")


@admin.register(Avaliacao)
class AvaliacaoAdmin(admin.ModelAdmin):
    list_display = (
        "titulo",
        "turma",
        "status",
        "criado_por",
        "data_inicio",
        "data_fim",
    )
    list_filter = ("status", "serie")
    search_fields = ("titulo",)
    inlines = (AvaliacaoQuestaoInline,)
    raw_id_fields = ("turma", "criado_por")

