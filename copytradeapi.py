import os
import requests
import secrets
import hashlib
import base64
import json
from flask import Flask, redirect, request, url_for, session # <--- ADDED session

# ==========================================
# CONFIGURATION
# ==========================================
API_BASE_URL = 'https://papi.copy-trade.io'
IDENTITY_URL = 'https://identity.copy-trade.io'
CLIENT_ID = 'api-client'
TENANT_ID = 'pepperstone' 
WHITE_LABEL_ID = 'pepperstone' 

app = Flask(__name__)
# Crucial: Flask uses secret_key to encrypt the session data stored in the user's cookie.
# Must be set via environment variable in Cloud Run for security.
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_urlsafe(32)) 

# --- DYNAMIC CONFIGURATION ---
BASE_URL = os.environ.get('BASE_URL', 'https://localhost')
REDIRECT_URI = f"{BASE_URL}" 

# Removed AUTH_STORE = {}

def generate_pkce():
    verifier = secrets.token_urlsafe(32)
    m = hashlib.sha256()
    m.update(verifier.encode('ascii'))
    challenge = base64.urlsafe_b64encode(m.digest()).decode('ascii').replace('=', '')
    return verifier, challenge

@app.route('/')
def index():
    # --- 1. AUTHENTICATION ---
    if 'code' in request.args:
        code = request.args.get('code')
        # Retrieve verifier from session, not AUTH_STORE
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
                    # Store token in session, not AUTH_STORE
                    session['access_token'] = data['access_token'] 
                    return redirect(url_for('index'))
                else:
                    return f"Token Exchange Error: {data.get('error_description', data.get('error', 'Unknown Error'))}"
            except Exception as e:
                return f"Token Error: {e}"

    # Check for token in session, not AUTH_STORE
    token = session.get('access_token') 
    
    if not token:
        # If no token, show login button
        return f'''
        <div style="display:flex; justify-content:center; align-items:center; height:100vh; font-family:sans-serif;">
            <a href="/login" style="padding:15px 30px; background:#007bff; color:white; text-decoration:none; border-radius:5px; font-weight:bold;">
                Login with Pepperstone
            </a>
            <div style="margin-top: 20px; font-size: 12px; color: #7f8c8d;">
                (Waiting for Client ID from developer)
            </div>
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
        
        # Check for expired/invalid token (401 Unauthorized)
        if resp.status_code == 401:
            session.pop('access_token', None) # Clear the bad token
            return redirect(url_for('index')) # Force re-login
            
        if resp.status_code == 200:
            data = resp.json()
            if data and len(data) > 0:
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
            /* ... (UI Styles remain the same) ... */
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
            <div class="footer">Live Data from Pepperstone API</div>
            <p style="font-size: 10px; color: #95a5a6;"><a href="/logout">Logout</a></p>
        </div>
    </body>
    </html>
    '''
    return html

@app.route('/login')
def login():
    verifier, challenge = generate_pkce()
    # Store verifier in session, not AUTH_STORE
    session['verifier'] = verifier 
    
    # Notice we use the global REDIRECT_URI here
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

@app.route('/logout')
def logout():
    session.pop('access_token', None)
    return redirect(url_for('index'))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host="0.0.0.0", port=port)