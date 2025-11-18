from rest_framework import serializers
from .models import Bundle, Purchase

class BundleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bundle
        fields = ['id', 'name', 'code', 'price', 'network']

class PurchaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Purchase
        fields = ['id', 'user', 'bundle', 'amount', 'paid', 'created_at']
