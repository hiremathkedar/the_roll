from django.urls import path
from . import views

urlpatterns = [
    path('', views.browse, name='browse'),
    path('lawyer/<int:lawyer_id>/', views.lawyer_detail, name='lawyer_detail'),
    path('availability/<int:slot_id>/book/', views.book_availability_slot, name='book_availability_slot'),
    path('availability/manage/', views.manage_availability, name='manage_availability'),
    path('u/<str:username>/', views.public_profile, name='public_profile'),

    path('signup/client/', views.client_signup, name='client_signup'),
    path('list-yourself/', views.list_yourself, name='list_yourself'),
    path('profile/', views.client_profile, name='client_profile'),
    path('profile/add-funds/', views.add_funds, name='add_funds'),

    path('dashboard/', views.lawyer_dashboard, name='lawyer_dashboard'),
    path('my-bookings/', views.my_bookings, name='my_bookings'),
    path('slot/<int:slot_id>/confirm/', views.confirm_slot, name='confirm_slot'),
    path('booking/<int:booking_id>/complete/', views.complete_booking, name='complete_booking'),
    path('booking/<int:booking_id>/cancel/', views.cancel_booking, name='cancel_booking'),
    path('booking/<int:booking_id>/decline/', views.decline_booking, name='decline_booking'),
    path('booking/<int:booking_id>/messages/', views.booking_messages, name='booking_messages'),
    path('booking/<int:booking_id>/review/', views.submit_review, name='submit_review'),
    path('booking/<int:booking_id>/complaint/', views.submit_complaint, name='submit_complaint'),

    path('experiences/', views.experiences_list, name='experiences_list'),
    path('experiences/new/', views.create_experience, name='create_experience'),
    path('experiences/<int:experience_id>/', views.experience_detail, name='experience_detail'),
    path('experiences/<int:experience_id>/delete/', views.delete_experience, name='delete_experience'),
    path('experiences/<int:experience_id>/like/', views.toggle_like, name='toggle_like'),
]
