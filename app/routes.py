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

        # Fetch strategy signals for Trades tab
        strategy_id = strategy_data.get('strategy_id')
        open_signals = []
        closed_signals = []
        closed_trades_range = request.args.get('range', '30d')  # Default: 30 days
        closed_trades_stats = {}

        # Detect copy state if account is selected
        selected_copier_id = request.args.get('copier_id')
        is_copying = False
        copy_settings = None

        if selected_copier_id and strategy_id:
            copy_settings, status_code = services.get_copy_settings(selected_copier_id, strategy_id, token)
            is_copying = (status_code == 200 and copy_settings is not None)

        if strategy_id:
            from datetime import datetime, timedelta

            # Fetch open signals (unchanged)
            open_signals = services.get_strategy_open_signals(strategy_id, token)

            # Compute date range for closed signals based on query param
            end_dt = datetime.utcnow()

            if closed_trades_range == '7d':
                start_dt = end_dt - timedelta(days=7)
            else:  # Default: 30d
                closed_trades_range = '30d'  # Normalize
                start_dt = end_dt - timedelta(days=30)

            start_dt_iso = start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
            end_dt_iso = end_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
            closed_signals = services.get_strategy_closed_signals(strategy_id, token, start_dt_iso, end_dt_iso)

            # Sort signals: newest first
            if open_signals:
                open_signals = sorted(open_signals, key=lambda x: x.get('OpenTimestamp', ''), reverse=True)
            if closed_signals:
                closed_signals = sorted(closed_signals, key=lambda x: x.get('CloseTimestamp', ''), reverse=True)

            # Compute summary stats for closed trades
            if closed_signals:
                closed_trades_stats = services.compute_closed_trades_stats(closed_signals)

        # --- 3. RENDER UI ---
        # Calculate display values
        inception_display = strategy_data.get('inception_date') or 'Unknown'
        fee_display = "Free" if strategy_data.get('performance_fee', 0) == 0 else f"{strategy_data['performance_fee']:.1f}%"

        response = make_response(render_template(
            'index.html',
            profile_info=profile_info,
            accounts_list=accounts_list,
            strategy=strategy_data,
            strategy_id=strategy_id,
            inception_display=inception_display,
            fee_display=fee_display,
            open_signals=open_signals,
            closed_signals=closed_signals,
            closed_trades_range=closed_trades_range,
            closed_trades_stats=closed_trades_stats,
            selected_copier_id=selected_copier_id,
            is_copying=is_copying,
            copy_settings=copy_settings,
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

        # Fetch brokers for the Link Account modal
        brokers = services.get_brokers(token)

        # Get default servers for first broker (if only one broker exists)
        default_servers = []
        if len(brokers) == 1:
            broker_detail = services.get_broker_detail(token, brokers[0].get('Code'))
            if broker_detail:
                default_servers = broker_detail.get('Servers', [])

        # Check for flash messages in query params
        link_success = request.args.get('link_success')
        link_error = request.args.get('link_error')
        unlink_success = request.args.get('unlink_success')
        unlink_error = request.args.get('unlink_error')

        response = make_response(render_template(
            'accounts.html',
            profile_name=profile_name,
            copiers=copiers_with_stats,
            brokers=brokers,
            default_servers=default_servers,
            link_success=link_success,
            link_error=link_error,
            unlink_success=unlink_success,
            unlink_error=unlink_error,
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
        """Debug route - display raw JSON for strategy open and closed signals."""
        token = session.get('access_token')
        if not token:
            return redirect(url_for('index'))

        strategy_id = request.args.get('strategy_id')

        open_signals = None
        closed_signals = None
        error_message = None

        if strategy_id:
            try:
                # Calculate date range for closed signals (last 30 days)
                from datetime import datetime, timedelta
                end_dt = datetime.utcnow()
                start_dt = end_dt - timedelta(days=30)

                # Format as ISO 8601 strings
                start_dt_iso = start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
                end_dt_iso = end_dt.strftime('%Y-%m-%dT%H:%M:%SZ')

                # Fetch strategy signals
                open_signals = services.get_strategy_open_signals(strategy_id, token)
                closed_signals = services.get_strategy_closed_signals(strategy_id, token, start_dt_iso, end_dt_iso)
            except Exception as e:
                error_message = f"Error fetching signals: {str(e)}"

        return render_template('debug.html',
                             strategy_id=strategy_id,
                             open_signals=open_signals,
                             closed_signals=closed_signals,
                             error_message=error_message)

    @app.route('/logout')
    def logout():
        """Clear local session and redirect to identity provider logout."""
        session.pop('access_token', None)
        session.clear()

        redirect_uri = app.config['BASE_URL']
        logout_url = services.build_logout_url(redirect_uri)

        return redirect(logout_url)

    @app.route('/copy-strategy', methods=['POST'])
    def copy_strategy():
        """Handle copy strategy form submission (create or update copy settings)."""
        token = session.get('access_token')
        if not token:
            return redirect(url_for('index'))

        # Get form data
        copier_id = request.form.get('copier_id')
        strategy_id = request.form.get('strategy_id')
        strategy_name = request.form.get('strategy_name', 'Strategy')
        trade_size_type = request.form.get('trade_size_type')
        trade_size_value = request.form.get('trade_size_value')
        is_open_existing = request.form.get('is_open_existing') == 'on'
        is_round_up = request.form.get('is_round_up') == 'on'
        source = request.form.get('source', 'dashboard')  # 'dashboard' or 'copying'

        # Validation
        if not copier_id or not strategy_id:
            return redirect(url_for('index'))

        # Build settings payload
        settings = {
            'tradeSizeType': trade_size_type,
            'tradeSizeValue': float(trade_size_value) if trade_size_value else 1.0,
            'isOpenExistingTrades': is_open_existing,
            'isRoundUpToMinimumSize': is_round_up
        }

        # Detect if already copying (GET first)
        copy_settings, status_code = services.get_copy_settings(copier_id, strategy_id, token)

        if status_code == 200:
            # Already copying - use PUT
            success, result = services.update_copy_settings(copier_id, strategy_id, token, settings)
            action = 'updated'
        else:
            # Not copying yet - use POST
            success, result = services.create_copy_settings(copier_id, strategy_id, token, settings)
            action = 'copied'

        # Redirect based on source
        if source == 'copying':
            if success:
                return redirect(url_for('copying', copy_success=f'{strategy_name} {action} successfully'))
            else:
                return redirect(url_for('copying', copy_error=f'Failed to {action[:-1]} {strategy_name}'))
        else:
            # Dashboard
            if success:
                return redirect(url_for('index', copier_id=copier_id, copy_success=f'{strategy_name} {action} successfully'))
            else:
                return redirect(url_for('index', copier_id=copier_id, copy_error=f'Failed to {action[:-1]} {strategy_name}'))

    @app.route('/copying')
    def copying():
        """Display all copier accounts and the strategies they are copying.

        Performance optimized: Only fetches essential data for initial view.
        Removed: copier stats, strategy stats (reduces API calls from ~30+ to ~11 for typical usage).
        """
        token = session.get('access_token')
        if not token:
            return redirect(url_for('index'))

        # Get profile ID (1 API call)
        profile_id = services.get_profile_id(token)
        if not profile_id:
            return "Error: Could not retrieve profile", 500

        # Check for flash messages in query params
        copy_success = request.args.get('copy_success')
        copy_error = request.args.get('copy_error')
        stop_success = request.args.get('stop_success')
        stop_error = request.args.get('stop_error')

        # Get all copiers for this profile (1 API call)
        copiers = services.list_profile_copiers(profile_id, token)

        # Build view model with nested data
        # Optimized: No longer fetching copier stats or strategy stats on initial load
        copiers_data = []
        for copier in copiers:
            copier_id = copier.get('Id')
            if not copier_id:
                continue

            # Build copier info (no API call - using data from list_profile_copiers)
            copier_info = {
                'id': copier_id,
                'name': copier.get('Name', 'Unknown'),
                'enabled': copier.get('IsEnabled', False),
                'server_code': copier.get('Connection', {}).get('ServerCode', 'N/A'),
                'username': copier.get('Connection', {}).get('Username', 'N/A')
            }

            # Get strategies being copied by this copier (1 API call per copier)
            strategies_list = services.list_copier_strategies(copier_id, token)

            strategies_data = []
            for strategy in strategies_list:
                strategy_id = strategy.get('Id')
                if not strategy_id:
                    continue

                # Get copy settings for this copier/strategy pair (1 API call per strategy)
                copy_settings, status_code = services.get_copy_settings(copier_id, strategy_id, token)
                if status_code != 200:
                    copy_settings = None

                # Build strategy data (no extra API call - using data from list_copier_strategies)
                strategy_data = {
                    'id': strategy_id,
                    'name': strategy.get('Name', 'Unknown'),
                    'profile_name': strategy.get('ProfileName', 'Unknown'),
                    'fee': strategy.get('Fee', 0) * 100 if strategy.get('Fee') is not None else 0,
                    'num_copiers': strategy.get('NumCopiers', 0)
                }

                strategies_data.append({
                    'strategy': strategy_data,
                    'settings': copy_settings
                })

            copiers_data.append({
                'copier': copier_info,
                'strategies': strategies_data
            })

        response = make_response(render_template(
            'copying.html',
            copiers_data=copiers_data,
            copy_success=copy_success,
            copy_error=copy_error,
            stop_success=stop_success,
            stop_error=stop_error,
            format_trade_sizing=services.format_trade_sizing
        ))
        return add_no_cache_headers(response)

    @app.route('/stop-copy', methods=['POST'])
    def stop_copy():
        """Handle stop copying form submission."""
        token = session.get('access_token')
        if not token:
            return redirect(url_for('index'))

        copier_id = request.form.get('copier_id')
        strategy_id = request.form.get('strategy_id')
        strategy_name = request.form.get('strategy_name', 'Strategy')
        mode = request.form.get('mode', 'Mirror')
        source = request.form.get('source', 'copying')  # 'copying' or 'dashboard'

        # Validation
        if not copier_id or not strategy_id:
            if source == 'dashboard':
                return redirect(url_for('index', copier_id=copier_id, stop_error='Missing copier or strategy'))
            return redirect(url_for('copying', stop_error='Missing copier or strategy'))

        # Validate mode
        if mode not in ['Mirror', 'Close', 'Manual']:
            mode = 'Mirror'

        # Delete copy settings
        success, status_code, error = services.delete_copy_settings(copier_id, strategy_id, token, mode)

        # Redirect based on source
        if source == 'dashboard':
            if success:
                return redirect(url_for('index', copier_id=copier_id, stop_success=f'Stopped copying {strategy_name}'))
            else:
                return redirect(url_for('index', copier_id=copier_id, stop_error=f'Failed to stop copying {strategy_name}'))
        else:
            # Redirect back to copying page
            if success:
                return redirect(url_for('copying', stop_success=f'Stopped copying {strategy_name}'))
            else:
                return redirect(url_for('copying', stop_error=f'Failed to stop copying {strategy_name}'))

    @app.route('/copier-trades')
    def copier_trades():
        """Display trades for a selected copier account."""
        token = session.get('access_token')
        if not token:
            return redirect(url_for('index'))

        # Get profile_id for caching key
        profile_id = services.get_profile_id(token)

        # Get accounts list for dropdown
        accounts_list = services.get_accounts_list(token)

        # Get open positions summary (cached, parallel fetch)
        open_positions_summary = {}
        if profile_id and accounts_list:
            open_positions_summary = services.get_open_positions_summary_for_profile(
                profile_id, token, accounts_list
            )

        # Get selected copier from query param
        selected_copier_id = request.args.get('copier_id')
        closed_trades_range = request.args.get('range', '30d')

        # Initialize data
        open_signals = []
        closed_signals = []
        closed_trades_stats = {}
        selected_copier_name = None

        # Find the selected copier name for display
        if selected_copier_id and accounts_list:
            for acc in accounts_list:
                if str(acc.get('id')) == str(selected_copier_id):
                    selected_copier_name = acc.get('name', 'Unknown')
                    break

        # Fetch signals if a copier is selected
        if selected_copier_id:
            from datetime import datetime, timedelta

            # Fetch open signals
            open_signals = services.get_copier_open_signals(selected_copier_id, token)

            # Compute date range for closed signals
            end_dt = datetime.utcnow()

            if closed_trades_range == '7d':
                start_dt = end_dt - timedelta(days=7)
            else:  # Default: 30d
                closed_trades_range = '30d'  # Normalize
                start_dt = end_dt - timedelta(days=30)

            start_dt_iso = start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
            end_dt_iso = end_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
            closed_signals = services.get_copier_closed_signals(selected_copier_id, token, start_dt_iso, end_dt_iso)

            # Sort signals: newest first
            if open_signals:
                open_signals = sorted(open_signals, key=lambda x: x.get('OpenTimestamp', ''), reverse=True)
            if closed_signals:
                closed_signals = sorted(closed_signals, key=lambda x: x.get('CloseTimestamp', ''), reverse=True)

            # Compute summary stats for closed trades
            if closed_signals:
                closed_trades_stats = services.compute_closed_trades_stats(closed_signals)

        response = make_response(render_template(
            'copier_trades.html',
            accounts_list=accounts_list,
            selected_copier_id=selected_copier_id,
            selected_copier_name=selected_copier_name,
            open_signals=open_signals,
            closed_signals=closed_signals,
            closed_trades_range=closed_trades_range,
            closed_trades_stats=closed_trades_stats,
            open_positions_summary=open_positions_summary,
            format_currency=services.format_currency
        ))
        return add_no_cache_headers(response)

    @app.route('/accounts/servers')
    def get_servers():
        """AJAX endpoint to fetch servers for a selected broker."""
        from flask import jsonify

        token = session.get('access_token')
        if not token:
            return jsonify({'error': 'Not authenticated'}), 401

        broker_code = request.args.get('brokerCode')
        if not broker_code:
            return jsonify({'error': 'brokerCode parameter required'}), 400

        broker_detail = services.get_broker_detail(token, broker_code)
        if broker_detail is None:
            return jsonify({'error': 'Broker not found'}), 404

        servers = broker_detail.get('Servers', [])
        return jsonify({'servers': servers})

    @app.route('/accounts/link', methods=['POST'])
    def link_account():
        """Handle link account form submission."""
        token = session.get('access_token')
        if not token:
            return redirect(url_for('index'))

        # Get profile ID
        profile_id = services.get_profile_id(token)
        if not profile_id:
            return redirect(url_for('accounts', link_error='Could not retrieve profile'))

        # Get form data
        account_name = request.form.get('account_name', 'My Account')
        broker_code = request.form.get('broker_code')
        server_code = request.form.get('server_code')
        username = request.form.get('username')
        password = request.form.get('password')

        # Validation
        if not broker_code or not server_code or not username or not password:
            return redirect(url_for('accounts', link_error='All fields are required'))

        # Build payload
        payload = {
            'name': account_name,
            'connection': {
                'brokerCode': broker_code,
                'serverCode': server_code,
                'username': username,
                'password': password
            }
        }

        # Create copier
        success, result = services.create_copier(token, profile_id, payload)

        if success:
            return redirect(url_for('accounts', link_success='Account linked successfully'))
        else:
            error_msg = result if isinstance(result, str) else 'Failed to link account'
            return redirect(url_for('accounts', link_error=error_msg))

    @app.route('/accounts/<copier_id>/unlink', methods=['POST'])
    def unlink_account(copier_id):
        """Handle unlink account request."""
        token = session.get('access_token')
        if not token:
            return redirect(url_for('index'))

        # Get profile ID
        profile_id = services.get_profile_id(token)
        if not profile_id:
            return redirect(url_for('accounts', unlink_error='Could not retrieve profile'))

        # Delete copier
        success, status_code, error = services.delete_copier(token, profile_id, copier_id)

        if success:
            return redirect(url_for('accounts', unlink_success='Account unlinked successfully'))
        else:
            error_msg = error if error else f'Failed to unlink account (status: {status_code})'
            return redirect(url_for('accounts', unlink_error=error_msg))
