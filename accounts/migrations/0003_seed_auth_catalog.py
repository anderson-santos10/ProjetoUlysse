from django.db import migrations


def seed_groups(apps, schema_editor):
    from django.apps import apps as django_apps
    from django.contrib.auth.management import create_permissions

    from accounts.catalog import seed_auth_catalog

    for app_config in django_apps.get_app_configs():
        create_permissions(app_config, verbosity=0)

    seed_auth_catalog()


def unseed_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(
        name__in=["aluno", "professor", "coordenador", "diretor"]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_alter_profile_options_alter_profile_role"),
        ("alunos", "0005_aluno_user"),
        ("questoes", "0009_alter_questao_options"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(seed_groups, unseed_groups),
    ]
