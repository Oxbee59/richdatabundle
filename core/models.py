from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from decimal import Decimal


# ------------------------------------
# PROFILE MODEL
# ------------------------------------
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    is_agent = models.BooleanField(default=False)           # user requested agent account
    is_agent_active = models.BooleanField(default=False)    # true after registration payment
    phone = models.CharField(max_length=30, blank=True)
    wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)


    def __str__(self):
        return f'Profile({self.user.username})'


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_profile(sender, instance, **kwargs):
    try:
        instance.profile.save()
    except:
        pass


# ------------------------------------
# EXISTING MODELS
# ------------------------------------
class Bundle(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    color = models.CharField(max_length=20, default="#3498db")
    logo = models.CharField(max_length=200, blank=True)
    network = models.CharField(max_length=50, default="MTN")

    def __str__(self):
        return f"{self.name} ({self.code})"


class Purchase(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    recipient = models.CharField(max_length=40)
    bundle = models.ForeignKey(Bundle, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    api_transaction_id = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return f"Purchase({self.id}) by {self.user.username}"


# ------------------------------------
# AGENT REGISTRATION
# ------------------------------------
class AgentRegistration(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    paystack_reference = models.CharField(max_length=128, blank=True, null=True)

    def __str__(self):
        status = "Paid" if self.paid else "Pending"
        return f"AgentRegistration({self.user.username}, {status})"


# ------------------------------------
# API MODELS
# ------------------------------------
class ApiKey(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    key = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)
    description = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"ApiKey({self.user.username}, {self.key[:8]}...)"


class ApiAccessLog(models.Model):
    api_key = models.ForeignKey(ApiKey, on_delete=models.SET_NULL, null=True)
    endpoint = models.CharField(max_length=128)
    method = models.CharField(max_length=10)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    status_code = models.IntegerField(null=True)

    def __str__(self):
        return f"ApiAccessLog({self.endpoint}, {self.status_code})"

# core/models.py (add at the bottom)

class AgentSettings(models.Model):
    """
    Stores global agent settings like registration fee.
    Only one instance is needed.
    """
    registration_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return f"AgentSettings(Registration Fee: ₵{self.registration_fee})"

    class Meta:
        verbose_name = "Agent Setting"
        verbose_name_plural = "Agent Settings"
