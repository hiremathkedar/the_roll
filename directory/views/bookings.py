from decimal import Decimal
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ..forms import ComplaintForm, LawyerReviewForm
from ..models import AvailabilitySlot, Booking, Experience, Message, TimeSlot, WalletTransaction
from .directory import ensure_default_availability, expire_stale_bookings


@login_required
def book_availability_slot(request, slot_id):
    if request.method != 'POST':
        return redirect('browse')
    if not hasattr(request.user, 'client_profile'):
        messages.error(request, "Only client accounts can book a consultation.")
        return redirect('browse')

    with transaction.atomic():
        slot = get_object_or_404(AvailabilitySlot.objects.select_for_update(), id=slot_id)
        client = request.user.client_profile
        client = type(client).objects.select_for_update().get(pk=client.pk)
        if not slot.is_available or slot.proposed_datetime <= timezone.now():
            messages.error(request, "That time is no longer available. Please choose another slot.")
            return redirect('lawyer_detail', lawyer_id=slot.lawyer_id)
        if client.wallet_balance < slot.lawyer.consultation_rate:
            messages.error(request, "Insufficient wallet balance to book this consultation.")
            return redirect('lawyer_detail', lawyer_id=slot.lawyer_id)

        client.wallet_balance -= slot.lawyer.consultation_rate
        client.save(update_fields=['wallet_balance'])
        booking = Booking.objects.create(
            client=client, lawyer=slot.lawyer, availability_slot=slot,
            amount_paid=slot.lawyer.consultation_rate, status='confirmed',
        )
        slot.is_available = False
        slot.save(update_fields=['is_available'])
        WalletTransaction.objects.create(
            user=client.user, booking=booking, amount=-booking.amount_paid, transaction_type='payment'
        )
    messages.success(request, "Consultation booked. Your payment is held in escrow until completion.")
    return redirect('my_bookings')


@login_required
def manage_availability(request):
    if not hasattr(request.user, 'lawyer_profile'):
        messages.error(request, "This page is for lawyer accounts.")
        return redirect('browse')
    lawyer = request.user.lawyer_profile
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'delete':
            slot = get_object_or_404(AvailabilitySlot, id=request.POST.get('slot_id'), lawyer=lawyer)
            if slot.is_available:
                slot.is_available = False
                slot.save(update_fields=['is_available'])
                messages.success(request, "Availability removed from your profile.")
            else:
                messages.error(request, "A booked time cannot be removed.")
        else:
            dt = parse_datetime(request.POST.get('proposed_datetime', ''))
            mode = request.POST.get('mode')
            if dt and timezone.is_naive(dt):
                dt = timezone.make_aware(dt)
            if (not dt or dt <= timezone.now() or dt.minute != 0
                    or dt.second or dt.microsecond
                    or mode not in dict(AvailabilitySlot._meta.get_field('mode').choices)):
                messages.error(request, "Choose a future time on the hour and a valid consultation mode. Each slot is one hour.")
            elif AvailabilitySlot.objects.filter(lawyer=lawyer, proposed_datetime=dt).exists():
                messages.error(request, "You already have a slot at that time.")
            else:
                AvailabilitySlot.objects.create(lawyer=lawyer, proposed_datetime=dt, mode=mode)
                messages.success(request, "Availability added to your profile.")
        return redirect('lawyer_dashboard')
    return redirect('lawyer_dashboard')


@login_required
def cancel_booking(request, booking_id):
    if request.method != 'POST':
        return redirect('my_bookings')

    with transaction.atomic():
        booking = get_object_or_404(
            Booking.objects.select_for_update().select_related('client'),
            id=booking_id,
            client__user=request.user,
        )
        if not booking.can_cancel():
            messages.error(request, "A booking cannot be cancelled or refunded within 10 hours of its consultation.")
            return redirect('my_bookings')

        client = booking.client
        client.wallet_balance += booking.amount_paid
        client.save(update_fields=['wallet_balance'])
        WalletTransaction.objects.create(
            user=client.user, booking=booking, amount=booking.amount_paid, transaction_type='refund'
        )
        booking.status = 'cancelled'
        booking.save()
        if booking.availability_slot_id:
            slot = booking.availability_slot
            if slot.proposed_datetime > timezone.now():
                slot.is_available = True
                slot.save(update_fields=['is_available'])

    messages.success(request, "Booking cancelled. The refund was returned to your wallet.")
    return redirect('my_bookings')


@login_required
def decline_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    if booking.lawyer.user != request.user:
        messages.error(request, "Not authorized.")
        return redirect('lawyer_dashboard')
    if booking.status != 'pending':
        messages.error(request, "This booking can no longer be declined.")
        return redirect('lawyer_dashboard')
    if request.method == 'POST':
        client = booking.client
        client.wallet_balance += booking.amount_paid
        client.save()
        WalletTransaction.objects.create(
            user=client.user, booking=booking, amount=booking.amount_paid, transaction_type='refund'
        )
        booking.status = 'cancelled'
        booking.save()
        messages.success(request, "Booking declined. The client has been refunded in full.")
    return redirect('lawyer_dashboard')


@login_required
def lawyer_dashboard(request):
    if not hasattr(request.user, 'lawyer_profile'):
        messages.error(request, "This page is for lawyer accounts.")
        return redirect('browse')

    expire_stale_bookings()
    lawyer = request.user.lawyer_profile
    ensure_default_availability(lawyer)
    bookings = lawyer.bookings.select_related('client__user').prefetch_related('time_slots').order_by('-created_at')

    if request.method == 'POST' and request.POST.get('booking_id'):
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
                    if dt.minute == 0 and not dt.second and not dt.microsecond:
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
        'availability_slots': lawyer.availability_slots.filter(
            proposed_datetime__gt=timezone.now(),
        ).annotate(
            is_booked=Exists(Booking.objects.filter(
                availability_slot_id=OuterRef('pk'), status__in=['confirmed', 'completed']
            ))
        ).filter(Q(is_available=True) | Q(is_booked=True)).order_by('proposed_datetime'),
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
def booking_messages(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)

    if request.user not in (booking.client.user, booking.lawyer.user):
        messages.error(request, "Not authorized.")
        return redirect('browse')

    if not booking.can_message():
        messages.error(request, "Messaging unlocks once this consultation is confirmed.")
        if hasattr(request.user, 'client_profile'):
            return redirect('my_bookings')
        return redirect('lawyer_dashboard')

    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        if text:
            Message.objects.create(booking=booking, sender=request.user, text=text)
        return redirect('booking_messages', booking_id=booking.id)

    other_party = booking.lawyer.user if request.user == booking.client.user else booking.client.user

    return render(request, 'directory/booking_messages.html', {
        'booking': booking,
        'thread': booking.messages.select_related('sender'),
        'other_party': other_party,
    })


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
    if request.method != 'POST':
        return redirect('my_bookings')

    with transaction.atomic():
        booking = get_object_or_404(
            Booking.objects.select_for_update().select_related('client', 'lawyer'),
            id=booking_id,
            client__user=request.user,
        )
        if booking.status != 'confirmed':
            messages.error(request, "This booking can't be marked complete right now.")
            return redirect('my_bookings')
        if not booking.can_complete():
            messages.error(request, "A consultation can only be marked complete after its one-hour time has ended.")
            return redirect('my_bookings')

        payout = booking.amount_paid * Decimal('0.90')
        platform_fee = booking.amount_paid * Decimal('0.10')
        lawyer = booking.lawyer
        lawyer.wallet_balance += payout
        lawyer.save(update_fields=['wallet_balance'])

        WalletTransaction.objects.create(user=lawyer.user, booking=booking, amount=payout, transaction_type='payout')
        WalletTransaction.objects.create(user=lawyer.user, booking=booking, amount=-platform_fee, transaction_type='platform_fee')

        booking.status = 'completed'
        booking.save()
    messages.success(request, "Consultation marked complete. Payment released to counsel (minus 10% platform fee).")
    return redirect('my_bookings')


@login_required
def submit_review(request, booking_id):
    if request.method != 'POST':
        return redirect('my_bookings')
    booking = get_object_or_404(Booking, id=booking_id, client__user=request.user, status='completed')
    if hasattr(booking, 'review'):
        messages.info(request, "You have already reviewed this consultation.")
        return redirect('my_bookings')

    form = LawyerReviewForm(request.POST)
    if form.is_valid():
        review = form.save(commit=False)
        review.booking = booking
        review.lawyer = booking.lawyer
        review.author = request.user
        review.save()
        messages.success(request, "Thank you for rating your lawyer.")
    else:
        messages.error(request, "Choose a rating from 1 to 5 before submitting.")
    return redirect('my_bookings')


@login_required
def submit_complaint(request, booking_id):
    if request.method != 'POST':
        return redirect('my_bookings')
    booking = get_object_or_404(
        Booking, id=booking_id, client__user=request.user, status__in=['confirmed', 'completed']
    )
    complaint_type = 'other'
    if booking.status == 'confirmed':
        if not booking.can_report_no_show():
            messages.error(request, "A no-show complaint can only be filed during the booked consultation hour.")
            return redirect('my_bookings')
        complaint_type = 'no_show'
    if hasattr(booking, 'complaint'):
        messages.info(request, "A complaint has already been submitted for this consultation.")
        return redirect('my_bookings')

    form = ComplaintForm(request.POST)
    if form.is_valid():
        complaint = form.save(commit=False)
        complaint.booking = booking
        complaint.complaint_type = complaint_type
        complaint.save()
        if complaint_type == 'no_show':
            messages.success(request, "Your no-show complaint is with the admin team. Payment is on hold during review.")
        else:
            messages.success(request, "Your complaint has been submitted for review.")
    else:
        messages.error(request, "Please describe the concern before submitting your complaint.")
    return redirect('my_bookings')
