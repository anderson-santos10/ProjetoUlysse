from django import forms
from django.core.files.uploadedfile import UploadedFile

from .media import validar_imagem_enviada
from .models import Questao


class QuestaoForm(forms.ModelForm):

    remover_imagem = forms.BooleanField(
        required=False,
        label="Remover imagem",
        help_text="Cria uma nova versão sem imagem. A versão anterior continua com o arquivo histórico.",
    )

    class Meta:
        model = Questao

        fields = [
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
        ]

        widgets = {
            'serie': forms.Select(attrs={
                'class': 'input form-control',
            }),

            'dificuldade': forms.Select(attrs={
                'class': 'input form-control',
            }),

            'enunciado': forms.Textarea(attrs={
                'class': 'input form-control',
                'rows': 5,
                'placeholder': 'Digite o enunciado da questão...',
            }),

            'alternativa_a': forms.TextInput(attrs={
                'class': 'input form-control',
                'placeholder': 'Digite a alternativa A',
            }),

            'alternativa_b': forms.TextInput(attrs={
                'class': 'input form-control',
                'placeholder': 'Digite a alternativa B',
            }),

            'alternativa_c': forms.TextInput(attrs={
                'class': 'input form-control',
                'placeholder': 'Digite a alternativa C',
            }),

            'alternativa_d': forms.TextInput(attrs={
                'class': 'input form-control',
                'placeholder': 'Digite a alternativa D',
            }),

            'resposta_correta': forms.RadioSelect(attrs={
                'class': 'radio-row',
            }),
            'imagem': forms.FileInput(attrs={
                'class': 'input',
                'accept': 'image/jpeg,image/png,image/webp',
                'data-image-preview': 'preview-imagem-questao',
            }),
            'imagem_alt': forms.TextInput(attrs={
                'class': 'input form-control',
                'placeholder': 'Descreva a imagem para leitores de tela',
            }),
        }

    def clean_imagem(self):
        arquivo = self.cleaned_data.get('imagem')
        if isinstance(arquivo, UploadedFile):
            return validar_imagem_enviada(arquivo)
        return arquivo

    def save(self, commit=True):
        instance = super().save(commit=False)
        novo_upload = isinstance(self.cleaned_data.get('imagem'), UploadedFile)
        if self.cleaned_data.get('remover_imagem') and not novo_upload:
            instance.imagem = None
        if commit:
            instance.save()
            self.save_m2m()
        return instance
