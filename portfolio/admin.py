from django.contrib import admin, messages

from .models import (
    FuelPrice, FuelRedemption, LitreLot, LitrePurchase, LitreWallet, Station,
)
from .services import RedemptionError, confirm_redemption


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "address", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code", "address")


@admin.register(FuelPrice)
class FuelPriceAdmin(admin.ModelAdmin):
    """Add a new row to change today's price. Old rows are kept as price history."""
    list_display = ("price_per_litre", "effective_from", "set_by")
    readonly_fields = ("set_by",)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.set_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(LitrePurchase)
class LitrePurchaseAdmin(admin.ModelAdmin):
    list_display = ("payment_reference", "user", "litres_bought", "price_per_litre", "total_amount", "status", "paid_at")
    list_filter = ("status",)
    search_fields = ("payment_reference", "user__username", "user__email")
    readonly_fields = ("total_amount", "created_at", "paid_at")
    
    def has_add_permission(self, request):
        # Disable add permission for LitrePurchase in admin
        return False
    def has_change_permission(self, request, obj=None):
        # Disable change permission for LitrePurchase in admin
        return False
    def has_delete_permission(self, request, obj=None):
        # Disable delete permission for LitrePurchase in admin
        return False


@admin.register(LitreLot)
class LitreLotAdmin(admin.ModelAdmin):
    list_display = ("user", "litres_remaining", "litres_purchased", "price_per_litre", "expires_at", "status")
    list_filter = ("status",)
    search_fields = ("user__username", "user__email")
    
    def has_add_permission(self, request):
        # Disable add permission for LitreLot in admin
        return False
    def has_change_permission(self, request, obj=None):
        # Disable change permission for LitreLot in admin
        return False
    def has_delete_permission(self, request, obj=None):
        # Disable delete permission for LitreLot in admin
        return False


admin.site.register(LitreWallet)
class LitreWalletAdmin(admin.ModelAdmin):
    
    def has_add_permission(self, request):
        # Disable add permission for LitreWallet in admin
        return False
    def has_change_permission(self, request, obj=None):
        # Disable change permission for LitreWallet in admin
        return False
    def has_delete_permission(self, request, obj=None):
        # Disable delete permission for LitreWallet in admin
        return False


@admin.register(FuelRedemption)
class FuelRedemptionAdmin(admin.ModelAdmin):
    list_display = ("user", "station", "litres_redeemed", "verification_code", "status", "qr_expires_at")
    list_filter = ("status", "station")
    search_fields = ("user__username", "user__email", "qr_code")
    actions = ["confirm_selected"]

    @admin.action(description="Confirm selected redemptions (fuel dispensed)")
    def confirm_selected(self, request, queryset):
        done = 0
        for redemption in queryset:
            try:
                confirm_redemption(redemption, attendant=request.user)
                done += 1
            except RedemptionError as exc:
                self.message_user(request, f"{redemption}: {exc}", level=messages.WARNING)
        if done:
            self.message_user(request, f"{done} redemption(s) confirmed.", level=messages.SUCCESS)
