/**
 * API y estado de Supabase
 */
const API_BASE = '';

async function fetchWithAuth(url, options = {}) {
  const token = localStorage.getItem('farmacia_token');
  const headers = { ...options.headers };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${url}`, { ...options, headers });
  if (res.status === 401) {
    localStorage.removeItem('farmacia_token');
    localStorage.removeItem('farmacia_user');
    window.location.href = '/';
    return;
  }
  return res;
}

async function checkSupabaseStatus() {
  try {
    const res = await fetch(`${API_BASE}/api/supabase-status`);
    const data = await res.json();
    return data.connected === true;
  } catch {
    return false;
  }
}

function updateSupabaseIndicator(connected) {
  const el = document.getElementById('supabase-status');
  if (!el) return;
  if (connected) {
    el.textContent = 'Conectado Online';
    el.className = 'px-3 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/30';
  } else {
    el.textContent = 'Sin conexión';
    el.className = 'px-3 py-1 rounded-full text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/30';
  }
}

async function refreshSupabaseStatus() {
  const connected = await checkSupabaseStatus();
  updateSupabaseIndicator(connected);
  return connected;
}
