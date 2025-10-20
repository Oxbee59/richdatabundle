from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
class Profile(models.Model):
    user = models.OneToOneField(User,on_delete=models.CASCADE)
    is_agent = models.BooleanField(default=False)
    phone = models.CharField(max_length=30,blank=True)
    def __str__(self): return f'Profile({self.user.username})'
@receiver(post_save,sender=User)
def create_profile(sender,instance,created,**kwargs):
    if created: Profile.objects.create(user=instance)
@receiver(post_save,sender=User)
def save_profile(sender,instance,**kwargs): instance.profile.save()
from django.db import models
from django.contrib.auth.models import User

class Bundle(models.Model):
    network = models.CharField(max_length=20)
    size_label = models.CharField(max_length=50)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    bundle_code = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)  # ✅ add this line

    def __str__(self):
        return f"{self.network} - {self.size_label} ({self.price}₦)"

class Purchase(models.Model):
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    bundle = models.ForeignKey(Bundle,on_delete=models.CASCADE)
    recipient = models.CharField(max_length=40)
    amount = models.DecimalField(max_digits=8,decimal_places=2)
    paid = models.BooleanField(default=False)
    api_transaction_id = models.CharField(max_length=255,blank=True,null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"{self.user.username} -> {self.recipient} | {self.bundle}"