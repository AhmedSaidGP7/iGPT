import numpy as np
import json
import requests
import io
import base64
import tempfile
import os
from openai import OpenAI
from pydub import AudioSegment
from django.conf import settings
from knowledge.models import KnowledgeBase

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
    """
    user_embedding_np = np.array(user_embedding)
    similarities = []
    for item in knowledge_base:
        try:
            db_embedding_np = np.array(json.loads(item.embedding))
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
    """
    
    # Construct the prompt with context from knowledge base
    context_text = "\n".join([item[1].question for item in context_questions])
    
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
        
    # Add the current user question
    messages.append({"role": "user", "content": user_question})
    
    try:
        response = openai_client.chat.completions.create(
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

def transcribe_audio_from_url(audio_url):
    """
    Downloads and transcribes an audio file from a given URL.
    """
    try:
        response = requests.get(audio_url)
        response.raise_for_status()
        audio_bytes = response.content
        
        # Use an in-memory file to handle the audio data
        audio_file_io = io.BytesIO(audio_bytes)
        audio_file_io.name = "audio.ogg"
            
        # Transcribe the audio file directly from memory
        transcription = openai_client.audio.transcriptions.create(
            model="whisper-1", 
            file=audio_file_io,
            language="ar"
        )
        return transcription.text
            
    except requests.exceptions.RequestException as e:
        print(f"Error downloading audio from URL: {e}")
        return None
    except Exception as e:
        print(f"Error transcribing audio from URL: {e}")
        return None


def transcribe_audio_from_base64(base64_audio, mimetype="audio/ogg"):
    """
    Decodes a base64 audio string and transcribes it using OpenAI's Whisper API.
    """
    try:
        # Decode the base64 string
        audio_data = base64.b64decode(base64_audio)
        
        # Determine file extension from mimetype
        ext = mimetype.split("/")[-1].split(";")[0]

        # Use pydub to load the audio from memory
        audio_segment = AudioSegment.from_file(io.BytesIO(audio_data), format=ext)
        
        # Create a temporary file to convert to a format that Whisper prefers (like mp3 or wav)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_audio:
            audio_segment.export(temp_audio.name, format="mp3")
            temp_audio_path = temp_audio.name
            
        # Transcribe the converted audio file
        with open(temp_audio_path, "rb") as audio_file:
            transcription = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ar"
            )
        
        # Clean up the temporary file
        os.remove(temp_audio_path)

        return transcription.text

    except Exception as e:
        print(f"❌ Error transcribing audio from base64: {e}")
        return "عذراً، حدث خطأ أثناء معالجة الرسالة الصوتية. هل يمكنك كتابة سؤالك بدلاً من ذلك؟"
