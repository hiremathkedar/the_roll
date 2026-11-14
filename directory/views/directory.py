from datetime import datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..models import AvailabilitySlot, Booking, Experience, Lawyer, PRACTICE_AREAS, WalletTransaction


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


def ensure_default_availability(lawyer, days=90):
    """Publish a rolling daily 10:00-18:00 schedule in one-hour slots."""
    today = timezone.localdate()
    default_slots = []
    for offset in range(days):
        day = today + timedelta(days=offset)
        for hour in range(10, 18):
            slot_time = timezone.make_aware(datetime.combine(day, time(hour=hour)))
            if slot_time > timezone.now():
                default_slots.append(AvailabilitySlot(
                    lawyer=lawyer, proposed_datetime=slot_time, mode='call',
                ))
    AvailabilitySlot.objects.bulk_create(default_slots, ignore_conflicts=True)


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
    ensure_default_availability(lawyer)
    same_city = False
    if request.user.is_authenticated and hasattr(request.user, 'client_profile'):
        same_city = request.user.client_profile.city.strip().lower() == lawyer.city.strip().lower()

    return render(request, 'directory/lawyer_detail.html', {
        'lawyer': lawyer,
        'same_city': same_city,
        'lawyer_reviews': lawyer.reviews.order_by('-created_at'),
        'lawyer_experiences': Experience.objects.filter(author=lawyer.user).order_by('-created_at'),
        'available_slots': lawyer.availability_slots.filter(is_available=True, proposed_datetime__gt=timezone.now()),
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
