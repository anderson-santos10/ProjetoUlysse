from django.core.management.base import BaseCommand

from questoes.integridade import auditar_integridade, formatar_relatorio


class Command(BaseCommand):
    help = (
        "Auditoria somente leitura da integridade de questões, "
        "versões e respostas históricas."
    )

    def handle(self, *args, **options):
        dados = auditar_integridade()
        self.stdout.write(formatar_relatorio(dados).rstrip())
        if not dados["ok"]:
            raise SystemExit(1)
