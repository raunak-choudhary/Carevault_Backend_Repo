from flask import Blueprint, jsonify, request, g
from routes.auth import token_required

# Import the services
from services.document_service import (
    allowed_file,
    upload_document_to_storage,
    get_document_by_id,
    get_all_documents_for_user,
)

# Defining the blueprint for documents
documents_bp = Blueprint("documents", __name__, url_prefix="/api/documents")


@documents_bp.route("/upload", methods=["POST"])
@token_required
def upload_document():
    """Route to upload a new document"""
    # Get the user ID from the token_required decorator
    user_id = g.current_user_profile["id"]

    # Check if the post request has the file part
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files["file"]

    # Get metadata from form fields
    title = request.form.get("title")
    document_type = request.form.get("document_type")
    description = request.form.get("description")
    document_date_str = request.form.get("document_date")
    notes = request.form.get("notes")
    tags = request.form.get("tags")
    provider_id = request.form.get("provider_id")

    # Basic validation
    if not title or not document_type:
        return jsonify({"error": "Missing required fields: title, document_type"}), 400
    if not file or not allowed_file(file.filename):
        return jsonify({"error": "File type not allowed"}), 400

    # Call the service function
    result, status_code = upload_document_to_storage(
        file=file,
        user_id=user_id,
        title=title,
        document_type=document_type,
        description=description,
        document_date_str=document_date_str,
        notes=notes,
        tags=tags,
        provider_id=provider_id,
    )

    return jsonify(result), status_code


@documents_bp.route("/<string:document_id>", methods=["GET"])
@token_required
def get_document(document_id):
    """Get document by ID"""
    user_id = g.current_user_profile["id"]

    # Call the service function
    result, status_code = get_document_by_id(document_id, user_id)

    return jsonify(result), status_code


@documents_bp.route("/", methods=["GET"])
@token_required
def get_all_documents():
    """Get all documents for the authenticated user"""
    user_id = g.current_user_profile["id"]

    # Call the service function
    result, status_code = get_all_documents_for_user(user_id)

    return jsonify(result), status_code
