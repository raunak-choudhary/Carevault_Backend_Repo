# routes/auth.py
from flask import Blueprint, request, jsonify, g
from supabase_client import get_supabase  # Import the initialized client
from functools import wraps

# Define the blueprint: 'auth' is the name, __name__ helps Flask find templates/static later if needed
# url_prefix ensures all routes in this file start with /api/v1/auth
auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

supabase = get_supabase()


# --- Authentication Decorator ---
def token_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        # Check for bearer token in Authorization header
        if "Authorization" in request.headers:
            auth_header = request.headers["Authorization"]
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1]

        if not token:
            return jsonify({"error": "Authentication Token is missing!"}), 401

        try:
            # Verify token with Supabase (adapting logic from core/security.py [cite: 1])
            user_response = supabase.auth.get_user(token)

            if not user_response or not user_response.user:
                return jsonify({"error": "Invalid or expired token"}), 401

            user_id = user_response.user.id

            # Fetch the user profile from your 'user_profiles' table
            profile_response = (
                supabase.table("user_profiles").select("*").eq("id", user_id).execute()
            )

            if not profile_response.data:
                # This case might happen if user exists in auth but not profiles table
                return jsonify({"error": "User profile not found"}), 404

            # Store the fetched profile in Flask's 'g' object for access in the route
            g.current_user_profile = profile_response.data[0]

        except Exception as e:
            print(f"Authentication error: {str(e)}")  # Log error
            # Check for specific Supabase/JWT errors if possible, otherwise return general error
            if "invalid JWT" in str(e).lower() or "token is invalid" in str(e).lower():
                return jsonify({"error": "Invalid or expired token"}), 401
            return jsonify({"error": "Could not validate credentials"}), 401

        # Proceed to the decorated route function
        return f(*args, **kwargs)

    return decorated_function


@auth_bp.route("/login", methods=["POST"])
def login():
    # Manual form data access (same as previous example)
    email = request.form.get(
        "username"
    )  # Corresponds to OAuth2PasswordRequestForm username
    password = request.form.get("password")

    if not email or not password:
        return jsonify({"error": "Missing email or password"}), 400

    try:
        # Directly call Supabase auth (logic adapted from services/auth.py)
        auth_response = supabase.auth.sign_in_with_password(
            {"email": email, "password": password}
        )

        if auth_response.user and auth_response.session:
            # Return token data directly
            return (
                jsonify(
                    {
                        "access_token": auth_response.session.access_token,
                        "refresh_token": auth_response.session.refresh_token,
                        "token_type": "bearer",
                    }
                ),
                200,
            )
        else:
            # Supabase client usually raises an exception on failure,
            # but check just in case it returns None without error.
            return jsonify({"error": "Invalid credentials"}), 401

    except Exception as e:
        # Log the error properly in a real app
        print(f"Login error: {str(e)}")
        # Check if the error message indicates bad credentials
        if "Invalid login credentials" in str(e):
            return jsonify({"error": "Invalid email or password"}), 401
        return (
            jsonify({"error": "Authentication failed"}),
            500,
        )  # Internal server error for unexpected issues


# --- Add other auth routes here (register, refresh, me, etc.) ---
# Example: Register route skeleton
@auth_bp.route("/register", methods=["POST"])
def register():
    # Get data from request.get_json()
    # Call Supabase sign_up (similar to services/auth.py)
    # Insert into user_profiles table
    # Return success or error
    pass  # Replace with actual logic


@auth_bp.route("/me", methods=["GET"])
@token_required  # Apply the authentication decorator
def get_user_profile():
    """Get current user profile"""
    # The decorator already fetched the profile and stored it in g.current_user_profile
    # The structure of this dictionary matches the UserProfile schema
    # (or rather, the columns in your user_profiles table).
    user_profile = g.current_user_profile
    return jsonify(user_profile), 200


# --- Refresh Token Route ---
@auth_bp.route("/refresh", methods=["POST"])
def refresh_token():
    """Refresh access token using a refresh token"""
    # Get refresh token from JSON body
    data = request.get_json()
    if not data or "refresh_token" not in data:
        return jsonify({"error": "Missing refresh_token in request body"}), 400

    refresh_token_str = data["refresh_token"]

    try:
        # Use Supabase client to refresh the session (logic from services/auth.py)
        # Note: Supabase `refresh_session` might implicitly use the refresh token
        # stored in the client if initialized with persist_session=True, or
        # you might need to explicitly pass it if managing tokens manually.
        # The python client's refresh_session takes the refresh token as an argument.
        refreshed_session_response = supabase.auth.refresh_session(refresh_token_str)

        if refreshed_session_response and refreshed_session_response.session:
            # Return new tokens (similar structure to Token schema)
            return (
                jsonify(
                    {
                        "access_token": refreshed_session_response.session.access_token,
                        "refresh_token": refreshed_session_response.session.refresh_token,  # Supabase usually provides a new refresh token
                        "token_type": "bearer",
                    }
                ),
                200,
            )
        else:
            # Should not happen if refresh_session raises error on failure, but good practice
            return jsonify({"error": "Failed to refresh token"}), 401

    except Exception as e:
        # Supabase client raises an AuthApiError for invalid refresh tokens etc.
        print(f"Token refresh error: {str(e)}")
        # You might want to inspect the error `e` for specifics if available
        return jsonify({"error": "Invalid or expired refresh token"}), 401
