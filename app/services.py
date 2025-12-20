"""
Business logic and API services for Copy Trade application.
All functions are pure - they take parameters and return data structures.
No Flask dependencies or session handling.
"""

import requests
import secrets
import hashlib
import base64
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================
# CONFIGURATION
# ==========================================
API_BASE_URL = 'https://papi.copy-trade.io'
IDENTITY_URL = 'https://identity.copy-trade.io'
CLIENT_ID = 'api-client'
TENANT_ID = 'pepperstone'
WHITE_LABEL_ID = 'pepperstone'

# Request timeout in seconds - fail fast rather than hang
REQUEST_TIMEOUT = (10, 60)

# Short timeout for summary/count calls (parallel fetches)
SUMMARY_REQUEST_TIMEOUT = 2

# Thread pool size for parallel fetches
MAX_PARALLEL_WORKERS = 10

# ==========================================
# IN-MEMORY CACHE
# ==========================================
# Simple cache for open positions summary
# Format: { profile_id: { 'timestamp': float, 'data': [...] } }
_open_positions_cache = {}
OPEN_POSITIONS_CACHE_TTL = 15  # seconds


def generate_pkce():
    """
    Generate PKCE verifier and challenge for OAuth2 authentication.

    Returns:
        tuple: (verifier, challenge) - Both are URL-safe base64 encoded strings
    """
    verifier = secrets.token_urlsafe(32)
    m = hashlib.sha256()
    m.update(verifier.encode('ascii'))
    challenge = base64.urlsafe_b64encode(m.digest()).decode('ascii').replace('=', '')
    return verifier, challenge


def exchange_code_for_token(code, verifier, redirect_uri):
    """
    Exchange authorization code for access token.

    Args:
        code: Authorization code from OAuth callback
        verifier: PKCE verifier from session
        redirect_uri: Redirect URI used in auth request

    Returns:
        dict: Token response data or error dict
    """
    payload = {
        'client_id': CLIENT_ID,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
        'code_verifier': verifier
    }
    r = requests.post(f"{IDENTITY_URL}/connect/token", data=payload)
    return r.json()


def get_profile_info(token):
    """
    Fetch profile information including name and account counts.

    Args:
        token: Access token for API authentication

    Returns:
        dict: Profile data with name, strategies_count, copiers_count
              None if request fails
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    try:
        # 1. Get userinfo to extract profile ID
        resp = requests.get(f"{IDENTITY_URL}/connect/userinfo", headers=headers)
        if resp.status_code != 200:
            return None

        userinfo = resp.json()
        profile_id = userinfo.get('https://copy-trade.io/profile')

        if not profile_id:
            return None

        # 2. Get profile details
        resp = requests.get(f"{API_BASE_URL}/api/profiles/{profile_id}", headers=headers)
        if resp.status_code != 200:
            return None

        profile_data = resp.json()

        # 3. Get strategies count
        resp = requests.get(f"{API_BASE_URL}/api/profiles/{profile_id}/strategies", headers=headers)
        strategies_count = len(resp.json()) if resp.status_code == 200 else 0

        # 4. Get copiers count
        resp = requests.get(f"{API_BASE_URL}/api/profiles/{profile_id}/copiers", headers=headers)
        copiers_count = len(resp.json()) if resp.status_code == 200 else 0

        return {
            'name': profile_data.get('Name', 'User'),
            'strategies_count': strategies_count,
            'copiers_count': copiers_count
        }
    except Exception:
        return None


def get_accounts_list(token):
    """
    Get list of all copier accounts for the authenticated user.

    Args:
        token: Access token for API authentication

    Returns:
        list: List of account dicts with id, name, server, username, enabled, type
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    accounts_list = []
    try:
        # Get profile ID first
        resp = requests.get(f"{IDENTITY_URL}/connect/userinfo", headers=headers)
        if resp.status_code == 200:
            userinfo = resp.json()
            profile_id = userinfo.get('https://copy-trade.io/profile')

            if profile_id:
                # Get all copiers (MetaTrader accounts that copy)
                resp = requests.get(f"{API_BASE_URL}/api/profiles/{profile_id}/copiers", headers=headers)
                if resp.status_code == 200:
                    copiers_data = resp.json()
                    for copier in copiers_data:
                        accounts_list.append({
                            'id': copier.get('Id'),
                            'name': copier.get('Name'),
                            'server': copier.get('Connection', {}).get('ServerCode', 'N/A'),
                            'username': copier.get('Connection', {}).get('Username', 'N/A'),
                            'enabled': copier.get('IsEnabled', True),
                            'type': 'copier'
                        })
    except Exception:
        pass  # Return empty list on error

    return accounts_list


def get_top_strategy(token):
    """
    Get the #1 top strategy from discover endpoint.

    Args:
        token: Access token for API authentication

    Returns:
        dict: Strategy data with all metrics, or default values on error
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    endpoint = f"{API_BASE_URL}/api/discover/Strategies"
    params = {"wl": WHITE_LABEL_ID}

    # Default values
    result = {
        'name': 'Unknown',
        'copiers': 0,
        'return_val': 0.0,
        'strategy_id': None,
        'inception_date': None,
        'performance_fee': 0.0,
        'total_trades': 0,
        'min_per_month': 0,
        'max_per_month': 0,
        'wins': 0,
        'losses': 0,
        'win_rate': 0,
        'realised_pnl': 0,
        'unrealised_pnl': 0,
        'max_drawdown': 0,
        'balance': 0,
        'equity': 0,
        'credit': 0,
        'leverage': 0,
        'copiers_year_profit': 0,
        'copiers_month_profit': 0,
        'copiers_total_balance': 0,
        'currency_code': 'USD',
        'unauthorized': False
    }

    try:
        resp = requests.get(endpoint, headers=headers, params=params)

        # If token is invalid/expired, signal to caller
        if resp.status_code == 401:
            result['unauthorized'] = True
            return result

        if resp.status_code == 200:
            data = resp.json()
            if data and len(data) > 0:
                top_item = data[0]

                raw_val = top_item.get('Value', 0)
                result['return_val'] = raw_val * 100

                strategy = top_item.get('Strategy', {})
                result['name'] = strategy.get('Name', 'Unknown')
                result['copiers'] = strategy.get('NumCopiers', 0)
                result['strategy_id'] = strategy.get('Id')

                # Get detailed strategy info
                if result['strategy_id']:
                    strategy_detail = get_strategy_detail(token, result['strategy_id'])
                    if strategy_detail:
                        result.update(strategy_detail)

    except Exception as e:
        result['name'] = "Connection Error"

    return result


def get_strategy_detail(token, strategy_id):
    """
    Get detailed strategy information including fee and stats.

    Args:
        token: Access token for API authentication
        strategy_id: Strategy ID to fetch details for

    Returns:
        dict: Detailed strategy metrics or None on error
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    detail = {}

    try:
        # Get performance fee
        detail_resp = requests.get(
            f"{API_BASE_URL}/api/strategies/{strategy_id}",
            headers=headers
        )
        if detail_resp.status_code == 200:
            strategy_detail = detail_resp.json()
            fee = strategy_detail.get('Fee')
            detail['performance_fee'] = (fee * 100) if fee is not None else 0.0

        # Get detailed stats
        stats_resp = requests.get(
            f"{API_BASE_URL}/api/strategies/{strategy_id}/stats",
            headers=headers,
            params={'wl': WHITE_LABEL_ID}
        )
        if stats_resp.status_code == 200:
            stats_data = stats_resp.json()

            # Extract inception date
            inception_str = stats_data.get('Inception')
            if inception_str:
                inception_dt = datetime.fromisoformat(inception_str.replace('Z', '+00:00'))
                detail['inception_date'] = inception_dt.strftime('%B %d, %Y')

            # Extract trade statistics
            trades_data = stats_data.get('Trades', {}).get('Inception', {})
            detail['total_trades'] = trades_data.get('Total', 0)
            detail['min_per_month'] = trades_data.get('MinPerMonth', 0)
            detail['max_per_month'] = trades_data.get('MaxPerMonth', 0)
            detail['wins'] = trades_data.get('Wins', 0)
            detail['losses'] = trades_data.get('Losses', 0)

            # Calculate win rate
            if detail['total_trades'] > 0:
                detail['win_rate'] = (detail['wins'] / detail['total_trades']) * 100
            else:
                detail['win_rate'] = 0

            # Extract profitability statistics
            profitability_data = stats_data.get('Profitability', {}).get('Inception', {})
            detail['realised_pnl'] = profitability_data.get('RealisedPnl', 0)
            detail['unrealised_pnl'] = profitability_data.get('UnrealisedPnl', 0)
            detail['max_drawdown'] = abs(profitability_data.get('MaxDrawdown', 0)) * 100

            # Extract account status
            status_data = stats_data.get('Status', {})
            detail['balance'] = status_data.get('Balance', 0)
            detail['credit'] = status_data.get('Credit', 0)
            detail['leverage'] = status_data.get('Leverage', 0)

            # Calculate equity
            detail['equity'] = detail['balance'] + detail['unrealised_pnl']

            # Extract copiers performance
            copiers_profit_data = stats_data.get('CopiersProfit', {})
            detail['copiers_year_profit'] = copiers_profit_data.get('Year', 0)
            detail['copiers_month_profit'] = copiers_profit_data.get('Month', 0)

            copiers_balance_data = stats_data.get('CopiersBalance', {})
            detail['copiers_total_balance'] = copiers_balance_data.get('Balance', 0)

            detail['currency_code'] = stats_data.get('CurrencyCode', 'USD')

        return detail

    except Exception:
        return None


def get_copiers_with_stats(token):
    """
    Get all copier accounts with their detailed statistics.

    Args:
        token: Access token for API authentication

    Returns:
        tuple: (profile_name, copiers_list) where copiers_list contains account details
               Returns (None, None) on error
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    try:
        # 1. Get profile ID
        resp = requests.get(f"{IDENTITY_URL}/connect/userinfo", headers=headers)
        if resp.status_code != 200:
            return None, None

        userinfo = resp.json()
        profile_id = userinfo.get('https://copy-trade.io/profile')

        if not profile_id:
            return None, None

        # 2. Get profile details
        resp = requests.get(f"{API_BASE_URL}/api/profiles/{profile_id}", headers=headers)
        profile_data = resp.json() if resp.status_code == 200 else {}
        profile_name = profile_data.get('Name', 'User')

        # 3. Get all copiers
        resp = requests.get(f"{API_BASE_URL}/api/profiles/{profile_id}/copiers", headers=headers)
        if resp.status_code != 200:
            return None, None

        copiers = resp.json()

        # 4. Fetch stats for each copier
        copiers_with_stats = []

        for copier in copiers:
            copier_id = copier['Id']
            stats_resp = requests.get(f"{API_BASE_URL}/api/copiers/{copier_id}/stats", headers=headers)

            stats = {}
            if stats_resp.status_code == 200:
                stats_data = stats_resp.json()

                # Extract with correct PascalCase field names
                status_obj = stats_data.get('Status', {})
                profitability_obj = stats_data.get('Profitability', {}).get('Inception', {})
                history = profitability_obj.get('History', [])

                balance = status_obj.get('Balance', 0)
                leverage = status_obj.get('Leverage')
                unrealised_pnl = profitability_obj.get('UnrealisedPnl', 0)
                realised_return = profitability_obj.get('RealisedReturn', 0)
                max_drawdown = profitability_obj.get('MaxDrawdown', 0)

                # Get most recent return from history (last item)
                latest_return = history[-1]['AccountReturn'] if history else realised_return

                equity = balance + unrealised_pnl

                stats = {
                    'balance': balance,
                    'equity': equity,
                    'leverage': leverage,
                    'return_pct': latest_return * 100,  # Convert to percentage
                    'drawdown_pct': max_drawdown * 100,  # Convert to percentage
                    'currency': stats_data.get('CurrencyCode', 'USD')
                }

            copiers_with_stats.append({
                'id': copier['Id'],
                'name': copier['Name'],
                'enabled': copier['IsEnabled'],
                'server': copier.get('Connection', {}).get('ServerCode', 'N/A'),
                'username': copier.get('Connection', {}).get('Username', 'N/A'),
                'stats': stats
            })

        return profile_name, copiers_with_stats

    except Exception as e:
        return None, None


def format_currency(value, code="USD"):
    """
    Format a numeric value as currency with appropriate symbol.

    Args:
        value: Numeric value to format
        code: Currency code (default: USD)

    Returns:
        str: Formatted currency string
    """
    symbol = "$" if code == "USD" else code
    return f"{symbol}{value:,.2f}"


def format_trade_sizing(size_type, size_value):
    """
    Format trade sizing for display, matching the modal dropdown labels exactly.

    Labels must match the copy/edit modal options:
    - Fixed → "Fixed (X.XX)"
    - MirrorSize → "Mirror Size (X.XXx)"
    - MirrorRiskByEquity → "Mirror Risk by Equity (X.XXx)"
    - MirrorRiskByBalance → "Mirror Risk by Balance (X.XXx)"

    Args:
        size_type: Trade size type string (e.g., 'Fixed', 'MirrorSize')
        size_value: Trade size value (numeric)

    Returns:
        str: Formatted trade sizing string
    """
    if size_type is None:
        return "-"

    # Ensure size_value is a float
    try:
        value = float(size_value) if size_value is not None else 1.0
    except (TypeError, ValueError):
        value = 1.0

    # Map API values to display labels (must match modal dropdown options)
    type_labels = {
        'Fixed': 'Fixed',
        'MirrorSize': 'Mirror Size',
        'MirrorRiskByEquity': 'Mirror Risk by Equity',
        'MirrorRiskByBalance': 'Mirror Risk by Balance'
    }

    label = type_labels.get(size_type, size_type)

    # Fixed shows just the value, others show value with 'x' suffix (multiplier)
    if size_type == 'Fixed':
        return f"{label} ({value:.2f})"
    else:
        return f"{label} ({value:.2f}x)"


def compute_closed_trades_stats(closed_signals):
    """
    Compute summary statistics for closed trades.

    Args:
        closed_signals: List of closed signal dicts with RealisedProfit and Instrument fields

    Returns:
        dict: Statistics including trades_count, wins_count, losses_count,
              win_rate_pct, total_realised_pnl, avg_realised_pnl,
              most_common_symbol, biggest_win, biggest_loss
    """
    if not closed_signals:
        return {
            'trades_count': 0,
            'wins_count': 0,
            'losses_count': 0,
            'win_rate_pct': 0.0,
            'total_realised_pnl': 0.0,
            'avg_realised_pnl': 0.0,
            'most_common_symbol': None,
            'biggest_win': 0.0,
            'biggest_loss': 0.0
        }

    trades_count = len(closed_signals)
    pnl_values = [signal.get('RealisedProfit', 0.0) for signal in closed_signals]

    wins = [pnl for pnl in pnl_values if pnl > 0]
    losses = [pnl for pnl in pnl_values if pnl < 0]

    wins_count = len(wins)
    losses_count = len(losses)
    win_rate_pct = (wins_count / trades_count * 100) if trades_count > 0 else 0.0

    total_realised_pnl = sum(pnl_values)
    avg_realised_pnl = total_realised_pnl / trades_count if trades_count > 0 else 0.0

    # Find most common symbol
    symbols = [signal.get('Instrument', '') for signal in closed_signals if signal.get('Instrument')]
    most_common_symbol = None
    if symbols:
        from collections import Counter
        symbol_counts = Counter(symbols)
        most_common_symbol = symbol_counts.most_common(1)[0][0]

    biggest_win = max(pnl_values) if pnl_values else 0.0
    biggest_loss = min(pnl_values) if pnl_values else 0.0

    return {
        'trades_count': trades_count,
        'wins_count': wins_count,
        'losses_count': losses_count,
        'win_rate_pct': win_rate_pct,
        'total_realised_pnl': total_realised_pnl,
        'avg_realised_pnl': avg_realised_pnl,
        'most_common_symbol': most_common_symbol,
        'biggest_win': biggest_win,
        'biggest_loss': biggest_loss
    }


def build_auth_url(redirect_uri, challenge):
    """
    Build OAuth authorization URL with PKCE challenge.

    Args:
        redirect_uri: Callback URI for OAuth flow
        challenge: PKCE challenge string

    Returns:
        str: Complete authorization URL
    """
    auth_url = (
        f"{IDENTITY_URL}/connect/authorize"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={redirect_uri}"
        f"&scope=openid%20profile%20email%20api%20copytrade%20offline_access"
        f"&code_challenge={challenge}"
        f"&code_challenge_method=S256"
        f"&acr_values=tenant:{TENANT_ID}%20sign_up:true"
        f"&screen_hint=sign_up"
    )
    return auth_url


def build_logout_url(redirect_uri):
    """
    Build logout URL for identity provider.

    Args:
        redirect_uri: Where to redirect after logout

    Returns:
        str: Complete logout URL
    """
    return f"{IDENTITY_URL}/connect/endsession?post_logout_redirect_uri={redirect_uri}?logged_out=1"


def get_open_signals(copier_id, token):
    """
    Get open signals (positions) for a specific copier account.

    Args:
        copier_id: Copier account ID
        token: Access token for API authentication

    Returns:
        list: List of open signal dicts, or empty list on error
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    try:
        resp = requests.get(
            f"{API_BASE_URL}/api/copiers/{copier_id}/signals/open",
            headers=headers
        )
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception:
        return []


def get_closed_signals(copier_id, token, start_dt_iso, end_dt_iso):
    """
    Get closed signals (historical trades) for a specific copier account.

    Args:
        copier_id: Copier account ID
        token: Access token for API authentication
        start_dt_iso: Start date-time in ISO 8601 format
        end_dt_iso: End date-time in ISO 8601 format

    Returns:
        list: List of closed signal dicts, or empty list on error
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    try:
        params = {
            'startDate': start_dt_iso,
            'endDate': end_dt_iso
        }
        resp = requests.get(
            f"{API_BASE_URL}/api/copiers/{copier_id}/signals/closed",
            headers=headers,
            params=params
        )
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception:
        return []


def get_strategy_open_signals(strategy_id, token):
    """
    Get open signals (positions) for a specific strategy account.

    Args:
        strategy_id: Strategy account ID
        token: Access token for API authentication

    Returns:
        list: List of open signal dicts, or empty list on error
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    try:
        resp = requests.get(
            f"{API_BASE_URL}/api/strategies/{strategy_id}/signals/open",
            headers=headers
        )
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception:
        return []


def get_strategy_closed_signals(strategy_id, token, start_dt_iso, end_dt_iso):
    """
    Get closed signals (historical trades) for a specific strategy account.

    Args:
        strategy_id: Strategy account ID
        token: Access token for API authentication
        start_dt_iso: Start date-time in ISO 8601 format
        end_dt_iso: End date-time in ISO 8601 format

    Returns:
        list: List of closed signal dicts, or empty list on error
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    try:
        params = {
            'startDate': start_dt_iso,
            'endDate': end_dt_iso
        }
        resp = requests.get(
            f"{API_BASE_URL}/api/strategies/{strategy_id}/signals/closed",
            headers=headers,
            params=params
        )
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception:
        return []


def get_copier_open_signals(copier_id, token):
    """
    Get open signals (current positions) for a specific copier account.

    Args:
        copier_id: Copier account ID
        token: Access token for API authentication

    Returns:
        list: List of open signal dicts, or empty list on error
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    try:
        resp = requests.get(
            f"{API_BASE_URL}/api/copiers/{copier_id}/signals/open",
            headers=headers,
            timeout=REQUEST_TIMEOUT
        )
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception:
        return []


def get_copier_closed_signals(copier_id, token, start_dt_iso, end_dt_iso):
    """
    Get closed signals (historical trades) for a specific copier account.

    Args:
        copier_id: Copier account ID
        token: Access token for API authentication
        start_dt_iso: Start date-time in ISO 8601 format
        end_dt_iso: End date-time in ISO 8601 format

    Returns:
        list: List of closed signal dicts, or empty list on error
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    try:
        params = {
            'startDate': start_dt_iso,
            'endDate': end_dt_iso
        }
        resp = requests.get(
            f"{API_BASE_URL}/api/copiers/{copier_id}/signals/closed",
            headers=headers,
            params=params,
            timeout=REQUEST_TIMEOUT
        )
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception:
        return []


def _get_copier_open_count(copier_id, token):
    """
    Get just the count of open positions for a copier (lightweight).

    Uses short timeout for parallel fetches. Returns 0 on any error.

    Args:
        copier_id: Copier account ID
        token: Access token for API authentication

    Returns:
        int: Number of open positions, or 0 on error
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    try:
        resp = requests.get(
            f"{API_BASE_URL}/api/copiers/{copier_id}/signals/open",
            headers=headers,
            timeout=SUMMARY_REQUEST_TIMEOUT
        )
        if resp.status_code == 200:
            signals = resp.json()
            return len(signals) if isinstance(signals, list) else 0
        return 0
    except Exception:
        return 0


def get_open_positions_summary_for_profile(profile_id, token, copiers_list):
    """
    Get open positions count for all copiers in a profile, with caching.

    Uses parallel fetching with ThreadPoolExecutor for speed.
    Results are cached for 15 seconds per profile_id.

    Args:
        profile_id: Profile ID (used as cache key)
        token: Access token for API authentication
        copiers_list: List of copier dicts from get_accounts_list()

    Returns:
        dict: {
            'copiers_with_positions': [
                {'copier_id': str, 'name': str, 'server_code': str, 'username': str, 'open_count': int},
                ...
            ],
            'total_copiers_with_positions': int,
            'total_open_positions': int,
            'cached': bool,
            'timestamp': float
        }
    """
    global _open_positions_cache

    current_time = time.time()

    # Check cache
    if profile_id in _open_positions_cache:
        cached = _open_positions_cache[profile_id]
        if current_time - cached['timestamp'] < OPEN_POSITIONS_CACHE_TTL:
            # Return cached data with flag
            return {
                **cached['data'],
                'cached': True
            }

    # Not cached or stale - fetch fresh data
    if not copiers_list:
        result = {
            'copiers_with_positions': [],
            'total_copiers_with_positions': 0,
            'total_open_positions': 0,
            'cached': False,
            'timestamp': current_time
        }
        _open_positions_cache[profile_id] = {'timestamp': current_time, 'data': result}
        return result

    # Prepare copier info for parallel fetch
    copier_info_map = {}
    for copier in copiers_list:
        copier_id = str(copier.get('id', ''))
        if copier_id:
            copier_info_map[copier_id] = {
                'copier_id': copier_id,
                'name': copier.get('name', 'Unknown'),
                'server_code': copier.get('server', 'N/A'),
                'username': copier.get('username', 'N/A')
            }

    # Parallel fetch open counts
    copier_counts = {}

    def fetch_count(copier_id):
        return copier_id, _get_copier_open_count(copier_id, token)

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
        futures = {executor.submit(fetch_count, cid): cid for cid in copier_info_map.keys()}

        for future in as_completed(futures):
            try:
                copier_id, count = future.result()
                copier_counts[copier_id] = count
            except Exception:
                # On any error, treat as 0
                copier_id = futures[future]
                copier_counts[copier_id] = 0

    # Build result list - only include copiers with open positions
    copiers_with_positions = []
    total_open = 0

    for copier_id, info in copier_info_map.items():
        count = copier_counts.get(copier_id, 0)
        total_open += count
        if count > 0:
            copiers_with_positions.append({
                **info,
                'open_count': count
            })

    # Sort by open_count descending
    copiers_with_positions.sort(key=lambda x: x['open_count'], reverse=True)

    result = {
        'copiers_with_positions': copiers_with_positions,
        'total_copiers_with_positions': len(copiers_with_positions),
        'total_open_positions': total_open,
        'cached': False,
        'timestamp': current_time
    }

    # Update cache
    _open_positions_cache[profile_id] = {'timestamp': current_time, 'data': result}

    return result


def get_copy_settings(copier_id, strategy_id, token):
    """
    Get copy settings for a copier/strategy pair.

    Args:
        copier_id: Copier account ID
        strategy_id: Strategy account ID
        token: Access token for API authentication

    Returns:
        tuple: (copy_settings dict or None, status_code)
               Returns (None, 404) if not copying
               Returns (settings, 200) if copying
               Returns (None, 0) on error
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    try:
        resp = requests.get(
            f"{API_BASE_URL}/api/copiers/{copier_id}/strategies/{strategy_id}/copy-settings",
            headers=headers,
            timeout=REQUEST_TIMEOUT
        )
        if resp.status_code == 200:
            return resp.json(), 200
        elif resp.status_code == 404:
            return None, 404
        return None, resp.status_code
    except Exception:
        return None, 0


def create_copy_settings(copier_id, strategy_id, token, settings):
    """
    Create copy settings (POST) for a copier/strategy pair.

    Args:
        copier_id: Copier account ID
        strategy_id: Strategy account ID
        token: Access token for API authentication
        settings: Dict with tradeSizeType, tradeSizeValue, isOpenExistingTrades, isRoundUpToMinimumSize

    Returns:
        tuple: (success: bool, response_data or error_message)
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    try:
        resp = requests.post(
            f"{API_BASE_URL}/api/copiers/{copier_id}/strategies/{strategy_id}/copy-settings",
            headers=headers,
            json=settings
        )
        
        if resp.ok:
            if resp.status_code == 204 or not resp.content:
                return True, {}
            return True, resp.json()
        return False, resp.text
    except Exception as e:
        return False, str(e)

        

def update_copy_settings(copier_id, strategy_id, token, settings):
    """
    Update copy settings (PUT) for a copier/strategy pair.

    Args:
        copier_id: Copier account ID
        strategy_id: Strategy account ID
        token: Access token for API authentication
        settings: Dict with tradeSizeType, tradeSizeValue, isOpenExistingTrades, isRoundUpToMinimumSize

    Returns:
        tuple: (success: bool, response_data or error_message)
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    try:
        resp = requests.put(
            f"{API_BASE_URL}/api/copiers/{copier_id}/strategies/{strategy_id}/copy-settings",
            headers=headers,
            json=settings
        )
        
        if resp.ok:
            if resp.status_code == 204 or not resp.content:
                return True, {}
            return True, resp.json()
        
        return False, resp.text

    except Exception as e:
        return False, str(e)
       

def get_profile_id(token):
    """
    Get the profile ID for the authenticated user.

    Args:
        token: Access token for API authentication

    Returns:
        str: Profile ID or None on error
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    try:
        resp = requests.get(f"{IDENTITY_URL}/connect/userinfo", headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            userinfo = resp.json()
            return userinfo.get('https://copy-trade.io/profile')
        return None
    except Exception:
        return None


def list_profile_copiers(profile_id, token):
    """
    List all copier accounts for a profile.

    Args:
        profile_id: Profile ID
        token: Access token for API authentication

    Returns:
        list: List of copier dicts, or empty list on error
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    try:
        resp = requests.get(
            f"{API_BASE_URL}/api/profiles/{profile_id}/copiers",
            headers=headers,
            timeout=REQUEST_TIMEOUT
        )
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception:
        return []


def list_copier_strategies(copier_id, token):
    """
    List all strategies being copied by a copier account.

    Args:
        copier_id: Copier account ID
        token: Access token for API authentication

    Returns:
        list: List of strategy dicts, or empty list on error
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    try:
        resp = requests.get(
            f"{API_BASE_URL}/api/copiers/{copier_id}/strategies",
            headers=headers,
            timeout=REQUEST_TIMEOUT
        )
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception:
        return []


def get_strategy_stats(strategy_id, token, wl=WHITE_LABEL_ID):
    """
    Get strategy statistics.

    Args:
        strategy_id: Strategy ID
        token: Access token for API authentication
        wl: White label ID (default: pepperstone)

    Returns:
        dict: Strategy stats or None on error
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    try:
        resp = requests.get(
            f"{API_BASE_URL}/api/strategies/{strategy_id}/stats",
            headers=headers,
            params={'wl': wl}
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


def delete_copy_settings(copier_id, strategy_id, token, mode='Mirror'):
    """
    Stop copying a strategy (DELETE copy settings).

    Args:
        copier_id: Copier account ID
        strategy_id: Strategy account ID
        token: Access token for API authentication
        mode: Deletion mode - Mirror|Close|Manual (default: Mirror)

    Returns:
        tuple: (success: bool, status_code: int, error_message: str or None)
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    try:
        resp = requests.delete(
            f"{API_BASE_URL}/api/copiers/{copier_id}/strategies/{strategy_id}/copy-settings",
            headers=headers,
            params={'mode': mode}
        )
        if resp.status_code in [200, 204]:
            return True, resp.status_code, None
        return False, resp.status_code, resp.text
    except Exception as e:
        return False, 0, str(e)


def get_brokers(token):
    """
    Get list of all available brokers.

    Args:
        token: Access token for API authentication

    Returns:
        list: List of broker dicts with Code and Name fields, or empty list on error
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    try:
        resp = requests.get(
            f"{API_BASE_URL}/api/brokers",
            headers=headers,
            timeout=REQUEST_TIMEOUT
        )
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception:
        return []


def get_broker_detail(token, broker_code):
    """
    Get detailed broker information including available servers.

    Args:
        token: Access token for API authentication
        broker_code: Broker code (e.g., 'Pepperstone')

    Returns:
        dict: Broker detail with Servers list, or None on error
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    try:
        resp = requests.get(
            f"{API_BASE_URL}/api/brokers/{broker_code}",
            headers=headers,
            timeout=REQUEST_TIMEOUT
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


def create_copier(token, profile_id, payload):
    """
    Link a new copier account (MetaTrader account) to the profile.

    Args:
        token: Access token for API authentication
        profile_id: Profile ID
        payload: Dict with structure:
            {
                "name": "Account Label",
                "connection": {
                    "brokerCode": "Pepperstone",
                    "serverCode": "PepperstoneEdge01",
                    "username": "12345678",
                    "password": "password123",
                    "currencyCode": "USD"  # optional
                }
            }

    Returns:
        tuple: (success: bool, response_data or error_message)
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    try:
        resp = requests.post(
            f"{API_BASE_URL}/api/profiles/{profile_id}/copiers",
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT
        )
        if resp.status_code in [200, 201]:
            return True, resp.json()
        return False, resp.text
    except Exception as e:
        return False, str(e)


def delete_copier(token, profile_id, copier_id):
    """
    Unlink a copier account from the profile.

    Args:
        token: Access token for API authentication
        profile_id: Profile ID
        copier_id: Copier account ID to unlink

    Returns:
        tuple: (success: bool, status_code: int, error_message: str or None)
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    try:
        resp = requests.delete(
            f"{API_BASE_URL}/api/profiles/{profile_id}/copiers/{copier_id}",
            headers=headers,
            timeout=REQUEST_TIMEOUT
        )
        if resp.status_code in [200, 204]:
            return True, resp.status_code, None
        return False, resp.status_code, resp.text
    except Exception as e:
        return False, 0, str(e)


# ==========================================
# PORTAL SERVICES
# ==========================================

def get_strategy_by_id(profile_id, strategy_id, token):
    """
    Get strategy data by explicit profile_id and strategy_id (not via discover endpoint).
    Used for portals where both IDs are already known.

    Args:
        profile_id: Profile ID that owns the strategy
        strategy_id: Strategy ID to fetch
        token: Access token for API authentication (user session token)

    Returns dict with same structure as get_top_strategy().
    """
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    # Default result structure (same as get_top_strategy)
    result = {
        'name': 'Unknown',
        'copiers': 0,
        'return_val': 0.0,
        'strategy_id': strategy_id,
        'inception_date': None,
        'performance_fee': 0.0,
        'total_trades': 0,
        'min_per_month': 0,
        'max_per_month': 0,
        'wins': 0,
        'losses': 0,
        'win_rate': 0,
        'realised_pnl': 0,
        'unrealised_pnl': 0,
        'max_drawdown': 0,
        'balance': 0,
        'equity': 0,
        'credit': 0,
        'leverage': 0,
        'copiers_year_profit': 0,
        'copiers_month_profit': 0,
        'copiers_total_balance': 0,
        'currency_code': 'USD',
        'unauthorized': False
    }

    try:
        # Fetch basic strategy info
        strategy_resp = requests.get(
            f"{API_BASE_URL}/api/strategies/{strategy_id}",
            headers=headers,
            timeout=REQUEST_TIMEOUT
        )

        if strategy_resp.status_code == 401:
            result['unauthorized'] = True
            return result

        if strategy_resp.status_code == 200:
            strategy_data = strategy_resp.json()
            result['name'] = strategy_data.get('Name', 'Unknown')
            result['copiers'] = strategy_data.get('NumCopiers', 0)
            fee = strategy_data.get('Fee')
            result['performance_fee'] = (fee * 100) if fee is not None else 0.0

        # Fetch detailed stats
        stats_resp = requests.get(
            f"{API_BASE_URL}/api/strategies/{strategy_id}/stats",
            headers=headers,
            params={'wl': WHITE_LABEL_ID},
            timeout=REQUEST_TIMEOUT
        )

        if stats_resp.status_code == 200:
            stats_data = stats_resp.json()

            # Extract profitability
            profitability = stats_data.get('Profitability', {}).get('Inception', {})
            return_pct = profitability.get('RealisedReturn', 0)
            result['return_val'] = return_pct * 100

            # Extract inception date
            inception_str = stats_data.get('Inception')
            if inception_str:
                inception_dt = datetime.fromisoformat(inception_str.replace('Z', '+00:00'))
                result['inception_date'] = inception_dt.strftime('%B %d, %Y')

            # Extract trade statistics
            trades_data = stats_data.get('Trades', {}).get('Inception', {})
            result['total_trades'] = trades_data.get('Total', 0)
            result['min_per_month'] = trades_data.get('MinPerMonth', 0)
            result['max_per_month'] = trades_data.get('MaxPerMonth', 0)
            result['wins'] = trades_data.get('Wins', 0)
            result['losses'] = trades_data.get('Losses', 0)

            # Calculate win rate
            if result['total_trades'] > 0:
                result['win_rate'] = (result['wins'] / result['total_trades']) * 100

            # Extract profitability stats
            result['realised_pnl'] = profitability.get('RealisedPnl', 0)
            result['unrealised_pnl'] = profitability.get('UnrealisedPnl', 0)
            result['max_drawdown'] = abs(profitability.get('MaxDrawdown', 0)) * 100

            # Extract account status
            status_data = stats_data.get('Status', {})
            result['balance'] = status_data.get('Balance', 0)
            result['credit'] = status_data.get('Credit', 0)
            result['leverage'] = status_data.get('Leverage', 0)
            result['equity'] = result['balance'] + result['unrealised_pnl']

            # Extract copiers performance
            copiers_profit_data = stats_data.get('CopiersProfit', {})
            result['copiers_year_profit'] = copiers_profit_data.get('Year', 0)
            result['copiers_month_profit'] = copiers_profit_data.get('Month', 0)

            copiers_balance_data = stats_data.get('CopiersBalance', {})
            result['copiers_total_balance'] = copiers_balance_data.get('Balance', 0)

            result['currency_code'] = stats_data.get('CurrencyCode', 'USD')

    except Exception as e:
        result['name'] = "Connection Error"

    return result
