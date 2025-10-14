from django.db import models

# Create your models here.

class OpenAISettings(models.Model):
    MODEL_CHOICES = [
        ('gpt-5', 'GPT-5'),
        ('gpt-5-mini', 'GPT-5 Mini'),
        ('gpt-4o', 'GPT-4o'),
        ('gpt-4o-mini', 'GPT-4o Mini'),
        ('gpt-4.1', 'GPT-4.1'),
        ('gpt-4.1-mini', 'GPT-4.1 Mini'),
    ]
    model_name = models.CharField(
        max_length=50,
        choices=MODEL_CHOICES,
        default='gpt-4o',
        verbose_name='Model'
    )
    agent_name = models.CharField(
        max_length=100,
        default='agentname',
        help_text='The display name of the assistant/agent'
    )

    system_context = models.TextField(
        default='You are a helpful assistant.',
        help_text='System message for the agent. Can be a long instruction or persona.'
    )
    temperature = models.FloatField(default=0.7)
    top_p = models.FloatField(default=1.0)
    frequency_penalty = models.FloatField(default=0.0)
    presence_penalty = models.FloatField(default=0.0)
    updated_at = models.DateTimeField(auto_now=True)


    # optional metadata
    def __str__(self):
        return f"{self.agent_name} ({self.model_name})"

    class Meta:
        verbose_name = "OpenAI Setting"
        verbose_name_plural = "OpenAI Settings"
