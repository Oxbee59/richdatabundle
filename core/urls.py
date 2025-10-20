from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('buy/', views.buy_bundle, name='buy_bundle'),
    path('my-purchases/', views.my_purchases, name='my_purchases'),
    path('profile/', views.profile, name='profile'),

    # Paystack payment routes
    path('paystack/callback/', views.paystack_callback, name='paystack_callback'),

    # ✅ New: Paystack Webhook route (for backend payment confirmation)
    path('paystack/webhook/', views.paystack_webhook, name='paystack_webhook'),
]
