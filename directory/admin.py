from django.contrib import admin
from .models import Lawyer, Client, Booking, TimeSlot, WalletTransaction, Review


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
    actions = ['mark_as_fined']

    @admin.action(description="Mark selected bookings as FINED (10%% clawback: 5%% to client, 5%% to platform)")
    def mark_as_fined(self, request, queryset):
        from decimal import Decimal
        fined_count = 0
        for booking in queryset:
            if booking.status == 'fined':
                continue
            fine_amount = booking.amount_paid * Decimal('0.10')
            client_bonus = booking.amount_paid * Decimal('0.05')
            platform_cut = booking.amount_paid * Decimal('0.05')

            lawyer = booking.lawyer
            client = booking.client

            lawyer.wallet_balance -= fine_amount
            lawyer.save()

            client.wallet_balance += client_bonus
            client.save()

            WalletTransaction.objects.create(
                user=lawyer.user, booking=booking, amount=-fine_amount,
                transaction_type='fine_penalty'
            )
            WalletTransaction.objects.create(
                user=client.user, booking=booking, amount=client_bonus,
                transaction_type='fine_bonus'
            )

            booking.status = 'fined'
            booking.save()
            fined_count += 1

        self.message_user(request, f"{fined_count} booking(s) marked as fined.")


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
    list_display = ('id', 'lawyer', 'created_at')
    list_filter = ('lawyer',)
    search_fields = ('text',)