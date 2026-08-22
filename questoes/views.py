from datetime import timedelta

from django.views.generic import ListView, CreateView
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.db.models import Max
from django.utils import timezone

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

        # Nunca fez questionário
        if not ultima_tentativa:
            return False, None, 0

        agora = timezone.now()

        proxima_tentativa = (
            ultima_tentativa.data +
            timedelta(hours=8)
        )

        # Ainda está dentro das 8 horas
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

        # Já passou das 8 horas
        return False, None, 0

    # =====================================================
    # POST
    # =====================================================

    def post(self, request, *args, **kwargs):

        questoes = list(self.get_queryset())

        if not questoes:
            return redirect(
                'questoes:lista_questoes'
            )

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

            # =============================================
            # VERIFICA BLOQUEIO
            # =============================================

            bloqueado, proxima_tentativa, segundos_restantes = (
                self.verificar_bloqueio(aluno)
            )

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
                'acertos'
            ] = 0

            request.session[
                'total_questoes'
            ] = 0

            # Guarda início
            request.session[
                'inicio_questionario'
            ] = timezone.now().isoformat()

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

            # Segurança: não permite responder
            # depois que o questionário terminou
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

            if resposta:

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
            # SALVA RESULTADO
            # =============================================

            Resultado.objects.create(
                aluno=aluno,
                acertos=acertos,
                erros=erros,
                total_questoes=total,
                nota=nota,
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

        questoes = context['questoes']

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

    template_name = 'questao_form.html'

    fields = [
        'numero',
        'serie',
        'dificuldade',
        'enunciado',
        'alternativa_a',
        'alternativa_b',
        'alternativa_c',
        'alternativa_d',
        'resposta_correta'
    ]

    success_url = reverse_lazy(
        'questoes:lista_questoes'
    )


# =========================================================
# RANKING
# =========================================================

class RankingView(ListView):

    model = Aluno

    template_name = 'ranking.html'

    context_object_name = 'ranking'

    def get_queryset(self):

        return Aluno.objects.annotate(
            melhor_nota=Max(
                'resultados__nota'
            )
        ).filter(
            melhor_nota__isnull=False
        ).order_by(
            '-melhor_nota',
            'nome'
        )