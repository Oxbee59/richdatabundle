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

    # Accept both webhook URL forms to avoid 404 from Paystack
    path('paystack-webhook/', views.paystack_webhook, name='paystack_webhook'),
    path('paystack/webhook/', views.paystack_webhook, name='paystack_webhook_alt'),

    # Agent registration payment start
    path('agent-register/<int:reg_id>/', views.agent_register, name='agent_register'),

    # ------- Simple API endpoints -------
    path('api/bundles/', views.api_bundles, name='api_bundles'),
    path('api/sell/', views.api_sell, name='api_sell'),
    path('api/agent/<int:user_id>/transactions/', views.api_agent_transactions, name='api_agent_transactions'),
]
