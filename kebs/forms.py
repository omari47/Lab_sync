from django import forms
from .models import Sample, SampleTestResult, Label
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.utils import timezone
from datetime import timedelta


class SampleForm(forms.ModelForm):
    class Meta:
        model = Sample
        fields = ['sample_type', 'sample_origin', 'batch_number', 'metadata']
        widgets = {
            'metadata': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add Bootstrap classes to form fields
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'


class SampleTestResultForm(forms.ModelForm):
    """Form for adding test results to samples"""

    expiry_date = forms.DateTimeField(
        initial=timezone.now() + timedelta(days=180),
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'})
    )

    class Meta:
        model = SampleTestResult
        fields = ['quality_analysis', 'compliance_status', 'expiry_date']
        widgets = {
            'quality_analysis': forms.Textarea(attrs={'rows': 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add Bootstrap classes to form fields
        for field_name, field in self.fields.items():
            if field_name != 'compliance_status':
                field.widget.attrs['class'] = 'form-control'
            else:
                field.widget.attrs['class'] = 'form-check-input'

        # Custom help text for compliance status
        self.fields['compliance_status'].help_text = 'Only compliant test results will mark a sample as completed.'


class LabelForm(forms.ModelForm):
    class Meta:
        model = Label
        fields = ['expiry_date']
        widgets = {
            'expiry_date': forms.DateInput(attrs={'type': 'date'})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add Bootstrap classes to form fields
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'


class SampleSearchForm(forms.Form):
    query = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by batch number, origin, etc.'
        })
    )


class LoginForm(AuthenticationForm):
    """Custom login form with Bootstrap styling"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Username'
        })
        self.fields['password'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Password'
        })


class RegisterForm(UserCreationForm):
    """Custom registration form with additional fields and Bootstrap styling"""
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add Bootstrap classes to all fields
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.is_active = False  # Inactive until approved by admin

        if commit:
            user.save()
        return user