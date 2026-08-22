"""
Google Sign-In for Veritas AI.

Wires up an OAuth 2.0 / OpenID Connect "Sign in with Google" flow using
Authlib, backed by Flask's server-side session. On successful login we
upsert a row in the local `users` table (see benchmark_db.py) and store
the user's id in the session cookie.

Setup:
  1. Create OAuth credentials at https://console.cloud.google.com/apis/credentials
     (Application type: Web application).
  2. Add an Authorized redirect URI matching AUTH_REDIRECT_PATH below,
     e.g. http://127.0.0.1:5000/auth/callback/google for local dev.
  3. Set these environment variables before starting server.py:
       GOOGLE_CLIENT_ID=...
       GOOGLE_CLIENT_SECRET=...
       FLASK_SECRET_KEY=some-long-random-string
     (For local http-only testing you may also need:
       OAUTHLIB_INSECURE_TRANSPORT=1
     Google OAuth requires https in production.)
"""

import os
from functools import wraps

from authlib.integrations.flask_client import OAuth
from flask import jsonify, redirect, request, session, url_for

AUTH_REDIRECT_PATH = "/auth/callback/google"

oauth = OAuth()


def init_auth(app):
    """Attach session config + the Google OAuth client to the Flask app."""
    app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )

    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=os.environ.get("GOOGLE_CLIENT_ID"),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth


def _upsert_user(get_db, claims):
    """Insert or update the local user row from Google's ID token claims."""
    google_sub = claims["sub"]
    email = claims.get("email")
    name = claims.get("name")
    picture = claims.get("picture")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO users (google_sub, email, name, picture)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(google_sub) DO UPDATE SET
            email=excluded.email,
            name=excluded.name,
            picture=excluded.picture
        """,
        (google_sub, email, name, picture),
    )
    conn.commit()
    cursor.execute("SELECT id, email, name, picture FROM users WHERE google_sub = ?", (google_sub,))
    user = dict(cursor.fetchone())
    conn.close()
    return user


def register_auth_routes(app, get_db):
    """Registers /auth/login, /auth/callback, /auth/logout, /api/auth/me."""

    @app.route("/auth/login/google")
    def login_google():
        redirect_uri = url_for("auth_callback_google", _external=True)
        return oauth.google.authorize_redirect(redirect_uri)

    @app.route(AUTH_REDIRECT_PATH, endpoint="auth_callback_google")
    def auth_callback_google():
        try:
            token = oauth.google.authorize_access_token()
        except Exception as e:
            return jsonify({"success": False, "error": f"Google sign-in failed: {e}"}), 400

        claims = token.get("userinfo") or oauth.google.parse_id_token(token)
        if not claims or not claims.get("sub"):
            return jsonify({"success": False, "error": "Google did not return a valid identity."}), 400

        user = _upsert_user(get_db, claims)
        session["user_id"] = user["id"]

        # Send the user back to the app's home page after login.
        return redirect("/")

    @app.route("/auth/logout", methods=["POST"])
    def logout():
        session.clear()
        return jsonify({"success": True})

    @app.route("/api/auth/me", methods=["GET"])
    def auth_me():
        user = get_current_user(get_db)
        if not user:
            return jsonify({"success": True, "authenticated": False})
        return jsonify({"success": True, "authenticated": True, "user": user})


def get_current_user(get_db):
    """Returns the logged-in user's dict, or None."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, name, picture FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def login_required(get_db):
    """Route decorator factory: 401s JSON requests that lack a logged-in session."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            user = get_current_user(get_db)
            if not user:
                return jsonify({"success": False, "error": "Sign in with Google required."}), 401
            request.current_user = user
            return view_func(*args, **kwargs)

        return wrapped

    return decorator
