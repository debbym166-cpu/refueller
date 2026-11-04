import uuid
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


#  Station, FuelPrice, LitreWallet,LitrePurchase,LitreLot,FuelRedemption
'''
NAME ADDRESS STATIONCODE, created at , is active
80L - jOHN
'''

class Station(models.Model):
    # start adding properties for the station 
    # name : str 
    # address: str
    
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True, blank=False,null =False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class FuelPrice(models.Model):
    price_per_litre = models.DecimalField(
        max_digits=8,
        decimal_places=2
    )

    effective_from = models.DateTimeField(
        auto_now_add=True
    )

    set_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fuel_prices_set"
    )

    class Meta:
        ordering = ["-effective_from"]
        verbose_name_plural = "Fuel Price History"

    def __str__(self):
        return f"₦{self.price_per_litre} / L"

    @classmethod
    def current_price(cls):
        """Latest price set in the admin, or the default from settings."""
        latest = cls.objects.first()  # Meta.ordering is -effective_from
        if latest:
            return latest.price_per_litre
        return settings.DEFAULT_PRICE_PER_LITRE


class LitrePurchase(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("SUCCESS", "Success"),
        ("FAILED", "Failed"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="litre_purchases",
    )

    litres_bought = models.DecimalField(
        max_digits=10,
        decimal_places=3
    )

    price_per_litre = models.DecimalField(
        max_digits=8,
        decimal_places=2
    )

    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        editable= False
    )

    payment_reference = models.CharField(
        max_length=100,
        unique=True
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="PENDING"
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return (
            f"{self.user.username} bought "
            f"{self.litres_bought}L  => ₦{self.total_amount}"
        )


    def save(self, *args , **kwargs):
        self.total_amount = (self.price_per_litre * self.litres_bought).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        super().save(*args, **kwargs)
        

class LitreWallet(models.Model):

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="litre_wallet"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.user.username}'s Litre Wallet"

    @property
    def available_litres(self):
        # LitreLot has no direct FK to LitreWallet - it's linked through
        # `user` (see the model relationships: User -> many LitreLots).
        lots = self.user.litre_lots.filter(
            status="ACTIVE",
            expires_at__gt=timezone.now(),
            litres_remaining__gt=0
        )

        return sum(
            (lot.litres_remaining for lot in lots),
            Decimal("0.000")
        )


class LitreLot(models.Model):

    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("EXHAUSTED", "Exhausted"),
        ("EXPIRED", "Expired"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="litre_lots"
    )

    purchase = models.OneToOneField(
        LitrePurchase,
        on_delete=models.CASCADE,
        related_name="litre_lot"
    )

    litres_purchased = models.DecimalField(
        max_digits=10,
        decimal_places=3
    )

    litres_remaining = models.DecimalField(
        max_digits=10,
        decimal_places=3
    )

    price_per_litre = models.DecimalField(
        max_digits=8,
        decimal_places=2
    )

    expires_at = models.DateTimeField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="ACTIVE"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return (
            f"{self.user.username} - "
            f"{self.litres_remaining}L remaining"
        )

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at


class FuelRedemption(models.Model):

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("REDEEMED", "Redeemed"),
        ("EXPIRED", "Expired"),
        ("CANCELLED", "Cancelled"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="fuel_redemptions"
    )

    station = models.ForeignKey(
        Station,
        on_delete=models.CASCADE,
        related_name="fuel_redemptions"
    )

    litres_redeemed = models.DecimalField(
        max_digits=10,
        decimal_places=3
    )

    qr_code = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False
    )

    qr_expires_at = models.DateTimeField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="PENDING"
    )

    redeemed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendant_redemptions"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    redeemed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    def __str__(self):
        return (
            f"{self.user.username} - "
            f"{self.litres_redeemed}L - "
            f"{self.status}"
        )

    @property
    def is_expired(self):
        return timezone.now() >= self.qr_expires_at

    @property
    def verification_code(self):
        """
        A short, human-typeable 6-digit code derived from the QR UUID.

        This isn't stored anywhere - it's calculated the same way every
        time from `qr_code`, so an attendant can type it in by hand and we
        can look the redemption back up by recalculating the same code for
        pending redemptions.
        """
        return str(int(self.qr_code.hex[:6], 16) % 1000000).zfill(6)
