from decimal import Decimal

from django.contrib import admin
from django.db import transaction
from .models import Lawyer, Client, Booking, TimeSlot, WalletTransaction, Review, Complaint


class TimeSlotInline(admin.TabularInline):
    model = TimeSlot
    extra = 1


class WalletTransactionInline(admin.TabularInline):
    model = WalletTransaction
    extra = 0
    readonly_fields = ('user', 'amount', 'transaction_type', 'created_at')
    can_delete = False


@admin.register(Lawyer)
class LawyerAdmin(admin.ModelAdmin):
    list_display = ('user', 'bar_number', 'city', 'consultation_rate', 'wallet_balance', 'is_verified')
    list_filter = ('is_verified', 'city')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'bar_number')


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('user', 'city', 'wallet_balance')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'lawyer', 'status', 'amount_paid', 'response_deadline', 'created_at')
    list_filter = ('status',)
    inlines = [TimeSlotInline, WalletTransactionInline]


@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = ('booking', 'proposed_datetime', 'mode', 'is_selected')
    list_filter = ('mode', 'is_selected')


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'transaction_type', 'amount', 'booking', 'created_at')
    list_filter = ('transaction_type',)
    readonly_fields = ('created_at',)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('id', 'lawyer', 'author', 'rating', 'booking', 'created_at')
    list_filter = ('lawyer',)
    search_fields = ('text',)


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ('id', 'booking', 'complaint_type', 'status', 'resolution', 'created_at', 'updated_at')
    list_filter = ('complaint_type', 'status', 'resolution', 'created_at')
    search_fields = ('text', 'booking__client__user__username', 'booking__lawyer__user__username')
    readonly_fields = (
        'booking', 'booking_client_contact', 'booking_lawyer_contact',
        'complaint_type', 'text', 'created_at', 'updated_at',
    )
    actions = ('confirm_no_show_and_refund', 'dismiss_no_show_and_release_payment')

    @admin.display(description='Client contact')
    def booking_client_contact(self, complaint):
        user = complaint.booking.client.user
        return f"{user.get_full_name() or user.username} <{user.email}>"

    @admin.display(description='Lawyer contact')
    def booking_lawyer_contact(self, complaint):
        user = complaint.booking.lawyer.user
        return f"{user.get_full_name() or user.username} <{user.email}>"

    @admin.action(description="Confirm lawyer no-show after contacting both parties; refund client")
    def confirm_no_show_and_refund(self, request, queryset):
        self._resolve_no_show_reports(request, queryset, refund_client=True)

    @admin.action(description="Dismiss no-show report after contacting both parties; release lawyer payment")
    def dismiss_no_show_and_release_payment(self, request, queryset):
        self._resolve_no_show_reports(request, queryset, refund_client=False)

    def _resolve_no_show_reports(self, request, queryset, *, refund_client):
        resolved = 0
        skipped = 0
        for selected in queryset:
            with transaction.atomic():
                complaint = Complaint.objects.select_for_update().get(pk=selected.pk)
                booking = Booking.objects.select_for_update().select_related(
                    'client__user', 'lawyer__user'
                ).get(pk=complaint.booking_id)
                if (complaint.complaint_type != 'no_show'
                        or complaint.status not in ('open', 'reviewing')
                        or booking.status != 'confirmed'
                        or not complaint.admin_notes.strip()):
                    skipped += 1
                    continue

                if refund_client:
                    client = booking.client
                    client.wallet_balance += booking.amount_paid
                    client.save(update_fields=('wallet_balance',))
                    WalletTransaction.objects.create(
                        user=client.user,
                        booking=booking,
                        amount=booking.amount_paid,
                        transaction_type='refund',
                    )
                    booking.status = 'cancelled'
                    complaint.resolution = 'refund_client'
                else:
                    payout = booking.amount_paid * Decimal('0.90')
                    platform_fee = booking.amount_paid * Decimal('0.10')
                    lawyer = booking.lawyer
                    lawyer.wallet_balance += payout
                    lawyer.save(update_fields=('wallet_balance',))
                    WalletTransaction.objects.create(
                        user=lawyer.user, booking=booking, amount=payout, transaction_type='payout'
                    )
                    WalletTransaction.objects.create(
                        user=lawyer.user, booking=booking, amount=-platform_fee, transaction_type='platform_fee'
                    )
                    booking.status = 'completed'
                    complaint.resolution = 'payment_released'

                booking.save(update_fields=('status', 'updated_at'))
                complaint.status = 'resolved'
                complaint.save(update_fields=('status', 'resolution', 'updated_at'))
                resolved += 1

        self.message_user(
            request,
            f"Resolved {resolved} no-show complaint(s); skipped {skipped}. "
            "Record contact with both parties in admin notes before deciding.",
        )
