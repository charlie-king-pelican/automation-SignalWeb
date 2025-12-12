"""
Copy Trade API - Application Entrypoint
This module serves as the minimal entrypoint for Gunicorn/Cloud Run deployment.
"""

from app import create_app

# Create Flask application instance
# This is what Gunicorn will reference with: gunicorn copytradeapi:app
app = create_app()

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8080))
    # Note: On Google Cloud Run, host="0.0.0.0" and PORT env var are essential
    app.run(debug=True, host="0.0.0.0", port=port)
