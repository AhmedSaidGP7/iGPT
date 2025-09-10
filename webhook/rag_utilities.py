import numpy as np
import json
import requests
from openai import OpenAI
from django.conf import settings
from .models import KnowledgeBaseChunk

# Initialize OpenAI client with API key from settings
openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)

def get_embeddings(text):
    """
    Generates a vector embedding for a given text using OpenAI's API.
    """
    try:
        response = openai_client.embeddings.create(
            input=text,
            model="text-embedding-3-small"
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"Error getting embeddings: {e}")
        return None

def find_most_similar_question(user_embedding, knowledge_base, top_n=3):
    """
    Finds the most similar questions in the knowledge base to the user's question.
    
    Args:
        user_embedding (list): The embedding vector of the user's question.
        knowledge_base (QuerySet): A Django QuerySet of KnowledgeBase objects.
        top_n (int): The number of most similar questions to return.
        
    Returns:
        list: A list of tuples, where each tuple contains (similarity_score, KnowledgeBase_object).
    """
    user_embedding_np = np.array(user_embedding)
    similarities = []
    for item in knowledge_base:
        try:
            # Use json.loads instead of eval for security
            db_embedding_np = np.array(json.loads(item.embedding_vector))
            similarity = np.dot(user_embedding_np, db_embedding_np) / (np.linalg.norm(user_embedding_np) * np.linalg.norm(db_embedding_np))
            similarities.append((similarity, item))
        except (json.JSONDecodeError, TypeError) as e:
            print(f"Error processing embedding for chunk {item.id}: {e}")
            continue
    
    similarities.sort(key=lambda x: x[0], reverse=True)
    return similarities[:top_n]


def generate_answer(user_question, context_questions, history=None):
    """
    Generates an answer using the provided context and conversation history.
    
    Args:
        user_question (str): The user's new question.
        context_questions (list): A list of relevant questions from the knowledge base to use as context.
        api_key (str): The OpenAI API key.
        history (list): A list of previous messages in the conversation for context.
        
    Returns:
        str: The generated answer.
    """
    client = openai_client
    
    # Construct the prompt with context from knowledge base
    context_text = "\n".join(context_questions)
    
    system_prompt = (
        "You are an AI assistant specialized in providing comprehensive answers based on the provided "
        "knowledge base and conversation history. Use the information to answer the user's question. "
        "If the information is not sufficient, state that you cannot provide a full answer based on the given context."
    )
    
    # Combine all messages for the API call
    messages = [{"role": "system", "content": system_prompt}]
    
    # Add knowledge base context
    messages.append({"role": "user", "content": f"Knowledge Base Context:\n{context_text}"})
    
    # Add conversation history
    if history:
        messages.extend(history)
        
    # Add the current user question only if it's not empty
    if user_question:
        messages.append({"role": "user", "content": user_question})
    else:
        # If the user's question is empty, provide a default response
        # to avoid the API error.
        messages.append({"role": "user", "content": "The user did not provide a text message. Please ask them to try again."})
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",  # You can change this to a different model if needed
            messages=messages,
            temperature=0.7,
            max_tokens=256,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error generating answer: {e}")
        return "Sorry, there was an error processing your request."
