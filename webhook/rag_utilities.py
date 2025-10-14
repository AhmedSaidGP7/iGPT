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
from core.models import OpenAISettings 
import logging

logger = logging.getLogger(__name__)


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

def find_most_similar_question(user_embedding, knowledge_base, top_n=5):
    """
    Finds the most similar questions in the knowledge base to the user's question.
    """
    user_embedding_np = np.array(user_embedding)
    similarities = []
    for item in knowledge_base:
        try:
            # Handle potential JSON strings from database
            if isinstance(item.embedding, str):
                db_embedding_np = np.array(json.loads(item.embedding))
            else:
                db_embedding_np = np.array(item.embedding)
                
            similarity = np.dot(user_embedding_np, db_embedding_np) / (np.linalg.norm(user_embedding_np) * np.linalg.norm(db_embedding_np))
            similarities.append((similarity, item))
        except (json.JSONDecodeError, TypeError) as e:
            print(f"Error processing embedding for chunk {item.id}: {e}")
            continue
    
    similarities.sort(key=lambda x: x[0], reverse=True)
    return similarities[:top_n]


def generate_answer(user_question, context_questions, history, agent_settings: OpenAISettings):
    """
    Generates an answer using the provided context and conversation history.
    """
    context_text = "\n".join(context_questions)

    # OpenAI API settings
    system_prompt = agent_settings.system_context
    model_name = agent_settings.model_name
    temperature = agent_settings.temperature
    top_p = agent_settings.top_p
    frequency_penalty = agent_settings.frequency_penalty
    presence_penalty = agent_settings.presence_penalty

    full_system_content = f"{system_prompt}\n\n[Knowledge Base Context Start]\n{context_text}\n[Knowledge Base Context End]"

    # Combine all messages for the API call
    messages = [{"role": "system", "content": full_system_content}]
    
    # Add conversation history
    if history:
        messages.extend(history)
        
    # Add the current user question
    messages.append({"role": "user", "content": user_question})

 
    try:
        response = openai_client.chat.completions.create(
            model="gpt-5-chat-latest",  # You can change this to a different model if needed
            messages=messages,
            temperature=0.7,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty
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




def analyze_image_from_base64(base64_image: str, user_question: str) -> str:
    """
    Analyzes an image provided as a base64 string using GPT-4 Vision API.
    """
    if not openai_client:
        return "Sorry, the AI service is not properly configured."
    
    if not base64_image:
        logger.warning("No Base64 image data provided for analysis.")
        return "لم يتم العثور على بيانات صورة لتحليلها."
    
    # تنظيف أي header من base64
    if base64_image.startswith('data:'):
        base64_image = base64_image.split(',', 1)[-1]
        logger.info("Removed Data URI header from base64 string.")
    
    mime_type = "image/jpeg"
    image_source = {"url": f"data:{mime_type};base64,{base64_image}"}
    
    logger.info(f"Using Base64 string of length {len(base64_image)} for Vision API analysis.")
    
    # تجهيز الرسالة
    content_parts = [
        {
            "type": "text",
            "text": user_question.strip() if user_question else "من فضلك راجع الصورة وأجب كما لو رأيتها مباشرة."
        },
        {
            "type": "image_url",
            "image_url": image_source
        }
    ]
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4.1",  # ← لازم موديل Vision
            messages=[
                {
                    "role": "user",
                    "content": content_parts
                }
            ],
            max_completion_tokens=500,
        )
        
        analysis_text = response.choices[0].message.content
        img_returned = f"[ تنبيه: الرد التالي هو نتيجة تحليل لصورة تم إرسالها وإرجاع النص التحليلي, تعامل معه كأنك رأيت الصورة نفسها وليس تحليل لها, كأنك شوفتها بعينك.]\n{analysis_text}"
        logger.info(f"Vision API analysis successful. Response length: {len(analysis_text)}.")
        return img_returned

    except Exception as e:
        logger.error(f"❌ Error analyzing image with Vision API: {e}", exc_info=True)
        return "عذراً، حدث خطأ أثناء تحليل الصورة. هل يمكنك وصفها لي أو إرسالها مرة أخرى؟"
