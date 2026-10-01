import re

from django.db import migrations, models


def move_legacy_addresses(apps, schema_editor):
    Company = apps.get_model("leads", "Company")
    for company in Company.objects.filter(address__isnull=True).exclude(internal_notes__isnull=True).iterator():
        remaining = []
        found = []
        for line in (company.internal_notes or "").splitlines():
            match = re.match(r"^\s*Адреса:\s*(.+?)\s*$", line, flags=re.IGNORECASE)
            if match:
                found.append(match.group(1))
            else:
                remaining.append(line)
        if found:
            company.address = "; ".join(found)[:500]
            company.internal_notes = "\n".join(remaining).strip() or None
            company.save(update_fields=["address", "internal_notes"])


class Migration(migrations.Migration):
    dependencies = [("leads", "0005_calllog_communication_sent")]
    operations = [
        migrations.AddField(
            model_name="company",
            name="address",
            field=models.CharField(blank=True, max_length=500, null=True, verbose_name="Адрес"),
        ),
        migrations.RunPython(move_legacy_addresses, migrations.RunPython.noop),
    ]
