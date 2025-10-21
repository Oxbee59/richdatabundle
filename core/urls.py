from django.urls import path
from . import views

urlpatterns = [
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.dashboard, name='dashboard'),
    path('buy-bundle/', views.buy_bundle, name='buy_bundle'),
    path('payment-success/', views.payment_success, name='payment_success'),
    path('paystack-webhook/', views.paystack_webhook, name='paystack_webhook'),
]
