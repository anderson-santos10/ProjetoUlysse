from .integridade import validar_par_questao_versao
from .models import RespostaResultado

LETRAS_VALIDAS = frozenset({"A", "B", "C", "D"})


def letra_original_ou_nenhuma(valor):
    if valor in LETRAS_VALIDAS:
        return valor
    return None


def montar_respostas_resultado(resultado, questoes, respostas, versoes):
    if not isinstance(respostas, dict):
        respostas = {}

    itens = []
    for questao in questoes:
        versao = versoes[questao.id]
        validar_par_questao_versao(questao, versao, obrigatorio=True)
        escolhida = letra_original_ou_nenhuma(respostas.get(str(questao.id)))
        gabarito = versao.resposta_correta
        itens.append(
            RespostaResultado(
                resultado=resultado,
                questao=questao,
                questao_versao=versao,
                resposta=escolhida,
                resposta_correta=gabarito,
                correta=bool(escolhida is not None and escolhida == gabarito),
            )
        )
    return itens


def persistir_respostas_resultado(resultado, questoes, respostas, versoes):
    itens = montar_respostas_resultado(resultado, questoes, respostas, versoes)
    if itens:
        RespostaResultado.objects.bulk_create(itens)
    return itens
