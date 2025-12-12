import os
import requests
import secrets
import hashlib
import base64
import json
from datetime import timedelta
from flask import Flask, redirect, request, url_for, session 

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
        # If no token, show login page
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {
                    background-color: #f4f6f8;
                    font-family: sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                }
                .login-card {
                    background: white;
                    width: 400px;
                    padding: 50px 40px;
                    border-radius: 20px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.05);
                    text-align: center;
                }
                .login-title {
                    font-size: 28px;
                    color: #333;
                    margin-bottom: 15px;
                    font-weight: 600;
                }
                .login-subtitle {
                    font-size: 14px;
                    color: #7f8c8d;
                    margin-bottom: 35px;
                }
                .login-btn {
                    display: inline-block;
                    padding: 15px 40px;
                    background: #2962ff;
                    color: white;
                    text-decoration: none;
                    border-radius: 8px;
                    font-weight: 600;
                    font-size: 15px;
                    transition: opacity 0.2s;
                }
                .login-btn:hover {
                    opacity: 0.9;
                }
            </style>
        </head>
        <body>
            <div class="login-card">
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
    except Exception as e:
        name = "Connection Error"

    # --- 3. RENDER UI ---
    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ background-color: #f4f6f8; font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; position: relative; }}
            .profile-info {{ position: absolute; top: 20px; left: 20px; background: white; padding: 15px 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.08); text-decoration: none; display: block; transition: transform 0.2s, box-shadow 0.2s; }}
            .profile-info:hover {{ transform: translateY(-2px); box-shadow: 0 4px 15px rgba(0,0,0,0.12); cursor: pointer; }}
            .profile-name {{ font-size: 16px; font-weight: 600; color: #333; margin-bottom: 5px; }}
            .profile-accounts {{ font-size: 12px; color: #7f8c8d; }}
            .profile-accounts span {{ color: #2962ff; font-weight: 600; }}
            .card {{ background: white; width: 450px; padding: 40px; border-radius: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.05); text-align: center; }}
            .badge {{ background-color: #f5a623; color: white; padding: 6px 16px; border-radius: 20px; font-weight: bold; font-size: 12px; margin-bottom: 25px; display:inline-block; }}
            .strategy-name {{ font-size: 26px; color: #333; margin-bottom: 35px; font-weight: 600; }}
            .stats-container {{ display: flex; justify-content: space-between; background-color: #f8f9fa; border-radius: 12px; padding: 25px 15px; }}
            .stat-box {{ text-align: center; flex: 1; border-right: 1px solid #e0e0e0; }}
            .stat-box:last-child {{ border-right: none; }}
            .stat-value {{ font-size: 22px; font-weight: 700; color: #2962ff; margin-bottom: 5px; }}
            .stat-label {{ font-size: 11px; color: #7f8c8d; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; }}
            .footer {{ margin-top: 30px; font-size: 12px; color: #bdc3c7; }}
            .copy-btn {{ background-color: #2962ff; color: white; border: none; padding: 12px 30px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; margin-top: 25px; transition: opacity 0.2s; }}
            .copy-btn:hover {{ opacity: 0.9; }}
        </style>
    </head>
    <body>
        {'<a href="/accounts" class="profile-info"><div class="profile-name">' + profile_info['name'] + '</div><div class="profile-accounts"><span>' + str(profile_info['strategies_count']) + '</span> Strategies • <span>' + str(profile_info['copiers_count']) + '</span> Copiers</div></a>' if profile_info else ''}
        <div class="card">
            <div class="badge">#1 Spotlight</div>
            <div class="strategy-name">{name}</div>
            <div class="stats-container">
                <div class="stat-box"><div class="stat-value">{return_val:,.2f}%</div><div class="stat-label">Return</div></div>
                <div class="stat-box"><div class="stat-value">{copiers}</div><div class="stat-label">Copiers</div></div>
                <div class="stat-box"><div class="stat-value">Inception</div><div class="stat-label">Period</div></div>
            </div>
            <button class="copy-btn">Copy</button>
            <p style="font-size: 10px; color: #95a5a6;"><a href="/logout">Logout</a></p>
        </div>
    </body>
    </html>
    '''
    return html

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

        return accounts_html

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
    """Temporary debug route to inspect API responses"""
    token = session.get('access_token')
    if not token:
        return """
        <html>
        <body style="font-family: monospace; padding: 20px;">
            <h2>❌ Not Logged In</h2>
            <p>Please <a href="/">go to homepage</a> and log in first.</p>
        </body>
        </html>
        """

    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    results = {}

    # 1. Get userinfo
    try:
        resp = requests.get(f"{IDENTITY_URL}/connect/userinfo", headers=headers)
        if resp.status_code == 200:
            results['userinfo'] = {'status': resp.status_code, 'data': resp.json()}
        else:
            results['userinfo'] = {'status': resp.status_code, 'error': resp.text}
    except Exception as e:
        results['userinfo'] = {'error': str(e)}

    # 2. Try to get profile ID from userinfo and fetch profile details
    if 'userinfo' in results and results['userinfo'].get('status') == 200:
        userinfo = results['userinfo']['data']
        # Profile ID is in the custom claim 'https://copy-trade.io/profile'
        profile_id = userinfo.get('https://copy-trade.io/profile')

        results['detected_profile_id'] = profile_id

        if profile_id:
            try:
                resp = requests.get(f"{API_BASE_URL}/api/profiles/{profile_id}", headers=headers)
                if resp.status_code == 200:
                    results['profile'] = {'status': resp.status_code, 'data': resp.json()}
                else:
                    results['profile'] = {'status': resp.status_code, 'error': resp.text}
            except Exception as e:
                results['profile'] = {'error': str(e)}

            # 3. Get strategies
            try:
                resp = requests.get(f"{API_BASE_URL}/api/profiles/{profile_id}/strategies", headers=headers)
                if resp.status_code == 200:
                    results['strategies'] = {'status': resp.status_code, 'count': len(resp.json()), 'data': resp.json()}
                else:
                    results['strategies'] = {'status': resp.status_code, 'error': resp.text}
            except Exception as e:
                results['strategies'] = {'error': str(e)}

            # 4. Get copiers
            try:
                resp = requests.get(f"{API_BASE_URL}/api/profiles/{profile_id}/copiers", headers=headers)
                if resp.status_code == 200:
                    results['copiers'] = {'status': resp.status_code, 'count': len(resp.json()), 'data': resp.json()}
                else:
                    results['copiers'] = {'status': resp.status_code, 'error': resp.text}
            except Exception as e:
                results['copiers'] = {'error': str(e)}
        else:
            results['error'] = 'Could not find profile_id in userinfo response'

    return f"""
    <html>
    <head>
        <style>
            body {{ font-family: monospace; padding: 20px; background: #f5f5f5; }}
            pre {{ background: white; padding: 20px; border-radius: 5px; overflow-x: auto; }}
            h2 {{ color: #2962ff; }}
        </style>
    </head>
    <body>
        <h2>🔍 API Debug Output</h2>
        <a href="/">← Back to Home</a>
        <pre>{json.dumps(results, indent=2, default=str)}</pre>
    </body>
    </html>
    """

@app.route('/logout')
def logout():
    # Clear local session
    session.pop('access_token', None)
    session.clear()

    # Redirect to Pepperstone's logout endpoint to clear their session
    logout_url = f"{IDENTITY_URL}/connect/endsession?post_logout_redirect_uri={REDIRECT_URI}"
    return redirect(logout_url)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    # Note: On Google Cloud Run, host="0.0.0.0" and the PORT environment variable are essential.
    app.run(debug=True, host="0.0.0.0", port=port)