from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from ..forms import ClientProfileForm, ClientSignUpForm, LawyerSignUpForm
from ..models import Experience, WalletTransaction


def client_signup(request):
    if request.method == 'POST':
        form = ClientSignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Welcome to The Roll. Your account is ready.")
            return redirect('browse')
    else:
        form = ClientSignUpForm()
    return render(request, 'directory/signup_client.html', {'form': form})


def list_yourself(request):
    if request.method == 'POST':
        form = LawyerSignUpForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "You're on the roll. Your file has been opened.")
            return redirect('lawyer_dashboard')
    else:
        form = LawyerSignUpForm()
    return render(request, 'directory/signup_lawyer.html', {'form': form})


@login_required
def client_profile(request):
    if not hasattr(request.user, 'client_profile'):
        messages.error(request, "This page is for client accounts.")
        return redirect('browse')
    client = request.user.client_profile
    if request.method == 'POST':
        form = ClientProfileForm(request.POST, request.FILES, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect('client_profile')
    else:
        form = ClientProfileForm(instance=client)
    own_experiences = Experience.objects.filter(author=request.user).order_by('-created_at')
    return render(request, 'directory/client_profile.html', {'client': client, 'form': form, 'own_experiences': own_experiences})


@login_required
def add_funds(request):
    if not hasattr(request.user, 'client_profile'):
        messages.error(request, "This page is for client accounts.")
        return redirect('browse')
    client = request.user.client_profile
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', '0'))
        except Exception:
            amount = Decimal('0')
        if amount > 0:
            client.wallet_balance += amount
            client.save()
            WalletTransaction.objects.create(user=request.user, amount=amount, transaction_type='topup')
            messages.success(request, f"₹{amount} added to your wallet.")
        else:
            messages.error(request, "Enter a valid amount.")
    return redirect('client_profile')
