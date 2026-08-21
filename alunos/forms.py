from django import forms
from .models import Aluno

class AlunoForm(forms.ModelForm):
    class Meta:
        model = Aluno
        fields = ['nome', 'ra', 'serie']
        widgets = {
            'nome': forms.TextInput(attrs={'placeholder': 'Digite o nome do aluno'}),
            'ra': forms.TextInput(attrs={'placeholder': 'Digite o RA'}),
            'serie': forms.Select(),
        }