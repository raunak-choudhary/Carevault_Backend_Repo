# services/chat_service.py
from supabase_client import get_supabase
from datetime import datetime
import json
import uuid
import requests
from config import RAGFLOW_API_URL, RAGFLOW_API_KEY, RAGFLOW_CHAT_ID

# Use the table name from your schema
MESSAGES_TABLE = "chat_messages"
# CONVERSATIONS_TABLE = "conversations" # Add if you implement conversation management

supabase = get_supabase()


def process_chat_message(user_id: str, data: dict):
    """
    Stores user message, calls RAGFlow Chat API for AI response, stores AI response.
    Returns: Tuple (ai_message_data | None, status_code_tuple)
    """
    message_content = data.get("message")
    document_ids = data.get("document_ids")
    # conversation_id = data.get('conversation_id') # RAGFlow uses session_id

    if not message_content:
        return None, ({"error": "Missing 'message' field in request body"}, 400)

    # --- Store User Message ---
    user_message_data = {
        "user_id": user_id,
        "message": message_content,
        "is_user": True,
        "document_ids": document_ids,  # "conversation_id": conversation_id,
    }
    try:
        user_msg_response = (
            supabase.table(MESSAGES_TABLE).insert(user_message_data).execute()
        )
        if not user_msg_response.data:
            return None, ({"error": "Failed to store user message"}, 500)
    except Exception as e:
        print(f"DB Error storing user message: {str(e)}")
        return None, ({"error": f"Failed to store user message: {str(e)}"}, 500)

    # --- Call RAGFlow Chat Completions API ---
    ai_response_content = "Error generating response."
    ragflow_session_id = None  # Will be needed if using sessions

    # Check if essential RAGFlow config is present
    if not RAGFLOW_API_URL or not RAGFLOW_CHAT_ID:
        print("Error: RAGFlow URL or Chat ID is not configured.")
        return None, ({"error": "Chat service is not configured"}, 500)

    # Construct the specific API endpoint URL
    ragflow_endpoint = (
        f"{RAGFLOW_API_URL}/api/v1/chats_openai/{RAGFLOW_CHAT_ID}/chat/completions"
    )

    # Prepare headers with API Key (if configured)
    headers = {"Content-Type": "application/json"}
    if RAGFLOW_API_KEY:
        headers["Authorization"] = f"Bearer {RAGFLOW_API_KEY}"

    # Prepare payload according to RAGFlow API PDF [cite: 167]
    # Setting stream: False for non-streaming response [cite: 169]
    # Note: The PDF is ambiguous on passing user_id for filtering here if not using sessions.
    # We assume filtering is tied to the chat_id configuration or knowledge base setup for now.
    # If filtering fails, session management (POST /sessions, then use session_id here) might be needed.

    ragflow_payload = {
        "model": "model",  # Dummy model name as per RAGFlow docs
        "messages": [
            {"role": "user", "content": message_content}
            # Add previous messages here if you implement history
        ],
        "stream": False,  # Keep non-streaming for simpler handling
        # Add other OpenAI parameters if needed (temperature, etc.)
    }

    try:
        timeout_seconds = 60
        print(
            f"Calling RAGFlow Chat API: {ragflow_endpoint} for user {user_id}"
        )  # Debug log
        response = requests.post(
            ragflow_endpoint,
            headers=headers,
            json=ragflow_payload,
            timeout=timeout_seconds,
        )
        response.raise_for_status()

        ragflow_response_data = response.json()
        print(f"RAGFlow Response Data: {ragflow_response_data}")  # Debug log

        if (
            ragflow_response_data.get("choices")
            and isinstance(ragflow_response_data["choices"], list)
            and len(ragflow_response_data["choices"]) > 0
        ):
            first_choice = ragflow_response_data["choices"][0]
            if first_choice.get("message") and isinstance(
                first_choice["message"], dict
            ):
                ai_response_content = first_choice["message"].get(
                    "content", "No content found in response."
                )
            else:
                ai_response_content = "Invalid message structure in response."
        else:
            # Handle cases where RAGFlow might return an error structure different from OpenAI
            if (
                "message" in ragflow_response_data
            ):  # Check for RAGFlow's own error format [cite: 12, 20]
                error_msg = ragflow_response_data.get(
                    "message", "RAGFlow returned an unspecified error"
                )
                print(
                    f"RAGFlow API returned error code {ragflow_response_data.get('code')}: {error_msg}"
                )
                return None, ({"error": f"AI assistant failed: {error_msg}"}, 502)
            else:
                ai_response_content = "Invalid/empty choices array in response."

    except requests.exceptions.Timeout:
        print(f"RAGFlow API call timed out for user {user_id}")
        return None, ({"error": "AI assistant timed out, please try again."}, 504)
    except requests.exceptions.RequestException as req_e:
        print(f"RAGFlow API request failed for user {user_id}: {str(req_e)}")
        error_detail = f"Failed to get AI response: {str(req_e)}"
        try:
            error_detail = (
                req_e.response.json().get("message", error_detail)
                if req_e.response
                else error_detail
            )
        except:
            pass
        return None, ({"error": error_detail}, 502)
    except Exception as e:
        print(f"Error processing RAGFlow response for user {user_id}: {str(e)}")
        return None, ({"error": f"Error processing AI response: {str(e)}"}, 500)
    # --- End RAGFlow Call ---

    # --- Store AI Message ---
    ai_message_data = {
        "user_id": user_id,
        "message": ai_response_content,
        "is_user": False,
        # "document_ids": retrieved_doc_ids, # Extract from reference if needed
        # "conversation_id": ragflow_session_id, # Map session_id if needed
    }
    try:
        ai_msg_response = (
            supabase.table(MESSAGES_TABLE).insert(ai_message_data).execute()
        )
        if not ai_msg_response.data:
            print(f"Warning: Failed to store AI message for user {user_id}")
            stored_ai_message = ai_message_data
            stored_ai_message["id"] = str(uuid.uuid4())
            stored_ai_message["created_at"] = datetime.now().isoformat() + "+00:00"
            return stored_ai_message, (
                {"warning": "AI response generated but not stored"},
                200,
            )

        stored_ai_message = ai_msg_response.data[0]
        return stored_ai_message, (None, 200)  # Success

    except Exception as e:
        print(f"DB Error storing AI message: {str(e)}")
        return None, ({"error": f"Failed to store AI response: {str(e)}"}, 500)
