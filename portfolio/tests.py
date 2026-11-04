from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import FuelPrice, FuelRedemption, LitreLot, LitrePurchase, Station


class BuyLitresTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ada@example.com", "ada@example.com", "pass12345!x")
        self.client.force_login(self.user)
        FuelPrice.objects.create(price_per_litre=Decimal("980"))
        self.url = reverse("portfolio:pump-up-buy-litres-page")

    def test_pages_require_login(self):
        self.client.logout()
        for name in ["home", "pump-up-buy-litres-page", "pump-up-litre-lots-page", "pump-up-redeem-fuel-page"]:
            response = self.client.get(reverse(f"portfolio:{name}"))
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login/", response["Location"])

    def test_clicking_pay_completes_the_purchase(self):
        response = self.client.post(self.url, {"litres": "20"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("buy-processing", response["Location"])

        purchase = LitrePurchase.objects.get()
        self.assertEqual(purchase.status, "SUCCESS")
        self.assertEqual(purchase.total_amount, Decimal("19600.00"))
        self.assertEqual(services.wallet_balance(self.user), Decimal("20.000"))

        lot = LitreLot.objects.get()
        self.assertAlmostEqual((lot.expires_at - timezone.now()).days, 89, delta=1)

        ref = purchase.payment_reference
        for name in ["buy-processing", "purchase-success"]:
            page = self.client.get(reverse(f"portfolio:pump-up-{name}-page"), {"reference": ref})
            self.assertEqual(page.status_code, 200)

    def test_purchase_is_only_credited_once(self):
        self.client.post(self.url, {"litres": "5"})
        purchase = LitrePurchase.objects.get()
        services.complete_purchase(purchase)
        services.complete_purchase(purchase)
        self.assertEqual(LitreLot.objects.count(), 1)

    def test_browser_cannot_set_the_price(self):
        self.client.post(self.url, {"litres": "10", "price_per_litre": "1"})
        self.assertEqual(LitrePurchase.objects.get().price_per_litre, Decimal("980.00"))

    def test_invalid_litres_rejected(self):
        for bad in ["", "abc", "0", "-5", "99999", "1.23456", "nan"]:
            response = self.client.post(self.url, {"litres": bad})
            self.assertEqual(response.status_code, 200, bad)
        self.assertEqual(LitrePurchase.objects.count(), 0)

    def test_cannot_open_someone_elses_purchase(self):
        self.client.post(self.url, {"litres": "5"})
        ref = LitrePurchase.objects.get().payment_reference
        other = User.objects.create_user("bob@example.com", "bob@example.com", "pass12345!x")
        self.client.force_login(other)
        page = self.client.get(reverse("portfolio:pump-up-purchase-success-page"), {"reference": ref})
        self.assertEqual(page.status_code, 404)


class WalletAndRedemptionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ada@example.com", "ada@example.com", "pass12345!x")
        self.client.force_login(self.user)
        FuelPrice.objects.create(price_per_litre=Decimal("980"))
        self.station = Station.objects.create(name="Total Lekki Phase 1", address="12 Admiralty Way", code="TL1")
        now = timezone.now()
        for i, (litres, days) in enumerate([(Decimal("20"), 60), (Decimal("10"), 5)]):
            p = LitrePurchase.objects.create(user=self.user, litres_bought=litres, price_per_litre=Decimal("900"),
                                             payment_reference=f"R{i}", status="SUCCESS", paid_at=now)
            LitreLot.objects.create(user=self.user, purchase=p, litres_purchased=litres, litres_remaining=litres,
                                    price_per_litre=Decimal("900"), expires_at=now + timedelta(days=days))

    def test_all_pages_render(self):
        for name in ["home", "pump-up-litre-lots-page", "pump-up-transaction-history-page",
                     "pump-up-price-history-page", "pump-up-buy-litres-page", "pump-up-redeem-fuel-page", "station", "about"]:
            response = self.client.get(reverse(f"portfolio:{name}"))
            self.assertEqual(response.status_code, 200, name)
        home = self.client.get(reverse("portfolio:home"))
        self.assertContains(home, "30.000")          # balance
        self.assertContains(home, "10.000L")         # expiring soon
        self.assertNotContains(home, "Tunde")

    def test_redeem_flow_deducts_earliest_expiring_first(self):
        response = self.client.post(reverse("portfolio:pump-up-redeem-fuel-page"), {"station": "TL1", "litres": "12"})
        self.assertEqual(response.status_code, 302)
        redemption = FuelRedemption.objects.get()
        self.assertEqual(redemption.status, "PENDING")
        self.assertEqual(services.wallet_balance(self.user), Decimal("30.000"))  # nothing deducted yet

        qr = self.client.get(reverse("portfolio:pump-up-qr-redemption-page", args=[redemption.qr_code]))
        self.assertContains(qr, redemption.verification_code)
        status = self.client.get(reverse("portfolio:pump-up-redemption-status", args=[redemption.qr_code])).json()
        self.assertEqual(status["status"], "PENDING")

        services.confirm_redemption(redemption)
        lots = list(LitreLot.objects.order_by("expires_at"))
        self.assertEqual(lots[0].litres_remaining, Decimal("0.000"))   # 10L lot (5 days) used first
        self.assertEqual(lots[0].status, "EXHAUSTED")
        self.assertEqual(lots[1].litres_remaining, Decimal("18.000"))
        done = self.client.get(reverse("portfolio:pump-up-redemption-success-page"), {"id": redemption.qr_code})
        self.assertContains(done, "12.000")

    def test_cannot_redeem_more_than_available_or_double_reserve(self):
        url = reverse("portfolio:pump-up-redeem-fuel-page")
        self.assertEqual(self.client.post(url, {"station": "TL1", "litres": "31"}).status_code, 200)
        self.assertEqual(FuelRedemption.objects.count(), 0)
        self.client.post(url, {"station": "TL1", "litres": "25"})
        self.assertEqual(FuelRedemption.objects.count(), 1)
        self.client.post(url, {"station": "TL1", "litres": "10"})   # only 5 left unreserved
        self.assertEqual(FuelRedemption.objects.count(), 1)

    def test_expired_and_cancelled_redemptions(self):
        r = services.create_redemption(self.user, self.station, Decimal("5"))
        r.qr_expires_at = timezone.now() - timedelta(seconds=1)
        r.save()
        page = self.client.get(reverse("portfolio:pump-up-qr-redemption-page", args=[r.qr_code]))
        self.assertEqual(page.status_code, 302)
        self.assertIn("qr-expired", page["Location"])
        with self.assertRaises(services.RedemptionError):
            services.confirm_redemption(r)

        r2 = services.create_redemption(self.user, self.station, Decimal("5"))
        self.client.post(reverse("portfolio:pump-up-redemption-cancel", args=[r2.qr_code]))
        r2.refresh_from_db()
        self.assertEqual(r2.status, "CANCELLED")

    def test_expired_lots_stop_counting(self):
        LitreLot.objects.filter(litres_purchased=10).update(expires_at=timezone.now() - timedelta(days=1))
        self.assertEqual(services.wallet_balance(self.user), Decimal("20.000"))
        history = self.client.get(reverse("portfolio:pump-up-transaction-history-page"))
        self.assertContains(history, "Unused litres expired")


class AuthTests(TestCase):
    def test_signup_login_and_next(self):
        response = self.client.post(reverse("portfolio:signup"),
                                    {"email": "New@Example.com", "password1": "S3cure-pass!", "password2": "S3cure-pass!"})
        self.assertContains(response, "Account created")
        user = User.objects.get(username="new@example.com")

        dup = self.client.post(reverse("portfolio:signup"),
                               {"email": "new@example.com", "password1": "S3cure-pass!", "password2": "S3cure-pass!"})
        self.assertContains(dup, "already exists")
        weak = self.client.post(reverse("portfolio:signup"),
                                {"email": "w@example.com", "password1": "123", "password2": "123"})
        self.assertContains(weak, "too short")

        bad = self.client.post(reverse("portfolio:login"), {"email": "new@example.com", "password": "wrong"})
        self.assertContains(bad, "Invalid email or password")

        target = reverse("portfolio:pump-up-buy-litres-page")
        ok = self.client.post(reverse("portfolio:login") + f"?next={target}",
                              {"email": "new@example.com", "password": "S3cure-pass!"})
        self.assertRedirects(ok, target, fetch_redirect_response=False)

        evil = self.client.post(reverse("portfolio:login") + "?next=https://evil.example/",
                                {"email": "new@example.com", "password": "S3cure-pass!"})
        self.assertRedirects(evil, reverse("portfolio:home"), fetch_redirect_response=False)
