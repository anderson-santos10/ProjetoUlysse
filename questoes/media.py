from io import BytesIO
from pathlib import Path
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.files.images import get_image_dimensions
from django.utils.text import get_valid_filename
from PIL import Image, UnidentifiedImageError

FORMATOS_PERMITIDOS = {"JPEG", "PNG", "WEBP"}
EXTENSOES_PERMITIDAS = {".jpg", ".jpeg", ".png", ".webp"}
TAMANHO_MAXIMO_BYTES = 5 * 1024 * 1024
PIXELS_MAXIMOS = 25_000_000

MENSAGEM_TIPO = "Envie uma imagem JPEG, PNG ou WEBP."
MENSAGEM_TAMANHO = "A imagem deve ter no máximo 5 MB."
MENSAGEM_INVALIDA = "O arquivo enviado não é uma imagem válida."
MENSAGEM_RESOLUCAO = "A imagem tem resolução alta demais para ser aceita."


def nome_arquivo_seguro(filename):
    original = get_valid_filename(Path(filename or "imagem").name)
    ext = Path(original).suffix.lower()
    if ext not in EXTENSOES_PERMITIDAS:
        ext = ".png"
    return f"{uuid4().hex}{ext}"


def upload_imagem_questao(instance, filename):
    pasta = getattr(instance, "questao_id", None) or getattr(instance, "pk", None) or "tmp"
    return f"questoes/{pasta}/{nome_arquivo_seguro(filename)}"


def validar_imagem_enviada(arquivo):
    if not arquivo:
        return arquivo
    tamanho = getattr(arquivo, "size", None)
    if tamanho is not None and tamanho > TAMANHO_MAXIMO_BYTES:
        raise ValidationError(MENSAGEM_TAMANHO)

    nome = getattr(arquivo, "name", "") or ""
    ext = Path(nome).suffix.lower()
    if ext and ext not in EXTENSOES_PERMITIDAS:
        raise ValidationError(MENSAGEM_TIPO)

    posicao = arquivo.tell() if hasattr(arquivo, "tell") else 0
    try:
        conteudo = arquivo.read()
    finally:
        if hasattr(arquivo, "seek"):
            arquivo.seek(posicao)

    if len(conteudo) > TAMANHO_MAXIMO_BYTES:
        raise ValidationError(MENSAGEM_TAMANHO)
    if not conteudo:
        raise ValidationError(MENSAGEM_INVALIDA)

    try:
        with Image.open(BytesIO(conteudo)) as imagem:
            imagem.verify()
        with Image.open(BytesIO(conteudo)) as imagem:
            formato = (imagem.format or "").upper()
            largura, altura = imagem.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError(MENSAGEM_INVALIDA) from exc

    if formato not in FORMATOS_PERMITIDOS:
        raise ValidationError(MENSAGEM_TIPO)
    if (largura or 0) * (altura or 0) > PIXELS_MAXIMOS:
        raise ValidationError(MENSAGEM_RESOLUCAO)

    try:
        get_image_dimensions(arquivo)
    except Exception as exc:
        raise ValidationError(MENSAGEM_INVALIDA) from exc
    if hasattr(arquivo, "seek"):
        arquivo.seek(0)
    return arquivo
