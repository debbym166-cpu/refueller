import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, password_validation
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import services
from .models import FuelPrice, FuelRedemption, LitreLot, LitrePurchase, Station

logger = logging.getLogger(__name__)

LOGIN = "portfolio:login"

GAUGE_HEIGHTS = [6, 8, 10, 12, 14, 16, 14, 12, 16, 10, 8, 14, 9, 12]


# ----------------------------------------------------------------- helpers
def _parse_litres(raw, minimum, maximum):
    """Return (Decimal, error). Accepts up to 3 decimal places."""
    try:
        litres = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        return None, "Enter a valid number of litres."
    if not litres.is_finite():
        return None, "Enter a valid number of litres."
    if litres != litres.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP):
        return None, "Litres can have at most 3 decimal places."
    litres = litres.quantize(Decimal("0.001"))
    if litres < minimum:
        return None, f"The minimum is {minimum.normalize():f}L."
    if litres > maximum:
        return None, f"The maximum is {maximum.normalize():f}L."
    return litres, None


def _price_context():
    price = FuelPrice.current_price()
    return {
        "price": price,
        "price_raw": str(price.normalize() if price == price.to_integral() else price),
    }


def _safe_next(request):
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return ""


# -------------------------------------------------------------------- auth
def signup(request):
    if request.user.is_authenticated:
        return redirect("portfolio:home")

    error = ""
    success = None

    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        password1 = request.POST.get("password1") or ""
        password2 = request.POST.get("password2") or ""

        errors = []
        try:
            validate_email(email)
        except ValidationError:
            errors.append("Enter a valid email address.")

        if password1 != password2:
            errors.append("Passwords do not match.")
        elif not errors:
            try:
                password_validation.validate_password(password1)
            except ValidationError as exc:
                errors.extend(exc.messages)

        if not errors and (
            User.objects.filter(username__iexact=email).exists()
            or User.objects.filter(email__iexact=email).exists()
        ):
            errors.append("An account with this email already exists.")

        if not errors:
            try:
                User.objects.create_user(username=email, email=email, password=password1)
                success = "Account created successfully. You can now log in."
            except IntegrityError:
                errors.append("An account with this email already exists.")

        error = "\n".join(errors)

    return render(request, "signup.html", {"error": error, "success": success})


def login_page(request):
    if request.user.is_authenticated:
        return redirect("portfolio:home")

    error = ""

    if request.method == "POST":
        identifier = (request.POST.get("email") or "").strip()
        password = request.POST.get("password") or ""

        if len(identifier) < 3:
            error = "Email is required."
        elif not password.strip():
            error = "Password is required."
        else:
            # Normal accounts use their email as username; fall back to a
            # unique email match so accounts such as the admin still work.
            user = authenticate(request, username=identifier, password=password)
            if user is None:
                matches = User.objects.filter(email__iexact=identifier)
                if matches.count() == 1:
                    user = authenticate(request, username=matches[0].username, password=password)
            if user is not None:
                auth_login(request, user)
                return redirect(_safe_next(request) or "portfolio:home")
            error = "Invalid email or password."

    return render(request, "register.html", {"error": error, "next": _safe_next(request)})


def about(request):
    return render(request, "about.html")


def contact(request):
    return render(request, "contact.html")


# ---------------------------------------------------------------- stations
@login_required(login_url=LOGIN)
def stationViews(request):
    """List stations. Staff can add one (this used to create a station on every page load)."""
    if request.method == "POST":
        if not request.user.is_staff:
            messages.error(request, "Only staff can add stations.")
            return redirect("portfolio:station")

        name = (request.POST.get("station-name") or "").strip()
        address = (request.POST.get("station-address") or "").strip()
        code = (request.POST.get("station-code") or "").strip()
        if not (name and address and code):
            messages.error(request, "Name, address and code are all required.")
        elif Station.objects.filter(code=code).exists():
            messages.error(request, "A station with that code already exists.")
        else:
            Station.objects.create(name=name, address=address, code=code, is_active=True)
            messages.success(request, f"{name} added.")
        return redirect("portfolio:station")

    return render(request, "station.html", {"stations": Station.objects.all().order_by("name")})


# --------------------------------------------------------------- dashboard
@login_required(login_url=LOGIN)
def homePage(request):
    user = request.user
    lots = list(services.active_lots(user))
    balance = sum((lot.litres_remaining for lot in lots), Decimal("0.000"))
    total_purchased = sum((lot.litres_purchased for lot in lots), Decimal("0.000"))
    price_ctx = _price_context()

    # wallet gauge: how much of what you bought into the active lots is still there
    on_count = 0
    if balance > 0 and total_purchased > 0:
        on_count = max(1, round(len(GAUGE_HEIGHTS) * float(balance / total_purchased)))
    gauge = [{"h": h, "on": i < on_count} for i, h in enumerate(GAUGE_HEIGHTS)]

    # price change over the last 7 days
    week_ago = timezone.now() - timedelta(days=7)
    older = FuelPrice.objects.filter(effective_from__lte=week_ago).first()
    price_change = None
    if older and older.price_per_litre:
        price_change = ((price_ctx["price"] - older.price_per_litre) / older.price_per_litre * 100).quantize(Decimal("0.1"))

    soon_cutoff = timezone.now() + timedelta(days=14)
    expiring = [lot for lot in lots if lot.expires_at <= soon_cutoff]

    hour = timezone.localtime().hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"

    context = {
        "greeting": greeting,
        "balance": balance,
        "gauge": gauge,
        "wallet_value": (balance * price_ctx["price"]).quantize(Decimal("1"), rounding=ROUND_HALF_UP),
        "price_change": price_change,
        "price_change_up": price_change is not None and price_change > 0,
        "expiring_litres": sum((lot.litres_remaining for lot in expiring), Decimal("0.000")),
        "expiring_until": max((lot.expires_at for lot in expiring), default=None),
        "recent_purchases": LitrePurchase.objects.filter(user=user, status="SUCCESS").order_by("-paid_at")[:2],
        "recent_redemptions": FuelRedemption.objects.filter(user=user, status="REDEEMED")
        .select_related("station").order_by("-redeemed_at")[:2],
        **price_ctx,
    }
    return render(request, "dashboard.html", context)


@login_required(login_url=LOGIN)
def litreLots(request):
    user = request.user
    services.sync_expired_lots(user)
    now = timezone.now()

    active = list(services.active_lots(user))
    expired = list(
        LitreLot.objects.filter(user=user, status="EXPIRED").order_by("-expires_at")
    )

    def decorate(lot):
        lot.days_left = max((lot.expires_at - now).days, 0)
        lot.percent_left = (
            int((lot.litres_remaining / lot.litres_purchased * 100).to_integral_value())
            if lot.litres_purchased else 0
        )
        lot.is_warning = lot.days_left <= 14
        return lot

    context = {
        "active_lots": [decorate(lot) for lot in active],
        "expired_lots": [decorate(lot) for lot in expired],
        "balance": sum((lot.litres_remaining for lot in active), Decimal("0.000")),
    }
    return render(request, "litre-lots.html", context)


@login_required(login_url=LOGIN)
def transactionHistory(request):
    user = request.user
    services.sync_expired_lots(user)
    services.expire_old_redemptions(user)

    rows = []
    for p in LitrePurchase.objects.filter(user=user, status="SUCCESS"):
        rows.append({"type": "buy", "when": p.paid_at or p.created_at, "title": "Litres purchased",
                     "litres": p.litres_bought, "naira": p.total_amount})
    for r in FuelRedemption.objects.filter(user=user, status="REDEEMED").select_related("station"):
        rows.append({"type": "redeem", "when": r.redeemed_at or r.created_at, "title": r.station.name,
                     "litres": r.litres_redeemed, "naira": None})
    for lot in LitreLot.objects.filter(user=user, status="EXPIRED", litres_remaining__gt=0):
        rows.append({"type": "expired", "when": lot.expires_at, "title": "Unused litres expired",
                     "litres": lot.litres_remaining, "naira": None})

    rows.sort(key=lambda row: row["when"], reverse=True)
    return render(request, "transaction-history.html", {"rows": rows})


@login_required(login_url=LOGIN)
def priceHistory(request):
    """Builds the four datasets the existing price-chart JS switches between."""
    now = timezone.now()
    history = list(FuelPrice.objects.order_by("effective_from"))
    current = FuelPrice.current_price()

    def price_at(moment):
        value = None
        for entry in history:
            if entry.effective_from <= moment:
                value = entry.price_per_litre
            else:
                break
        if value is None:
            value = history[0].price_per_litre if history else current
        return float(value)

    ranges = {"7D": 7, "30D": 30, "90D": 90, "1Y": 365}
    datasets = {}
    for key, days in ranges.items():
        steps = 7
        points = []
        for i in range(steps):
            moment = now - timedelta(days=days) + timedelta(days=days) * i / (steps - 1)
            local = timezone.localtime(moment)
            points.append([f"{local:%b} {local.day}", price_at(moment)])
        datasets[key] = points

    return render(request, "price-history.html", {
        "datasets": datasets,
        "recent_prices": FuelPrice.objects.all()[:8],
        **_price_context(),
    })


# --------------------------------------------------------------------- buy
@login_required(login_url=LOGIN)
def buyLitre(request):
    price_ctx = _price_context()
    context = {
        "validity_days": settings.LITRE_VALIDITY_DAYS,
        "expiry_date": timezone.now() + timedelta(days=settings.LITRE_VALIDITY_DAYS),
        "litres_value": "20",
        "max_litres": settings.MAX_LITRES_PER_PURCHASE,
        **price_ctx,
    }
    context["total_preview"] = f"{(price_ctx['price'] * 20).quantize(Decimal('1'), rounding=ROUND_HALF_UP):,}"

    if request.method == "POST":
        litres, error = _parse_litres(request.POST.get("litres"), Decimal("1"), settings.MAX_LITRES_PER_PURCHASE)
        if error:
            messages.error(request, error)
            context["litres_value"] = request.POST.get("litres", "20")
            return render(request, "buy-litres.html", context)

        purchase = services.create_pending_purchase(request.user, litres)
        services.complete_purchase(purchase)
        return redirect(f"{reverse('portfolio:pump-up-buy-processing-page')}?reference={purchase.payment_reference}")


    return render(request, "buy-litres.html", context)


@login_required(login_url=LOGIN)
def buyProcessingView(request):
    reference = request.GET.get("reference", "")
    purchase = get_object_or_404(LitrePurchase, payment_reference=reference, user=request.user, status="SUCCESS")
    return render(request, "buy-processing.html", {
        "purchase": purchase,
        "success_url": f"{reverse('portfolio:pump-up-purchase-success-page')}?reference={purchase.payment_reference}",
    })


@login_required(login_url=LOGIN)
def purchaseSuccessView(request):
    purchase = get_object_or_404(
        LitrePurchase.objects.select_related("litre_lot"),
        payment_reference=request.GET.get("reference", ""), user=request.user, status="SUCCESS",
    )
    lot = getattr(purchase, "litre_lot", None)
    return render(request, "purchase-success.html", {
        "purchase": purchase,
        "expires_at": lot.expires_at if lot else None,
    })


# ------------------------------------------------------------------ redeem
def _qr_svg(content):
    """QR as inline SVG. Needs the `segno` package; without it the page still
    works and shows the 6-digit code for the attendant to type in."""
    try:
        import segno
    except ImportError:
        return ""
    return segno.make(content, error="m").svg_inline(scale=5, border=1, dark="#10241C", light="#FFFFFF", omitsize=True)


@login_required(login_url=LOGIN)
def redeemFuelView(request):
    user = request.user
    stations = list(Station.objects.filter(is_active=True).order_by("name"))
    available = services.available_to_redeem(user)

    if request.method == "POST":
        station = next((s for s in stations if s.code == request.POST.get("station")), None)
        if available > 0:
            litres, error = _parse_litres(request.POST.get("litres"), Decimal("0.5"), available)
        else:
            litres, error = None, "You have no litres available to redeem."
        if station is None and not error:
            error = "Choose one of the listed stations."
        if error:
            messages.error(request, error)
        else:
            redemption = services.create_redemption(user, station, litres)
            return redirect("portfolio:pump-up-qr-redemption-page", code=redemption.qr_code)

    now = timezone.now()
    lots = []
    for i, lot in enumerate(services.active_lots(user)):
        soon = lot.expires_at <= now + timedelta(days=14)
        label = (
            f"From lot expiring {lot.expires_at:%b} {lot.expires_at.day} (soonest)"
            if i == 0 else f"From lot purchased {lot.created_at:%b} {lot.created_at.day}"
        )
        lots.append({"litres": float(lot.litres_remaining), "label": label, "badge": "warning" if soon else "healthy"})

    return render(request, "redeem-fuel.html", {
        "stations": stations,
        "available": available,
        "available_raw": str(available),
        "lots_data": lots,
        "default_litres": min(Decimal("10"), available) if available > 0 else Decimal("0"),
    })


def _own_redemption(request, code):
    redemption = get_object_or_404(FuelRedemption.objects.select_related("station"), qr_code=code, user=request.user)
    services.expire_old_redemptions(request.user)
    redemption.refresh_from_db()
    return redemption


@login_required(login_url=LOGIN)
def qrRedemptionView(request, code):
    redemption = _own_redemption(request, code)
    if redemption.status == "REDEEMED":
        return redirect(f"{reverse('portfolio:pump-up-redemption-success-page')}?id={redemption.qr_code}")
    if redemption.status != "PENDING":
        return redirect(f"{reverse('portfolio:pump-up-redemption-expired-page')}?id={redemption.qr_code}")

    seconds = max(int((redemption.qr_expires_at - timezone.now()).total_seconds()), 0)
    return render(request, "qr-redemption.html", {
        "redemption": redemption,
        "seconds_remaining": seconds,
        "countdown_text": f"{seconds // 60}:{seconds % 60:02d}",
        "qr_svg": _qr_svg(str(redemption.qr_code)),
        "status_url": reverse("portfolio:pump-up-redemption-status", args=[redemption.qr_code]),
        "success_url": f"{reverse('portfolio:pump-up-redemption-success-page')}?id={redemption.qr_code}",
        "expired_url": f"{reverse('portfolio:pump-up-redemption-expired-page')}?id={redemption.qr_code}",
    })


@login_required(login_url=LOGIN)
def redemptionStatus(request, code):
    redemption = _own_redemption(request, code)
    return JsonResponse({
        "status": redemption.status,
        "seconds_remaining": max(int((redemption.qr_expires_at - timezone.now()).total_seconds()), 0),
    })


@login_required(login_url=LOGIN)
@require_POST
def cancelRedemption(request, code):
    redemption = _own_redemption(request, code)
    if redemption.status == "PENDING":
        redemption.status = "CANCELLED"
        redemption.save(update_fields=["status"])
        messages.success(request, "Redemption cancelled. Nothing was deducted.")
    return redirect("portfolio:home")


@login_required(login_url=LOGIN)
def qrRedemptionExpiredView(request):
    redemption = _own_redemption(request, request.GET["id"]) if _is_uuid(request.GET.get("id")) else None
    return render(request, "qr-redemption-expired.html", {"redemption": redemption})


@login_required(login_url=LOGIN)
def redemptionSuccessView(request):
    if not _is_uuid(request.GET.get("id")):
        raise Http404
    redemption = get_object_or_404(
        FuelRedemption.objects.select_related("station", "redeemed_by"),
        qr_code=request.GET["id"], user=request.user, status="REDEEMED",
    )
    return render(request, "redemption-success.html", {
        "redemption": redemption,
        "balance": services.wallet_balance(request.user),
    })


def _is_uuid(value):
    import uuid
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False
