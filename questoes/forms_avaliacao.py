from django import forms

from alunos.escopo import queryset_turmas_visiveis
from alunos.models import Aluno

from .avaliacoes import validar_datas_avaliacao
from .models import Avaliacao, Questao


class AvaliacaoForm(forms.ModelForm):
    questoes = forms.ModelMultipleChoiceField(
        queryset=Questao.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Questões",
    )

    class Meta:
        model = Avaliacao
        fields = [
            "titulo",
            "descricao",
            "turma",
            "data_inicio",
            "data_fim",
            "tempo_limite_minutos",
            "tentativas_maximas",
        ]
        widgets = {
            "titulo": forms.TextInput(attrs={"class": "input"}),
            "descricao": forms.Textarea(attrs={"class": "input", "rows": 3}),
            "turma": forms.Select(attrs={"class": "input"}),
            "data_inicio": forms.DateTimeInput(
                attrs={"class": "input", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "data_fim": forms.DateTimeInput(
                attrs={"class": "input", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "tempo_limite_minutos": forms.NumberInput(attrs={"class": "input", "min": 1}),
            "tentativas_maximas": forms.NumberInput(attrs={"class": "input", "min": 1}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        turmas = queryset_turmas_visiveis(user).filter(ativa=True)
        self.fields["turma"].queryset = turmas
        serie = None
        if self.instance.pk:
            serie = self.instance.serie
        elif self.data.get("turma"):
            turma = turmas.filter(pk=self.data.get("turma")).first()
            serie = turma.serie if turma else None
        elif turmas.count() == 1:
            serie = turmas.first().serie
        if serie:
            self.fields["questoes"].queryset = Questao.objects.filter(
                serie=serie
            ).order_by("numero")
        else:
            self.fields["questoes"].queryset = Questao.objects.none()
            self.fields["questoes"].help_text = (
                "Salve a avaliação com a turma para listar as questões da série."
            )
        if self.instance.pk:
            self.fields["questoes"].initial = list(
                self.instance.itens.values_list("questao_id", flat=True)
            )
        for campo in ("data_inicio", "data_fim"):
            self.fields[campo].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]

    def clean(self):
        dados = super().clean()
        validar_datas_avaliacao(dados.get("data_inicio"), dados.get("data_fim"))
        turma = dados.get("turma")
        if turma and self.user:
            if not queryset_turmas_visiveis(self.user).filter(pk=turma.pk).exists():
                raise forms.ValidationError("Turma fora do seu escopo.")
        return dados


class RelatorioFiltroForm(forms.Form):
    periodo = forms.CharField(required=False)
    turma = forms.IntegerField(required=False)
    serie = forms.CharField(required=False)
    aluno = forms.ModelChoiceField(
        queryset=Aluno.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "input"}),
    )
