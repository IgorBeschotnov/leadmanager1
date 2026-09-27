from django.contrib import messages
from django.shortcuts import redirect, render

from accounts.models import User

from .forms import PartnerContactForm
from .models import CarouselSlide


def home(request):
    """Головна публічна сторінка: карусель про проєкт, соцмережі, команда.

    Нічого тут не потребує логіну — це навмисно відкрита вітрина.
    Тексти/слайди/соцмережі редагуються в /admin/, не в шаблоні
    (site_settings прилітає в контекст сам, через context_processors).
    """
    staff = (
        User.objects.filter(is_public_profile=True)
        .order_by("public_order", "first_name", "username")
    )
    slides = CarouselSlide.objects.filter(is_active=True)
    return render(request, "public_site/home.html", {
        "staff": staff,
        "slides": slides,
    })


def partner_form(request):
    """Окрема вкладка «Допомогти зв'язатись».

    POST створює Company з source=PUBLIC_FORM_SOURCE, stage='new' —
    менеджер побачить її у «Задачі» з поміткою «З сайту», подзвонить
    і доопрацює картку як завжди.
    """
    if request.method == "POST":
        form = PartnerContactForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Дякуємо! Заявку передано менеджеру — з вами звʼяжуться найближчим часом.",
            )
            return redirect("public_site:partner_form")
    else:
        form = PartnerContactForm()

    return render(request, "public_site/partner_form.html", {"form": form})
