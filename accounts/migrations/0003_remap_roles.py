from django.db import migrations


def forward(apps, schema_editor):
    """旧2ロール→新3ロールへ移行。
    staff → crew / leader かつ superuser → admin（システム管理者）/ その他 leader はそのまま。
    """
    User = apps.get_model("accounts", "User")
    User.objects.filter(role="staff").update(role="crew")
    User.objects.filter(role="leader", is_superuser=True).update(role="admin")


def backward(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(role="admin").update(role="leader")
    User.objects.filter(role="crew").update(role="staff")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_alter_user_role"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
