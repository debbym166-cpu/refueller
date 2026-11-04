from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = "portfolio"

urlpatterns = [
    path('', views.homePage, name='home'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    path('station/', views.stationViews, name='station'),
    path('signup/', views.signup, name='signup'),
    path('login/', views.login_page, name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # buying litres
    path('buy-litres/', views.buyLitre, name='pump-up-buy-litres-page'),
    path('buy-processing/', views.buyProcessingView, name='pump-up-buy-processing-page'),
    path('purchase-success/', views.purchaseSuccessView, name='pump-up-purchase-success-page'),

    # redeeming fuel
    path('redeem-fuel/', views.redeemFuelView, name='pump-up-redeem-fuel-page'),
    path('redemption/<uuid:code>/', views.qrRedemptionView, name='pump-up-qr-redemption-page'),
    path('redemption/<uuid:code>/status/', views.redemptionStatus, name='pump-up-redemption-status'),
    path('redemption/<uuid:code>/cancel/', views.cancelRedemption, name='pump-up-redemption-cancel'),
    path('redemption-success/', views.redemptionSuccessView, name='pump-up-redemption-success-page'),
    path('qr-expired/', views.qrRedemptionExpiredView, name='pump-up-redemption-expired-page'),

    # wallet info
    path('litre-lots/', views.litreLots, name='pump-up-litre-lots-page'),
    path('transaction-history/', views.transactionHistory, name='pump-up-transaction-history-page'),
    path('price-history/', views.priceHistory, name='pump-up-price-history-page'),
]
