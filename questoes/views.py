import random

from django.contrib import messages
from datetime import datetime
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.db.models import Prefetch, Q
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.http import HttpResponseRedirect
from django.utils import timezone

from accounts.mixins import PermissionRequiredMixin
from accounts.querystring import without_page
from alunos.escopo import queryset_resultados_visiveis
from alunos.models import Aluno
from alunos.security import formatar_tempo
from alunos.session import (
    aluno_session_exists,
    bind_linked_aluno_session,
    clear_aluno_session,
)
from alunos.matriculas import matricula_ativa_em

from .cooldown import verificar_bloqueio as verificar_bloqueio_aluno
from .forms import QuestaoForm
from .models import Questao, RespostaResultado, Resultado
from .persistencia import persistir_respostas_resultado
from .scoring import calcular_xp as calcular_xp_prova
from .versionamento import (
    VersaoTentativaInvalida,
    aplicar_edicao_com_versao,
    mapa_versoes_atuais,
    resolver_versoes_tentativa,
)


class ListaQuestoesView(ListView):

    model = Questao
    template_name = 'questoes_list.html'
    context_object_name = 'questoes'

    def dispatch(self, request, *args, **kwargs):
        bind_linked_aluno_session(request)

        aluno_id = request.session.get('aluno_id')

        if not aluno_session_exists(aluno_id):
            if aluno_id:
                clear_aluno_session(request.session)
                messages.error(
                    request,
                    'Aluno não encontrado. Faça o acesso novamente.',
                )
            return redirect('alunos:acesso_aluno')

        return super().dispatch(request, *args, **kwargs)

    def _parse_inicio_questionario(self, inicio):
        if not inicio:
            return None
        try:
            parsed = timezone.datetime.fromisoformat(inicio)
        except (TypeError, ValueError):
            return None
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(
                parsed,
                timezone.get_current_timezone(),
            )
        return parsed

    def _resultado_desta_tentativa(self, aluno, inicio):
        inicio_dt = self._parse_inicio_questionario(inicio)
        if aluno is None or inicio_dt is None:
            return None
        return (
            Resultado.objects
            .filter(aluno=aluno, data__gte=inicio_dt)
            .order_by('data')
            .first()
        )

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
        ).select_related('versao_atual').order_by('numero')

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
        return verificar_bloqueio_aluno(aluno)

    def _post_bloqueado_por_cooldown(self, request):
        aluno_id = request.session.get('aluno_id')

        if not aluno_id:
            return False

        try:
            aluno = Aluno.objects.get(id=aluno_id)
        except Aluno.DoesNotExist:
            return False

        (
            bloqueado,
            proxima_tentativa,
            segundos_restantes,
        ) = self.verificar_bloqueio(aluno)

        if not bloqueado:
            return False

        request.session['questionario_bloqueado'] = True
        request.session['segundos_restantes'] = segundos_restantes
        return True

    # =====================================================
    # CALCULA XP
    # =====================================================

    def calcular_xp(self, questoes, respostas, versoes=None):
        return calcular_xp_prova(questoes, respostas, versoes=versoes)

    # =====================================================
    # POST
    # =====================================================

    def post(self, request, *args, **kwargs):

        acao = request.POST.get('acao')

        if acao in (
            'novo_questionario',
            'responder',
            'avancar',
            'finalizar',
        ) and self._post_bloqueado_por_cooldown(request):
            return redirect(
                'questoes:lista_questoes'
            )

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
                ).select_related('versao_atual').order_by('numero')
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

            request.session[
                'questoes_versoes'
            ] = mapa_versoes_atuais(questoes)

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
        versoes = resolver_versoes_tentativa(questoes, request.session)
        conteudo = versoes[questao.id]

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
            ] = conteudo.resposta_correta

            request.session[
                'acertou'
            ] = (
                resposta ==
                conteudo.resposta_correta
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
                return redirect('alunos:acesso_aluno')

            inicio = request.session.get(
                'inicio_questionario'
            )

            with transaction.atomic():
                try:
                    aluno = (
                        Aluno.objects
                        .select_for_update()
                        .get(id=aluno_id)
                    )
                except Aluno.DoesNotExist:
                    return redirect('alunos:acesso_aluno')

                ja_finalizado = request.session.get(
                    'questionario_finalizado',
                    False,
                )
                resultado_existente = self._resultado_desta_tentativa(
                    aluno,
                    inicio,
                )

                if ja_finalizado or resultado_existente is not None:
                    request.session['questionario_finalizado'] = True
                    return redirect('questoes:lista_questoes')

                try:
                    versoes = resolver_versoes_tentativa(
                        questoes,
                        request.session,
                        estrito=True,
                    )
                except VersaoTentativaInvalida:
                    messages.error(
                        request,
                        'Não foi possível registrar esta tentativa porque '
                        'os dados da prova estão inconsistentes. '
                        'Inicie um novo simulado.',
                    )
                    return redirect('questoes:lista_questoes')

                acertos = sum(
                    respostas.get(str(q.id))
                    == versoes[q.id].resposta_correta
                    for q in questoes
                )

                total = len(questoes)
                erros = total - acertos
                nota = (
                    round((acertos / total) * 10, 2)
                    if total
                    else 0
                )

                xp_ganho = self.calcular_xp(
                    questoes,
                    respostas,
                    versoes,
                )

                inicio_dt = self._parse_inicio_questionario(inicio)
                tempo_segundos = 0
                if inicio_dt is not None:
                    tempo_segundos = max(
                        0,
                        int((timezone.now() - inicio_dt).total_seconds()),
                    )

                aluno.xp += xp_ganho
                aluno.save(update_fields=['xp'])

                resultado = Resultado.objects.create(
                    aluno=aluno,
                    acertos=acertos,
                    erros=erros,
                    total_questoes=total,
                    nota=nota,
                    xp_ganho=xp_ganho,
                    tempo_segundos=tempo_segundos,
                    matricula=matricula_ativa_em(aluno),
                )
                persistir_respostas_resultado(
                    resultado,
                    questoes,
                    respostas,
                    versoes,
                )

            request.session['acertos'] = acertos
            request.session['total_questoes'] = total
            request.session['xp_ganho'] = xp_ganho
            request.session['tempo_segundos'] = tempo_segundos
            request.session['questionario_finalizado'] = True
            request.session['resposta_mostrada'] = False

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
        questao_conteudo = None

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

            versoes = resolver_versoes_tentativa(
                questoes,
                self.request.session,
            )
            conteudo = versoes[questao_atual.id]
            questao_conteudo = conteudo

            textos = {
                'A': conteudo.alternativa_a,
                'B': conteudo.alternativa_b,
                'C': conteudo.alternativa_c,
                'D': conteudo.alternativa_d,
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
            'questao_conteudo': questao_conteudo,

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
            'tempo_segundos':
                self.request.session.get('tempo_segundos', 0),
            'tempo_formatado': formatar_tempo(
                self.request.session.get('tempo_segundos', 0)
            ),
            'tempo_bloqueio_formatado': formatar_tempo(segundos_restantes),
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

class CadastrarQuestaoView(PermissionRequiredMixin, CreateView):

    permission_required = "questoes.add_questao"

    model = Questao
    form_class = QuestaoForm
    template_name = 'questao_form.html'

    def form_valid(self, form):
        with transaction.atomic():
            self.object = form.save()
        messages.success(
            self.request,
            'Questão cadastrada com sucesso.',
        )
        return HttpResponseRedirect(self.get_success_url())

    success_url = reverse_lazy('questoes:gestao')


class GestaoQuestoesView(PermissionRequiredMixin, ListView):

    permission_required = "questoes.view_questao"
    model = Questao
    template_name = "questao_gestao.html"
    context_object_name = "questoes"
    paginate_by = 20

    def get_queryset(self):
        queryset = Questao.objects.all().order_by("serie", "numero")
        busca = self.request.GET.get("q", "").strip()
        serie = self.request.GET.get("serie", "").strip()
        dificuldade = self.request.GET.get("dificuldade", "").strip()
        if busca:
            filtro = Q(enunciado__icontains=busca)
            if busca.isdigit():
                filtro |= Q(numero=int(busca))
            queryset = queryset.filter(filtro)
        if serie:
            queryset = queryset.filter(serie=serie)
        if dificuldade:
            queryset = queryset.filter(dificuldade=dificuldade)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["busca"] = self.request.GET.get("q", "").strip()
        context["serie_filtro"] = self.request.GET.get("serie", "").strip()
        context["dificuldade_filtro"] = self.request.GET.get("dificuldade", "").strip()
        context["series"] = Questao.SERIE_CHOICES
        context["dificuldades"] = Questao.DIFICULDADE_CHOICES
        context["querystring"] = without_page(self.request)
        return context


class EditarQuestaoView(PermissionRequiredMixin, UpdateView):

    permission_required = "questoes.change_questao"
    model = Questao
    form_class = QuestaoForm
    template_name = "questao_form.html"
    success_url = reverse_lazy("questoes:gestao")

    def form_valid(self, form):
        self.object = aplicar_edicao_com_versao(form)
        messages.success(
            self.request,
            "Questão atualizada com sucesso.",
        )
        return HttpResponseRedirect(self.get_success_url())


class ListaResultadosView(PermissionRequiredMixin, ListView):

    permission_required = "questoes.view_resultado"
    model = Resultado
    template_name = "resultado_list.html"
    context_object_name = "resultados"
    paginate_by = 20

    def get_queryset(self):
        queryset = queryset_resultados_visiveis(
            self.request.user,
            Resultado.objects
            .select_related("aluno", "matricula", "matricula__turma", "avaliacao")
            .order_by("-data"),
        )
        busca = self.request.GET.get("q", "").strip()
        serie = self.request.GET.get("serie", "").strip()
        data = self.request.GET.get("data", "").strip()
        nota = self.request.GET.get("nota", "").strip()
        if busca:
            queryset = queryset.filter(
                Q(aluno__nome__icontains=busca) | Q(aluno__ra__icontains=busca)
            )
        if serie:
            queryset = queryset.filter(aluno__serie=serie)
        if data:
            try:
                datetime.strptime(data, "%Y-%m-%d")
            except ValueError:
                return queryset.none()
            queryset = queryset.filter(data__date=data)
        if nota:
            try:
                nota_valor = Decimal(nota.replace(",", "."))
            except InvalidOperation:
                return queryset.none()
            queryset = queryset.filter(nota=nota_valor)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["busca"] = self.request.GET.get("q", "").strip()
        context["serie_filtro"] = self.request.GET.get("serie", "").strip()
        context["data_filtro"] = self.request.GET.get("data", "").strip()
        context["nota_filtro"] = self.request.GET.get("nota", "").strip()
        context["series"] = Aluno.SERIES
        context["querystring"] = without_page(self.request)
        return context


class DetalheResultadoView(PermissionRequiredMixin, DetailView):

    permission_required = "questoes.view_resultado"
    model = Resultado
    template_name = "resultado_detail.html"
    context_object_name = "resultado"

    def get_queryset(self):
        return queryset_resultados_visiveis(
            self.request.user,
            Resultado.objects
            .select_related("aluno", "matricula", "matricula__turma", "avaliacao")
            .prefetch_related(
                Prefetch(
                    "respostas_questoes",
                    queryset=(
                        RespostaResultado.objects
                        .select_related("questao", "questao_versao")
                        .order_by("questao__serie", "questao__numero")
                    ),
                )
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tempo_formatado"] = formatar_tempo(
            self.object.tempo_segundos
        )
        respostas = list(self.object.respostas_questoes.all())
        context["tem_respostas_questoes"] = bool(respostas)
        context["desempenho_questoes"] = respostas
        return context
