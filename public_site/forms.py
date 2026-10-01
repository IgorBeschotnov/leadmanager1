from django import forms

from leads.models import Company, PUBLIC_FORM_SOURCE


class PartnerContactForm(forms.ModelForm):
    """Публична форма «Допомогти зв'язатись».

    Свідомо мінімум полів — це не повноцінна картка ліда (це заповнить
    менеджер після дзвінка), а лише те, без чого не можна зв'язатись.
    """

    message = forms.CharField(
        label="Повідомлення",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Коротко: чим можете допомогти або що потрібно"}),
    )

    class Meta:
        model = Company
        fields = ["name", "contact_person", "phones", "emails", "city", "address"]
        labels = {
            "name": "Назва компанії / організації / ім'я",
            "contact_person": "Контактна особа",
            "phones": "Телефон",
            "emails": "Email",
            "city": "Місто",
            "address": "Адреса (за бажанням)",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Наприклад: ФОП Іваненко або просто ваше ім'я"}),
            "contact_person": forms.TextInput(attrs={"placeholder": "Хто ви (якщо не вказано вище)"}),
            "phones": forms.TextInput(attrs={"placeholder": "+380..."}),
            "emails": forms.TextInput(attrs={"placeholder": "you@example.com"}),
            "city": forms.TextInput(attrs={"placeholder": "Місто"}),
            "address": forms.TextInput(attrs={"placeholder": "Вулиця, будинок"}),
        }

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("phones") and not cleaned.get("emails"):
            raise forms.ValidationError(
                "Залиште хоча б телефон або email — інакше ми не зможемо звʼязатись."
            )
        return cleaned

    def save(self, commit=True):
        lead = super().save(commit=False)
        lead.source = PUBLIC_FORM_SOURCE
        lead.stage = "new"
        message = self.cleaned_data.get("message", "").strip()
        if message:
            lead.internal_notes = f"[Повідомлення з форми]\n{message}"
        if commit:
            lead.save()
        return lead
