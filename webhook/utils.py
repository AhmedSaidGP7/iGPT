from core.models import OpenAISettings
from django.core.exceptions import ObjectDoesNotExist

def get_agent_settings_by_id(agent_id: int):
    """Retrieves a specific agent's settings by its ID, raising an error if not found."""
    try:
        return OpenAISettings.objects.get(id=agent_id) 
    except ObjectDoesNotExist:
        logger.error(f"Agent ID {agent_id} not found in OpenAISettings.")
        raise ObjectDoesNotExist(f"No Agent with ID {agent_id} found.")