from django import forms

from .models import Questao


class QuestaoForm(forms.ModelForm):

    class Meta:
        model = Questao

        fields = [
            'numero',
            'serie',
            'dificuldade',
            'enunciado',
            'alternativa_a',
            'alternativa_b',
            'alternativa_c',
            'alternativa_d',
            'resposta_correta',
        ]

        widgets = {
            'numero': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: 1',
                'min': 1,
            }),

            'serie': forms.Select(attrs={
                'class': 'form-control',
            }),

            'dificuldade': forms.Select(attrs={
                'class': 'form-control',
            }),

            'enunciado': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Digite o enunciado da questão...',
            }),

            'alternativa_a': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Digite a alternativa A',
            }),

            'alternativa_b': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Digite a alternativa B',
            }),

            'alternativa_c': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Digite a alternativa C',
            }),

            'alternativa_d': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Digite a alternativa D',
            }),

            'resposta_correta': forms.Select(attrs={
                'class': 'form-control',
            }),
        }