from django.contrib.admin import ModelAdmin, register, TabularInline

from .models import Aluno, Matricula, Turma


class MatriculaInline(TabularInline):
    model = Matricula
    extra = 0
    fields = ("turma", "data_inicio", "data_fim", "ativa")
    readonly_fields = ("turma", "data_inicio", "data_fim", "ativa")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@register(Aluno)
class AlunoAdmin(ModelAdmin):

    list_display = (
        "nome",
        "ra",
        "serie",
        "mostrar_foto_ranking",
        "user",
    )
    list_filter = ("serie",)
    search_fields = ("nome", "ra")
    inlines = (MatriculaInline,)


@register(Turma)
class TurmaAdmin(ModelAdmin):
    list_display = (
        "nome",
        "serie",
        "ano_letivo",
        "ativa",
        "professor_responsavel",
    )
    list_filter = ("serie", "ano_letivo", "ativa")
    search_fields = ("nome", "professor_responsavel__username")
    raw_id_fields = ("professor_responsavel",)

    def has_delete_permission(self, request, obj=None):
        return False


@register(Matricula)
class MatriculaAdmin(ModelAdmin):
    list_display = ("aluno", "turma", "data_inicio", "data_fim", "ativa")
    list_filter = ("ativa", "turma__ano_letivo", "turma__serie")
    search_fields = ("aluno__nome", "aluno__ra", "turma__nome")
    raw_id_fields = ("aluno", "turma")

    def has_delete_permission(self, request, obj=None):
        return False
