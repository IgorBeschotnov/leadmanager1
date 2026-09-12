from django.core.management.base import BaseCommand
from leads.models import Company, Category, DataSource


SOURCES = [
    ("test_vinnytsia_guide", "Test: business-guide Вінниця"),
    ("test_kyiv_excel", "Test: Excel Київ 2026"),
    ("test_odessa_scrap", "Test: скрапер Одеса"),
    ("test_lviv_meat", "Test: м'ясні Львів"),
    ("test_build_kharkiv", "Test: будівництво Харків"),
]

CITIES = [
    ("Вінниця", "Вінницька"),
    ("Київ", "Київська"),
    ("Одеса", "Одеська"),
    ("Львів", "Львівська"),
    ("Харків", "Харківська"),
]

CAT_NAMES = ["Будівництво", "Харчова", "Офіс", "Медицина", "Торгівля"]


class Command(BaseCommand):
    help = "Создаёт ~50 тестовых лидов + источники DataSource"

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=50)
        parser.add_argument("--clear-test", action="store_true",
                            help="Удалить старые test_* лиды перед созданием")

    def handle(self, *args, **options):
        count = options["count"]
        if options["clear_test"]:
            deleted, _ = Company.objects.filter(source__startswith="test_").delete()
            self.stdout.write(f"Удалено старых test-лидов: {deleted}")

        cats = []
        for name in CAT_NAMES:
            c, _ = Category.objects.get_or_create(name=name)
            cats.append(c)

        for key, title in SOURCES:
            DataSource.objects.get_or_create(key=key, defaults={"title": title, "is_released": False})

        stages = ["new", "new", "new", "in_progress", ]
        created = 0
        for i in range(1, count + 1):
            src_key, _ = SOURCES[(i - 1) % len(SOURCES)]
            city, region = CITIES[(i - 1) % len(CITIES)]
            stage = stages[(i - 1) % len(stages)]
            phone = f"+38050{1000000 + i}"

            company = Company.objects.create(
                name=f"ТОВ Тест-{i:02d} {city}",
                city=city,
                region=region,
                phones=phone,
                emails=f"info{i}@test-company.ua",
                contact_person=f"Контакт {i}",
                source=src_key,
                stage=stage,
                website=f"https://example{i}.test",
            )
            company.categories.add(cats[(i - 1) % len(cats)])
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Создано лидов: {created}. Источников: {len(SOURCES)} (все закрыты)."
        ))
        self.stdout.write("Открой в админке: Источники данных → отметь → «Открыть для команды»")