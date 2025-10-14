# core/context_processors.py

from core.models import OpenAISettings

def global_agents(request):
    """Adds all available agents to the template context globally."""
    return {
        'all_agents': OpenAISettings.objects.all().order_by('agent_name'),
    }

# ولا تنسى إضافته إلى settings.py
# TEMPLATES = [
#     {
#         'OPTIONS': {
#             'context_processors': [
#                 # ...
#                 'core.context_processors.global_agents', # 💥 إضافة هذا
#             ],
#         },
#     },
# ]