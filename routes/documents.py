import os
import uuid
from flask import Blueprint, jsonify, request, g
from werkzeug.utils import secure_filename
from datetime import datetime

from supabase_client import get_supabase
from routes.auth import token_required

# Defining the blueprint for documents
documents_bp = Blueprint("documents", __name__, url_prefix="/api/documents")

supabase = get_supabase()

# Allowed file extensions for document uploads
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "txt", "jpg", "jpeg", "png"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@documents_bp.route("/upload", methods=["POST"])
@token_required
def upload_document():

    # The user profile is in g.current_user_profile thanks to @token_required
    user_id = g.current_user_profile["id"]

    # --- Get data from multipart/form-data ---
    # Check if the post request has the file part
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    file = request.files["file"]

    # --- Get metadata from form fields ---

    title = request.form.get("title")
    document_type = request.form.get(
        "document_type"
    )  # Consider validating against DocumentType Enum values
    description = request.form.get("description")
    document_date_str = request.form.get(
        "document_date"
    )  # Expecting ISO format string e.g., 'YYYY-MM-DD'
    notes = request.form.get("notes")  # Capture notes from form
    tags = request.form.get("tags")  # Capture tags from form
    provider = request.form.get("provider")  # Capture provider from form

    # --- Basic Validation ---
    if not title or not document_type:
        return jsonify({"error": "Missing required fields: title, document_type"}), 400
    if not file or not allowed_file(file.filename):
        return jsonify({"error": "File type not allowed"}), 400

    document_date = None

    if document_date_str:
        try:
            # Attempt to parse date string - adjust format if needed
            document_date = datetime.strptime(document_date_str, "%Y-%m-%d").date()
        except ValueError:
            return (
                jsonify({"error": "Invalid document_date format. Use YYYY-MM-DD"}),
                400,
            )

    try:
        filename = secure_filename(file.filename)
        file_ext = os.path.splitext(filename)[1].lower()
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        storage_path = f"documents/{user_id}/{unique_filename}"
        file_content = file.read()
        file_size = len(file_content)
        content_type = file.content_type
        file.seek(0)

        storage_response = supabase.storage.from_("documents").upload(
            path=storage_path,
            file=file_content,
            file_options={"content-type": content_type},
        )

        public_url = supabase.storage.from_("documents").get_public_url(storage_path)

        document_data = {
            "user_id": user_id,
            "title": title,
            "description": description,  # Include description if needed in DB
            "document_type": document_type,
            "document_date": (
                document_date.isoformat()
                if document_date
                else datetime.now().date().isoformat()
            ),
            "file_path": storage_path,
            "content_type": content_type,
            "file_size": file_size,
            "notes": notes,  # Save notes to DB
            "tags": tags,
            "provider": provider,
        }

        db_response = supabase.table("documents").insert(document_data).execute()

        if not db_response.data:
            try:
                supabase.storage.from_("documents").remove([storage_path])
            except Exception as cleanup_error:
                print(f"Storage cleanup failed: {cleanup_error}")
            return jsonify({"error": "Failed to save document metadata"}), 500

        return jsonify(
            {
                "error": None,
                "message": "Document uploaded successfully.",
                "success": True,
            },
            200,
        )

    except Exception as e:
        print(f"Document upload error: {str(e)}")
        return jsonify({"error": f"Document upload failed: {str(e)}"}), 500


# --- GET Specific Document Route ---
@documents_bp.route("/<string:document_id>", methods=["GET"])
@token_required
def get_document(document_id):
    """Get document by ID"""
    user_id = g.current_user_profile["id"]

    try:
        # Fetch document from DB (adapting logic from services/documents.py)
        response = (
            supabase.table("documents").select("*").eq("id", document_id).execute()
        )

        if not response.data:
            return jsonify({"error": "Document not found"}), 404

        document_db = response.data[0]

        # Verify ownership
        if document_db.get("user_id") != user_id:
            return jsonify({"error": "Access denied to this document"}), 403

        # Get the public download URL
        download_url = None
        try:
            download_url = supabase.storage.from_("documents").get_public_url(
                document_db["file_path"]
            )
            # Add the fetched URL to the dictionary to be passed to the mapping function
            document_db["download_url"] = download_url
        except Exception as url_error:
            print(
                f"Could not get public URL for {document_db.get('file_path')}: {url_error}"
            )
            document_db["download_url"] = (
                None  # Ensure the key exists even if URL fails
            )

        # Map database record to the frontend's expected structure
        frontend_document = map_db_to_frontend(document_db)

        return (
            jsonify(
                {
                    "error": None,
                    "message": "Document fetched successfully.",
                    "success": True,
                    "document": frontend_document,
                }
            ),
            200,
        )

    except Exception as e:
        print(f"Error fetching document {document_id}: {str(e)}")  # Log error
        return jsonify({"error": f"Failed to fetch document: {str(e)}"}), 500


# --- Helper Function to Map DB fields to Frontend fields ---
def map_db_to_frontend(db_doc: dict) -> dict:
    """Maps a document dictionary from DB schema to frontend expected schema."""

    # Derive fileName from file_path
    file_name = (
        os.path.basename(db_doc.get("file_path", ""))
        if db_doc.get("file_path")
        else None
    )

    # Format dates (assuming DB stores them as ISO strings or datetime objects)
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
        "id": str(db_doc.get("id")),  # Ensure ID is string if needed
        "userId": db_doc.get("user_id"),
        "patientId": db_doc.get(
            "user_id"
        ),  # Assuming patientId is same as userId for now
        "createdAt": formatted_created_at,
        "status": (
            "processed" if db_doc.get("is_ocr_processed") else "uploaded"
        ),  # Example mapping for 'status'
        "fileUrl": db_doc.get("download_url"),  # Use the generated URL
        "title": db_doc.get("title"),
        "type": db_doc.get("document_type"),  # Map document_type to type
        "provider": db_doc.get(
            "provider_id"
        ),  # Returning ID for now, fetch name if needed later
        "date": formatted_document_date,  # Map document_date to date
        "notes": db_doc.get("notes"),
        "tags": [],  # Placeholder - DB schema doesn't have tags
        "fileName": file_name,
        "fileType": db_doc.get("content_type"),  # Map content_type to fileType
        "fileSize": db_doc.get("file_size"),
    }
