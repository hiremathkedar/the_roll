from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Value
from django.db.models.functions import Concat
from django.shortcuts import get_object_or_404, redirect, render

from ..forms import ExperienceCommentForm, ExperienceForm
from ..models import Experience, ExperienceLike


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
