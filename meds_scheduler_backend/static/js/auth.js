/**
 * Auth: login, registro, logout
 */
function isLoggedIn() {
  return !!localStorage.getItem('farmacia_token');
}

function requireAuth() {
  if (!isLoggedIn()) {
    window.location.href = '/';
    return false;
  }
  return true;
}

function getCurrentUser() {
  try {
    return JSON.parse(localStorage.getItem('farmacia_user') || 'null');
  } catch {
    return null;
  }
}

function setSession(access_token, user) {
  localStorage.setItem('farmacia_token', access_token);
  localStorage.setItem('farmacia_user', JSON.stringify(user || {}));
}

function logout() {
  localStorage.removeItem('farmacia_token');
  localStorage.removeItem('farmacia_user');
  window.location.href = '/';
}

async function login(email, password) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Error al iniciar sesión');
  setSession(data.access_token, data.user);
  return data;
}

async function register(email, password, nombre) {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, nombre: nombre || null }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Error al registrarse');
  if (data.access_token) setSession(data.access_token, data.user);
  return data;
}
