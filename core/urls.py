# core/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('buy-bundle/', views.buy_bundle, name='buy_bundle'),
    path('payment-success/', views.payment_success, name='payment_success'),
    path('my-purchases/', views.my_purchases, name='my_purchases'),
    path('profile/', views.profile, name='profile'),
    path('paystack-webhook/', views.paystack_webhook, name='paystack_webhook'),
]
