"""Optional session authentication for an HTTPS proxy; server remains loopback-only."""
from datetime import timedelta
import hashlib
import hmac
import time
import threading
from collections import OrderedDict
from flask import request, session, redirect, jsonify, render_template_string

PAGE = '''<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kronos sign in</title><body style="font:16px system-ui;max-width:420px;margin:40px auto;padding:20px">
<h1>Kronos sign in</h1><p>Enter your private dashboard access token. This is separate from your Polygon key.</p>
<form method="post"><label>Access token <input name="token" type="password" required autocomplete="current-password" style="font:inherit;width:100%;padding:10px;box-sizing:border-box"></label>
<button style="font:inherit;margin-top:16px;padding:12px">Sign in</button></form><p>{{ error }}</p></body></html>'''


def configure_access(app, token):
    if not token or len(token) < 32:
        raise ValueError('Authenticated mode requires KRONOS_ACCESS_TOKEN with at least 32 characters in private .env.')
    app.config.update(SECRET_KEY=hashlib.sha256(token.encode()).digest(),
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict',
                      SESSION_COOKIE_SECURE=True, PERMANENT_SESSION_LIFETIME=timedelta(hours=12))
    attempts = OrderedDict()
    attempt_lock = threading.Lock()

    @app.before_request
    def protect():
        if request.path == '/login':
            return None
        if not session.get('kronos_access'):
            if request.path.startswith('/api/'):
                return jsonify(error='Sign in to Kronos first.'), 401
            return redirect('/login')
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            # Requests from third-party pages cannot mutate an authenticated dashboard.
            origin = request.headers.get('Origin')
            if not origin or origin.rstrip('/') != request.host_url.rstrip('/').replace('http://', 'https://', 1):
                return jsonify(error='Request origin did not match the dashboard HTTPS address.'), 403

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        error = ''
        if request.method == 'POST':
            ip = request.remote_addr
            now = time.monotonic()
            with attempt_lock:
                recent = [t for t in attempts.get(ip, []) if now-t < 60]
                if len(recent) >= 5:
                    return render_template_string(PAGE, error='Too many attempts. Wait one minute.'), 429
                recent.append(now)
                attempts[ip] = recent
                if len(attempts) > 1000:
                    attempts.popitem(last=False)
            supplied = request.form.get('token', '')
            if hmac.compare_digest(supplied.encode(), token.encode()):
                session.clear()
                session['kronos_access'] = True
                session.permanent = True
                return redirect('/')
            error = 'Incorrect access token.'
        return render_template_string(PAGE, error=error)

    @app.post('/logout')
    def logout():
        session.clear()
        return redirect('/login')

    @app.after_request
    def private_response(response):
        response.headers['Cache-Control'] = 'no-store'
        # Existing localhost CORS support must not expose authenticated API responses.
        for key in list(response.headers.keys()):
            if key.lower().startswith('access-control-'):
                del response.headers[key]
        return response
    # Flask runs response hooks in reverse order; strip CORS after the existing hook.
    hooks = app.after_request_funcs[None]
    hooks.insert(0, hooks.pop())
