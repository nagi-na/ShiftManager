from django.db import migrations


def normalize(apps, schema_editor):
    """旧TimeField由来の "HH:MM:SS" を "HH:MM" に整える。"""
    ShiftRequestDay = apps.get_model("shifts", "ShiftRequestDay")
    for day in ShiftRequestDay.objects.all():
        changed = False
        if day.start_time and len(day.start_time) > 5:
            day.start_time = day.start_time[:5]
            changed = True
        if day.end_time and len(day.end_time) > 5:
            day.end_time = day.end_time[:5]
            changed = True
        if changed:
            day.save(update_fields=["start_time", "end_time"])


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0002_alter_shiftrequestday_end_time_and_more"),
    ]

    operations = [
        migrations.RunPython(normalize, migrations.RunPython.noop),
    ]
