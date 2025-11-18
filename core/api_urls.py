from django.urls import path
from . import views

urlpatterns = [
    path('bundles/', views.api_bundles, name='api_bundles'),
    path('sell/', views.api_sell, name='api_sell'),
    path('agent/<int:user_id>/tx/', views.api_agent_transactions, name='api_agent_transactions'),
]
