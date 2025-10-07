from django.db import models
# Create your models here.

class KnowledgeBase(models.Model):
    """
    Model to store questions and their vector embeddings.
    """
    brief = models.CharField(max_length=264, null =True)
    question = models.TextField(verbose_name='Question')
    embedding = models.JSONField(verbose_name='Embedding', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.brief
