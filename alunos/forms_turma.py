from django import forms

from .escopo import usuarios_podem_ser_responsaveis
from .models import Aluno, Matricula, Turma


class TurmaForm(forms.ModelForm):
    class Meta:
        model = Turma
        fields = [
            "nome",
            "serie",
            "ano_letivo",
            "ativa",
            "professor_responsavel",
        ]
        widgets = {
            "nome": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "Ex.: A",
                "autocomplete": "off",
            }),
            "serie": forms.Select(attrs={"class": "input"}),
            "ano_letivo": forms.NumberInput(attrs={
                "class": "input",
                "min": 2000,
                "max": 2100,
            }),
            "professor_responsavel": forms.Select(attrs={"class": "input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["professor_responsavel"].queryset = usuarios_podem_ser_responsaveis()
        self.fields["professor_responsavel"].label_from_instance = (
            lambda user: user.get_username()
        )


class MatricularAlunoForm(forms.Form):
    aluno = forms.ModelChoiceField(
        queryset=Aluno.objects.none(),
        label="Aluno",
        widget=forms.Select(attrs={"class": "input"}),
    )

    def __init__(self, *args, turma=None, **kwargs):
        super().__init__(*args, **kwargs)
        ocupados = Matricula.objects.filter(ativa=True).values_list("aluno_id", flat=True)
        queryset = Aluno.objects.exclude(pk__in=ocupados).order_by("nome")
        if turma is not None:
            queryset = queryset.filter(serie=turma.serie)
        self.fields["aluno"].queryset = queryset


class TransferirAlunoForm(forms.Form):
    aluno = forms.ModelChoiceField(
        queryset=Aluno.objects.none(),
        label="Aluno",
        widget=forms.Select(attrs={"class": "input"}),
    )
    turma_destino = forms.ModelChoiceField(
        queryset=Turma.objects.none(),
        label="Turma de destino",
        widget=forms.Select(attrs={"class": "input"}),
    )

    def __init__(self, *args, turma_origem=None, turmas_destino=None, **kwargs):
        super().__init__(*args, **kwargs)
        if turma_origem is not None:
            self.fields["aluno"].queryset = (
                Aluno.objects
                .filter(matriculas__turma=turma_origem, matriculas__ativa=True)
                .order_by("nome")
            )
        destino = turmas_destino if turmas_destino is not None else Turma.objects.none()
        if turma_origem is not None:
            destino = destino.exclude(pk=turma_origem.pk)
        self.fields["turma_destino"].queryset = destino.filter(ativa=True)
