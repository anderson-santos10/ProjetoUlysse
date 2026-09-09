from django import forms
from django.core.files.uploadedfile import UploadedFile

from questoes.media import validar_imagem_enviada

from .models import Aluno


class AlunoForm(forms.ModelForm):
    remover_foto = forms.BooleanField(
        required=False,
        label='Remover foto',
    )

    class Meta:
        model = Aluno
        fields = ['nome', 'ra', 'serie', 'foto', 'mostrar_foto_ranking']
        widgets = {
            'nome': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Digite o nome do aluno',
                'autocomplete': 'name',
                'autofocus': True,
            }),
            'ra': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Digite o RA',
                'autocomplete': 'off',
            }),
            'serie': forms.Select(attrs={'class': 'input'}),
            'foto': forms.FileInput(attrs={
                'class': 'input',
                'accept': 'image/jpeg,image/png,image/webp',
                'data-image-preview': 'preview-foto-aluno',
            }),
            'mostrar_foto_ranking': forms.CheckboxInput(),
        }

    def clean_foto(self):
        arquivo = self.cleaned_data.get('foto')
        if isinstance(arquivo, UploadedFile):
            return validar_imagem_enviada(arquivo)
        return arquivo

    def save(self, commit=True):
        instance = super().save(commit=False)
        novo_upload = isinstance(self.cleaned_data.get('foto'), UploadedFile)
        if self.cleaned_data.get('remover_foto') and not novo_upload:
            instance.foto = None
        if commit:
            instance.save()
            self.save_m2m()
        return instance
