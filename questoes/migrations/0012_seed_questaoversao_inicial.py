from django.db import migrations


def criar_versoes_iniciais(apps, schema_editor):
    Questao = apps.get_model("questoes", "Questao")
    QuestaoVersao = apps.get_model("questoes", "QuestaoVersao")

    for questao in Questao.objects.all().order_by("id"):
        if questao.versoes.exists():
            atual = questao.versoes.order_by("versao").last()
            if questao.versao_atual_id is None:
                Questao.objects.filter(pk=questao.pk).update(versao_atual=atual)
            continue
        versao = QuestaoVersao.objects.create(
            questao=questao,
            versao=1,
            numero=questao.numero,
            serie=questao.serie,
            dificuldade=questao.dificuldade,
            enunciado=questao.enunciado,
            alternativa_a=questao.alternativa_a,
            alternativa_b=questao.alternativa_b,
            alternativa_c=questao.alternativa_c,
            alternativa_d=questao.alternativa_d,
            resposta_correta=questao.resposta_correta,
        )
        Questao.objects.filter(pk=questao.pk).update(versao_atual=versao)


def remover_versoes_iniciais(apps, schema_editor):
    Questao = apps.get_model("questoes", "Questao")
    QuestaoVersao = apps.get_model("questoes", "QuestaoVersao")
    Questao.objects.update(versao_atual=None)
    QuestaoVersao.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("questoes", "0011_questaoversao"),
    ]

    operations = [
        migrations.RunPython(criar_versoes_iniciais, remover_versoes_iniciais),
    ]
