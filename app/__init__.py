"""
Flask application factory for Copy Trade dashboard.
"""

import os
import secrets
from datetime import timedelta
from flask import Flask


def create_app():
    """
    Create and configure the Flask application.

    Returns:
        Flask: Configured Flask application instance
    """
    app = Flask(__name__,
                template_folder='../templates',
                static_folder='../static')

    # Security: Retrieve secret key from environment or generate secure random key
    app.secret_key = os.environ.get('SECRET_KEY', secrets.token_urlsafe(32))

    # Configure session timeout to 1 hour
    app.permanent_session_lifetime = timedelta(hours=1)

    # Dynamic configuration for Cloud Run deployment
    app.config['BASE_URL'] = os.environ.get('BASE_URL', 'https://localhost')

    # Register routes
    from app.routes import register_routes
    register_routes(app)

    return app
