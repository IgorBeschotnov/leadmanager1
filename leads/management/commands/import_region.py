"""
Універсальний імпорт лідів з Excel (business-guide) по областях.

Скопіюй як:
    leads/management/commands/import_region.py

Запуск (один файл):
    python manage.py import_region data/cherkaska_raw.xlsx
    python manage.py import_region data/kyivska_raw.xlsx --dry-run

Запуск усіх *_raw.xlsx з папки data:
    python manage.py import_region data --all
    python manage.py import_region data --all --dry-run
"""

import re
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from leads.models import Company

# Мапінг частини імені файлу → регіон
REGION_MAP = {
    "cherkaska": "Черкаська область",
    "chernivska": "Чернівецька область",
    "ivanofrankivska": "Івано-Франківська область",
    "kharkivska": "Харківська область",
    "khersonska": "Херсонська область",
    "khmelnytska": "Хмельницька область",
    "kirovohradska": "Кіровоградська область",
    "kyivska": "Київська область",
    "livska": "Львівська область",
    "lvivska": "Львівська область",
    "mykolaivska": "Миколаївська область",
    "odeska": "Одеська область",
    "poltavska": "Полтавська область",
    "rivnenska": "Рівненська область",
    "sumska": "Сумська область",
    "ternopilska": "Тернопільська область",
    "vinnytska": "Вінницька область",
    "vinnicay": "Вінницька область",
    "volyn": "Волинська область",
    "zakarpatska": "Закарпатська область",
    "zaporizka": "Запорізька область",
    "zhytomyrska": "Житомирська область",
    "zhitomerskaya": "Житомирська область",
}


def detect_region(filename: str) -> str:
    name = filename.lower().replace("-", "").replace("_", "")
    for key, region in REGION_MAP.items():
        if key in name:
            return region
    return "Україна"


def clean_phones(raw):
    if not raw or str(raw).strip().lower() in ("не указан", "не вказано", "-", "none"):
        return None
    raw = str(raw)
    phones = re.findall(r"\+?38[\s\-\(]*\d{2,3}[\s\-\)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}", raw)
    if not phones:
        phones = re.findall(r"\d[\d\s\-\(\)]{8,15}\d", raw)
    cleaned = []
    for p in phones:
        digits = re.sub(r"\D", "", p)
        if digits.startswith("38") and len(digits) >= 12:
            digits = digits[:12]
        elif digits.startswith("0") and len(digits) >= 10:
            digits = "38" + digits
        elif len(digits) == 9:
            digits = "380" + digits
        if len(digits) >= 10:
            formatted = "+" + digits
            if formatted not in cleaned:
                cleaned.append(formatted)
    return ", ".join(cleaned) if cleaned else None


def clean_email(raw):
    if not raw or str(raw).strip().lower() in ("не указан", "не вказано", "-", "none"):
        return None
    emails = re.findall(r"[\w.\-+]+@[\w.\-]+\.\w+", str(raw))
    return ", ".join(emails) if emails else None


def parse_city(address, region):
    if not address:
        return None
    m = re.search(r"(?:м\.|смт\.|с\.|селище)\s*([^,]+)", str(address), re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # часті міста
    cities = (
        "Київ|Черкаси|Умань|Сміла|Золотоноша|Канів|Харків|Одеса|Львів|Дніпро|"
        "Запоріжжя|Вінниця|Полтава|Суми|Миколаїв|Херсон|Чернівці|Рівне|"
        "Тернопіль|Івано-Франківськ|Луцьк|Ужгород|Житомир|Хмельницький|"
        "Кропивницький|Кіровоград"
    )
    m2 = re.search(rf"({cities})", str(address), re.IGNORECASE)
    return m2.group(1).strip() if m2 else None


def import_file(xlsx_path: Path, dry_run: bool, stdout, style):
    try:
        import openpyxl
    except ImportError:
        stdout.write(style.ERROR("Потрібен openpyxl: pip install openpyxl"))
        return 0, 0, 0

    region = detect_region(xlsx_path.name)
    source = f"business-guide.com.ua — {region}"

    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    stdout.write(f"\n📄 {xlsx_path.name} → {region} ({len(rows)} рядків)")

    created = skipped = errors = 0

    with transaction.atomic():
        for i, row in enumerate(rows, start=2):
            if not row or not row[0]:
                skipped += 1
                continue

            name = str(row[0]).strip()
            phones = clean_phones(row[1] if len(row) > 1 else None)

            # тільки з телефонами
            if not phones:
                skipped += 1
                continue

            if Company.objects.filter(name__iexact=name).exists():
                skipped += 1
                continue

            emails = clean_email(row[2] if len(row) > 2 else None)
            address = str(row[3]).strip() if len(row) > 3 and row[3] else None
            website = str(row[4]).strip() if len(row) > 4 and row[4] else None
            city = parse_city(address, region)

            if dry_run:
                stdout.write(f"  [DRY] {name[:50]:50} | {phones[:22]:22} | {city or '—'}")
                created += 1
                continue

            try:
                Company.objects.create(
                    name=name,
                    phones=phones,
                    emails=emails,
                    city=city,
                    region=region,
                    website=website if website and website.startswith("http") else None,
                    source=source,
                    stage="new",
                    internal_notes=f"Адреса: {address}" if address else None,
                )
                created += 1
            except Exception as e:
                errors += 1
                stdout.write(style.ERROR(f"  ERR row {i}: {name[:40]} → {e}"))

        if dry_run:
            raise SystemExit  # rollback

    return created, skipped, errors


class Command(BaseCommand):
    help = "Імпорт лідів з Excel по областях (тільки з телефонами)"

    def add_arguments(self, parser):
        parser.add_argument(
            "path",
            type=str,
            help="Шлях до .xlsx файлу або до папки data",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Імпортувати всі *_raw.xlsx з папки",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Тільки показати, без запису в БД",
        )

    def handle(self, *args, **options):
        path = Path(options["path"])
        dry_run = options["dry_run"]
        do_all = options["all"]

        files = []
        if path.is_file() and path.suffix.lower() in (".xlsx", ".xls"):
            files = [path]
        elif path.is_dir() and do_all:
            files = sorted(path.glob("*_raw.xlsx")) + sorted(path.glob("*raw*.xlsx"))
            # унікальні
            files = list(dict.fromkeys(files))
        elif path.is_dir():
            self.stderr.write(self.style.ERROR(
                "Вказана папка. Додай --all щоб імпортувати всі *_raw.xlsx"
            ))
            return
        else:
            self.stderr.write(self.style.ERROR(f"Не знайдено: {path}"))
            return

        if not files:
            self.stderr.write(self.style.ERROR("Немає файлів для імпорту"))
            return

        total_c = total_s = total_e = 0
        for f in files:
            try:
                c, s, e = import_file(f, dry_run, self.stdout, self.style)
                total_c += c
                total_s += s
                total_e += e
            except SystemExit:
                self.stdout.write(self.style.WARNING(
                    f"\nDRY-RUN для {f.name}: було б створено записи (див. вище). Нічого не записано."
                ))
                return

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Разом: створено {total_c}, пропущено {total_s}, помилок {total_e}"
        ))
