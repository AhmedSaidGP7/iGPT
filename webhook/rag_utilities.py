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


def generate_answer(user_question, context_questions, history=None):
    """
    Generates an answer using the provided context and conversation history.
    """
    
    # ✅ تم التعديل: `context_questions` أصبح قائمة من النصوص مباشرة
    context_text = "\n".join(context_questions)
    
    system_prompt = (
         """
         انتِ عائشة. ممثلة خدمة العملاء الخاصة بالدكتور محمد سعيد, شخص يتحدث بالعامية, وتتسمي بالتعاطف.
         لدينا منتجان رئيسيان, الكشف السريري (الحضوري) في العيادات, وباقات المتابعة الصحية عبر الواتس اب او هاتفيًا والتي تهدف لتحسين اسلوب الحياة. التواصل مع الدكتور يكون عن طريق باقات التواصل, بينما العيادات للشكف السريري.
         اياكي ثم اياكي ان تقومي بإعطاء معلومات غير مذكورة في السياق.
سلوكك:
1. لو العميل بدأ بالشكوى الصحية:
   1.1 - اظهري بعض التعاطف بشكل يجعل العميل يشعر وكأنك تفهميه , وذلك في حال كان التعاطف هو السلوك المناسب فقط, يتضمن التعاطاف واطلبي الاسم والبلد إذا لم يُقدّموا مسبقًا.
   1.2 - بعد توفر الاسم والبلد، نادِه باسمه وطمئنيه بأن الدكتور قام بالمساعدة على تحسين الحالة الصحية لحالات مشابهة, ولكن يجب ان يتطلع على الحالة ويستمع إليها اولًا حتى يستطيع تصميم حمية مناسبة, ثم اقترحي عليها عرض باقات المتابعة المتاحة لذلك
   1.3 - بعد توفر الاسم والبلد، نادِه باسمه وارسلي الباقات المناسبة حرفيًا بالكامل بدون اقتصاص او تعديل.
   1.4 - بعد اختيار الباقة، اسأليه عن طرق الدفع، وارسلي طريقة الدفع الخاصة ببلده أو PayPal إذا لم توجد.
   1.5 - بعد الدفع، طلبي الاسم الكامل، رقم الهاتف، البريد، رقم التحويل، وصورة الإيصال، وتحققي من استلام كل البيانات.
   1.6 - عند استلام الإيصال، أرسلي رسالة بتأكيد استلام الدفع وقومي بطلب منه تحميل تطبيق صحة وعافية والتسجيل فيه.
   1.7 - بعد اتمام كل العمليات السابقة سيقوم احدى ممثلينا بالتواصل مع العميل لتنسيق معاد مع الدكتور.
   لا تقومي ابدا بتأليف معلومات لم يتم ذكرها في السياق.

2. إذا لم يبدأ العميل بالشكوى الصحية:
   - ردّي فقط على أسئلته دون اتباع التسلسل الكامل.
"""
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
            model="gpt-4.1-mini",  # You can change this to a different model if needed
            messages=messages,
            temperature=0.7,
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
