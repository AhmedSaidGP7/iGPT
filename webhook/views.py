import json
import logging
import requests
import threading
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from .models import Client, Message, Response
from core.models import OpenAISettings
from .rag_utilities import (
    get_embeddings,
    find_most_similar_question,
    generate_answer,
    transcribe_audio_from_base64,
    analyze_image_from_base64,
)
from .utils import get_agent_settings_by_id
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
# Removed duplicated imports

logger = logging.getLogger(__name__)

# Debounce settings
DEBOUNCE_TIME = 5 
_user_buffers = {} 


def send_message_to_client(jid: str, text: str, instance_id: str, evolution_key: str, server_url: str):
    """Sends the final text reply to the Evolution API."""
    try:
        url = f"{server_url}/message/sendText/{instance_id}"
        headers = {
            "apikey": evolution_key,
            "Content-Type": "application/json"
        }
        payload = {
            "number": jid.split('@')[0],
            "text": text,
            "delay": 7000,
            "linkPreview": True,
        }
        
        # Added timeout for safety
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        
        logger.info(f"✅ API SUCCESS: Message sent to {jid}. Status: {response.status_code}.")
        return response.json()
        
    except requests.exceptions.RequestException as e:
        # Added detailed error logging for API failure
        error_details = f"URL: {url}, Error: {e}"
        if hasattr(e, 'response') and e.response is not None:
             error_details += f", API Response: {e.response.text}"
        
        logger.error(f"❌ API FAILURE: Error sending message to {jid}: {error_details}", exc_info=True)
        return None


def _process_buffered_message_logic(jid: str, instance_id: str, evolution_key: str, server_url: str, user_data: dict, agent_settings: OpenAISettings, buffer_key: str):
    """
    Core logic to process the buffered message.
    Takes all data explicitly, and the full buffer_key for cleanup.
    """
    
    # 1. Check and extract data from the buffer
    if buffer_key not in _user_buffers:
        logger.warning(f"⚠️ BUFFER MISS: Key {buffer_key} not found. Cleared by faster thread.")
        return

    # Extract data for processing
    user_message_content = user_data['content']
    message_type = user_data['message_type']
    image_url = user_data['image_url']
    
    # 💥 CRITICAL: Clear the buffer IMMEDIATELY after reading the data.
    del _user_buffers[buffer_key] 
    
    # Added logging before AI process
    logger.info(f"➡️ AI START: Processing content for {jid}: '{user_message_content[:50]}...'")


    try:
        with transaction.atomic():
            # 2. Create Message Record
            client, _ = Client.objects.get_or_create(jid=jid)
            user_message = Message.objects.create(
                client=client,
                message_type=message_type,
                content=user_message_content,
                image_url=image_url,
            )

            # 3. Build Conversation History
            conversation_history = []
            messages = Message.objects.filter(client=client).select_related('client', 'response').order_by('-timestamp')[:10]
            
            for msg in reversed(messages):
                if msg.content:
                    conversation_history.append({"role": "user", "content": msg.content})
                    try:
                        ai_response = msg.response
                        conversation_history.append({"role": "assistant", "content": ai_response.content})
                    except Response.DoesNotExist: 
                        # Log a warning instead of passing silently
                        logger.warning(f"Message ID {msg.id} has no corresponding response in history.")
                        pass

            # 4. Retrieve Context (RAG/Embeddings)
            logger.info("➡️ RAG START: Retrieving context chunks.")
            knowledge_base_chunks = list(agent_settings.knowledge_chunks.all())
            
            # CRITICAL: Ensure content is not empty before embedding (though already checked in webhook)
            if not user_message_content:
                reply_text = "I apologize, but I could not process your message content."
            else:
                user_embedding = get_embeddings(user_message.content)
                similar_questions_info = find_most_similar_question(user_embedding, knowledge_base_chunks)
                context_questions = [item[1].question for item in similar_questions_info]
                
                # 5. Generate Answer
                reply_text = generate_answer(
                    user_message.content,
                    context_questions,
                    conversation_history,
                    agent_settings
                )

            # 6. Save Response
            Response.objects.create(message=user_message, content=reply_text)
            logger.info(f"✅ AI FINISHED: Reply text generated (Length: {len(reply_text)}).")

        # 7. Send Reply (outside the transaction)
        send_message_to_client(jid, reply_text, instance_id, evolution_key, server_url)
        
        logger.info(f"✅ PROCESS COMPLETE: Successfully processed and replied to {jid}.")
        
    except Exception as e:
        # 🔴 CORE LOGIC FAIL: This is the critical log to check for RAG/OpenAI errors
        logger.error(f"🔴 CORE LOGIC FAIL: An error occurred while processing logic for {jid} (Message Type: {message_type}): {e}", exc_info=True)


def _process_buffered_message_threaded(buffer_key: str, agent_id: int):
    """
    The thread-safe intermediary function. Extracts data from the buffer 
    using the unique buffer_key and then calls the core logic.
    """
    logger.info(f"➡️ THREAD ENTRY: Starting processing for buffer key: {buffer_key}")
    try:
        # CRITICAL: Check the buffer before trying to load agent settings
        if buffer_key not in _user_buffers:
             logger.warning(f"⚠️ BUFFER MISS: Key {buffer_key} not found for processing.")
             return
             
        # Extract necessary connection data from the buffer
        user_data = _user_buffers[buffer_key]
        
        # Extract JID from the buffer key: JID:INSTANCE_ID:MESSAGE_ID
        jid = buffer_key.split(':')[0] 
        instance_id = user_data['instance_id']
        evolution_key = user_data['evolution_key']
        server_url = user_data['server_url']
        
        # Look up the Agent inside the Thread
        agent_settings = get_agent_settings_by_id(agent_id)
        
        # Call core logic
        _process_buffered_message_logic(jid, instance_id, evolution_key, server_url, user_data, agent_settings, buffer_key)
        
    except ObjectDoesNotExist:
        logger.critical(f"❌ AGENT FAIL: Agent ID {agent_id} could not be loaded for processing.")
    except Exception as e:
        logger.error(f"🔴 THREAD FAIL: Threaded processing failed for Agent {agent_id}: {e}", exc_info=True)

@csrf_exempt
def webhook(request, agent_id: int):
    """
    The main entry point for all Webhook messages.
    """
    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        request_body = json.loads(request.body.decode('utf-8'))
        
        # ... (Extract connection data) ...
        instance_id = request_body.get('instance')
        evolution_key = request_body.get('apikey')
        server_url = request_body.get('server_url') 
        
        if not instance_id or not evolution_key or not server_url:
            logger.error("Missing critical instance data in webhook payload.")
            return JsonResponse({'status': 'error', 'message': 'Missing instance data'}, status=400)

        # Ignore messages sent by the bot itself or non-upsert events
        if request_body.get('event') != 'messages.upsert' or request_body.get('data', {}).get('key', {}).get('fromMe', False):
            return JsonResponse({'status': 'ignored', 'message': 'Event not processed'}, status=200)

        data = request_body.get('data', {})
        jid = data.get('key', {}).get('remoteJid') or request_body.get('sender')
        push_name = data.get('pushName', 'Unknown')
        message_body = data.get('message', {})
        message_type = data.get('messageType')
        
        message_key_id = data.get('key', {}).get('id')
        
        if not jid or not message_key_id:
            logger.error("JID or Message ID not found in webhook data.")
            return JsonResponse({'status': 'error', 'message': 'JID or Message ID not found'}, status=400)

        # Update/Create Client data
        client, created = Client.objects.get_or_create(
            jid=jid,
            defaults={'name': push_name}
        )
        if not created and client.name != push_name:
            client.name = push_name
            client.save()

        user_message_content = None
        image_url = None

        # Process message types
        if message_type in ['conversation', 'extendedTextMessage']:
            user_message_content = message_body.get('conversation') or message_body.get('extendedTextMessage', {}).get('text')
        
        elif message_type == 'imageMessage':
            image_message_data = message_body.get('imageMessage', {})
            # Extract the caption (the text question)
            user_message_content = message_body.get('imageMessage', {}).get('caption')
            # Extract the Base64 data 
            base64_data = request_body.get('data', {}).get('message', {}).get('base64') 

            if base64_data:
                logger.info(f"🖼️ Received Base64 image with length: {len(base64_data)}")
                # 3. Analyze the image and replace the content with the analysis text
                user_message_content = analyze_image_from_base64(
                    base64_image=base64_data,
                    user_question=user_message_content
                )
            else:
                # Handle case where no Base64 data is found
                logger.warning("No Base64 image data found in imageMessage payload.")
                user_message_content = user_message_content or "[Image received without data for analysis]"
        
            # image_url is not used but kept for consistency if needed in the future
            image_url = image_message_data.get('url')
        
        elif message_type == 'audioMessage':
            audio_message_data = message_body.get('audioMessage', {})
            base64_data = request_body.get('data', {}).get('message', {}).get('base64')
            mimetype = audio_message_data.get('mimetype', 'audio/ogg')
            voice_note_url = audio_message_data.get('url')
            
            if base64_data:
                print("✅ Found Base64 audio, starting transcription...")
                user_message_content = transcribe_audio_from_base64(base64_data, mimetype)
            else:
                logger.warning("❌ No Base64 audio found in the payload.")
                user_message_content = "[Audio message, but no Base64 found]"
            
            # CRITICAL: If transcription fails and returns None, set a default message
            if not user_message_content:
                user_message_content = "[Transcription failed or returned empty text]"


        if not user_message_content:
            logger.warning(f"Message type '{message_type}' has no valid text content and will be ignored.")
            return JsonResponse({'status': 'unsupported', 'message': 'Cannot process messages without text content.'}, status=200)
            

        # 2. Setup the Debounce Buffer and Handle Deduplication
        buffer_key = f"{jid}:{instance_id}:{message_key_id}"

        # 2a. Duplicate Message Check (Deduplication)
        if buffer_key in _user_buffers:
            if _user_buffers[buffer_key].get('timer') and _user_buffers[buffer_key]['timer'].is_alive():
                _user_buffers[buffer_key]['timer'].cancel()
                logger.warning(f"⚠️ DEDUPLICATION: Ignoring DUPLICATE webhook POST for message ID: {message_key_id}. Timer cancelled.")
                return JsonResponse({'status': 'ignored', 'message': 'Duplicate message ID received, cancelling previous timer.'}, status=200)
            # If the key exists but the timer is NOT alive, it means the message was processed successfully (or failed fully).
            # We ignore it to prevent reprocessing, as the message ID is the key.
            logger.warning(f"⚠️ DEDUPLICATION: Message ID {message_key_id} already exists in buffer (processed/failed). Ignoring.")
            return JsonResponse({'status': 'ignored', 'message': 'Message ID already processed.'}, status=200)
            
        # 2b. Debounce/New Message Logic
        _user_buffers[buffer_key] = {
            'content': user_message_content,
            'message_type': message_type,
            'image_url': image_url,
            'instance_id': instance_id,
            'evolution_key': evolution_key,
            'server_url': server_url
        }

        # 3. Restart the Debounce Timer
        new_timer = threading.Timer(
            DEBOUNCE_TIME, 
            _process_buffered_message_threaded, 
            args=[buffer_key, agent_id] 
        )
        new_timer.start()
        _user_buffers[buffer_key]['timer'] = new_timer
        
        logger.info(f"✅ WEBHOOK: Message {message_key_id} received. Debounce timer set to {DEBOUNCE_TIME}s.")

        return JsonResponse({
            'status': 'success',
            'reply': 'Message received, debounce active.',
            'instance_id': instance_id,
            'agent_id': agent_id
        })
    
    except ObjectDoesNotExist:
        logger.error(f"Attempted to access unknown Agent ID: {agent_id}")
        return JsonResponse({'status': 'error', 'message': f'Agent ID {agent_id} not found.'}, status=404)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON received: {e}")
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"🔴 UNEXPECTED FAIL: An unexpected error occurred in webhook for Agent {agent_id}: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'Internal Server Error'}, status=500)