from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm

# Signup form
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

# Login form
class LoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={'autofocus': True}))
    password = forms.CharField(widget=forms.PasswordInput)

# Buy bundle form
class BuyForm(forms.Form):
    recipient = forms.CharField(max_length=40, label='Recipient number')
    bundle_code = forms.CharField(widget=forms.HiddenInput(), required=False)
    amount = forms.DecimalField(max_digits=8, decimal_places=2, widget=forms.HiddenInput(), required=False)
