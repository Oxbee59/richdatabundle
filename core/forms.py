# core/forms.py
from django import forms
from django.contrib.auth.models import User

class SignupForm(forms.ModelForm):
    password1 = forms.CharField(widget=forms.PasswordInput, label='Password')
    password2 = forms.CharField(widget=forms.PasswordInput, label='Confirm Password')
    is_agent = forms.BooleanField(label='Register as agent', required=False)
    phone = forms.CharField(label='Phone (optional)', required=False)

    class Meta:
        model = User
        fields = ['username', 'email']

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p1 != p2:
            raise forms.ValidationError('Passwords do not match.')
        return cleaned

class BuyForm(forms.Form):
    recipient = forms.CharField(max_length=40, label='Recipient number')
    bundle_id = forms.IntegerField(widget=forms.HiddenInput, required=False)
    amount = forms.DecimalField(max_digits=8, decimal_places=2, widget=forms.HiddenInput, required=False)
