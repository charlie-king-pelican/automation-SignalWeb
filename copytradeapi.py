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
        # If no token, show login button
        return f'''
        <div style="display:flex; justify-content:center; align-items:center; height:100vh; font-family:sans-serif;">
            <a href="/login" style="padding:15px 30px; background:#007bff; color:white; text-decoration:none; border-radius:5px; font-weight:bold;">
                Login with Pepperstone
            </a>
        </div>
        '''

    # --- 2. FETCH DATA ---
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
            body {{ background-color: #f4f6f8; font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
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
        # Profile ID might be in 'sub', 'profile_id', or another field - we'll see
        profile_id = userinfo.get('profile_id') or userinfo.get('sub')

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
    # Log out by clearing the token from the session
    session.pop('access_token', None)
    return redirect(url_for('index'))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    # Note: On Google Cloud Run, host="0.0.0.0" and the PORT environment variable are essential.
    app.run(debug=True, host="0.0.0.0", port=port)