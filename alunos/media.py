from questoes.media import nome_arquivo_seguro


def upload_foto_aluno(instance, filename):
    pasta = instance.pk or "tmp"
    return f"alunos/{pasta}/{nome_arquivo_seguro(filename)}"
