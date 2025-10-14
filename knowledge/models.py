from django.db import models
from core.models import OpenAISettings 

# Create your models here.

class KnowledgeBase(models.Model):
    """
    Model to store questions and their vector embeddings.
    """
    agent = models.ForeignKey(
        OpenAISettings,
        on_delete=models.CASCADE,
        related_name="knowledge_chunks",
        null = True,
    )
    brief = models.CharField(max_length=264, null =True)
    question = models.TextField(verbose_name='Question')
    embedding = models.JSONField(verbose_name='Embedding', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.brief
