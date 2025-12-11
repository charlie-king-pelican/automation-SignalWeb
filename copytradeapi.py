import os
import requests
import secrets
import hashlib
import base64
import json
from flask import Flask, redirect, request, url_for

# ==========================================
# CONFIGURATION
# ==========================================
API_BASE_URL = 'https://papi.copy-trade.io'
IDENTITY_URL = 'https://identity.copy-trade.io'
CLIENT_ID = 'api-client'
TENANT_ID = 'pepperstone' 
WHITE_LABEL_ID = 'pepperstone' 

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_key_for_local_only')

# --- DYNAMIC CONFIGURATION ---
# If running on Cloud, this will be your Google URL. 
# If running locally, it defaults to localhost.
BASE_URL = os.environ.get('BASE_URL', 'https://localhost')
REDIRECT_URI = f"{BASE_URL}" 

AUTH_STORE = {}

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
        verifier = AUTH_STORE.get('verifier')
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
                    AUTH_STORE['access_token'] = data['access_token']
                    return redirect(url_for('index'))
            except Exception as e:
                return f"Token Error: {e}"

    token = AUTH_STORE.get('access_token')
    if not token:
        # Pass the dynamic redirect URI to the login endpoint
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
        if resp.status_code == 200:
            data = resp.json()
            if data and len(data) > 0:
                # To change strategy, change this index: data[0], data[1], etc.
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
        </div>
    </body>
    </html>
    '''
    return html

@app.route('/login')
def login():
    verifier, challenge = generate_pkce()
    AUTH_STORE['verifier'] = verifier
    
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

if __name__ == "__main__":
    # Get the PORT from Google Cloud, or default to 8080 locally
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host="0.0.0.0", port=port)