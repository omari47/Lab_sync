from django.utils import timezone

def current_time_context(request):
    """
    Context processor to make the current time available to all templates
    """
    return {
        'current_time': timezone.now(),
        'current_date': timezone.now().date(),
    }