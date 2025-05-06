# services/chat_service.py
from supabase_client import get_supabase
from datetime import datetime
import json
import io
import uuid
import requests
import base64
from config import RAGFLOW_API_URL, RAGFLOW_API_KEY, RAGFLOW_CHAT_ID, OPENAI_API_KEY
from openai import OpenAI
from werkzeug.datastructures import FileStorage  # Type hint for file object
from werkzeug.utils import secure_filename
from services.document_service import upload_document_to_storage
import fitz
import mimetypes
import os

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

    attachments = []
    if document_ids and isinstance(document_ids, list) and len(document_ids) > 0:

        ai_response_content = (
            "The file will be processed and uploaded to your documents library."
        )

    else:

        # Create the final payload
        ragflow_payload = {
            "model": "model",  # Dummy model name as per RAGFlow docs
            "messages": [
                {
                    "role": "user",
                    "content": message_content,
                }
                # Add previous messages here if you implement history
            ],
            "stream": False,  # Keep non-streaming for simpler handling
            # Add other OpenAI parameters if needed (temperature, etc.)
        }

        print(f"RAGFlow Payload: {ragflow_payload}")  # Debug log

        # return

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


# --- Function: Get Chat History ---
def get_chat_history(user_id: str):
    """
    Fetches a paginated list of chat messages for a user.
    Orders by creation time ascending (oldest first).
    Returns: Tuple (list_of_messages | None, total_count | 0)
    """
    try:
        query = (
            supabase.table(MESSAGES_TABLE)
            .select("*", count="exact")
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            # .range(skip, skip + limit - 1)
        )

        response = query.execute()

        messages = response.data

        for message in messages:
            message["content"] = message["message"]
            message["sender"] = "user" if message["is_user"] else "ai"

        total = (
            response.count
            if hasattr(response, "count") and response.count is not None
            else len(messages)
        )

        return messages, total

    except Exception as e:
        print(f"DB Error listing chat messages for user {user_id}: {str(e)}")
        return None, 0  # Return None and 0 count on error


def format_openai_vision_content(file_content, mime_type):
    base64_encoded_content = base64.b64encode(file_content).decode("utf-8")
    if mime_type.startswith("image/"):
        return f"data:{mime_type};base64,{base64_encoded_content}"
    elif mime_type == "application/pdf":
        print("Warning: Sending raw PDF to vision model.")
        return process_pdf_for_analysis(file_content)
    else:
        raise ValueError(f"Unsupported file type for vision analysis: {mime_type}")


# The detailed extraction prompt
EXTRACTION_PROMPT = """
    Analyze the provided document content. Perform the following tasks:
    1. Classify Document Type: Determine the most likely type from this list: [prescription, lab_report, doctor_note, insurance, vaccination, imaging, other]. Use 'other' if unsure.
    2. Extract Key Information:
        * document_date: Primary date found (YYYY-MM-DD format) or null.
        * title: Concise title (max 50 chars) or null.
        * provider_name: Primary doctor/facility name or null.
        * notes: Brief 1-2 sentence summary or null.
        * tags: List of 3-5 relevant keywords (strings) or empty list [].
    3. Format Output: Return ONLY a single, valid JSON object with keys: "document_type", "document_date", "title", "provider_name", "notes", "tags". Use null for missing values. Ensure "tags" is a list.

    Example JSON Output:
    {
    "document_type": "lab_report",
    "document_date": "2025-05-01",
    "title": "Complete Blood Count (CBC)",
    "provider_name": "Dr. Evelyn Reed",
    "notes": "Results within normal limits.",
    "tags": ["cbc", "blood test", "normal"]
    }

    Strict Instructions:
    - Adhere strictly to the allowed document types.
    - Ensure the date format is "YYYY-MM-DD" or null.
    - Provide null for keys where information is not found.
    - Ensure the "tags" value is a JSON list of strings (or empty list).
    - Output ONLY the JSON object and nothing else.

    Document Content follows this instruction.
    """


def process_pdf_for_analysis(pdf_content):
    """
    Convert first page of PDF to high-resolution image for more reliable vision model analysis.

    Args:
        pdf_content: Bytes content of the PDF file

    Returns:
        Data URL string with base64-encoded image content
    """
    try:

        # Open PDF from bytes
        pdf_document = fitz.open(stream=pdf_content, filetype="pdf")

        # Get first page (or loop through pages if needed)
        first_page = pdf_document[0]

        # Render to image with higher resolution
        # Use a higher zoom factor (2.0) for better quality
        pix = first_page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))

        # Convert to PNG bytes
        img_data = pix.tobytes("png")

        # Create data URL for the image
        base64_img = base64.b64encode(img_data).decode("utf-8")
        return f"data:image/png;base64,{base64_img}"

    except ImportError as e:
        print(f"PDF conversion requires PyMuPDF: {e}")
        # Fallback to original method
        base64_pdf = base64.b64encode(pdf_content).decode("utf-8")
        return f"data:application/pdf;base64,{base64_pdf}"
    except Exception as e:
        print(f"PDF conversion error: {e}")
        # Fallback to original method
        base64_pdf = base64.b64encode(pdf_content).decode("utf-8")
        return f"data:application/pdf;base64,{base64_pdf}"


def process_uploaded_document(user_id: str, user_token: str, file: FileStorage):
    """
    Analyzes uploaded file with OpenAI, calls internal /documents API to save.
    Returns: Tuple (result_data | error_dict, status_code)
    """
    if not OPENAI_API_KEY:
        return {"error": "AI service not configured"}, 500

    extracted_metadata = None
    file_content = None

    # --- Step 1: Analyze Document with OpenAI ---
    try:
        file_content = file.read()
        file.seek(0)  # Reset stream position for potential reuse
        content_type = file.content_type or "application/octet-stream"
        original_filename = (
            secure_filename(file.filename) if file.filename else "uploaded_file"
        )

        openai_image_data_url = format_openai_vision_content(file_content, content_type)
        client = OpenAI(api_key=OPENAI_API_KEY)

        print("--- Calling OpenAI API for document analysis ---")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": EXTRACTION_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": openai_image_data_url},
                        },
                    ],
                }
            ],
            max_tokens=400,
            response_format={"type": "json_object"},
        )

        print(f"--- OpenAI API Response: {response} ---")

        extracted_metadata_json = response.choices[0].message.content
        print(f"--- OpenAI Raw Response: {extracted_metadata_json} ---")
        extracted_metadata = json.loads(extracted_metadata_json)

        if not extracted_metadata or not isinstance(extracted_metadata, dict):
            raise ValueError("AI failed to return valid JSON metadata.")
        if not extracted_metadata.get("document_type") or not extracted_metadata.get(
            "title"
        ):
            # Use filename as fallback title if AI fails to generate one
            extracted_metadata["title"] = (
                extracted_metadata.get("title") or original_filename
            )
            if not extracted_metadata.get("document_type"):
                extracted_metadata["document_type"] = "other"  # Default type
            print(
                f"Warning: AI failed to return required fields. Using fallbacks: {extracted_metadata}"
            )
            # Decide if you want to proceed with defaults or return error
            # For now, let's proceed with defaults/fallbacks

    except ValueError as ve:
        print(f"Value Error during AI analysis step: {ve}")
        return {"error": str(ve)}, 400  # Bad request if file type unsupported etc.
    except Exception as e:
        print(f"Error during OpenAI document analysis: {e}")
        return {
            "error": f"AI analysis failed: {e}"
        }, 500  # Internal Server Error (AI Service)

    # --- Step 2: Use direct function call instead of API request ---
    try:
        # Prepare provider_id if available from metadata
        provider_name = extracted_metadata.get("provider_name")
        provider_id = None  # You could look up provider_id by name if needed

        # Extract tags from metadata for direct passing
        tags = extracted_metadata.get("tags", [])

        # Format notes without the provider part since we're passing provider_id separately
        notes = f"Summary: {extracted_metadata.get('notes', '') or ''}. Tags: {', '.join(tags) or 'None'}".strip()

        # Call the service function directly
        file.seek(0)  # Reset file pointer position
        result, status_code = upload_document_to_storage(
            file=file,
            user_id=user_id,
            title=extracted_metadata.get("title"),
            document_type=extracted_metadata.get("document_type", "other"),
            description=None,  # You could set this if needed
            document_date_str=extracted_metadata.get("document_date"),
            notes=notes,
            tags=tags,
            provider_id=provider_id,
        )

        if status_code != 200:
            # Handle error from document upload
            raise Exception(
                f"Document upload failed: {result.get('error', 'Unknown reason')}"
            )

        # Check for document ID
        document_id = result.get("document_id")
        print(f"--- Document upload successful: ID {document_id} ---")

        # Return the successful data from the service function call
        return result, status_code

    except requests.exceptions.RequestException as req_e:
        print(f"Error calling internal document upload API: {req_e}")
        # Try to extract error from response if possible
        error_msg = f"Failed to save document: {req_e}"
        try:
            error_msg = (
                req_e.response.json().get("message", error_msg)
                if req_e.response
                else error_msg
            )
        except:
            pass
        return {
            "error": error_msg
        }, 502  # Bad Gateway (failed to talk to internal service)
    except Exception as e:
        print(f"Error in internal API call or indexing step: {e}")
        return {"error": f"Failed processing after analysis: {e}"}, 500
