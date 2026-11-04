"""Business rules for LitreVault (kept out of views so they are easy to test)."""
import logging
import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    FuelPrice, FuelRedemption, LitreLot, LitrePurchase, LitreWallet,
)

logger = logging.getLogger(__name__)

THREE_DP = Decimal("0.001")


def get_wallet(user):
    wallet, _ = LitreWallet.objects.get_or_create(user=user)
    return wallet


# ---------------------------------------------------------------- purchases
def create_pending_purchase(user, litres):
    """Price is always read on the server - the browser's price is never trusted."""
    price = FuelPrice.current_price()
    return LitrePurchase.objects.create(
        user=user,
        litres_bought=litres,
        price_per_litre=price,
        payment_reference="LV-" + uuid.uuid4().hex[:12].upper(),
        status="PENDING",
    )


def complete_purchase(purchase):
    """
    Mark the purchase as paid and put the litres in the wallet as a new lot.
    (No payment provider for now: clicking Pay completes the purchase.)
    Safe to call twice - litres are only ever added once.
    """
    with transaction.atomic():
        purchase = (
            LitrePurchase.objects.select_for_update()
            .select_related("user")
            .get(pk=purchase.pk)
        )
        if purchase.status == "SUCCESS":
            return purchase

        now = timezone.now()
        purchase.status = "SUCCESS"
        purchase.paid_at = now
        purchase.save(update_fields=["status", "paid_at"])

        get_wallet(purchase.user)
        LitreLot.objects.create(
            user=purchase.user,
            purchase=purchase,
            litres_purchased=purchase.litres_bought,
            litres_remaining=purchase.litres_bought,
            price_per_litre=purchase.price_per_litre,
            expires_at=now + timedelta(days=settings.LITRE_VALIDITY_DAYS),
            status="ACTIVE",
        )
        return purchase


# ----------------------------------------------------------------- lots
def sync_expired_lots(user):
    """Mark lots whose validity ended so they stop counting towards the balance."""
    LitreLot.objects.filter(
        user=user, status="ACTIVE", expires_at__lte=timezone.now()
    ).update(status="EXPIRED")


def active_lots(user):
    sync_expired_lots(user)
    return LitreLot.objects.filter(
        user=user, status="ACTIVE", litres_remaining__gt=0, expires_at__gt=timezone.now()
    ).order_by("expires_at", "created_at")


def wallet_balance(user):
    return sum((lot.litres_remaining for lot in active_lots(user)), Decimal("0.000"))


# ------------------------------------------------------------ redemptions
def expire_old_redemptions(user=None):
    qs = FuelRedemption.objects.filter(status="PENDING", qr_expires_at__lte=timezone.now())
    if user is not None:
        qs = qs.filter(user=user)
    qs.update(status="EXPIRED")


def pending_litres(user):
    expire_old_redemptions(user)
    return sum(
        (r.litres_redeemed for r in FuelRedemption.objects.filter(user=user, status="PENDING")),
        Decimal("0.000"),
    )


def available_to_redeem(user):
    """Balance minus litres already reserved by QR codes that are still live."""
    return max(wallet_balance(user) - pending_litres(user), Decimal("0.000"))


def create_redemption(user, station, litres):
    return FuelRedemption.objects.create(
        user=user,
        station=station,
        litres_redeemed=litres,
        qr_expires_at=timezone.now() + timedelta(minutes=settings.REDEMPTION_QR_MINUTES),
        status="PENDING",
    )


class RedemptionError(Exception):
    pass


def confirm_redemption(redemption, attendant=None):
    """
    Called when a station attendant confirms a QR/code.
    Deducts litres from the earliest-expiring lots first, all-or-nothing.
    """
    with transaction.atomic():
        redemption = FuelRedemption.objects.select_for_update().get(pk=redemption.pk)

        if redemption.status != "PENDING":
            raise RedemptionError(f"This redemption is already {redemption.get_status_display().lower()}.")
        if redemption.is_expired:
            redemption.status = "EXPIRED"
            redemption.save(update_fields=["status"])
            raise RedemptionError("This QR code has expired.")

        needed = redemption.litres_redeemed
        lots = list(active_lots(redemption.user).select_for_update())
        if sum((lot.litres_remaining for lot in lots), Decimal("0")) < needed:
            raise RedemptionError("The customer no longer has enough valid litres.")

        for lot in lots:
            if needed <= 0:
                break
            take = min(lot.litres_remaining, needed)
            lot.litres_remaining = (lot.litres_remaining - take).quantize(THREE_DP)
            if lot.litres_remaining <= 0:
                lot.status = "EXHAUSTED"
            lot.save(update_fields=["litres_remaining", "status"])
            needed -= take

        redemption.status = "REDEEMED"
        redemption.redeemed_by = attendant
        redemption.redeemed_at = timezone.now()
        redemption.save(update_fields=["status", "redeemed_by", "redeemed_at"])
        return redemption
