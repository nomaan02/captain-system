# GUI JWT Authentication — Implementation Plan

## Problem

The audit added JWT authentication middleware to the API (Gap G-002). The backend is fully implemented and enforced. The GUI has zero auth integration — every API call returns 401, every WebSocket connection gets closed with 4003.

## Current State

### Backend (complete, no changes needed)

| Component | Status | Location |
|-----------|--------|----------|
| JWT middleware | Enforced on all HTTP paths except exempt set | `api.py:113-145` |
| Exempt paths | `/api/health`, `/api/status`, `/auth/token`, `/docs`, `/openapi.json`, `/redoc` | `api.py:103-110` |
| Token issuer | `POST /auth/token` — accepts `{api_key, user_id}`, returns `{access_token, token_type, expires_in}` | `api.py:279-309` |
| WebSocket auth | Requires `?token=<jwt>` query param, validates `sub` matches path `user_id` | `api.py:317-347` |
| Env vars | `JWT_SECRET_KEY` (auto-generates if empty), `API_SECRET_KEY` (required for login), `JWT_EXPIRY_HOURS` (default 24) | `api.py:92-95` |

### GUI (needs all auth work)

| Component | Status | Location |
|-----------|--------|----------|
| API client | Native `fetch`, no auth headers | `src/api/client.js` |
| WebSocket | Connects to `/ws/{userId}`, no token param | `src/ws/useWebSocket.js:32` |
| Login page | Does not exist | — |
| Auth context | Does not exist | — |
| Token storage | Does not exist | — |
| Route protection | None — all routes publicly accessible | `src/App.jsx` |

---

## Phase 0: Environment Variables

### What to do

Add three variables to `.env.template` and your actual `.env`:

```bash
# ── JWT AUTHENTICATION ───────────────────────────────────────────
JWT_SECRET_KEY=   # SET THIS — generate: python3 -c "import secrets; print(secrets.token_hex(32))"
API_SECRET_KEY=   # SET THIS — generate: python3 -c "import secrets; print(secrets.token_urlsafe(32))"
JWT_EXPIRY_HOURS=24
```

Pass them through in `docker-compose.yml` to `captain-command`:

```yaml
JWT_SECRET_KEY: ${JWT_SECRET_KEY}
API_SECRET_KEY: ${API_SECRET_KEY}
JWT_EXPIRY_HOURS: ${JWT_EXPIRY_HOURS:-24}
```

### Files to change

- `.env.template` — add the 3 vars with generation hints
- `.env` — add actual generated values
- `docker-compose.yml` — pass vars to `captain-command` service environment block

### Verification

```bash
# After rebuild, confirm auth endpoint is available:
curl -s http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"api_key": "<your API_SECRET_KEY>"}' | python3 -m json.tool
# Should return: {"access_token": "eyJ...", "token_type": "bearer", "expires_in": 86400}
```

---

## Phase 1: Auth Context & Token Storage

### What to create

**New file:** `captain-gui/src/auth/AuthContext.jsx`

This React context manages the full auth lifecycle:
- Stores JWT token in `localStorage` under key `captain_jwt`
- Provides `login(apiKey)`, `logout()`, and `token` to all components
- On mount: checks `localStorage` for existing token, validates it hasn't expired (decode the `exp` claim client-side)
- On login: calls `POST /auth/token` with `{api_key: apiKey}`, stores the returned `access_token`
- On logout: clears `localStorage`, resets state
- Exposes `isAuthenticated` boolean derived from token presence + non-expired

### Pattern to follow

```jsx
import { createContext, useContext, useState, useEffect, useCallback } from 'react';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);

  // On mount: restore token from localStorage if not expired
  useEffect(() => {
    const stored = localStorage.getItem('captain_jwt');
    if (stored && !isExpired(stored)) {
      setToken(stored);
    } else {
      localStorage.removeItem('captain_jwt');
    }
    setLoading(false);
  }, []);

  const login = useCallback(async (apiKey) => {
    const res = await fetch('/auth/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: apiKey, user_id: 'primary_user' }),
    });
    if (!res.ok) throw new Error('Authentication failed');
    const data = await res.json();
    localStorage.setItem('captain_jwt', data.access_token);
    setToken(data.access_token);
    return data;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('captain_jwt');
    setToken(null);
  }, []);

  return (
    <AuthContext.Provider value={{ token, login, logout, isAuthenticated: !!token, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);

function isExpired(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return payload.exp * 1000 < Date.now();
  } catch { return true; }
}
```

### Files to change

- **Create:** `captain-gui/src/auth/AuthContext.jsx`
- **Edit:** `captain-gui/src/main.jsx` — wrap `<App />` with `<AuthProvider>`

### Verification

Check the context is available by temporarily adding `console.log(useAuth())` in any component — should return `{token: null, isAuthenticated: false, ...}`.

---

## Phase 2: Login Page

### What to create

**New file:** `captain-gui/src/pages/LoginPage.jsx`

Simple form with one field (API secret key). On submit: calls `login(apiKey)` from auth context. On success: redirects to `/`. On failure: shows error message.

### Design

- Centered card, "Captain System" title
- Single password-type input for the API key
- Submit button
- Error display below the form
- No registration flow (single-user system, key is set in `.env`)

### Pattern

```jsx
import { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { useNavigate } from 'react-router-dom';

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [apiKey, setApiKey] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(apiKey);
      navigate('/');
    } catch {
      setError('Invalid API key');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
      <form onSubmit={handleSubmit} style={{ width: 360, padding: 32 }}>
        <h2>Captain System</h2>
        <input
          type="password"
          placeholder="API Secret Key"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          autoFocus
        />
        <button type="submit" disabled={loading || !apiKey}>
          {loading ? 'Authenticating...' : 'Login'}
        </button>
        {error && <p style={{ color: 'red' }}>{error}</p>}
      </form>
    </div>
  );
}
```

### Files to change

- **Create:** `captain-gui/src/pages/LoginPage.jsx`
- **Edit:** `captain-gui/src/App.jsx` — add login route, wrap authenticated routes with a guard

### Verification

Navigate to `/login` — form should render. Submit with wrong key — shows error. Submit with correct key — redirects to `/` with token stored in localStorage.

---

## Phase 3: API Client — Inject Bearer Token

### What to change

**Edit:** `captain-gui/src/api/client.js`

The `fetchJson` function needs to read the token from `localStorage` and inject it as a `Bearer` header on every request.

### Exact change

In `fetchJson(url, options)` (line 3-9), add:

```javascript
const token = localStorage.getItem('captain_jwt');
const headers = {
  'Content-Type': 'application/json',
  ...(token ? { Authorization: `Bearer ${token}` } : {}),
  ...options?.headers,
};
```

Also add a 401 interceptor: if the API returns 401, clear the stored token and redirect to `/login`:

```javascript
if (res.status === 401) {
  localStorage.removeItem('captain_jwt');
  window.location.href = '/login';
  return;
}
```

### Files to change

- **Edit:** `captain-gui/src/api/client.js` — modify `fetchJson`

### Verification

```bash
# Open browser DevTools > Network tab
# After login, every API call should show:
# Request Headers → Authorization: Bearer eyJ...
```

---

## Phase 4: WebSocket — Pass Token Query Param

### What to change

**Edit:** `captain-gui/src/ws/useWebSocket.js`

The WebSocket URL at line 32 currently builds:
```javascript
`${proto}//${host}/ws/${userId}`
```

Change to:
```javascript
const token = localStorage.getItem('captain_jwt');
const url = `${proto}//${host}/ws/${userId}${token ? `?token=${token}` : ''}`;
```

Also handle close code 4003 (auth failure) — clear token and redirect to login instead of reconnecting:

```javascript
if (event.code === 4003) {
  localStorage.removeItem('captain_jwt');
  window.location.href = '/login';
  return; // don't reconnect
}
```

### Files to change

- **Edit:** `captain-gui/src/ws/useWebSocket.js` — add token to URL, handle 4003

### Verification

Browser DevTools > Network > WS tab — the WebSocket URL should show `?token=eyJ...` and the connection should stay open (not immediately close with 4003).

---

## Phase 5: Route Protection

### What to change

**Edit:** `captain-gui/src/App.jsx`

Wrap all authenticated routes in a guard component that redirects to `/login` if not authenticated:

```jsx
function RequireAuth({ children }) {
  const { isAuthenticated, loading } = useAuth();
  if (loading) return null; // or a spinner
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return children;
}
```

Route structure becomes:
```jsx
<Routes>
  <Route path="/login" element={<LoginPage />} />
  <Route element={<RequireAuth><Layout /></RequireAuth>}>
    <Route path="/" element={<DashboardPage />} />
    <Route path="/models" element={<ModelsPage />} />
    {/* ... all other routes ... */}
  </Route>
</Routes>
```

### Files to change

- **Edit:** `captain-gui/src/App.jsx` — add `RequireAuth` wrapper, add `/login` route

### Verification

- Open `http://localhost` in incognito — should redirect to `/login`
- Login with API key — should redirect to dashboard, all pages accessible
- Clear localStorage and refresh — should redirect back to `/login`

---

## Phase 6: Rebuild & End-to-End Verification

### Steps

```bash
# 1. Rebuild GUI and Command
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build captain-gui captain-command

# 2. Wait for GUI to deploy, restart nginx
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d nginx

# 3. Verify login flow
# Open http://localhost — should redirect to /login
# Enter your API_SECRET_KEY from .env
# Should redirect to dashboard with all green lights

# 4. Verify API calls have auth
# DevTools > Network — all /api/* calls should have Authorization: Bearer header

# 5. Verify WebSocket connects
# DevTools > Network > WS — connection to /ws/primary_user?token=... should be open

# 6. Verify token persistence
# Refresh the page — should stay logged in (token in localStorage)

# 7. Verify token expiry
# Wait 24h or temporarily set JWT_EXPIRY_HOURS=0 — should redirect to login

# 8. Run unit tests
PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
  python3 -B -m pytest tests/ \
  --ignore=tests/test_integration_e2e.py \
  --ignore=tests/test_pipeline_e2e.py \
  --ignore=tests/test_pseudotrader_account.py \
  --ignore=tests/test_offline_feedback.py \
  --ignore=tests/test_stress.py \
  --ignore=tests/test_account_lifecycle.py \
  -v
```

### Checklist

- [ ] `/login` page renders
- [ ] Wrong API key shows error
- [ ] Correct API key redirects to dashboard
- [ ] All API status lights green
- [ ] WebSocket connected (WS light green)
- [ ] QuestDB light green
- [ ] Redis light green
- [ ] Page refresh stays authenticated
- [ ] Incognito window redirects to login
- [ ] `docker stop captain-command && docker start captain-command` — token survives restart (if JWT_SECRET_KEY is set in .env)
- [ ] 95/95 tests pass

---

## File Change Summary

| Action | File | Phase |
|--------|------|-------|
| Edit | `.env.template` | 0 |
| Edit | `.env` | 0 |
| Edit | `docker-compose.yml` | 0 |
| Create | `captain-gui/src/auth/AuthContext.jsx` | 1 |
| Edit | `captain-gui/src/main.jsx` | 1 |
| Create | `captain-gui/src/pages/LoginPage.jsx` | 2 |
| Edit | `captain-gui/src/api/client.js` | 3 |
| Edit | `captain-gui/src/ws/useWebSocket.js` | 4 |
| Edit | `captain-gui/src/App.jsx` | 5 |

**9 files total (2 new, 7 edits). Zero backend changes.**

---

## Anti-Patterns to Avoid

- Do NOT disable the JWT middleware or add more exempt paths as a workaround
- Do NOT store the API secret key in the GUI code or bundle
- Do NOT use cookies for JWT storage (localStorage is correct for SPA + same-origin API)
- Do NOT add a registration endpoint — this is a single-user/known-operator system
- Do NOT decode the JWT on the server for the GUI's benefit — the GUI only needs the opaque token string
- Do NOT change the backend auth code — it is complete and tested
