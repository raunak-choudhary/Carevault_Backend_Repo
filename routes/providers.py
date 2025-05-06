# routes/providers.py
from flask import Blueprint, request, jsonify, g
from services.provider_service import get_providers, get_provider_by_id
from routes.auth import token_required  # Assuming listing providers requires login

providers_bp = Blueprint("providers", __name__, url_prefix="/api/providers")


@providers_bp.route("/", methods=["GET"])
@token_required
def list_providers():
    """Get a list of providers with filtering and pagination"""
    # Parse query parameters
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

    specialty_filter = request.args.get("specialty")
    name_filter = request.args.get("name")

    # Call service function
    providers_list, total_count = get_providers(
        skip=skip,
        limit=limit,
        specialty_filter=specialty_filter,
        name_filter=name_filter,
    )

    # Format response
    if providers_list is None:  # Service indicated an error
        return (
            jsonify(
                {
                    "success": False,
                    "error": True,
                    "message": "Failed to retrieve providers",
                    "data": None,
                }
            ),
            500,
        )

    # NOTE: Returning raw DB data here. Add mapping if FE needs different keys.
    return (
        jsonify(
            {
                "success": True,
                "error": False,
                "message": "Providers retrieved successfully.",
                "data": {
                    "providers": providers_list,
                    "total": total_count,
                    "skip": skip,
                    "limit": limit,
                },
            }
        ),
        200,
    )


@providers_bp.route("/<string:provider_id>", methods=["GET"])
@token_required
def get_provider(provider_id):
    """Get details for a specific provider by ID"""

    provider_data, status_code = get_provider_by_id(provider_id)

    if status_code == 200:
        # NOTE: Returning raw DB data. Add mapping if needed.
        return (
            jsonify(
                {
                    "success": True,
                    "error": False,
                    "message": "Provider details fetched successfully.",
                    "data": provider_data,
                }
            ),
            200,
        )
    elif status_code == 404:
        return (
            jsonify(
                {
                    "success": False,
                    "error": True,
                    "message": "Provider not found",
                    "data": None,
                }
            ),
            404,
        )
    else:  # Handle 500
        return (
            jsonify(
                {
                    "success": False,
                    "error": True,
                    "message": "Failed to retrieve provider details",
                    "data": None,
                }
            ),
            500,
        )
