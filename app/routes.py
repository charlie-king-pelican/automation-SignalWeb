"""
Flask routes for Copy Trade dashboard.
All HTML rendering is done via templates - no inline HTML strings.
"""

from flask import render_template, redirect, request, url_for, session, make_response
from app import services


def add_no_cache_headers(response):
    """
    Add headers to prevent browser caching of authenticated pages.

    Args:
        response: Flask response object

    Returns:
        Flask response object with no-cache headers
    """
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response


def register_routes(app):
    """
    Register all application routes with the Flask app.

    Args:
        app: Flask application instance
    """

    @app.route('/')
    def index():
        """Main dashboard page - handles OAuth callback and displays strategy data."""

        # --- 1. AUTHENTICATION & TOKEN EXCHANGE ---
        if 'code' in request.args:
            code = request.args.get('code')
            verifier = session.pop('verifier', None)

            if verifier:
                redirect_uri = app.config['BASE_URL']
                data = services.exchange_code_for_token(code, verifier, redirect_uri)

                if 'access_token' in data:
                    session['access_token'] = data['access_token']
                    session.permanent = True  # Enable 1-hour timeout
                    return redirect(url_for('index'))
                else:
                    error_msg = data.get('error_description', data.get('error', 'Unknown Error'))
                    return f"Token Exchange Error: {error_msg}"

        # Check for token in session
        token = session.get('access_token')

        if not token:
            # Check if user just logged out
            logged_out = request.args.get('logged_out')
            return render_template('login.html', logged_out=logged_out)

        # --- 2. FETCH DATA ---
        profile_info = services.get_profile_info(token)
        accounts_list = services.get_accounts_list(token)
        strategy_data = services.get_top_strategy(token)

        # If token is invalid/expired, clear session and force re-login
        if strategy_data.get('unauthorized'):
            session.pop('access_token', None)
            return redirect(url_for('index'))

        # --- 3. RENDER UI ---
        # Calculate display values
        inception_display = strategy_data.get('inception_date') or 'Unknown'
        fee_display = "Free" if strategy_data.get('performance_fee', 0) == 0 else f"{strategy_data['performance_fee']:.1f}%"

        response = make_response(render_template(
            'index.html',
            profile_info=profile_info,
            accounts_list=accounts_list,
            strategy=strategy_data,
            inception_display=inception_display,
            fee_display=fee_display,
            format_currency=services.format_currency
        ))
        return add_no_cache_headers(response)

    @app.route('/accounts')
    def accounts():
        """Display all copier accounts with balance and equity."""
        token = session.get('access_token')
        if not token:
            return redirect(url_for('index'))

        profile_name, copiers_with_stats = services.get_copiers_with_stats(token)

        if profile_name is None:
            return "Error fetching accounts data", 500

        response = make_response(render_template(
            'accounts.html',
            profile_name=profile_name,
            copiers=copiers_with_stats,
            format_currency=services.format_currency
        ))
        return add_no_cache_headers(response)

    @app.route('/login')
    def login():
        """Initiate OAuth login flow with PKCE."""
        verifier, challenge = services.generate_pkce()
        session['verifier'] = verifier

        redirect_uri = app.config['BASE_URL']
        auth_url = services.build_auth_url(redirect_uri, challenge)

        return redirect(auth_url)

    @app.route('/debug/api')
    def debug_api():
        """Debug route - cleared for production."""
        token = session.get('access_token')
        if not token:
            return redirect(url_for('index'))

        return render_template('debug.html')

    @app.route('/logout')
    def logout():
        """Clear local session and redirect to identity provider logout."""
        session.pop('access_token', None)
        session.clear()

        redirect_uri = app.config['BASE_URL']
        logout_url = services.build_logout_url(redirect_uri)

        return redirect(logout_url)
