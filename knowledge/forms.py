from django import forms
from .models import KnowledgeBase
from webhook.rag_utilities import get_embeddings  

class KnowledgeBaseForm(forms.ModelForm):
    brief = forms.CharField(
        required=False,
        label="العنوان المختصر",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    question = forms.CharField(
        required=True,
        label="السؤال",
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4})
    )

    class Meta:
        model = KnowledgeBase
        fields = ['brief', 'question']

    def save(self, commit=True):
        kb = super().save(commit=False)

        # Generate embedding for the question
        kb.embedding = get_embeddings(kb.question)

        if commit:
            kb.save()
        return kb
