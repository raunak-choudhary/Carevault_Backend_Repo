# routes/medications.py
from flask import Blueprint, request, jsonify, g

# Import the service function
from services.medication_service import (
    create_medication_reminder,
    get_medication_by_id,
    get_medications,
)
from routes.auth import token_required

medications_bp = Blueprint("medications", __name__, url_prefix="/api/medications")


@medications_bp.route("/", methods=["POST"])
@token_required
def add_medication_reminder_route():
    user_id = g.current_user_profile["id"]
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request is empty or missing JSON data."}), 400

    try:
        # Call the service function
        created_medication, error_response = create_medication_reminder(user_id, data)

        if error_response:
            # If service function returned an error tuple
            error_msg, status_code = error_response
            return jsonify(error_msg), status_code

        # If successful, return the created medication
        return (
            jsonify(
                {
                    "error": False,
                    "message": "Medication added successfully.",
                    "success": True,
                },
            ),
            201,
        )

    except ValueError as ve:  # Catch specific validation errors if service raises them
        return jsonify({"error": str(ve)}), 400
    except Exception as e:  # Catch unexpected errors from service
        print(f"Error in add_medication route: {str(e)}")
        return jsonify({"error": "An unexpected error occurred"}), 500


# --- New Route: Get Single Medication ---
@medications_bp.route("/<string:medication_id>", methods=["GET"])
@token_required
def get_medication(medication_id):
    """Get a specific medication reminder by ID"""
    user_id = g.current_user_profile["id"]

    try:

        # Call the service function which now returns (data, status_code)
        medication_data, status_code = get_medication_by_id(user_id, medication_id)

        # Handle response based on status code returned by service
        if status_code == 200:
            # Success
            return (
                jsonify(
                    {
                        "error": False,
                        "message": "Medication details fetched successfully.",
                        "data": medication_data,
                        "success": True,
                    },
                ),
                200,
            )
        elif status_code == 404:
            return (
                jsonify(
                    {
                        "error": True,
                        "success": False,
                        "message": "Medication reminder not found",
                    }
                ),
                404,
            )
        elif status_code == 403:
            return (
                jsonify(
                    {
                        "error": True,
                        "success": False,
                        "message": "Access denied to this medication reminder",
                    }
                ),
                403,
            )
        else:  # Handle 500 or other unexpected errors
            return (
                jsonify(
                    {
                        "error": True,
                        "success": False,
                        "message": "Failed to retrieve medication reminder",
                    }
                ),
                500,
            )

    except Exception as e:
        # Catch any other unexpected errors from the service
        print(f"Error in get_medication route: {str(e)}")
        return (
            jsonify(
                {
                    "error": True,
                    "success": False,
                    "message": "Failed to retrieve medication reminder",
                }
            ),
            500,
        )


# --- Route: List Medications ---
@medications_bp.route("/", methods=["GET"])
@token_required
def list_medications():
    """Get a list of medication reminders for the user with filtering"""
    user_id = g.current_user_profile["id"]

    # --- Get and Parse Query Parameters ---
    try:
        skip = int(request.args.get("skip", 0))
        limit = int(request.args.get("limit", 10))
    except ValueError:
        return (
            jsonify(
                {
                    "success": False,
                    "error": True,
                    "message": "Invalid skip or limit parameter",
                    "data": None,
                }
            ),
            400,
        )

    title_filter = request.args.get("title")  # Free text filter for medication name
    active_param = request.args.get(
        "active"
    )  # Filter by active status ('true'/'false')

    active_filter = None
    if active_param is not None:
        if active_param.lower() == "true":
            active_filter = True
        elif active_param.lower() == "false":
            active_filter = False
        else:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": True,
                        "message": "Invalid 'active' filter value. Use 'true' or 'false'.",
                        "data": None,
                    }
                ),
                400,
            )
    # --- Call Service ---
    medications, total_count = get_medications(
        user_id=user_id,
        skip=skip,
        limit=limit,
        title_filter=title_filter,
        active_filter=active_filter,
    )

    # --- Format Response ---
    if medications is None:  # Indicates an error occurred in the service
        return (
            jsonify(
                {
                    "success": False,
                    "error": True,
                    "message": "Failed to retrieve medication list",
                    "data": None,
                }
            ),
            500,
        )

    for medication in medications:
        medication["status"] = "active" if medication["active"] else "inactive"
        medication["refillDate"] = medication["end_date"]
        medication["unit"] = medication["dosage_unit"]
        medication["name"] = medication["medication_name"]

    return (
        jsonify(
            {
                "success": True,
                "error": False,
                "message": "Medications retrieved successfully.",
                "data": {
                    "medications": medications,
                    "total": total_count,
                    "skip": skip,
                    "limit": limit,
                },
            }
        ),
        200,
    )
