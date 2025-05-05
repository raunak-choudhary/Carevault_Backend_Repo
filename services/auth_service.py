from supabase_client import get_supabase
from datetime import datetime, timedelta
from typing import Optional

supabase = get_supabase()


def request_email_verification(user_email: str):
    """
    Requests Supabase to resend the verification email (signup confirmation).
    Returns: Tuple (None, status_code) -> 200 on success/attempt, 500 on error.
    """
    try:
        # Use the resend method for the 'signup' type email
        # Note: This sends the standard signup confirmation email again.
        response = supabase.auth.ver(email=user_email)
        # Check response if needed, although it might not error out for non-existent emails
        print(f"Supabase resend response for {user_email}: {response}")  # Log response
        return None, 200
    except Exception as e:
        # Catch potential API call errors, rate limiting, etc.
        print(f"Error requesting verification resend for {user_email}: {str(e)}")
        return None, 500  # Internal Server Error
