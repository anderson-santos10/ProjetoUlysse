from django.core.management.base import BaseCommand

from accounts.catalog import GROUPS, seed_auth_catalog


class Command(BaseCommand):
    help = "Cria ou atualiza grupos e permissões do sistema (idempotente)."

    def handle(self, *args, **options):
        seed_auth_catalog()
        self.stdout.write(
            self.style.SUCCESS(
                "Grupos atualizados: " + ", ".join(GROUPS)
            )
        )
