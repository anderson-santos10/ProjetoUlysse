from django.db import migrations


def seed_turma_permissions(apps, schema_editor):
    from django.apps import apps as django_apps
    from django.contrib.auth.management import create_permissions

    from accounts.catalog import seed_auth_catalog

    for app_config in django_apps.get_app_configs():
        create_permissions(app_config, verbosity=0)
    seed_auth_catalog()


def noop(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("alunos", "0007_turma_matricula"),
        ("accounts", "0003_seed_auth_catalog"),
    ]

    operations = [
        migrations.RunPython(seed_turma_permissions, noop),
    ]
