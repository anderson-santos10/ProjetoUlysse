def calcular_xp(questoes, respostas, versoes=None):
    """
    Calcula o XP ganho pelo aluno na prova.

    XP base:

    Fácil   = 10 XP
    Médio   = 15 XP
    Difícil = 20 XP

    A partir do 3º acerto consecutivo:
    +5 XP de bônus por acerto.

    Qualquer erro zera a sequência.

    Quando versoes é informado, gabarito e dificuldade vêm da
    QuestaoVersao da tentativa, não do cadastro atual.
    """
    xp_total = 0
    sequencia_acertos = 0
    xp_dificuldade = {
        "facil": 10,
        "medio": 15,
        "dificil": 20,
    }
    versoes = versoes or {}

    for questao in questoes:
        conteudo = versoes.get(questao.id, questao)
        resposta = respostas.get(str(questao.id))

        if resposta != conteudo.resposta_correta:
            sequencia_acertos = 0
            continue

        sequencia_acertos += 1
        xp = xp_dificuldade.get(conteudo.dificuldade, 0)

        if sequencia_acertos >= 3:
            xp += 5

        xp_total += xp

    return xp_total
