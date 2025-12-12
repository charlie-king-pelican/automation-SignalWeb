import os
import requests
import secrets
import hashlib
import base64
import json
from datetime import timedelta
from flask import Flask, redirect, request, url_for, session, make_response 

# ==========================================
# CONFIGURATION
# ==========================================
API_BASE_URL = 'https://papi.copy-trade.io'
IDENTITY_URL = 'https://identity.copy-trade.io'

# !!! IMPORTANT: REPLACE WITH YOUR OFFICIAL CLIENT ID !!!
CLIENT_ID = 'api-client' 

TENANT_ID = 'pepperstone' 
WHITE_LABEL_ID = 'pepperstone' 

app = Flask(__name__)
# Crucial for security and stability: Retrieves the secure key from Cloud Run environment.
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_urlsafe(32)) 

# CONFIGURE SESSION TIMEOUT TO 1 HOUR
app.permanent_session_lifetime = timedelta(hours=1)

# --- DYNAMIC CONFIGURATION ---
# BASE_URL is set via environment variable in Cloud Run (e.g., https://your-app.run.app)
BASE_URL = os.environ.get('BASE_URL', 'https://localhost')
REDIRECT_URI = f"{BASE_URL}" 

def generate_pkce():
    verifier = secrets.token_urlsafe(32)
    m = hashlib.sha256()
    m.update(verifier.encode('ascii'))
    challenge = base64.urlsafe_b64encode(m.digest()).decode('ascii').replace('=', '')
    return verifier, challenge

def add_no_cache_headers(response):
    """Add headers to prevent browser caching of authenticated pages"""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

def get_profile_info(token):
    """Fetch profile information including name and account counts"""
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

@app.route('/')
def index():
    # --- 1. AUTHENTICATION & TOKEN EXCHANGE ---
    if 'code' in request.args:
        code = request.args.get('code')
        # Retrieve verifier from session
        verifier = session.pop('verifier', None) 
        
        if verifier:
            try:
                payload = {
                    'client_id': CLIENT_ID,
                    'grant_type': 'authorization_code',
                    'code': code,
                    'redirect_uri': REDIRECT_URI,
                    'code_verifier': verifier
                }
                r = requests.post(f"{IDENTITY_URL}/connect/token", data=payload)
                data = r.json()
                if 'access_token' in data:
                    session['access_token'] = data['access_token'] 
                    
                    # MARK SESSION AS PERMANENT (enables the 1-hour timeout)
                    session.permanent = True 
                    
                    return redirect(url_for('index'))
                else:
                    return f"Token Exchange Error: {data.get('error_description', data.get('error', 'Unknown Error'))}"
            except Exception as e:
                return f"Token Error: {e}"

    # Check for token in session. If present, user is logged in for up to 1 hour.
    token = session.get('access_token') 
    
    if not token:
        # Check if user just logged out
        logged_out = request.args.get('logged_out')
        logout_message = ''
        if logged_out:
            logout_message = '<div class="logout-success">✓ You have been logged out successfully</div>'

        # If no token, show login page
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    background-color: #f4f6f8;
                    font-family: sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                }}
                .login-card {{
                    background: white;
                    width: 400px;
                    padding: 50px 40px;
                    border-radius: 20px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.05);
                    text-align: center;
                }}
                .login-title {{
                    font-size: 28px;
                    color: #333;
                    margin-bottom: 15px;
                    font-weight: 600;
                }}
                .login-subtitle {{
                    font-size: 14px;
                    color: #7f8c8d;
                    margin-bottom: 35px;
                }}
                .logout-success {{
                    background: #d4edda;
                    color: #155724;
                    padding: 12px 20px;
                    border-radius: 8px;
                    margin-bottom: 25px;
                    font-size: 14px;
                    border: 1px solid #c3e6cb;
                }}
                .login-btn {{
                    display: inline-block;
                    padding: 15px 40px;
                    background: #2962ff;
                    color: white;
                    text-decoration: none;
                    border-radius: 8px;
                    font-weight: 600;
                    font-size: 15px;
                    transition: opacity 0.2s;
                }}
                .login-btn:hover {{
                    opacity: 0.9;
                }}
            </style>
        </head>
        <body>
            <div class="login-card">
                {logout_message}
                <div class="login-title">Welcome</div>
                <div class="login-subtitle">Sign in to access your trading accounts</div>
                <a href="/login" class="login-btn">Login with Pepperstone</a>
            </div>
        </body>
        </html>
        '''

    # --- 2. FETCH PROFILE INFO ---
    profile_info = get_profile_info(token)

    # --- 3. FETCH STRATEGY DATA ---
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    endpoint = f"{API_BASE_URL}/api/discover/Strategies"
    params = {"wl": WHITE_LABEL_ID}

    name = "Unknown"
    copiers = 0
    return_val = 0.0
    strategy_id = None
    inception_date = None
    performance_fee = 0.0
    total_trades = 0
    min_per_month = 0
    max_per_month = 0
    wins = 0
    losses = 0
    realised_pnl = 0
    unrealised_pnl = 0
    max_drawdown = 0
    balance = 0
    equity = 0
    credit = 0
    leverage = 0
    copiers_year_profit = 0
    copiers_month_profit = 0
    copiers_total_balance = 0
    currency_code = "USD"

    try:
        resp = requests.get(endpoint, headers=headers, params=params)

        # If token is invalid/expired mid-session, clear session and force re-login
        if resp.status_code == 401:
            session.pop('access_token', None)
            return redirect(url_for('index'))

        if resp.status_code == 200:
            data = resp.json()
            if data and len(data) > 0:
                # Displays the #1 Strategy (change index if needed)
                top_item = data[0]

                raw_val = top_item.get('Value', 0)
                return_val = raw_val * 100

                strategy = top_item.get('Strategy', {})
                name = strategy.get('Name', 'Unknown')
                copiers = strategy.get('NumCopiers', 0)
                strategy_id = strategy.get('Id')

                # Fee is not in discover endpoint, need to fetch from detail endpoint
                if strategy_id:
                    # Get full strategy details including Fee
                    try:
                        detail_resp = requests.get(
                            f"{API_BASE_URL}/api/strategies/{strategy_id}",
                            headers=headers
                        )
                        if detail_resp.status_code == 200:
                            strategy_detail = detail_resp.json()
                            fee = strategy_detail.get('Fee')
                            # Performance fee is nullable, convert to percentage if exists
                            if fee is not None:
                                performance_fee = fee * 100  # Convert to percentage
                            else:
                                performance_fee = 0.0
                    except Exception:
                        pass  # If detail fetch fails, use default 0.0

                # Get detailed stats for this strategy
                if strategy_id:
                    try:
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
                                from datetime import datetime
                                inception_dt = datetime.fromisoformat(inception_str.replace('Z', '+00:00'))
                                inception_date = inception_dt.strftime('%B %d, %Y')

                            # Extract trade statistics
                            trades_data = stats_data.get('Trades', {}).get('Inception', {})
                            total_trades = trades_data.get('Total', 0)
                            min_per_month = trades_data.get('MinPerMonth', 0)
                            max_per_month = trades_data.get('MaxPerMonth', 0)
                            wins = trades_data.get('Wins', 0)
                            losses = trades_data.get('Losses', 0)

                            # Extract profitability statistics
                            profitability_data = stats_data.get('Profitability', {}).get('Inception', {})
                            realised_pnl = profitability_data.get('RealisedPnl', 0)
                            unrealised_pnl = profitability_data.get('UnrealisedPnl', 0)
                            max_drawdown = abs(profitability_data.get('MaxDrawdown', 0)) * 100  # Convert to positive percentage

                            # Extract account status
                            status_data = stats_data.get('Status', {})
                            balance = status_data.get('Balance', 0)
                            credit = status_data.get('Credit', 0)
                            leverage = status_data.get('Leverage', 0)

                            # Calculate equity (balance + unrealised P&L)
                            equity = balance + unrealised_pnl

                            # Extract copiers performance
                            copiers_profit_data = stats_data.get('CopiersProfit', {})
                            copiers_year_profit = copiers_profit_data.get('Year', 0)
                            copiers_month_profit = copiers_profit_data.get('Month', 0)

                            copiers_balance_data = stats_data.get('CopiersBalance', {})
                            copiers_total_balance = copiers_balance_data.get('Balance', 0)

                            currency_code = stats_data.get('CurrencyCode', 'USD')
                    except Exception:
                        pass  # If stats fetch fails, just use default values
    except Exception as e:
        name = "Connection Error"

    # --- 3. RENDER UI ---
    # Calculate win rate if we have trades
    win_rate = 0
    if total_trades > 0:
        win_rate = (wins / total_trades) * 100

    inception_display = inception_date if inception_date else "Unknown"

    # Format performance fee display
    fee_display = "Free" if performance_fee == 0 else f"{performance_fee:.1f}%"

    # Format currency values with thousands separators
    def format_currency(value, code="USD"):
        symbol = "$" if code == "USD" else code
        return f"{symbol}{value:,.2f}"

    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ background-color: #f4f6f8; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; position: relative; padding: 20px; }}
            .profile-info {{ position: absolute; top: 20px; left: 20px; background: white; padding: 15px 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.08); text-decoration: none; display: block; transition: transform 0.2s, box-shadow 0.2s; }}
            .profile-info:hover {{ transform: translateY(-2px); box-shadow: 0 4px 15px rgba(0,0,0,0.12); cursor: pointer; }}
            .profile-name {{ font-size: 16px; font-weight: 600; color: #333; margin-bottom: 5px; }}
            .profile-accounts {{ font-size: 12px; color: #7f8c8d; }}
            .profile-accounts span {{ color: #2962ff; font-weight: 600; }}
            .card {{ background: white; width: 650px; max-width: 95vw; padding: 40px; border-radius: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.05); text-align: center; }}
            .badge {{ background-color: #f5a623; color: white; padding: 6px 16px; border-radius: 20px; font-weight: bold; font-size: 12px; margin-bottom: 15px; display:inline-block; }}
            .strategy-name {{ font-size: 28px; color: #333; margin-bottom: 8px; font-weight: 700; }}
            .inception-date {{ font-size: 13px; color: #7f8c8d; margin-bottom: 30px; }}
            .inception-date span {{ color: #2962ff; font-weight: 600; }}

            /* Main stats */
            .stats-container {{ display: flex; justify-content: space-between; background-color: #f8f9fa; border-radius: 12px; padding: 25px 15px; margin-bottom: 15px; }}
            .stat-box {{ text-align: center; flex: 1; border-right: 1px solid #e0e0e0; }}
            .stat-box:last-child {{ border-right: none; }}
            .stat-value {{ font-size: 24px; font-weight: 700; color: #2962ff; margin-bottom: 5px; }}
            .stat-label {{ font-size: 11px; color: #7f8c8d; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; }}

            /* Trade Performance Section */
            .trades-section {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px; padding: 25px; color: white; margin-bottom: 15px; }}
            .section-title {{ font-size: 13px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 20px; opacity: 0.9; font-weight: 600; }}
            .trades-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
            .trade-stat {{ background: rgba(255,255,255,0.15); padding: 15px; border-radius: 8px; backdrop-filter: blur(10px); }}
            .trade-stat-value {{ font-size: 22px; font-weight: 700; margin-bottom: 5px; }}
            .trade-stat-label {{ font-size: 10px; opacity: 0.9; text-transform: uppercase; letter-spacing: 0.5px; }}
            .win-loss-row {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; margin-top: 12px; }}

            /* Profitability & Risk Section */
            .profitability-section {{ background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); border-radius: 12px; padding: 25px; color: white; margin-bottom: 15px; }}
            .profit-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
            .profit-stat {{ background: rgba(255,255,255,0.15); padding: 15px; border-radius: 8px; backdrop-filter: blur(10px); }}
            .profit-stat-value {{ font-size: 20px; font-weight: 700; margin-bottom: 5px; }}
            .profit-stat-label {{ font-size: 10px; opacity: 0.9; text-transform: uppercase; letter-spacing: 0.5px; }}
            .negative {{ color: #ff6b6b; }}

            /* Account Status Section */
            .account-section {{ background: linear-gradient(135deg, #fc4a1a 0%, #f7b733 100%); border-radius: 12px; padding: 25px; color: white; margin-bottom: 15px; }}
            .account-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
            .account-stat {{ background: rgba(255,255,255,0.15); padding: 15px; border-radius: 8px; backdrop-filter: blur(10px); }}
            .account-stat-value {{ font-size: 20px; font-weight: 700; margin-bottom: 5px; }}
            .account-stat-label {{ font-size: 10px; opacity: 0.9; text-transform: uppercase; letter-spacing: 0.5px; }}

            /* Copiers Performance Section */
            .copiers-section {{ background: linear-gradient(135deg, #2193b0 0%, #6dd5ed 100%); border-radius: 12px; padding: 25px; color: white; margin-bottom: 20px; }}
            .copiers-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
            .copier-stat {{ background: rgba(255,255,255,0.15); padding: 15px; border-radius: 8px; backdrop-filter: blur(10px); }}
            .copier-stat-value {{ font-size: 20px; font-weight: 700; margin-bottom: 5px; }}
            .copier-stat-label {{ font-size: 10px; opacity: 0.9; text-transform: uppercase; letter-spacing: 0.5px; }}

            /* Button */
            .copy-btn {{ background-color: #2962ff; color: white; border: none; padding: 14px 40px; border-radius: 10px; font-size: 15px; font-weight: 600; cursor: pointer; margin-top: 10px; transition: transform 0.2s, box-shadow 0.2s; box-shadow: 0 4px 15px rgba(41, 98, 255, 0.3); }}
            .copy-btn:hover {{ transform: translateY(-2px); box-shadow: 0 6px 20px rgba(41, 98, 255, 0.4); }}
        </style>
    </head>
    <body>
        {'<a href="/accounts" class="profile-info"><div class="profile-name">' + profile_info['name'] + '</div><div class="profile-accounts"><span>' + str(profile_info['strategies_count']) + '</span> Strategies • <span>' + str(profile_info['copiers_count']) + '</span> Copiers</div></a>' if profile_info else ''}
        <div class="card">
            <div class="badge">#1 Spotlight</div>
            <div class="strategy-name">{name}</div>
            <div class="inception-date">Trading since <span>{inception_display}</span></div>

            <!-- Main Performance Stats -->
            <div class="stats-container">
                <div class="stat-box"><div class="stat-value">{return_val:,.2f}%</div><div class="stat-label">Total Return</div></div>
                <div class="stat-box"><div class="stat-value">{copiers:,}</div><div class="stat-label">Copiers</div></div>
                <div class="stat-box"><div class="stat-value">{fee_display}</div><div class="stat-label">Performance Fee</div></div>
            </div>

            <!-- Trade Performance Section -->
            <div class="trades-section">
                <div class="section-title">TRADE PERFORMANCE</div>
                <div class="trades-grid">
                    <div class="trade-stat">
                        <div class="trade-stat-value">{total_trades:,}</div>
                        <div class="trade-stat-label">Total Trades</div>
                    </div>
                    <div class="trade-stat">
                        <div class="trade-stat-value">{min_per_month:,}</div>
                        <div class="trade-stat-label">Min / Month</div>
                    </div>
                    <div class="trade-stat">
                        <div class="trade-stat-value">{max_per_month:,}</div>
                        <div class="trade-stat-label">Max / Month</div>
                    </div>
                </div>
                <div class="win-loss-row">
                    <div class="trade-stat">
                        <div class="trade-stat-value">{wins:,}</div>
                        <div class="trade-stat-label">Wins</div>
                    </div>
                    <div class="trade-stat">
                        <div class="trade-stat-value">{losses:,}</div>
                        <div class="trade-stat-label">Losses</div>
                    </div>
                    <div class="trade-stat">
                        <div class="trade-stat-value">{win_rate:.1f}%</div>
                        <div class="trade-stat-label">Win Rate</div>
                    </div>
                </div>
            </div>

            <!-- Profitability & Risk Section -->
            <div class="profitability-section">
                <div class="section-title">PROFITABILITY & RISK</div>
                <div class="profit-grid">
                    <div class="profit-stat">
                        <div class="profit-stat-value">{format_currency(realised_pnl, currency_code)}</div>
                        <div class="profit-stat-label">Realised P&L</div>
                    </div>
                    <div class="profit-stat">
                        <div class="profit-stat-value">{format_currency(unrealised_pnl, currency_code)}</div>
                        <div class="profit-stat-label">Unrealised P&L</div>
                    </div>
                    <div class="profit-stat">
                        <div class="profit-stat-value">{max_drawdown:.2f}%</div>
                        <div class="profit-stat-label">Max Drawdown</div>
                    </div>
                </div>
            </div>

            <!-- Account Status Section -->
            <div class="account-section">
                <div class="section-title">ACCOUNT STATUS</div>
                <div class="account-grid">
                    <div class="account-stat">
                        <div class="account-stat-value">{format_currency(balance, currency_code)}</div>
                        <div class="account-stat-label">Balance</div>
                    </div>
                    <div class="account-stat">
                        <div class="account-stat-value">{format_currency(equity, currency_code)}</div>
                        <div class="account-stat-label">Equity</div>
                    </div>
                    <div class="account-stat">
                        <div class="account-stat-value">1:{leverage}</div>
                        <div class="account-stat-label">Leverage</div>
                    </div>
                </div>
            </div>

            <!-- Copiers Performance Section -->
            <div class="copiers-section">
                <div class="section-title">COPIERS PERFORMANCE</div>
                <div class="copiers-grid">
                    <div class="copier-stat">
                        <div class="copier-stat-value">{format_currency(copiers_year_profit, currency_code)}</div>
                        <div class="copier-stat-label">Year Profit</div>
                    </div>
                    <div class="copier-stat">
                        <div class="copier-stat-value">{format_currency(copiers_month_profit, currency_code)}</div>
                        <div class="copier-stat-label">Month Profit</div>
                    </div>
                    <div class="copier-stat">
                        <div class="copier-stat-value">{format_currency(copiers_total_balance, currency_code)}</div>
                        <div class="copier-stat-label">Total AUM</div>
                    </div>
                </div>
            </div>

            <button class="copy-btn">Copy Strategy</button>
            <p style="font-size: 10px; color: #95a5a6; margin-top: 20px;"><a href="/logout" style="color: #7f8c8d; text-decoration: none;">Logout</a></p>
        </div>
    </body>
    </html>
    '''
    response = make_response(html)
    return add_no_cache_headers(response)

@app.route('/accounts')
def accounts():
    """Display all copier accounts with balance and equity"""
    token = session.get('access_token')
    if not token:
        return redirect(url_for('index'))

    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    try:
        # 1. Get profile ID
        resp = requests.get(f"{IDENTITY_URL}/connect/userinfo", headers=headers)
        if resp.status_code != 200:
            return "Error fetching user info", 500

        userinfo = resp.json()
        profile_id = userinfo.get('https://copy-trade.io/profile')

        if not profile_id:
            return "Profile ID not found", 500

        # 2. Get profile details
        resp = requests.get(f"{API_BASE_URL}/api/profiles/{profile_id}", headers=headers)
        profile_data = resp.json() if resp.status_code == 200 else {}
        profile_name = profile_data.get('Name', 'User')

        # 3. Get all copiers
        resp = requests.get(f"{API_BASE_URL}/api/profiles/{profile_id}/copiers", headers=headers)
        if resp.status_code != 200:
            return "Error fetching copiers", 500

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

        # 5. Render accounts page
        accounts_html = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ background-color: #f4f6f8; font-family: sans-serif; padding: 40px; margin: 0; }}
                .header {{ max-width: 1000px; margin: 0 auto 30px; display: flex; justify-content: space-between; align-items: center; }}
                .header h1 {{ font-size: 28px; color: #333; margin: 0; }}
                .back-link {{ color: #2962ff; text-decoration: none; font-weight: 600; font-size: 14px; }}
                .back-link:hover {{ text-decoration: underline; }}
                .container {{ max-width: 1000px; margin: 0 auto; }}
                .account-card {{ background: white; border-radius: 12px; padding: 20px 25px; margin-bottom: 15px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); display: flex; justify-content: space-between; align-items: center; }}
                .account-info {{ flex: 1; }}
                .account-name {{ font-size: 16px; font-weight: 600; color: #333; margin-bottom: 5px; }}
                .account-details {{ font-size: 13px; color: #7f8c8d; }}
                .account-details span {{ margin-right: 15px; }}
                .account-stats {{ text-align: right; }}
                .stat-row {{ margin-bottom: 5px; }}
                .stat-label {{ font-size: 11px; color: #7f8c8d; text-transform: uppercase; letter-spacing: 0.5px; margin-right: 8px; }}
                .stat-value {{ font-size: 16px; font-weight: 700; color: #2962ff; }}
                .no-data {{ text-align: center; padding: 60px 20px; color: #7f8c8d; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>{profile_name}'s Accounts</h1>
                <a href="/" class="back-link">← Back to Dashboard</a>
            </div>
            <div class="container">
        '''

        if not copiers_with_stats:
            accounts_html += '<div class="no-data">No copier accounts found</div>'
        else:
            for copier in copiers_with_stats:
                balance = copier['stats'].get('balance', 0)
                equity = copier['stats'].get('equity', 0)
                leverage = copier['stats'].get('leverage')
                return_pct = copier['stats'].get('return_pct', 0)
                drawdown_pct = copier['stats'].get('drawdown_pct', 0)
                currency = copier['stats'].get('currency', 'USD')

                # Determine color for return (green if positive, red if negative)
                return_color = '#2e7d32' if return_pct >= 0 else '#c62828'

                accounts_html += f'''
                <div class="account-card">
                    <div class="account-info">
                        <div class="account-name">{copier['name']}</div>
                        <div class="account-details">
                            <span>{copier['server']}</span>
                            <span>#{copier['username']}</span>
                            {f'<span style="color: #7f8c8d; font-size: 12px;">1:{leverage}</span>' if leverage else ''}
                        </div>
                    </div>
                    <div class="account-stats">
                        <div class="stat-row">
                            <span class="stat-label">Balance</span>
                            <span class="stat-value">{currency} {balance:,.2f}</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">Equity</span>
                            <span class="stat-value">{currency} {equity:,.2f}</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">Return</span>
                            <span class="stat-value" style="color: {return_color};">{return_pct:+.2f}%</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">Max Drawdown (Equity)</span>
                            <span class="stat-value" style="color: #c62828;">{drawdown_pct:.2f}%</span>
                        </div>
                    </div>
                </div>
                '''

        accounts_html += '''
            </div>
        </body>
        </html>
        '''

        response = make_response(accounts_html)
        return add_no_cache_headers(response)

    except Exception as e:
        return f"Error: {e}", 500

@app.route('/login')
def login():
    verifier, challenge = generate_pkce()
    session['verifier'] = verifier 
    
    auth_url = (
        f"{IDENTITY_URL}/connect/authorize"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope=openid%20profile%20email%20api%20copytrade%20offline_access"
        f"&code_challenge={challenge}"
        f"&code_challenge_method=S256"
        f"&acr_values=tenant:{TENANT_ID}"
    )
    return redirect(auth_url)

@app.route('/debug/api')
def debug_api():
    """Debug route - cleared for production"""
    token = session.get('access_token')
    if not token:
        return redirect(url_for('index'))

    return """
    <html>
    <head>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                padding: 40px;
                background: #f5f5f5;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
            }
            .container {
                background: white;
                padding: 40px;
                border-radius: 12px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.08);
                text-align: center;
                max-width: 500px;
            }
            h2 {
                color: #333;
                margin-bottom: 10px;
            }
            p {
                color: #7f8c8d;
                margin-bottom: 30px;
            }
            a {
                color: #2962ff;
                text-decoration: none;
                font-weight: 600;
                padding: 12px 30px;
                background: #f0f5ff;
                border-radius: 8px;
                display: inline-block;
                transition: background 0.2s;
            }
            a:hover {
                background: #e3edff;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Debug Mode</h2>
            <p>Debug endpoint is currently cleared.<br>Ready for new debugging tasks.</p>
            <a href="/">← Back to Dashboard</a>
        </div>
    </body>
    </html>
    """

@app.route('/logout')
def logout():
    # Clear local session
    session.pop('access_token', None)
    session.clear()

    # Full logout: clears both app session AND identity provider session
    logout_url = f"{IDENTITY_URL}/connect/endsession?post_logout_redirect_uri={REDIRECT_URI}?logged_out=1"
    return redirect(logout_url)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    # Note: On Google Cloud Run, host="0.0.0.0" and the PORT environment variable are essential.
    app.run(debug=True, host="0.0.0.0", port=port)