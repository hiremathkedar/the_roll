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
    ('call', 'Call'),
    ('text', 'Text'),
    ('in_person', 'In Person'),
]

BOOKING_STATUS = [
    ('pending', 'Pending Lawyer Response'),
    ('slots_offered', 'Slots Offered'),
    ('expired', 'Expired'),
    ('confirmed', 'Confirmed'),
    ('completed', 'Completed'),
    ('fined', 'Fined'),
    ('cancelled', 'Cancelled'),
]

TRANSACTION_TYPES = [
    ('payment', 'Client Payment (Escrow In)'),
    ('payout', 'Lawyer Payout'),
    ('platform_fee', 'Platform Fee'),
    ('refund', 'Refund to Client'),
    ('fine_bonus', 'Fine Bonus to Client'),
    ('fine_penalty', 'Fine Penalty on Lawyer'),
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_expired(self):
        return self.status == 'pending' and timezone.now() > self.response_deadline

    def __str__(self):
        return f"Booking #{self.id}: {self.client} -> {self.lawyer} [{self.status}]"


class TimeSlot(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='time_slots')
    proposed_datetime = models.DateTimeField()
    mode = models.CharField(max_length=20, choices=MODE_CHOICES)
    is_selected = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.proposed_datetime} ({self.mode}) for Booking #{self.booking_id}"


class WalletTransaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wallet_transactions')
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_type}: {self.amount} -> {self.user}"


class Review(models.Model):
    """A rating/review of a specific lawyer. Shown ONLY on that lawyer's profile, visible to everyone.
    Displayed anonymously, but tied to an author internally for moderation/spam control."""
    lawyer = models.ForeignKey(Lawyer, on_delete=models.CASCADE, related_name='reviews')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='lawyer_reviews')
    text = models.TextField()
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Review of {self.lawyer} - {self.rating}star"


class Experience(models.Model):
    """A general, Reddit-style real-life experience post. Not tied to any lawyer.
    Displayed anonymously; author kept internally for permissions/like tracking."""
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