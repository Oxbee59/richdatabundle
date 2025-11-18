from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    is_agent = models.BooleanField(default=False)           # user indicated they want to be agent
    is_agent_active = models.BooleanField(default=False)    # set True after successful registration payment
    phone = models.CharField(max_length=30, blank=True)

    def __str__(self):
        return f'Profile({self.user.username})'

@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_profile(sender, instance, **kwargs):
    # ensure profile exists and saved
    try:
        instance.profile.save()
    except Exception:
        # in some rare timing cases profile may not exist yet
        pass


# ---------- Existing domain models (bundles & purchases) ----------
from decimal import Decimal

class Bundle(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    color = models.CharField(max_length=20, default="#3498db")
    logo = models.CharField(max_length=200, blank=True, help_text="Static path to network logo (e.g. 'images/mtn.png')")
    network = models.CharField(max_length=50, default="MTN")

    def __str__(self):
        return f"{self.name} ({self.code})"


class Purchase(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)   # the actor (customer or agent making the sale)
    recipient = models.CharField(max_length=40)
    bundle = models.ForeignKey(Bundle, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    api_transaction_id = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return f"Purchase({self.id}) by {self.user.username} – {self.bundle.name}"


# ---------- New: Agent registration payment tracker ----------
class AgentRegistration(models.Model):
    """
    Tracks one-time agent registration payments. We'll use its id in Paystack 'reference'.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    paystack_reference = models.CharField(max_length=128, blank=True, null=True)

    def __str__(self):
        status = "Paid" if self.paid else "Pending"
        return f"AgentRegistration({self.user.username}, {status})"
