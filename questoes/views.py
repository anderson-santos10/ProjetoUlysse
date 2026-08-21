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

    def post(self, request, *args, **kwargs):

        questoes = list(self.get_queryset())

        if not questoes:
            return redirect('questoes:lista_questoes')

        acao = request.POST.get('acao')

        # ==========================================
        # NOVO QUESTIONÁRIO
        # ==========================================

        if acao == 'novo_questionario':
            request.session['questao_atual'] = 0
            request.session['respostas'] = {}
            request.session['questionario_finalizado'] = False
            request.session['resposta_mostrada'] = False
            request.session['acertos'] = 0
            request.session['total_questoes'] = 0

            # Registra o início do questionário
            request.session['inicio_questionario'] = timezone.now().isoformat()

            return redirect('questoes:lista_questoes')

        # ==========================================
        # QUESTÃO ATUAL
        # ==========================================

        indice = int(
            request.session.get('questao_atual', 0)
        )

        indice = max(
            0,
            min(indice, len(questoes) - 1)
        )

        questao = questoes[indice]

        respostas = request.session.get(
            'respostas',
            {}
        )

        if not isinstance(respostas, dict):
            respostas = {}

        # ==========================================
        # RESPONDER
        # ==========================================

        if acao == 'responder':

            resposta = request.POST.get('resposta')

            if resposta:

                respostas[str(questao.id)] = resposta

                request.session['respostas'] = respostas

                # Marca que a resposta foi enviada
                request.session['resposta_mostrada'] = True

                # Guarda a alternativa escolhida
                request.session['resposta_escolhida'] = resposta

                # Guarda a resposta correta
                request.session['resposta_correta'] = (
                    questao.resposta_correta
                )

                # Verifica se acertou
                acertou = (
                    resposta == questao.resposta_correta
                )

                request.session['acertou'] = acertou

            return redirect('questoes:lista_questoes')

        # ==========================================
        # AVANÇAR
        # ==========================================

        if acao == 'avancar':

            if indice < len(questoes) - 1:

                request.session['questao_atual'] = indice + 1

            request.session['resposta_mostrada'] = False

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

            return redirect('questoes:lista_questoes')

        # ==========================================
        # FINALIZAR
        # ==========================================

        if acao == 'finalizar':
            aluno_id = request.session.get('aluno_id')

            if not aluno_id:
                return redirect('home')

            try:
                aluno = Aluno.objects.get(id=aluno_id)
            except Aluno.DoesNotExist:
                return redirect('home')

            if request.session.get('questionario_finalizado', False):
                return redirect('questoes:lista_questoes')

            acertos = sum(
                respostas.get(str(q.id)) == q.resposta_correta
                for q in questoes
            )

            total = len(questoes)
            erros = total - acertos
            nota = round((acertos / total) * 10, 2) if total else 0

            # Calcula o tempo total do questionário
            inicio = request.session.get('inicio_questionario')

            tempo_segundos = 0

            if inicio:
                inicio = timezone.datetime.fromisoformat(inicio)
                agora = timezone.now()

                tempo_segundos = int(
                    (agora - inicio).total_seconds()
                )

            Resultado.objects.create(
                aluno=aluno,
                acertos=acertos,
                erros=erros,
                total_questoes=total,
                nota=nota,
                tempo_segundos=tempo_segundos
            )

            request.session['acertos'] = acertos
            request.session['total_questoes'] = total
            request.session['questionario_finalizado'] = True
            request.session['resposta_mostrada'] = False

            return redirect('questoes:lista_questoes')

    # ==========================================
    # CONTEXT
    # ==========================================

    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        questoes = context['questoes']

        # ==========================================
        # ALUNO
        # ==========================================

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

        # ==========================================
        # QUESTÃO ATUAL
        # ==========================================

        indice = int(
            self.request.session.get(
                'questao_atual',
                0
            )
        )

        if questoes:

            indice = max(
                0,
                min(indice, len(questoes) - 1)
            )

            questao_atual = questoes[indice]

        else:

            indice = 0
            questao_atual = None

        # ==========================================
        # RESPOSTA
        # ==========================================

        respostas = self.request.session.get(
            'respostas',
            {}
        )

        resposta_atual = None

        if questao_atual:

            resposta_atual = respostas.get(
                str(questao_atual.id)
            )

        # ==========================================
        # CONTROLE DE EXIBIÇÃO
        # ==========================================

        resposta_mostrada = self.request.session.get(
            'resposta_mostrada',
            False
        )

        resposta_escolhida = self.request.session.get(
            'resposta_escolhida'
        )

        resposta_correta = self.request.session.get(
            'resposta_correta'
        )

        acertou = self.request.session.get(
            'acertou',
            False
        )

        # ==========================================
        # CONTEXT
        # ==========================================

        context.update({

            'aluno': aluno,

            'questao_atual': questao_atual,

            'indice_atual': indice,

            'numero_questao': indice + 1,

            'total_questoes': len(questoes),

            'primeira_questao': indice == 0,

            'ultima_questao': (
                bool(questoes)
                and indice == len(questoes) - 1
            ),

            # Resposta salva
            'resposta_atual': resposta_atual,

            # Só fica True depois de clicar RESPONDER
            'resposta_mostrada': resposta_mostrada,

            # Alternativa escolhida
            'resposta_escolhida': resposta_escolhida,

            # Alternativa correta
            'resposta_correta': resposta_correta,

            # Resultado
            'acertou': acertou,

            # Questionário
            'questionario_finalizado':
                self.request.session.get(
                    'questionario_finalizado',
                    False
                ),

            # Resultado final
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

        # ==========================================
        # ERROS E NOTA
        # ==========================================

        total = context['total_resultado']

        acertos = context['acertos']

        context['erros'] = max(
            total - acertos,
            0
        )

        context['nota'] = (
            round((acertos / total) * 10, 2)
            if total
            else 0
        )

        return context


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