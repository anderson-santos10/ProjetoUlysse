from django.contrib import admin

from .models import Questao, Resultado


@admin.register(Questao)
class QuestaoAdmin(admin.ModelAdmin):

    list_display = (
        'numero',
        'serie',
        'dificuldade',
        'resposta_correta',
    )

    list_filter = (
        'serie',
        'dificuldade',
    )

    search_fields = (
        'enunciado',
    )


@admin.register(Resultado)
class ResultadoAdmin(admin.ModelAdmin):

    list_display = (
        'aluno',
        'nota',
        'acertos',
        'erros',
        'total_questoes',
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