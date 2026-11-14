from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Avg
from datetime import timedelta


PRACTICE_AREAS = [
    ('family', 'Family Law'),
    ('criminal', 'Criminal Law'),
    ('corporate', 'Corporate Law'),
    ('immigration', 'Immigration Law'),
    ('property', 'Property Law'),
    ('civil', 'Civil Law'),
    ('tax', 'Tax Law'),
    ('labour', 'Labour & Employment'),
    ('ip', 'Intellectual Property'),
    ('other', 'Other'),
]

MODE_CHOICES = [
    ('call', 'Video Call'),
    ('text', 'Text'),
    ('in_person', 'In Person'),
]

BOOKING_STATUS = [
    ('pending', 'Pending Lawyer Response'),
    ('slots_offered', 'Slots Offered'),
    ('expired', 'Expired'),
    ('confirmed', 'Confirmed'),
    ('completed', 'Completed'),
    ('cancelled', 'Cancelled'),
]

TRANSACTION_TYPES = [
    ('payment', 'Client Payment (Escrow In)'),
    ('payout', 'Lawyer Payout'),
    ('platform_fee', 'Platform Fee'),
    ('refund', 'Refund to Client'),
    ('topup', 'Wallet Top-Up'),
]

RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]


class Lawyer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='lawyer_profile')
    bar_number = models.CharField(max_length=50, unique=True)
    bio = models.TextField(blank=True)
    city = models.CharField(max_length=100)
    practice_areas = models.CharField(max_length=255, help_text="Comma-separated keys from PRACTICE_AREAS")
    years_experience = models.PositiveIntegerField(default=0)
    consultation_rate = models.DecimalField(max_digits=10, decimal_places=2, help_text="Rate per consultation")
    wallet_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_verified = models.BooleanField(default=False)
    photo = models.ImageField(upload_to='lawyer_photos/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def practice_area_list(self):
        keys = [k.strip() for k in self.practice_areas.split(',') if k.strip()]
        lookup = dict(PRACTICE_AREAS)
        return [lookup.get(k, k) for k in keys]

    def average_rating(self):
        result = self.reviews.aggregate(avg=Avg('rating'))['avg']
        return round(result, 1) if result else None

    def rating_count(self):
        return self.reviews.filter(rating__isnull=False).count()

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.bar_number})"


class Client(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='client_profile')
    city = models.CharField(max_length=100)
    photo = models.ImageField(upload_to='client_photos/', blank=True, null=True)
    wallet_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username


def default_response_deadline():
    return timezone.now() + timedelta(hours=24)


class Booking(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='bookings')
    lawyer = models.ForeignKey(Lawyer, on_delete=models.CASCADE, related_name='bookings')
    status = models.CharField(max_length=20, choices=BOOKING_STATUS, default='pending')
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    response_deadline = models.DateTimeField(default=default_response_deadline)
    availability_slot = models.ForeignKey('AvailabilitySlot', on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_expired(self):
        return self.status == 'pending' and timezone.now() > self.response_deadline

    def can_message(self):
        return self.status in ['confirmed', 'completed']

    def consultation_datetime(self):
        if self.availability_slot_id:
            return self.availability_slot.proposed_datetime
        selected_slot = self.time_slots.filter(is_selected=True).first()
        return selected_slot.proposed_datetime if selected_slot else None

    def consultation_end_datetime(self):
        starts_at = self.consultation_datetime()
        return starts_at + timedelta(hours=1) if starts_at else None

    def can_cancel(self):
        if self.status in ['pending', 'slots_offered']:
            return True
        starts_at = self.consultation_datetime()
        cancellation_deadline = starts_at - timedelta(hours=10) if starts_at else None
        return (
            self.status == 'confirmed'
            and cancellation_deadline is not None
            and timezone.now() < cancellation_deadline
        )

    def can_complete(self):
        ends_at = self.consultation_end_datetime()
        return (
            self.status == 'confirmed'
            and ends_at is not None
            and timezone.now() >= ends_at
            and not Complaint.objects.filter(booking_id=self.pk).exists()
        )

    def can_report_no_show(self):
        starts_at = self.consultation_datetime()
        ends_at = starts_at + timedelta(hours=1) if starts_at else None
        return (
            self.status == 'confirmed'
            and starts_at is not None
            and ends_at is not None
            and starts_at <= timezone.now() < ends_at
            and not Complaint.objects.filter(booking_id=self.pk).exists()
        )

    def __str__(self):
        return f"Booking #{self.id}: {self.client} -> {self.lawyer} [{self.status}]"


class TimeSlot(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='time_slots')
    proposed_datetime = models.DateTimeField()
    mode = models.CharField(max_length=20, choices=MODE_CHOICES)
    is_selected = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.proposed_datetime} ({self.mode}) for Booking #{self.booking_id}"


class AvailabilitySlot(models.Model):
    """A lawyer's published consultation time, which can be booked once."""
    lawyer = models.ForeignKey(Lawyer, on_delete=models.CASCADE, related_name='availability_slots')
    proposed_datetime = models.DateTimeField()
    mode = models.CharField(max_length=20, choices=MODE_CHOICES)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['proposed_datetime']
        constraints = [
            models.UniqueConstraint(fields=['lawyer', 'proposed_datetime'], name='unique_lawyer_availability_time'),
        ]

    def __str__(self):
        return f"{self.lawyer}: {self.proposed_datetime} ({self.mode})"


class WalletTransaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wallet_transactions')
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_type}: {self.amount} -> {self.user}"


class Message(models.Model):
    """Direct message between the client and lawyer of a specific booking.
    Only usable once the booking is confirmed (or completed)."""
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Message on Booking #{self.booking_id} from {self.sender}"


class Review(models.Model):
    """A rating/review of a specific lawyer. Shown ONLY on that lawyer's profile, visible to everyone."""
    booking = models.OneToOneField('Booking', on_delete=models.SET_NULL, null=True, blank=True, related_name='review')
    lawyer = models.ForeignKey(Lawyer, on_delete=models.CASCADE, related_name='reviews')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='lawyer_reviews')
    text = models.TextField(blank=True)
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Review of {self.lawyer} - {self.rating}star"


class Complaint(models.Model):
    TYPE_CHOICES = [
        ('other', 'Other complaint'),
        ('no_show', 'Lawyer did not attend'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('reviewing', 'Under Review'),
        ('resolved', 'Resolved'),
    ]
    RESOLUTION_CHOICES = [
        ('refund_client', 'Client refunded'),
        ('payment_released', 'Payment released to lawyer'),
        ('other', 'Other resolution'),
    ]

    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='complaint')
    complaint_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='other')
    text = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    resolution = models.CharField(max_length=20, choices=RESOLUTION_CHOICES, blank=True)
    admin_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Complaint for Booking #{self.booking_id} ({self.get_status_display()})"


class Experience(models.Model):
    """A general, Reddit-style real-life experience post. Not tied to any lawyer."""
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='experiences')
    title = models.CharField(max_length=200)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def like_count(self):
        return self.likes.count()

    def comment_count(self):
        return self.comments.count()

    def __str__(self):
        return self.title


class ExperienceComment(models.Model):
    experience = models.ForeignKey(Experience, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='experience_comments')
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Comment on {self.experience_id}"


class ExperienceLike(models.Model):
    experience = models.ForeignKey(Experience, on_delete=models.CASCADE, related_name='likes')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='experience_likes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('experience', 'user')
