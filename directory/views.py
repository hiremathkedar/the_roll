from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.db.models import Q, Count, Value
from django.db.models.functions import Concat
from .models import (
    Lawyer, Review, PRACTICE_AREAS, Booking, TimeSlot, WalletTransaction,
    Experience, ExperienceComment, ExperienceLike,
)
from .forms import (
    ClientSignUpForm, LawyerSignUpForm, LawyerReviewForm,
    ExperienceForm, ExperienceCommentForm, ClientProfileForm,
)


def expire_stale_bookings():
    stale = Booking.objects.filter(status='pending', response_deadline__lt=timezone.now())
    for booking in stale:
        client = booking.client
        client.wallet_balance += booking.amount_paid
        client.save()
        WalletTransaction.objects.create(
            user=client.user, booking=booking, amount=booking.amount_paid, transaction_type='refund'
        )
        booking.status = 'expired'
        booking.save()


def browse(request):
    lawyers = Lawyer.objects.select_related('user').all()

    practice_area = request.GET.get('practice_area', '')
    city = request.GET.get('city', '').strip()
    name = request.GET.get('name', '').strip()
    sort = request.GET.get('sort', '')

    if practice_area:
        lawyers = lawyers.filter(practice_areas__icontains=practice_area)
    if city:
        lawyers = lawyers.filter(city__icontains=city)
    if name:
        lawyers = lawyers.filter(
            Q(user__first_name__icontains=name) |
            Q(user__last_name__icontains=name) |
            Q(user__username__icontains=name)
        )

    if sort == 'rate_low':
        lawyers = lawyers.order_by('consultation_rate')
    elif sort == 'rate_high':
        lawyers = lawyers.order_by('-consultation_rate')
    elif sort == 'experience':
        lawyers = lawyers.order_by('-years_experience')
    else:
        lawyers = lawyers.order_by('-created_at')

    context = {
        'lawyers': lawyers,
        'practice_areas': PRACTICE_AREAS,
        'selected_practice_area': practice_area,
        'selected_city': city,
        'selected_name': name,
        'selected_sort': sort,
        'total_count': Lawyer.objects.count(),
        'cities_count': Lawyer.objects.values('city').distinct().count(),
        'completed_count': Booking.objects.filter(status='completed').count(),
        'total_bookings': Booking.objects.count(),
    }
    return render(request, 'directory/browse.html', context)


def lawyer_detail(request, lawyer_id):
    lawyer = get_object_or_404(Lawyer, id=lawyer_id)
    same_city = False
    if request.user.is_authenticated and hasattr(request.user, 'client_profile'):
        same_city = request.user.client_profile.city.strip().lower() == lawyer.city.strip().lower()

    review_form = LawyerReviewForm()
    if request.method == 'POST' and request.user.is_authenticated:
        review_form = LawyerReviewForm(request.POST)
        if review_form.is_valid():
            review = review_form.save(commit=False)
            review.lawyer = lawyer
            review.author = request.user
            review.save()
            messages.success(request, "Your review was posted to this lawyer's profile.")
            return redirect('lawyer_detail', lawyer_id=lawyer.id)

    return render(request, 'directory/lawyer_detail.html', {
        'lawyer': lawyer,
        'same_city': same_city,
        'review_form': review_form,
        'lawyer_reviews': lawyer.reviews.order_by('-created_at'),
        'lawyer_experiences': Experience.objects.filter(author=lawyer.user).order_by('-created_at'),
    })


def public_profile(request, username):
    target_user = get_object_or_404(User, username=username)

    if hasattr(target_user, 'lawyer_profile'):
        return redirect('lawyer_detail', lawyer_id=target_user.lawyer_profile.id)

    if hasattr(target_user, 'client_profile'):
        client = target_user.client_profile
        experiences = Experience.objects.filter(author=target_user).order_by('-created_at')
        return render(request, 'directory/public_client_profile.html', {
            'profile_user': target_user,
            'client': client,
            'experiences': experiences,
        })

    messages.error(request, "This user doesn't have a public profile.")
    return redirect('browse')


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


@login_required
def confirm_selection(request, lawyer_id):
    lawyer = get_object_or_404(Lawyer, id=lawyer_id)
    if not hasattr(request.user, 'client_profile'):
        messages.error(request, "Only client accounts can select a lawyer. Sign up as a client first.")
        return redirect('lawyer_detail', lawyer_id=lawyer.id)

    client = request.user.client_profile
    insufficient = client.wallet_balance < lawyer.consultation_rate

    return render(request, 'directory/confirm_selection.html', {
        'lawyer': lawyer,
        'client': client,
        'insufficient': insufficient,
    })


@login_required
def select_lawyer(request, lawyer_id):
    lawyer = get_object_or_404(Lawyer, id=lawyer_id)
    if not hasattr(request.user, 'client_profile'):
        messages.error(request, "Only client accounts can select a lawyer. Sign up as a client first.")
        return redirect('lawyer_detail', lawyer_id=lawyer.id)

    client = request.user.client_profile

    if request.method == 'POST':
        if client.wallet_balance < lawyer.consultation_rate:
            messages.error(request, "Insufficient wallet balance to select this counsel.")
            return redirect('lawyer_detail', lawyer_id=lawyer.id)

        client.wallet_balance -= lawyer.consultation_rate
        client.save()

        booking = Booking.objects.create(
            client=client, lawyer=lawyer, amount_paid=lawyer.consultation_rate
        )
        WalletTransaction.objects.create(
            user=client.user, booking=booking, amount=-lawyer.consultation_rate, transaction_type='payment'
        )
        messages.success(
            request,
            f"₹{lawyer.consultation_rate} placed in escrow. "
            f"{lawyer.user.get_full_name() or lawyer.user.username} has 24 hours to respond with available slots."
        )
        return redirect('my_bookings')

    return redirect('lawyer_detail', lawyer_id=lawyer.id)


@login_required
def lawyer_dashboard(request):
    if not hasattr(request.user, 'lawyer_profile'):
        messages.error(request, "This page is for lawyer accounts.")
        return redirect('browse')

    expire_stale_bookings()
    lawyer = request.user.lawyer_profile
    bookings = lawyer.bookings.select_related('client__user').prefetch_related('time_slots').order_by('-created_at')

    if request.method == 'POST':
        booking_id = request.POST.get('booking_id')
        booking = get_object_or_404(Booking, id=booking_id, lawyer=lawyer, status='pending')
        slots_created = 0
        for i in range(1, 4):
            dt_str = request.POST.get(f'slot{i}_datetime')
            mode = request.POST.get(f'slot{i}_mode')
            if dt_str and mode:
                dt = parse_datetime(dt_str)
                if dt:
                    if timezone.is_naive(dt):
                        dt = timezone.make_aware(dt)
                    TimeSlot.objects.create(booking=booking, proposed_datetime=dt, mode=mode)
                    slots_created += 1

        if slots_created:
            booking.status = 'slots_offered'
            booking.save()
            messages.success(request, f"{slots_created} time slot(s) sent to the client.")
        else:
            messages.error(request, "Please provide at least one valid time slot.")
        return redirect('lawyer_dashboard')

    return render(request, 'directory/lawyer_dashboard.html', {
        'lawyer': lawyer,
        'bookings': bookings,
        'own_experiences': Experience.objects.filter(author=request.user).order_by('-created_at'),
    })


@login_required
def my_bookings(request):
    if not hasattr(request.user, 'client_profile'):
        messages.error(request, "This page is for client accounts.")
        return redirect('browse')

    expire_stale_bookings()
    client = request.user.client_profile
    bookings = client.bookings.select_related('lawyer__user').prefetch_related('time_slots').order_by('-created_at')
    return render(request, 'directory/my_bookings.html', {'client': client, 'bookings': bookings})


@login_required
def confirm_slot(request, slot_id):
    slot = get_object_or_404(TimeSlot, id=slot_id)
    booking = slot.booking

    if booking.client.user != request.user:
        messages.error(request, "Not authorized.")
        return redirect('my_bookings')
    if booking.status != 'slots_offered':
        messages.error(request, "This booking is no longer awaiting slot confirmation.")
        return redirect('my_bookings')

    booking.time_slots.update(is_selected=False)
    slot.is_selected = True
    slot.save()
    booking.status = 'confirmed'
    booking.save()
    messages.success(request, "Slot confirmed. Your consultation is booked.")
    return redirect('my_bookings')


@login_required
def complete_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)

    if booking.client.user != request.user:
        messages.error(request, "Not authorized.")
        return redirect('my_bookings')
    if booking.status != 'confirmed':
        messages.error(request, "This booking can't be marked complete right now.")
        return redirect('my_bookings')

    payout = booking.amount_paid * Decimal('0.90')
    platform_fee = booking.amount_paid * Decimal('0.10')

    lawyer = booking.lawyer
    lawyer.wallet_balance += payout
    lawyer.save()

    WalletTransaction.objects.create(user=lawyer.user, booking=booking, amount=payout, transaction_type='payout')
    WalletTransaction.objects.create(user=lawyer.user, booking=booking, amount=-platform_fee, transaction_type='platform_fee')

    booking.status = 'completed'
    booking.save()
    messages.success(request, "Consultation marked complete. Payment released to counsel (minus 10% platform fee).")
    return redirect('my_bookings')


# ---------- Experiences (general, Reddit-style wall) ----------

def experiences_list(request):
    query = request.GET.get('q', '').strip()
    sort = request.GET.get('sort', 'newest')

    exps = Experience.objects.exclude(title='').annotate(
        full_name=Concat('author__first_name', Value(' '), 'author__last_name'),
        num_likes=Count('likes', distinct=True),
        num_comments=Count('comments', distinct=True),
    )

    if query:
        search_term = query.lstrip('@').strip()
        filters = (
            Q(title__icontains=search_term) |
            Q(body__icontains=search_term) |
            Q(author__username__icontains=search_term) |
            Q(full_name__icontains=search_term) |
            Q(author__first_name__icontains=search_term) |
            Q(author__last_name__icontains=search_term)
        )
        if search_term.isdigit():
            filters |= Q(author__id=int(search_term)) | Q(id=int(search_term))
        exps = exps.filter(filters)

    if sort == 'liked':
        exps = exps.order_by('-num_likes', '-created_at')
    elif sort == 'commented':
        exps = exps.order_by('-num_comments', '-created_at')
    else:
        exps = exps.order_by('-created_at')

    return render(request, 'directory/experiences_list.html', {
        'experiences': exps,
        'query': query,
        'sort': sort,
    })


def experience_detail(request, experience_id):
    experience = get_object_or_404(Experience, id=experience_id)

    if request.method == 'POST':
        if not request.user.is_authenticated:
            messages.error(request, "Log in to comment.")
            return redirect('login')
        form = ExperienceCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.experience = experience
            comment.author = request.user
            comment.save()
            return redirect('experience_detail', experience_id=experience.id)
    else:
        form = ExperienceCommentForm()

    user_has_liked = request.user.is_authenticated and experience.likes.filter(user=request.user).exists()

    return render(request, 'directory/experience_detail.html', {
        'experience': experience,
        'comments': experience.comments.select_related('author'),
        'form': form,
        'user_has_liked': user_has_liked,
    })


@login_required
def toggle_like(request, experience_id):
    experience = get_object_or_404(Experience, id=experience_id)
    like, created = ExperienceLike.objects.get_or_create(experience=experience, user=request.user)
    if not created:
        like.delete()
    return redirect('experience_detail', experience_id=experience.id)


@login_required
def delete_experience(request, experience_id):
    experience = get_object_or_404(Experience, id=experience_id)
    if experience.author != request.user:
        messages.error(request, "You can only delete your own experience.")
        return redirect('experience_detail', experience_id=experience.id)
    if request.method == 'POST':
        experience.delete()
        messages.success(request, "Your experience was deleted.")
        return redirect('experiences_list')
    return redirect('experience_detail', experience_id=experience.id)


@login_required
def create_experience(request):
    if request.method == 'POST':
        form = ExperienceForm(request.POST)
        if form.is_valid():
            experience = form.save(commit=False)
            experience.author = request.user
            experience.save()
            messages.success(request, "Your experience was posted.")
            return redirect('experience_detail', experience_id=experience.id)
    else:
        form = ExperienceForm()
    return render(request, 'directory/create_experience.html', {'form': form})