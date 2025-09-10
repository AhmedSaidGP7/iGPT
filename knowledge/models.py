from django.db import models
# Create your models here.

class KnowledgeBase(models.Model):
    """
    Model to store questions and their vector embeddings.
    """
    question = models.TextField(verbose_name='Question')
    embedding = models.JSONField(verbose_name='Embedding')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.question
