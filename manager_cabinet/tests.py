from datetime import timedelta

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User, Team, UserCapability
from leads.models import Company, CallLog


class LeadBusinessLogicTests(TestCase):
    """
    Проверяем главную бизнес-логику кабинета менеджера.
    """

    def setUp(self):
        """Создаём тестовые данные перед каждым тестом."""
        # Команда
        self.team = Team.objects.create(name="Тестовая команда")

        # Менеджер
        self.manager = User.objects.create_user(
            username="manager1",
            password="testpass123",
            first_name="Тетяна",
            is_staff=True,
            team=self.team,
        )
        UserCapability.objects.create(user=self.manager, capability="operator")
        UserCapability.objects.create(user=self.manager, capability="sales")

        # Лид, который ждёт отправки КП
        self.lead_letter = Company.objects.create(
            name="Компания Тест КП",
            stage="letter_sent",
            is_sent_by_manager=False,
            team=self.team,
            assigned_to=self.manager,
        )

        # Лид-партнёр
        self.lead_partner = Company.objects.create(
            name="Компания Партнёр",
            stage="success",
            team=self.team,
            assigned_to=self.manager,
        )

        self.client = Client()
        self.client.login(username="manager1", password="testpass123")

    # ─────────────────────────────────────────────
    # 1. Кнопка «КП відправлено»
    # ─────────────────────────────────────────────

    def test_mark_sent_sets_flag_and_callback(self):
        """После нажатия is_sent_by_manager=True и callback_date ≈ +3 дня"""
        url = reverse("manager:lead_detail", args=[self.lead_letter.pk])

        response = self.client.post(url, {
            "action": "mark_sent",
        })

        self.lead_letter.refresh_from_db()

        self.assertTrue(self.lead_letter.is_sent_by_manager)
        self.assertIsNotNone(self.lead_letter.callback_date)

        # Проверяем, что дата примерно через 3 дня (допуск ±1 минута)
        expected = timezone.now() + timedelta(days=3)
        diff = abs((self.lead_letter.callback_date - expected).total_seconds())
        self.assertLess(diff, 60)

    def test_mark_sent_creates_call_log(self):
        """После отметки КП появляется запись в истории"""
        url = reverse("manager:lead_detail", args=[self.lead_letter.pk])

        self.client.post(url, {"action": "mark_sent"})

        logs = CallLog.objects.filter(company=self.lead_letter)
        self.assertEqual(logs.count(), 1)
        self.assertIn("КП відправлено", logs.first().comment)

    def test_mark_sent_does_not_require_sum_and_weight(self):
        """Сумма и вес больше не нужны при отправке КП"""
        url = reverse("manager:lead_detail", args=[self.lead_letter.pk])

        # Отправляем БЕЗ donation_amount и package_weight
        response = self.client.post(url, {
            "action": "mark_sent",
        })

        self.lead_letter.refresh_from_db()
        self.assertTrue(self.lead_letter.is_sent_by_manager)
        # В заметках не должно появиться "Сума" или "Вага"
        notes = self.lead_letter.internal_notes or ""
        self.assertNotIn("Сума", notes)
        self.assertNotIn("Вага", notes)

    # ─────────────────────────────────────────────
    # 2. Блок «Допомога партнера»
    # ─────────────────────────────────────────────

    def test_record_help_writes_sum_and_weight(self):
        """Фиксация помощи записывает сумму и вес в internal_notes"""
        url = reverse("manager:lead_detail", args=[self.lead_partner.pk])

        self.client.post(url, {
            "action": "record_help",
            "donation_amount": "5000",
            "package_weight": "12",
        })

        self.lead_partner.refresh_from_db()
        notes = self.lead_partner.internal_notes or ""

        self.assertIn("Сума допомоги: 5000 грн", notes)
        self.assertIn("Вага: 12 кг", notes)

    def test_record_help_creates_call_log(self):
        """Фиксация помощи создаёт запись в истории"""
        url = reverse("manager:lead_detail", args=[self.lead_partner.pk])

        self.client.post(url, {
            "action": "record_help",
            "donation_amount": "3000",
            "package_weight": "8",
        })

        logs = CallLog.objects.filter(company=self.lead_partner)
        self.assertEqual(logs.count(), 1)
        self.assertIn("Зафіксовано допомогу", logs.first().comment)
        self.assertIn("3000", logs.first().comment)

    def test_record_help_only_for_success_stage(self):
        """Нельзя зафиксировать помощь, если лид ещё не партнёр"""
        # Пытаемся зафиксировать помощь на лиде со статусом letter_sent
        url = reverse("manager:lead_detail", args=[self.lead_letter.pk])

        self.client.post(url, {
            "action": "record_help",
            "donation_amount": "1000",
            "package_weight": "5",
        })

        self.lead_letter.refresh_from_db()
        notes = self.lead_letter.internal_notes or ""
        self.assertNotIn("Сума допомоги", notes)