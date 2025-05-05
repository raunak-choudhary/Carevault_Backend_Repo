# app.py
from flask import Flask, jsonify, redirect, url_for
from config import API_V1_STR, PROJECT_NAME  # Import config

# Import blueprints from the routes package
from routes.auth import auth_bp

# Import other blueprints as you create them
from routes.documents import documents_bp
from routes.medications import medications_bp
from routes.appointments import appointments_bp
from routes.chat import chat_bp
from routes.providers import providers_bp

from routes.chat import chat_bp

# from routes.appointments import appointments_bp
# from routes.dashboard import dashboard_bp

# Optional: Import Flask-CORS if you added it to requirements.txt
from flask_cors import CORS


def create_app():
    app = Flask(__name__)

    # Optional: Configure CORS
    CORS(app, resources={r"/api/*": {"origins": "http://localhost:3000"}})  # Example

    app.config["PROJECT_NAME"] = PROJECT_NAME
    # You can add other configurations here if needed
    # e.g., app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')

    # Register Blueprints
    app.register_blueprint(auth_bp)
    # Register other blueprints here
    app.register_blueprint(documents_bp)
    app.register_blueprint(medications_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(appointments_bp)
    app.register_blueprint(providers_bp)
    # app.register_blueprint(dashboard_bp)

    @app.route("/api")
    def api_index():
        # Redirect root to a simple API status or docs page if you have one
        return jsonify({"status": f"{app.config['PROJECT_NAME']} API is running"}), 200

    @app.route("/")
    def index():
        return redirect("/api")

    # Add a simple error handler for demonstration
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Not Found"}), 404

    return app


if __name__ == "__main__":
    app = create_app()
    # Use Flask's development server
    # host='0.0.0.0' makes it accessible externally, debug=True enables auto-reload
    app.run(host="0.0.0.0", port=1999, debug=True)
