import os
import io
import json
import requests
import uuid
from flask import jsonify
from werkzeug.utils import secure_filename
from datetime import datetime
import logging

from supabase_client import get_supabase
from config import RAGFLOW_API_URL, RAGFLOW_API_KEY, RAGFLOW_DATASET_ID

# Add proper logging instead of print statements
logger = logging.getLogger(__name__)

# Allowed file extensions for document uploads
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "txt", "jpg", "jpeg", "png"}

supabase = get_supabase()


def allowed_file(filename):
    """Check if a filename has an allowed extension"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def upload_document_to_storage(
    file,
    user_id,
    title,
    document_type,
    description=None,
    document_date_str=None,
    notes=None,
    tags=None,
    provider_id=None,
):
    """
    Uploads a document to Supabase storage and saves its metadata to the database

    Args:
        file: The file object from the request
        user_id: ID of the current user
        title: Document title
        document_type: Type of document
        description: Optional document description
        document_date_str: Optional document date in YYYY-MM-DD format
        notes: Optional notes about the document
        tags: Optional tags for the document
        provider_id: Optional ID of the healthcare provider

    Returns:
        Dictionary with success/error information and status code
    """
    # Process document_date if provided
    document_date = None
    if document_date_str:
        try:
            document_date = datetime.strptime(document_date_str, "%Y-%m-%d").date()
        except ValueError:
            return {"error": "Invalid document_date format. Use YYYY-MM-DD"}, 400

    # Process the file
    filename = secure_filename(file.filename)
    file_ext = os.path.splitext(filename)[1].lower()
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    storage_path = f"{user_id}/{unique_filename}"
    file_content = file.read()
    file_size = len(file_content)
    content_type = file.content_type
    file.seek(0)

    try:
        # Upload to Supabase storage
        storage_response = supabase.storage.from_("documents").upload(
            path=storage_path,
            file=file_content,
            file_options={"content-type": content_type},
        )

        print(f"Storage upload response: {storage_response}")

        public_url = (
            supabase.storage.from_("documents")
            .create_signed_url(storage_path, expires_in=60 * 60 * 24 * 7)
            .get("signedURL")
        )

        # Prepare document metadata
        document_data = {
            "user_id": user_id,
            "title": title,
            "description": description,
            "document_type": document_type,
            "document_date": (
                document_date.isoformat()
                if document_date
                else datetime.now().date().isoformat()
            ),
            "file_path": storage_path,
            "notes": notes,
            "tags": tags,
            "provider_id": provider_id,
            "file_type": file_ext,
        }

        # Save to database
        db_response = supabase.table("documents").insert(document_data).execute()

        if not db_response.data:
            # Clean up storage if database insert fails
            try:
                supabase.storage.from_("documents").remove([storage_path])
            except Exception as cleanup_error:
                print(f"Storage cleanup failed: {cleanup_error}")
            return {"error": "Failed to save document metadata"}, 500

        # --- Step 3: Trigger RAGFlow Indexing (Now Implemented) ---
        if RAGFLOW_DATASET_ID:
            indexing_success = trigger_ragflow_indexing(
                user_id=user_id,
                dataset_id=RAGFLOW_DATASET_ID,
                filename=filename,
                file_content=file_content,  # Pass the content bytes
                content_type=content_type,
            )
            if not indexing_success:
                # Log the failure but don't block the user response,
                # as the document IS saved in our primary store.
                print(
                    f"Warning: RAGFlow indexing failed for doc {filename}, user {user_id}"
                )
                # You could potentially add a flag to the returned data or store failed indexing jobs for retry
                # saved_document_details['indexing_status'] = 'failed'

        """
        
        id: Date.now().toString(),
        name: file.name,
        type: file.type,
        size: file.size,
        url: URL.createObjectURL(file),
        processed: true,
        
        """

        return {
            "error": None,
            "message": "Document uploaded successfully.",
            "success": True,
            "document": {
                "id": db_response.data[0]["id"] if db_response.data else None,
                "name": filename,
                "type": content_type,
                "size": file_size,
                "url": public_url,
                "processed": True,
            },
        }, 200

    except Exception as e:
        print(f"Document upload error: {str(e)}")
        return {
            "error": str(e),
            "message": "Failed to upload document",
            "success": False,
        }, 500


def get_document_by_id(document_id, user_id):
    """
    Fetch a document by ID and verify ownership

    Args:
        document_id: ID of the document to fetch
        user_id: ID of the current user for ownership verification

    Returns:
        Dictionary with document data or error information and status code
    """
    try:
        # Fetch document from database
        response = (
            supabase.table("documents").select("*").eq("id", document_id).execute()
        )

        if not response.data:
            return {"error": "Document not found"}, 404

        document_db = response.data[0]

        # Verify ownership
        if document_db.get("user_id") != user_id:
            return {"error": "Access denied to this document"}, 403

        # Get the download URL
        try:
            download_url = supabase.storage.from_("documents").create_signed_url(
                document_db["file_path"],
                expires_in=60 * 60 * 24 * 7,  # URL valid for 7 days
            )
            document_db["download_url"] = download_url["signedURL"]
        except Exception as url_error:
            print(
                f"Could not get signed URL for {document_db.get('file_path')}: {url_error}"
            )
            document_db["download_url"] = None

        # Map provider_id to provider name
        document_db["provider"] = None
        if document_db["provider_id"]:
            provider_response = (
                supabase.table("providers")
                .select("name")
                .eq("id", document_db["provider_id"])
                .execute()
            )
            if provider_response.data:
                document_db["provider"] = provider_response.data[0]["name"]

        # Map to frontend format
        frontend_document = map_db_to_frontend(document_db)

        return {
            "error": None,
            "message": "Document fetched successfully.",
            "success": True,
            "document": frontend_document,
        }, 200

    except Exception as e:
        print(f"Error fetching document {document_id}: {str(e)}")
        return {"error": f"Failed to fetch document: {str(e)}"}, 500


def get_all_documents_for_user(user_id):
    """
    Fetch all documents for a user

    Args:
        user_id: ID of the user

    Returns:
        Dictionary with documents data or error information and status code
    """
    try:
        # Fetch documents from database
        response = (
            supabase.table("documents")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )

        if not response.data:
            return {"error": "No documents found"}, 200

        documents = response.data

        # Process each document
        for document in documents:
            # Get download URL
            try:
                document["download_url"] = (
                    supabase.storage.from_("documents")
                    .create_signed_url(
                        document["file_path"],
                        expires_in=60 * 60 * 24 * 7,  # URL valid for 7 days
                    )
                    .get("signedURL")
                )
            except Exception as url_error:
                print(
                    f"Could not get signed URL for {document.get('file_path')}: {url_error}"
                )
                document["download_url"] = None

            # Map provider_id to provider name
            document["provider"] = None
            if document["provider_id"]:
                provider_response = (
                    supabase.table("providers")
                    .select("name")
                    .eq("id", document["provider_id"])
                    .execute()
                )
                if provider_response.data:
                    document["provider"] = provider_response.data[0]["name"]

        # Map to frontend format
        mapped_documents = [map_db_to_frontend(doc) for doc in documents]

        return {
            "error": None,
            "message": "Documents fetched successfully.",
            "success": True,
            "documents": mapped_documents,
        }, 200

    except Exception as e:
        print(f"Error fetching documents: {str(e)}")
        return {"error": f"Failed to fetch documents: {str(e)}"}, 500


def map_db_to_frontend(db_doc):
    """
    Maps a document dictionary from DB schema to frontend expected schema

    Args:
        db_doc: Document dictionary from database

    Returns:
        Dictionary formatted for frontend consumption
    """
    # Derive fileName from file_path
    file_name = (
        os.path.basename(db_doc.get("file_path", ""))
        if db_doc.get("file_path")
        else None
    )

    # Format dates
    created_at_iso = db_doc.get("created_at")
    document_date_iso = db_doc.get("document_date")

    # Handle potential timezone info if present in 'created_at'
    try:
        created_at_dt = (
            datetime.fromisoformat(created_at_iso.replace("Z", "+00:00"))
            if created_at_iso
            else None
        )
        formatted_created_at = (
            created_at_dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
            if created_at_dt
            else None
        )
    except (ValueError, TypeError):
        formatted_created_at = created_at_iso  # Fallback if parsing fails

    try:
        # Ensure document_date is just YYYY-MM-DD
        document_date_dt = (
            datetime.fromisoformat(document_date_iso).date()
            if document_date_iso
            else None
        )
        formatted_document_date = (
            document_date_dt.isoformat() if document_date_dt else None
        )
    except (ValueError, TypeError):
        formatted_document_date = document_date_iso  # Fallback

    return {
        "id": str(db_doc.get("id")),
        "userId": db_doc.get("user_id"),
        "patientId": db_doc.get("user_id"),
        "createdAt": formatted_created_at,
        "status": "processed" if db_doc.get("is_ocr_processed") else "uploaded",
        "fileUrl": db_doc.get("download_url"),
        "title": db_doc.get("title"),
        "type": db_doc.get("document_type"),
        "provider": db_doc.get("provider"),
        "date": formatted_document_date,
        "notes": db_doc.get("notes"),
        "tags": db_doc.get("tags", []),
        "fileName": file_name,
        "fileType": db_doc.get("content_type") or db_doc.get("file_type"),
        "fileSize": db_doc.get("file_size"),
    }


# --- New Helper Function for RAGFlow Indexing ---
def trigger_ragflow_indexing(
    user_id: str, dataset_id: str, filename: str, file_content: bytes, content_type: str
):
    """Sends document to RAGFlow for indexing with user_id metadata."""
    if not RAGFLOW_API_URL or not dataset_id:
        print("Error: RAGFlow URL or Dataset ID not configured for indexing.")
        return False

    ragflow_upload_url = f"{RAGFLOW_API_URL}/api/v1/datasets/{dataset_id}/documents"
    headers = {}
    if RAGFLOW_API_KEY:
        headers["Authorization"] = f"Bearer {RAGFLOW_API_KEY}"
    # Note: Content-Type header is set automatically by requests for multipart/form-data

    try:
        files_payload = {"file": (filename, io.BytesIO(file_content), content_type)}

        # --- Passing Metadata ---
        # The RAGFlow PDF for POST /documents doesn't explicitly show metadata passing.
        # Common ways include a separate 'metadata' form field with JSON string.
        # **This requires testing with your RAGFlow instance.**
        # Assume sending 'metadata' field with JSON string:
        metadata_payload_str = json.dumps({"user_id": user_id})
        data_payload = {"metadata": metadata_payload_str}
        # If RAGFlow expects metadata differently (e.g., separate fields), adjust 'data_payload'.
        # If metadata must be set via PUT /documents/{id} later, you'd need that doc ID from the POST response.

        print(
            f"--- Calling RAGFlow Indexing API: {ragflow_upload_url} for user {user_id} ---"
        )
        response = requests.post(
            ragflow_upload_url,
            headers=headers,
            data=data_payload,  # Send metadata here (Hypothesized)
            files=files_payload,
            timeout=60,  # Indexing might take time
        )
        response.raise_for_status()
        ragflow_response = response.json()

        print(ragflow_response)

        # Check if the response contains a document ID

        # Check RAGFlow's response code
        if ragflow_response.get("code") == 0:
            print(
                f"--- RAGFlow indexing initiated successfully for {filename} (User: {user_id}) ---"
            )
            # Optionally return document ID from RAGFlow if needed:
            document_id = ragflow_response.get("data", [{}])[0].get("id")

            if document_id:
                trigger_ragflow_parse(document_id)

            return True
        else:
            print(
                f"Error from RAGFlow indexing API: {ragflow_response.get('message', 'Unknown RAGFlow error')}"
            )
            return False

    except requests.exceptions.RequestException as req_e:
        print(f"Error calling RAGFlow indexing API: {req_e}")
        try:
            print(f"RAGFlow Error Response: {req_e.response.text}")
        except:
            pass
        return False
    except Exception as e:
        print(f"Unexpected error during RAGFlow indexing: {e}")
        return False


def trigger_ragflow_parse(document_id: str):

    ragflow_parse_url = f"{RAGFLOW_API_URL}/api/v1/datasets/{RAGFLOW_DATASET_ID}/chunks"
    headers = {"content-type": "application/json"}
    if RAGFLOW_API_KEY:
        headers["Authorization"] = f"Bearer {RAGFLOW_API_KEY}"

    payload = {
        "document_ids": [document_id],
    }

    print(f"--- Calling RAGFlow Parsing API: {ragflow_parse_url} ---")
    print(f"Payload: {payload}")

    try:
        response = requests.post(
            ragflow_parse_url,
            headers=headers,
            data=json.dumps(payload),
            timeout=60,
        )

        response.raise_for_status()
        ragflow_response = response.json()
        print(ragflow_response)
        return
    except requests.exceptions.RequestException as req_e:
        print(f"Error calling RAGFlow parsing API: {req_e}")
        return
    except Exception as e:
        print(f"Unexpected error during RAGFlow parsing: {e}")
        return
