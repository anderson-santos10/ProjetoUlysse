import random
from datetime import timedelta

from django.views.generic import ListView, CreateView
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.utils import timezone

from .forms import QuestaoForm
from .models import Questao, Resultado
from alunos.models import Aluno


class ListaQuestoesView(ListView):

    model = Questao
    template_name = 'questoes_list.html'
    context_object_name = 'questoes'

    # =====================================================
    # QUESTÕES DA SÉRIE DO ALUNO
    # =====================================================

    def get_queryset(self):

        aluno_id = self.request.session.get('aluno_id')

        if not aluno_id:
            return Questao.objects.none()

        try:
            aluno = Aluno.objects.get(id=aluno_id)
        except Aluno.DoesNotExist:
            return Questao.objects.none()

        return Questao.objects.filter(
            serie=aluno.serie
        ).order_by('numero')

    # =====================================================
    # RETORNA QUESTÕES NA ORDEM SALVA NA SESSÃO
    # =====================================================

    def obter_questoes_questionario(self):

        questoes_base = list(self.get_queryset())

        if not questoes_base:
            return []

        questoes_ordem = self.request.session.get(
            'questoes_ordem'
        )

        if not questoes_ordem:
            return questoes_base

        questoes_dict = {
            questao.id: questao
            for questao in questoes_base
        }

        questoes = [
            questoes_dict[questao_id]
            for questao_id in questoes_ordem
            if questao_id in questoes_dict
        ]

        return questoes

    # =====================================================
    # VERIFICA BLOQUEIO DE 8 HORAS
    # =====================================================

    def verificar_bloqueio(self, aluno):

        if not aluno:
            return False, None, 0

        ultima_tentativa = (
            Resultado.objects
            .filter(aluno=aluno)
            .order_by('-data')
            .first()
        )

        if not ultima_tentativa:
            return False, None, 0

        agora = timezone.now()

        proxima_tentativa = (
            ultima_tentativa.data +
            timedelta(hours=8)
        )

        if agora < proxima_tentativa:

            segundos_restantes = int(
                (
                    proxima_tentativa - agora
                ).total_seconds()
            )

            return (
                True,
                proxima_tentativa,
                segundos_restantes
            )

        return False, None, 0

    # =====================================================
    # CALCULA XP
    # =====================================================

    def calcular_xp(self, questoes, respostas):

        """
        Calcula o XP ganho pelo aluno na prova.

        XP base:

        Fácil   = 10 XP
        Médio   = 15 XP
        Difícil = 20 XP

        A partir do 3º acerto consecutivo:
        +5 XP de bônus por acerto.

        Qualquer erro zera a sequência.

        Exemplo:

        Acerto 1 → XP normal
        Acerto 2 → XP normal
        Acerto 3 → XP normal + 5
        Acerto 4 → XP normal + 5
        Acerto 5 → XP normal + 5

        Se errar:

        Erro → 0 XP e sequência volta para 0.
        """

        xp_total = 0

        sequencia_acertos = 0

        xp_dificuldade = {
            'facil': 10,
            'medio': 15,
            'dificil': 20,
        }

        for questao in questoes:

            resposta = respostas.get(
                str(questao.id)
            )

            # =================================================
            # ERRO
            # =================================================

            if resposta != questao.resposta_correta:

                # Zera a sequência
                sequencia_acertos = 0

                continue

            # =================================================
            # ACERTO
            # =================================================

            sequencia_acertos += 1

            # XP base da dificuldade
            xp = xp_dificuldade.get(
                questao.dificuldade,
                0
            )

            # =================================================
            # BÔNUS DE SEQUÊNCIA
            # =================================================

            if sequencia_acertos >= 3:

                xp += 5

            # Adiciona ao XP total da prova
            xp_total += xp

        return xp_total

    # =====================================================
    # POST
    # =====================================================

    def post(self, request, *args, **kwargs):

        acao = request.POST.get('acao')

        # =================================================
        # NOVO QUESTIONÁRIO
        # =================================================

        if acao == 'novo_questionario':

            aluno_id = request.session.get(
                'aluno_id'
            )

            if not aluno_id:
                return redirect('home')

            try:
                aluno = Aluno.objects.get(
                    id=aluno_id
                )
            except Aluno.DoesNotExist:
                return redirect('home')

            questoes = list(
                Questao.objects.filter(
                    serie=aluno.serie
                ).order_by('numero')
            )

            if not questoes:
                return redirect(
                    'questoes:lista_questoes'
                )

            # =============================================
            # VERIFICA BLOQUEIO
            # =============================================

            (
                bloqueado,
                proxima_tentativa,
                segundos_restantes
            ) = self.verificar_bloqueio(aluno)

            if bloqueado:

                request.session[
                    'questionario_bloqueado'
                ] = True

                request.session[
                    'segundos_restantes'
                ] = segundos_restantes

                return redirect(
                    'questoes:lista_questoes'
                )

            # =============================================
            # LIBERADO
            # =============================================

            request.session[
                'questionario_bloqueado'
            ] = False

            request.session.pop(
                'segundos_restantes',
                None
            )

            # =============================================
            # RANDOMIZA AS QUESTÕES
            # =============================================

            questoes_ids = [
                questao.id
                for questao in questoes
            ]

            random.shuffle(questoes_ids)

            request.session[
                'questoes_ordem'
            ] = questoes_ids

            # =============================================
            # RANDOMIZA AS ALTERNATIVAS
            # =============================================

            alternativas_ordem = {}

            for questao in questoes:

                alternativas = [
                    'A',
                    'B',
                    'C',
                    'D'
                ]

                random.shuffle(alternativas)

                alternativas_ordem[
                    str(questao.id)
                ] = alternativas

            request.session[
                'alternativas_ordem'
            ] = alternativas_ordem

            # =============================================
            # INICIA QUESTIONÁRIO
            # =============================================

            request.session[
                'questao_atual'
            ] = 0

            request.session[
                'respostas'
            ] = {}

            request.session[
                'questionario_finalizado'
            ] = False

            request.session[
                'resposta_mostrada'
            ] = False

            request.session[
                'resposta_escolhida'
            ] = None

            request.session[
                'resposta_correta'
            ] = None

            request.session[
                'acertou'
            ] = False

            request.session[
                'acertos'
            ] = 0

            request.session[
                'total_questoes'
            ] = 0

            request.session[
                'xp_ganho'
            ] = 0

            # Guarda início
            request.session[
                'inicio_questionario'
            ] = timezone.now().isoformat()

            return redirect(
                'questoes:lista_questoes'
            )

        # =================================================
        # QUESTÕES NA ORDEM DO QUESTIONÁRIO
        # =================================================

        questoes = self.obter_questoes_questionario()

        if not questoes:
            return redirect(
                'questoes:lista_questoes'
            )

        # =================================================
        # QUESTÃO ATUAL
        # =================================================

        indice = int(
            request.session.get(
                'questao_atual',
                0
            )
        )

        indice = max(
            0,
            min(
                indice,
                len(questoes) - 1
            )
        )

        questao = questoes[indice]

        respostas = request.session.get(
            'respostas',
            {}
        )

        if not isinstance(respostas, dict):
            respostas = {}

        # =================================================
        # RESPONDER
        # =================================================

        if acao == 'responder':

            if request.session.get(
                'questionario_finalizado',
                False
            ):
                return redirect(
                    'questoes:lista_questoes'
                )

            resposta = request.POST.get(
                'resposta'
            )

            # Garante resposta válida
            if resposta not in [
                'A',
                'B',
                'C',
                'D'
            ]:
                return redirect(
                    'questoes:lista_questoes'
                )

            respostas[
                str(questao.id)
            ] = resposta

            request.session[
                'respostas'
            ] = respostas

            request.session[
                'resposta_mostrada'
            ] = True

            request.session[
                'resposta_escolhida'
            ] = resposta

            request.session[
                'resposta_correta'
            ] = questao.resposta_correta

            request.session[
                'acertou'
            ] = (
                resposta ==
                questao.resposta_correta
            )

            return redirect(
                'questoes:lista_questoes'
            )

        # =================================================
        # AVANÇAR
        # =================================================

        if acao == 'avancar':

            if request.session.get(
                'questionario_finalizado',
                False
            ):
                return redirect(
                    'questoes:lista_questoes'
                )

            if indice < len(questoes) - 1:

                request.session[
                    'questao_atual'
                ] = indice + 1

            request.session[
                'resposta_mostrada'
            ] = False

            request.session.pop(
                'resposta_escolhida',
                None
            )

            request.session.pop(
                'resposta_correta',
                None
            )

            request.session.pop(
                'acertou',
                None
            )

            return redirect(
                'questoes:lista_questoes'
            )

        # =================================================
        # FINALIZAR
        # =================================================

        if acao == 'finalizar':

            aluno_id = request.session.get(
                'aluno_id'
            )

            if not aluno_id:
                return redirect('home')

            try:
                aluno = Aluno.objects.get(
                    id=aluno_id
                )
            except Aluno.DoesNotExist:
                return redirect('home')

            # Impede finalizar duas vezes
            if request.session.get(
                'questionario_finalizado',
                False
            ):
                return redirect(
                    'questoes:lista_questoes'
                )

            # =============================================
            # CALCULA RESULTADO
            # =============================================

            acertos = sum(
                respostas.get(str(q.id))
                == q.resposta_correta
                for q in questoes
            )

            total = len(questoes)

            erros = total - acertos

            nota = (
                round(
                    (acertos / total) * 10,
                    2
                )
                if total
                else 0
            )

            # =============================================
            # CALCULA XP
            # =============================================

            xp_ganho = self.calcular_xp(
                questoes,
                respostas
            )

            # =============================================
            # CALCULA TEMPO
            # =============================================

            inicio = request.session.get(
                'inicio_questionario'
            )

            tempo_segundos = 0

            if inicio:

                inicio = timezone.datetime.fromisoformat(
                    inicio
                )

                agora = timezone.now()

                tempo_segundos = max(
                    0,
                    int(
                        (
                            agora - inicio
                        ).total_seconds()
                    )
                )

            # =============================================
            # ADICIONA XP AO ALUNO
            # =============================================

            aluno.xp += xp_ganho

            aluno.save(
                update_fields=['xp']
            )

            # =============================================
            # SALVA RESULTADO
            # =============================================

            Resultado.objects.create(
                aluno=aluno,
                acertos=acertos,
                erros=erros,
                total_questoes=total,
                nota=nota,
                xp_ganho=xp_ganho,
                tempo_segundos=tempo_segundos
            )

            # =============================================
            # SALVA RESULTADO NA SESSÃO
            # =============================================

            request.session[
                'acertos'
            ] = acertos

            request.session[
                'total_questoes'
            ] = total

            request.session[
                'xp_ganho'
            ] = xp_ganho

            request.session[
                'questionario_finalizado'
            ] = True

            request.session[
                'resposta_mostrada'
            ] = False

            return redirect(
                'questoes:lista_questoes'
            )

        return redirect(
            'questoes:lista_questoes'
        )

    # =====================================================
    # CONTEXT
    # =====================================================

    def get_context_data(self, **kwargs):

        context = super().get_context_data(
            **kwargs
        )

        # =================================================
        # QUESTÕES NA ORDEM RANDOMIZADA
        # =================================================

        questoes = self.obter_questoes_questionario()

        # =================================================
        # ALUNO
        # =================================================

        aluno_id = self.request.session.get(
            'aluno_id'
        )

        aluno = None

        if aluno_id:

            try:
                aluno = Aluno.objects.get(
                    id=aluno_id
                )
            except Aluno.DoesNotExist:
                pass

        # =================================================
        # BLOQUEIO DE 8 HORAS
        # =================================================

        (
            questionario_bloqueado,
            proxima_tentativa,
            segundos_restantes
        ) = self.verificar_bloqueio(aluno)

        # =================================================
        # QUESTÃO ATUAL
        # =================================================

        indice = int(
            self.request.session.get(
                'questao_atual',
                0
            )
        )

        if questoes:

            indice = max(
                0,
                min(
                    indice,
                    len(questoes) - 1
                )
            )

            questao_atual = questoes[indice]

        else:

            indice = 0
            questao_atual = None

        # =================================================
        # RESPOSTAS
        # =================================================

        respostas = self.request.session.get(
            'respostas',
            {}
        )

        if not isinstance(respostas, dict):
            respostas = {}

        resposta_atual = None

        if questao_atual:

            resposta_atual = respostas.get(
                str(questao_atual.id)
            )

        # =================================================
        # ALTERNATIVAS RANDOMIZADAS
        # =================================================

        alternativas = []

        if questao_atual:

            alternativas_ordem = (
                self.request.session.get(
                    'alternativas_ordem',
                    {}
                )
            )

            ordem = alternativas_ordem.get(
                str(questao_atual.id),
                ['A', 'B', 'C', 'D']
            )

            textos = {
                'A': questao_atual.alternativa_a,
                'B': questao_atual.alternativa_b,
                'C': questao_atual.alternativa_c,
                'D': questao_atual.alternativa_d,
            }

            letras_exibicao = [
                'A',
                'B',
                'C',
                'D'
            ]

            for letra_exibicao, letra_original in zip(
                letras_exibicao,
                ordem
            ):

                alternativas.append({
                    'letra': letra_exibicao,
                    'letra_original': letra_original,
                    'texto': textos[letra_original],
                })

        # =================================================
        # CONTROLE DE EXIBIÇÃO
        # =================================================

        resposta_mostrada = (
            self.request.session.get(
                'resposta_mostrada',
                False
            )
        )

        resposta_escolhida = (
            self.request.session.get(
                'resposta_escolhida'
            )
        )

        resposta_correta = (
            self.request.session.get(
                'resposta_correta'
            )
        )

        acertou = (
            self.request.session.get(
                'acertou',
                False
            )
        )

        # =================================================
        # CONTEXT
        # =================================================

        context.update({

            'aluno': aluno,

            'questao_atual': questao_atual,

            'indice_atual': indice,

            'numero_questao': indice + 1,

            'total_questoes': len(questoes),

            'primeira_questao': (
                indice == 0
            ),

            'ultima_questao': (
                bool(questoes)
                and indice == len(questoes) - 1
            ),

            # Alternativas
            'alternativas': alternativas,

            # Resposta
            'resposta_atual':
                resposta_atual,

            'resposta_mostrada':
                resposta_mostrada,

            'resposta_escolhida':
                resposta_escolhida,

            'resposta_correta':
                resposta_correta,

            'acertou':
                acertou,

            # Questionário
            'questionario_finalizado':
                self.request.session.get(
                    'questionario_finalizado',
                    False
                ),

            # Bloqueio
            'questionario_bloqueado':
                questionario_bloqueado,

            'proxima_tentativa':
                proxima_tentativa,

            'segundos_restantes':
                segundos_restantes,

            # Resultado
            'acertos':
                self.request.session.get(
                    'acertos',
                    0
                ),

            'total_resultado':
                self.request.session.get(
                    'total_questoes',
                    0
                ),

            'xp_ganho':
                self.request.session.get(
                    'xp_ganho',
                    0
                ),

            'xp_total':
                aluno.xp if aluno else 0,
        })

        # =================================================
        # ERROS E NOTA
        # =================================================

        total = context[
            'total_resultado'
        ]

        acertos = context[
            'acertos'
        ]

        context['erros'] = max(
            total - acertos,
            0
        )

        context['nota'] = (
            round(
                (acertos / total) * 10,
                2
            )
            if total
            else 0
        )

        return context

# =========================================================
# CADASTRAR QUESTÃO
# =========================================================

class CadastrarQuestaoView(CreateView):

    model = Questao
    form_class = QuestaoForm
    template_name = 'questao_form.html'

    success_url = reverse_lazy(
        'area_professor'
    )

    def form_valid(self, form):

        print(
            "QUESTÃO SALVA:",
            form.cleaned_data
        )

        return super().form_valid(form)

    def form_invalid(self, form):

        print(
            "ERRO AO SALVAR QUESTÃO:"
        )

        print(form.errors)

        return super().form_invalid(form)