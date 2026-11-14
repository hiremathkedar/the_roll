"""Request handlers grouped by product area."""

from .accounts import add_funds, client_profile, client_signup, list_yourself
from .bookings import (
    book_availability_slot,
    booking_messages,
    cancel_booking,
    complete_booking,
    confirm_slot,
    decline_booking,
    lawyer_dashboard,
    manage_availability,
    my_bookings,
    submit_complaint,
    submit_review,
)
from .directory import browse, lawyer_detail, public_profile
from .experiences import (
    create_experience,
    delete_experience,
    experience_detail,
    experiences_list,
    toggle_like,
)
