# Loop through all providers and fill in the missing data - review_count (like 12, 13, 14), rating (3.4, 4.8, etc), hours (like Mon-Fri: 9AM-5PM),about (like "Dr. Smith is a board-certified physician with over 10 years of experience in family medicine.")

from supabase_client import get_supabase
import random
import time
from datetime import datetime

supabase = get_supabase()

PROVIDERS_TABLE = "providers"  # Assumes schema modified as discussed


def generate_about_text(name, specialty):
    """Generate a professional description for the provider based on their specialty."""
    prefixes = {
        "Dr.": "physician",
        "APRN": "advanced practice registered nurse",
        "PA": "physician assistant",
        "NP": "nurse practitioner",
    }

    # Extract title if present
    title = "Dr."  # Default
    for prefix in prefixes:
        if name.startswith(prefix):
            title = prefix
            break

    profession = prefixes.get(title, "healthcare provider")

    templates = [
        f"{name} is a board-certified {profession} with over {random.randint(5, 20)} years of experience in {specialty}.",
        f"As a dedicated {profession} specializing in {specialty}, {name} is committed to providing comprehensive, patient-centered care.",
        f"{name} is a highly skilled {profession} who brings {random.randint(5, 20)} years of expertise in {specialty} to provide compassionate, evidence-based care.",
        f"With specialized training in {specialty}, {name} focuses on developing personalized treatment plans that address each patient's unique health needs.",
    ]

    return random.choice(templates)


def generate_hours():
    """Generate a random schedule string."""
    formats = [
        "Mon-Fri: 9AM-5PM",
        "Mon-Thu: 8AM-6PM, Fri: 8AM-2PM",
        "Mon,Wed,Fri: 8AM-4PM, Tue,Thu: 10AM-7PM",
        "Mon-Fri: 7AM-3PM",
        "Mon-Thu: 9AM-7PM, Fri: 9AM-5PM",
    ]
    return random.choice(formats)


def update_provider_data():
    """Fetch all providers and update missing data."""
    try:
        # Fetch all providers
        response = supabase.table(PROVIDERS_TABLE).select("*").execute()

        if not response.data:
            print("No providers found in the database.")
            return

        providers = response.data
        print(f"Found {len(providers)} providers to update.")

        updated_count = 0

        for provider in providers:
            provider_id = provider.get("id")
            name = provider.get("name", "")
            specialty = provider.get("specialty", "healthcare")

            # Generate missing data
            update_data = {
                "review_count": random.randint(8, 50),
                "rating": round(
                    random.uniform(3.0, 5.0), 1
                ),  # Random rating between 3.0-5.0 with one decimal
                "hours": generate_hours(),
                "about": generate_about_text(name, specialty),
                "updated_at": datetime.now().isoformat(),
            }

            # Update the provider record
            update_response = (
                supabase.table(PROVIDERS_TABLE)
                .update(update_data)
                .eq("id", provider_id)
                .execute()
            )

            if update_response.data:
                updated_count += 1
                print(f"Updated provider: {name}")
            else:
                print(f"Failed to update provider: {name}")

            # Add a small delay to prevent rate limiting
            time.sleep(0.2)

        print(
            f"Successfully updated {updated_count} out of {len(providers)} providers."
        )

    except Exception as e:
        print(f"Error updating providers: {str(e)}")


if __name__ == "__main__":
    print("Starting provider data update...")
    update_provider_data()
    print("Provider data update complete.")
