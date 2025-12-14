"""
Flask routes for Copy Trade dashboard.
All HTML rendering is done via templates - no inline HTML strings.
"""

import os
import secrets
import json
from datetime import datetime
from collections import deque
from flask import render_template, redirect, request, url_for, session, make_response
from app import services

# ==========================================
# DEBUG LOGGING - In-Memory Ring Buffer
# ==========================================
# Stores last 200 copy attempts for debugging
copy_debug_logs = deque(maxlen=200)


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
    @app.context_processor
    def inject_portal_slug():
        return dict(active_portal_slug=session.get('active_portal_slug'))
    # Add custom Jinja2 filter for JSON parsing
    @app.template_filter('from_json')
    def from_json_filter(value):
        """Parse JSON string to Python object."""
        if not value:
            return {}
        try:
            return json.loads(value)
        except:
            return {}

    def format_currency(value, currency_code='USD'):
        """Format currency value with proper symbol."""
        symbols = {'USD': '$', 'EUR': '€', 'GBP': '£', 'JPY': '¥', 'AUD': 'A$', 'CAD': 'C$'}
        symbol = symbols.get(currency_code, currency_code)
        return f"{symbol}{value:,.2f}"

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
                    # Redirect to original destination if saved, otherwise to dashboard
                    next_url = session.pop('next_url', None)
                    return redirect(next_url if next_url else url_for('index'))
                else:
                    error_msg = data.get('error_description', data.get('error', 'Unknown Error'))
                    return f"Token Exchange Error: {error_msg}"

        # Check for token in session
        token = session.get('access_token')

        session.pop('active_portal_slug', None)

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

    @app.route("/debug/routes")
    def debug_routes():
        return "<br>".join(sorted(str(r) for r in app.url_map.iter_rules()))

    @app.route('/debug/copy-logs')
    def debug_copy_logs():
        """Display in-memory debug logs for copy attempts."""
        from flask import jsonify

        # Option to return JSON
        if request.args.get('format') == 'json':
            return jsonify(list(copy_debug_logs))

        # Otherwise return HTML table
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Copy Debug Logs</title>
            <style>
                body { font-family: monospace; padding: 20px; background: #f5f5f5; }
                h1 { color: #333; }
                .controls { margin-bottom: 20px; }
                .controls a {
                    padding: 8px 16px;
                    background: #2962ff;
                    color: white;
                    text-decoration: none;
                    border-radius: 4px;
                    margin-right: 10px;
                }
                .controls a:hover { opacity: 0.8; }
                table {
                    width: 100%;
                    border-collapse: collapse;
                    background: white;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
                th, td {
                    padding: 12px;
                    text-align: left;
                    border-bottom: 1px solid #ddd;
                }
                th {
                    background: #2962ff;
                    color: white;
                    position: sticky;
                    top: 0;
                }
                tr:hover { background: #f9f9f9; }
                .success { color: #155724; font-weight: bold; }
                .error { color: #721c24; font-weight: bold; }
                .modal-copy { color: #0066cc; }
                .modal-edit { color: #cc6600; }
                pre {
                    max-width: 400px;
                    overflow: auto;
                    background: #f8f8f8;
                    padding: 4px 8px;
                    border-radius: 3px;
                    font-size: 11px;
                }
                .empty {
                    text-align: center;
                    padding: 40px;
                    color: #999;
                }
            </style>
        </head>
        <body>
            <h1>🔍 Copy Debug Logs (Last 200)</h1>
            <div class="controls">
                <a href="/debug/copy-logs">Refresh</a>
                <a href="/debug/copy-logs?format=json">View as JSON</a>
                <a href="/">Back to Dashboard</a>
            </div>
        """

        if not copy_debug_logs:
            html += '<div class="empty">No copy attempts logged yet. Try copying a strategy to see debug info here.</div>'
        else:
            html += """
            <table>
                <thead>
                    <tr>
                        <th>Timestamp</th>
                        <th>Copier</th>
                        <th>Strategy</th>
                        <th>Source</th>
                        <th>Modal</th>
                        <th>Already Copying?</th>
                        <th>Action</th>
                        <th>API Success</th>
                        <th>API Result</th>
                        <th>Redirect Params</th>
                    </tr>
                </thead>
                <tbody>
            """

            # Reverse to show newest first
            for entry in reversed(list(copy_debug_logs)):
                timestamp = entry.get('timestamp', 'N/A')
                copier_id = entry.get('copier_id', 'N/A')
                strategy_id = entry.get('strategy_id', 'N/A')
                source = entry.get('source', 'N/A')
                modal_type = entry.get('modal_type', 'N/A')
                already_copying = entry.get('already_copying')
                action_path = entry.get('action_path', 'N/A')

                api_result = entry.get('api_result', {})
                api_success = api_result.get('success')
                result_summary = api_result.get('result_summary', 'N/A')

                redirect_info = entry.get('redirect', {})
                redirect_params = redirect_info.get('params', {})

                # Error handling
                if 'error' in entry:
                    error_msg = entry['error']
                    html += f"""
                    <tr>
                        <td>{timestamp}</td>
                        <td colspan="9" class="error">ERROR: {error_msg}</td>
                    </tr>
                    """
                    continue

                # Success/failure styling
                success_class = 'success' if api_success else 'error'
                success_text = '✓ TRUE' if api_success else '✗ FALSE'

                already_copying_text = '✓ Yes' if already_copying else '✗ No'
                modal_class = f'modal-{modal_type}'

                html += f"""
                <tr>
                    <td>{timestamp}</td>
                    <td>{copier_id}</td>
                    <td>{strategy_id}</td>
                    <td>{source}</td>
                    <td class="{modal_class}">{modal_type}</td>
                    <td>{already_copying_text}</td>
                    <td><strong>{action_path}</strong></td>
                    <td class="{success_class}">{success_text}</td>
                    <td><pre>{result_summary}</pre></td>
                    <td><pre>{json.dumps(redirect_params, indent=2)}</pre></td>
                </tr>
                """

            html += """
                </tbody>
            </table>
            """

        html += """
        </body>
        </html>
        """

        return html

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
        # Initialize debug log entry
        debug_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'copier_id': None,
            'strategy_id': None,
            'portal_slug': None,
            'source': None,
            'modal_type': None,
            'already_copying': None,
            'action_path': None,
            'api_result': {},
            'redirect': {}
        }

        token = session.get('access_token')
        if not token:
            debug_entry['error'] = 'No access token'
            copy_debug_logs.append(debug_entry)
            return redirect(url_for('index'))

        # Get form data
        copier_id = request.form.get('copier_id')
        strategy_id = request.form.get('strategy_id')
        strategy_name = request.form.get('strategy_name', 'Strategy')
        trade_size_type = request.form.get('trade_size_type')
        trade_size_value = request.form.get('trade_size_value')
        is_open_existing = request.form.get('is_open_existing') == 'on'
        is_round_up = request.form.get('is_round_up') == 'on'
        source = request.form.get('source', 'dashboard')  # 'dashboard', 'copying', or 'portal'
        portal_slug = request.form.get('portal_slug')  # For portal tracking
        modal_type = request.form.get('modal_type', 'copy')  # 'copy' or 'edit'

        # Update debug entry
        debug_entry.update({
            'copier_id': copier_id,
            'strategy_id': strategy_id,
            'portal_slug': portal_slug,
            'source': source,
            'modal_type': modal_type
        })

        # Validation
        if not copier_id or not strategy_id:
            error_msg = 'Missing account or strategy'
            debug_entry['error'] = 'Validation failed: ' + error_msg
            debug_entry['redirect'] = {
                'url': f'{source} page',
                'params': {'copy_error': error_msg, 'modal': modal_type}
            }
            copy_debug_logs.append(debug_entry)

            if source == 'portal' and portal_slug:
                return redirect(url_for('portal_view', slug=portal_slug, copy_error=error_msg, modal=modal_type))
            elif source == 'copying':
                return redirect(url_for('copying', copy_error=error_msg, modal=modal_type))
            else:
                return redirect(url_for('index', copy_error=error_msg, modal=modal_type))

        # Build settings payload
        settings = {
            'tradeSizeType': trade_size_type,
            'tradeSizeValue': float(trade_size_value) if trade_size_value else 1.0,
            'isOpenExistingTrades': is_open_existing,
            'isRoundUpToMinimumSize': is_round_up
        }

        # Detect if already copying (GET first)
        copy_settings, status_code = services.get_copy_settings(copier_id, strategy_id, token)
        debug_entry['already_copying'] = (status_code == 200)

        # Determine action and execute API call
        if status_code == 200:
            # Already copying - use PUT
            debug_entry['action_path'] = 'UPDATE_COPY'
            api_success, api_result = services.update_copy_settings(copier_id, strategy_id, token, settings)
            success_msg = 'Copy settings updated successfully'
            error_msg_base = 'Failed to update copy settings'
        else:
            # Not copying yet - use POST
            debug_entry['action_path'] = 'CREATE_COPY'
            api_success, api_result = services.create_copy_settings(copier_id, strategy_id, token, settings)
            success_msg = 'Copy started successfully'
            error_msg_base = 'Failed to start copying'

        # CRITICAL: Do not overwrite api_success - it is the source of truth
        # Record API result in debug log
        debug_entry['api_result'] = {
            'success': api_success,
            'result_summary': str(api_result)[:200] if api_result is not None else None
        }

        # Build final messages
        if api_success:
            final_message = success_msg
        else:
            # Add error details if available
            error_detail = str(api_result)[:200] if api_result else 'Unknown error'
            final_message = f'{error_msg_base} - {error_detail}'

        # Track successful copies from portals
        if api_success and source == 'portal' and portal_slug:
            from app.models import Portal, db

            portal = Portal.query.filter_by(slug=portal_slug).first()
            if portal:
                # Increment successful copies counter
                portal.successful_copies += 1
                portal.last_copied_at = datetime.utcnow()

                # PortalEvent tracking disabled to fix IntegrityError - re-enable later
                # from app.models import PortalEvent
                # profile_id = services.get_profile_id(token)
                # if profile_id:
                #     now_utc = datetime.utcnow()
                #     copy_event = PortalEvent(
                #         portal_id=portal.id,
                #         event_type='copy_success',
                #         profile_id=profile_id,
                #         copier_id=copier_id,
                #         occurred_at=now_utc,
                #         event_day=now_utc.date()
                #     )
                #     db.session.add(copy_event)

                db.session.commit()

        # Build redirect with explicit modal targeting
        if source == 'copying':
            if api_success:
                redirect_url = url_for('copying', copy_success=final_message, modal=modal_type)
            else:
                redirect_url = url_for('copying', copy_error=final_message, modal=modal_type)
        elif source == 'portal' and portal_slug:
            if api_success:
                redirect_url = url_for('portal_view', slug=portal_slug, copier_id=copier_id,
                                      copy_success=final_message, modal=modal_type)
            else:
                redirect_url = url_for('portal_view', slug=portal_slug, copier_id=copier_id,
                                      copy_error=final_message, modal=modal_type)
        else:
            # Dashboard
            if api_success:
                redirect_url = url_for('index', copier_id=copier_id, copy_success=final_message, modal=modal_type)
            else:
                redirect_url = url_for('index', copier_id=copier_id, copy_error=final_message, modal=modal_type)

        # Log final redirect decision
        debug_entry['redirect'] = {
            'url': redirect_url,
            'params': {
                'copy_success' if api_success else 'copy_error': final_message,
                'modal': modal_type
            }
        }

        # Append to debug logs
        copy_debug_logs.append(debug_entry)

        return redirect(redirect_url)

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

    # ==========================================
    # AUTHENTICATED PORTAL ROUTES
    # ==========================================

    @app.route('/p/<slug>')
    def portal_view(slug):
        """
        Authenticated portal view - displays specific strategy with full functionality.

        Requires authentication via existing OAuth flow.
        Provides same features as main dashboard: copy, link/unlink accounts, signals.
        Uses session['access_token'] same as all other authenticated routes.
        """
        from app.models import Portal, db

        # Fetch active portal
        portal = Portal.query.filter_by(slug=slug, is_active=True).first()
        if not portal:
            return render_template('404.html'), 404

        # Check authentication - redirect to login if not authenticated
        token = session.get('access_token')
        if not token:
            # Save the requested URL to redirect back after login
            session['next_url'] = request.url
            return redirect(url_for('login'))  # Initiate OAuth flow
        session['active_portal_slug'] = slug

        # Track portal view - PortalEvent disabled to fix IntegrityError, re-enable later
        profile_id = services.get_profile_id(token)
        if profile_id:
            from datetime import datetime
            now_utc = datetime.utcnow()

            # PortalEvent tracking disabled - just update Portal counters
            # from app.models import PortalEvent
            # from sqlalchemy.exc import IntegrityError
            # today_utc = now_utc.date()
            # view_event = PortalEvent(
            #     portal_id=portal.id,
            #     event_type='view',
            #     profile_id=profile_id,
            #     occurred_at=now_utc,
            #     event_day=today_utc
            # )
            # try:
            #     db.session.add(view_event)
            #     db.session.flush()
            #     portal.total_views += 1
            # except IntegrityError:
            #     db.session.rollback()

            # Update Portal counters directly (without event deduplication for now)
            portal.total_views += 1
            portal.last_viewed_at = now_utc
            db.session.commit()

        # Fetch user profile and accounts (needed for copy functionality)
        profile_info = services.get_profile_info(token)
        accounts_list = services.get_accounts_list(token)

        # Fetch strategy data using authenticated user's token
        strategy_data = services.get_strategy_by_id(portal.profile_id, portal.strategy_id, token)

        # Handle unauthorized (expired token, etc.)
        if strategy_data.get('unauthorized'):
            session.pop('access_token', None)  # Clear invalid token
            session['next_url'] = request.url
            return redirect(url_for('index'))

        # Parse theme configuration
        theme = json.loads(portal.theme_json) if portal.theme_json else {}
        theme.setdefault('headline', strategy_data.get('name', 'Trading Strategy'))
        theme.setdefault('subheadline', f"Trading since {strategy_data.get('inception_date', 'N/A')}")
        theme.setdefault('cta_text', 'Start Copying')
        theme.setdefault('cta_url', '#')
        theme.setdefault('visible_sections', {'overview': True, 'signals': True, 'trades': True})

        # Get selected copier from query params (for account selector)
        selected_copier_id = request.args.get('copier_id')

        # Check if selected account is copying this strategy
        is_copying = False
        copy_settings = None
        if selected_copier_id:
            copy_settings, status_code = services.get_copy_settings(
                selected_copier_id, portal.strategy_id, token
            )
            is_copying = (status_code == 200 and copy_settings is not None)

        # Fetch signals
        open_signals = []
        closed_signals = []
        closed_trades_range = request.args.get('range', '30d')

        if theme['visible_sections'].get('signals'):
            open_signals = services.get_strategy_open_signals(portal.strategy_id, token)

        if theme['visible_sections'].get('trades'):
            from datetime import datetime, timedelta
            end_dt = datetime.utcnow()
            days = 30 if closed_trades_range == '30d' else 7
            start_dt = end_dt - timedelta(days=days)
            start_dt_iso = start_dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
            end_dt_iso = end_dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
            closed_signals = services.get_strategy_closed_signals(portal.strategy_id, token, start_dt_iso, end_dt_iso)

        # Compute closed trade stats
        closed_trades_stats = services.compute_closed_trades_stats(closed_signals)

        fee_display = f"{strategy_data['performance_fee']:.1f}%" if strategy_data['performance_fee'] > 0 else "None"

        # Render portal template (authenticated, no-cache headers)
        response = make_response(render_template(
            'portal.html',
            portal=portal,
            theme=theme,
            profile_info=profile_info,
            accounts_list=accounts_list,
            strategy=strategy_data,
            strategy_id=portal.strategy_id,
            fee_display=fee_display,
            inception_display=strategy_data.get('inception_date', 'N/A'),
            open_signals=open_signals,
            closed_signals=closed_signals,
            closed_trades_range=closed_trades_range,
            closed_trades_stats=closed_trades_stats,
            selected_copier_id=selected_copier_id,
            is_copying=is_copying,
            copy_settings=copy_settings,
            format_currency=format_currency
        ))
        return add_no_cache_headers(response)

    # ==========================================
    # ADMIN ROUTES
    # ==========================================

    def require_admin():
        """Check admin authentication."""
        if not session.get('admin_authenticated'):
            return redirect(url_for('admin_login'))
        return None

    @app.route('/admin/login', methods=['GET', 'POST'])
    def admin_login():
        """Admin login page."""
        if request.method == 'POST':
            password = request.form.get('password')
            admin_password = os.environ.get('ADMIN_PASSWORD')

            if not admin_password:
                return "Admin not configured", 500

            if password == admin_password:
                session['admin_authenticated'] = True
                session.permanent = True
                return redirect(url_for('admin_portals'))
            else:
                return render_template('admin_login.html', error="Invalid password")

        if session.get('admin_authenticated'):
            return redirect(url_for('admin_portals'))

        return render_template('admin_login.html')

    @app.route('/admin/logout')
    def admin_logout():
        """Admin logout."""
        session.pop('admin_authenticated', None)
        return redirect(url_for('admin_login'))

    @app.route('/admin/portals')
    def admin_portals():
        """List all portals."""
        auth_check = require_admin()
        if auth_check:
            return auth_check

        from app.models import Portal, db
        portals = Portal.query.order_by(Portal.created_at.desc()).all()
        response = make_response(render_template('admin_portals.html', portals=portals))
        return add_no_cache_headers(response)

    @app.route('/admin/portals/create', methods=['GET', 'POST'])
    def admin_portal_create():
        """Create new portal."""
        auth_check = require_admin()
        if auth_check:
            return auth_check

        from app.models import Portal, db

        if request.method == 'POST':
            slug = secrets.token_urlsafe(32)  # 256 bits entropy, ~43 chars

            visible_sections = {
                'overview': request.form.get('visible_overview') == 'on',
                'signals': request.form.get('visible_signals') == 'on',
                'trades': request.form.get('visible_trades') == 'on'
            }

            theme = {
                'headline': request.form.get('headline', ''),
                'subheadline': request.form.get('subheadline', ''),
                'cta_text': request.form.get('cta_text', ''),
                'cta_url': request.form.get('cta_url', ''),
                'visible_sections': visible_sections
            }

            portal = Portal(
                name=request.form.get('name'),
                slug=slug,
                profile_id=request.form.get('profile_id'),
                strategy_id=request.form.get('strategy_id'),
                is_active=request.form.get('is_active') == 'on',
                theme_json=json.dumps(theme)
            )

            db.session.add(portal)
            db.session.commit()

            return redirect(url_for('admin_portals'))

        response = make_response(render_template('admin_portal_form.html', portal=None))
        return add_no_cache_headers(response)

    @app.route('/admin/portals/<int:portal_id>/edit', methods=['GET', 'POST'])
    def admin_portal_edit(portal_id):
        """Edit existing portal."""
        auth_check = require_admin()
        if auth_check:
            return auth_check

        from app.models import Portal, db
        portal = Portal.query.get_or_404(portal_id)

        # Ensure theme_json is never None (for portals created before default was added)
        if portal.theme_json is None:
            portal.theme_json = '{}'

        if request.method == 'POST':
            visible_sections = {
                'overview': request.form.get('visible_overview') == 'on',
                'signals': request.form.get('visible_signals') == 'on',
                'trades': request.form.get('visible_trades') == 'on'
            }

            theme = {
                'headline': request.form.get('headline', ''),
                'subheadline': request.form.get('subheadline', ''),
                'cta_text': request.form.get('cta_text', ''),
                'cta_url': request.form.get('cta_url', ''),
                'visible_sections': visible_sections
            }

            portal.name = request.form.get('name')
            portal.profile_id = request.form.get('profile_id')
            portal.strategy_id = request.form.get('strategy_id')
            portal.is_active = request.form.get('is_active') == 'on'
            portal.theme_json = json.dumps(theme)

            db.session.commit()
            return redirect(url_for('admin_portals'))

        response = make_response(render_template('admin_portal_form.html', portal=portal))
        return add_no_cache_headers(response)

    @app.route('/admin/portals/<int:portal_id>/delete', methods=['POST'])
    def admin_portal_delete(portal_id):
        """Delete portal."""
        auth_check = require_admin()
        if auth_check:
            return auth_check

        from app.models import Portal, db
        portal = Portal.query.get_or_404(portal_id)
        db.session.delete(portal)
        db.session.commit()
        return redirect(url_for('admin_portals'))

    @app.route('/admin/portals/<int:portal_id>/toggle', methods=['POST'])
    def admin_portal_toggle(portal_id):
        """Toggle portal active status."""
        auth_check = require_admin()
        if auth_check:
            return auth_check

        from app.models import Portal, db
        portal = Portal.query.get_or_404(portal_id)
        portal.is_active = not portal.is_active
        db.session.commit()
        return redirect(url_for('admin_portals'))
