from django.contrib import admin

from .models import Aluno


@admin.register(Aluno)
class AlunoAdmin(admin.ModelAdmin):

    list_display = (
        'nome',
        'ra',
        'serie',
    )

    list_filter = (
        'serie',
    )

    search_fields = (
        'nome',
        'ra',
    )