from django.db import transaction
from django.db.models import Max

from .models import Questao, QuestaoVersao


class VersaoTentativaInvalida(ValueError):
    """Mapa de versões da sessão está presente, mas é inválido ou adulterado."""


CAMPOS_CONTEUDO = (
    "serie",
    "dificuldade",
    "enunciado",
    "alternativa_a",
    "alternativa_b",
    "alternativa_c",
    "alternativa_d",
    "resposta_correta",
    "imagem",
    "imagem_alt",
)


def _valor_campo(obj, campo):
    valor = getattr(obj, campo)
    if campo == "imagem":
        return getattr(valor, "name", "") or ""
    return valor


def snapshot_conteudo(questao):
    dados = {campo: _valor_campo(questao, campo) for campo in CAMPOS_CONTEUDO}
    dados["numero"] = questao.numero
    return dados


def questao_diverge_da_versao_atual(questao):
    if not questao.versao_atual_id:
        return False
    atual = questao.versao_atual
    if atual.questao_id != questao.pk:
        return True
    if atual.numero != questao.numero:
        return True
    return any(
        _valor_campo(questao, campo) != _valor_campo(atual, campo)
        for campo in CAMPOS_CONTEUDO
    )


def criar_versao(questao):
    with transaction.atomic():
        locked = Questao.objects.select_for_update().get(pk=questao.pk)
        proximo = (
            QuestaoVersao.objects
            .filter(questao_id=locked.pk)
            .aggregate(n=Max("versao"))["n"]
            or 0
        ) + 1
        versao = QuestaoVersao.objects.create(
            questao=locked,
            versao=proximo,
            **snapshot_conteudo(questao),
        )
        Questao.objects.filter(pk=locked.pk).update(versao_atual=versao)
        questao.versao_atual = versao
        return versao


def garantir_primeira_versao(questao):
    atual = questao.versao_atual if questao.versao_atual_id else None
    if atual is not None and atual.questao_id == questao.id:
        return atual
    existente = (
        questao.versoes
        .filter(questao_id=questao.id)
        .order_by("versao")
        .first()
    )
    if existente:
        Questao.objects.filter(pk=questao.pk).update(versao_atual=existente)
        questao.versao_atual = existente
        return existente
    return criar_versao(questao)


def formulario_alterou_conteudo(form):
    alterados = set(form.changed_data)
    return bool(alterados & set(CAMPOS_CONTEUDO))


def aplicar_edicao_com_versao(form):
    with transaction.atomic():
        pk = form.instance.pk
        if pk:
            Questao.objects.select_for_update().get(pk=pk)
        return form.save()


def mapa_versoes_atuais(questoes):
    mapa = {}
    for questao in questoes:
        versao = questao.versao_atual
        if versao is None or versao.questao_id != questao.id:
            versao = garantir_primeira_versao(questao)
        mapa[str(questao.id)] = versao.id
    return mapa


def _parse_id_versao(valor):
    if valor is None or valor == "":
        return None, "ausente"
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None, "invalido"
    if numero <= 0:
        return None, "invalido"
    return numero, "ok"


def _mapa_da_sessao(session):
    if session is None or "questoes_versoes" not in session:
        return None
    bruto = session.get("questoes_versoes")
    if not isinstance(bruto, dict) or not bruto:
        return None
    return bruto


def resolver_versoes_tentativa(questoes, session, estrito=False):
    """
    Resolve as versões congeladas no início da prova.

    Sem mapa na sessão (prova aberta antes do versionamento):
    usa a versão atual. Não reconstrói histórico inexistente.

    Com mapa presente e adulterado (versão de outra questão, ID
    inexistente, valor inválido): levanta VersaoTentativaInvalida
    quando estrito=True. Não substitui em silêncio.
    """
    bruto = _mapa_da_sessao(session)
    legado = bruto is None

    ids = []
    if bruto:
        for questao in questoes:
            numero, status = _parse_id_versao(bruto.get(str(questao.id)))
            if status == "ok":
                ids.append(numero)

    carregadas = {}
    if ids:
        for versao in QuestaoVersao.objects.filter(id__in=ids):
            carregadas[versao.id] = versao

    resultado = {}
    sem_versao = []
    adulterado = False

    for questao in questoes:
        if legado:
            sem_versao.append(questao)
            continue
        numero, status = _parse_id_versao(bruto.get(str(questao.id)))
        if status != "ok":
            adulterado = True
            sem_versao.append(questao)
            continue
        versao = carregadas.get(numero)
        if versao is None or versao.questao_id != questao.id:
            adulterado = True
            continue
        resultado[questao.id] = versao

    if estrito and adulterado:
        raise VersaoTentativaInvalida(
            "Mapa de versões da tentativa é inválido ou adulterado."
        )

    if sem_versao or len(resultado) < len(questoes):
        faltantes = [
            questao for questao in questoes if questao.id not in resultado
        ]
        if estrito and not legado and faltantes:
            raise VersaoTentativaInvalida(
                "Mapa de versões da tentativa é inválido ou adulterado."
            )
        ids_faltantes = [item.id for item in faltantes]
        por_id = {
            item.id: item
            for item in Questao.objects.filter(id__in=ids_faltantes).select_related(
                "versao_atual"
            )
        }
        for questao in faltantes:
            atual = por_id.get(questao.id, questao)
            resultado[questao.id] = garantir_primeira_versao(atual)

    return resultado
