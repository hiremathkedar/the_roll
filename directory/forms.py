from django import forms
from django.db import transaction
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Lawyer, Client, PRACTICE_AREAS, Review, RATING_CHOICES, Experience, ExperienceComment


class ClientSignUpForm(UserCreationForm):
    first_name = forms.CharField(max_length=100, required=True)
    last_name = forms.CharField(max_length=100, required=False)
    email = forms.EmailField(required=True)
    city = forms.CharField(max_length=100, required=True)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'username', 'password1', 'password2']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.email = self.cleaned_data['email']
        if commit:
            with transaction.atomic():
                user.save()
                Client.objects.create(
                    user=user,
                    city=self.cleaned_data['city'],
                    wallet_balance=0,
                )
        return user


class LawyerSignUpForm(UserCreationForm):
    first_name = forms.CharField(max_length=100, required=True)
    last_name = forms.CharField(max_length=100, required=False)
    email = forms.EmailField(required=True)
    bar_number = forms.CharField(max_length=50, required=True, label="Bar Council Number")
    city = forms.CharField(max_length=100, required=True)
    bio = forms.CharField(widget=forms.Textarea, required=False)
    years_experience = forms.IntegerField(min_value=0, required=True)
    consultation_rate = forms.DecimalField(max_digits=10, decimal_places=2, required=True, label="Consultation Rate (₹)")
    practice_areas = forms.MultipleChoiceField(
        choices=PRACTICE_AREAS,
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )
    photo = forms.ImageField(required=False, label="Profile Photo")

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'username', 'password1', 'password2']

    def clean_bar_number(self):
        bar_number = self.cleaned_data['bar_number'].strip()
        if Lawyer.objects.filter(bar_number=bar_number).exists():
            raise forms.ValidationError("This Bar Council Number is already registered on The Roll.")
        return bar_number

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.email = self.cleaned_data['email']
        if commit:
            with transaction.atomic():
                user.save()
                Lawyer.objects.create(
                    user=user,
                    bar_number=self.cleaned_data['bar_number'],
                    city=self.cleaned_data['city'],
                    bio=self.cleaned_data['bio'],
                    years_experience=self.cleaned_data['years_experience'],
                    consultation_rate=self.cleaned_data['consultation_rate'],
                    practice_areas=",".join(self.cleaned_data['practice_areas']),
                    photo=self.cleaned_data.get('photo'),
                    wallet_balance=0,
                    is_verified=False,
                )
        return user


class LawyerReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'text']
        widgets = {
            'rating': forms.Select(choices=RATING_CHOICES),
            'text': forms.Textarea(attrs={'placeholder': 'Share your experience with this counsel...', 'rows': 3}),
        }


class ExperienceForm(forms.ModelForm):
    class Meta:
        model = Experience
        fields = ['title', 'body']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'Give your experience a short title'}),
            'body': forms.Textarea(attrs={'placeholder': "What happened? Others will be able to comment.", 'rows': 6}),
        }


class ExperienceCommentForm(forms.ModelForm):
    class Meta:
        model = ExperienceComment
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={'placeholder': 'Add a comment...', 'rows': 2}),
        }
        labels = {'text': ''}


class ClientProfileForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['city', 'photo']