# Meds Scheduler Backend (Farmacia + Supabase)

Backend en **FastAPI** conectado a **Supabase** vía **REST (httpx)**, con un panel web (HTML + Tailwind CDN) servido desde el mismo servidor.

## Requisitos

- Python 3.12+ (ideal)
- Cuenta y proyecto en Supabase

## Configuración

### 1) Variables de entorno

Crea un archivo `.env` en la raíz del proyecto con:

```env
SUPABASE_URL=https://TU-PROYECTO.supabase.co
SUPABASE_KEY=TU_ANON_PUBLIC_KEY
```

- **SUPABASE_URL**: Supabase Dashboard → Project Settings → API → Project URL
- **SUPABASE_KEY**: Supabase Dashboard → Project Settings → API → anon public key

### 2) Instalar dependencias

En la raíz del proyecto:

```bash
pip install -r requirements.txt
```

### 3) Ejecutar el servidor

```bash
uvicorn app.main:app --reload
```

Abrir:

- **Login**: `http://127.0.0.1:8000/`
- **Registro**: `http://127.0.0.1:8000/register.html`
- **Dashboard**: `http://127.0.0.1:8000/dashboard.html`
- **Inventario (CRUD)**: `http://127.0.0.1:8000/medicamentos.html`

## Estructura del frontend (estáticos)

Los archivos están dentro de `static/`:

- **Páginas HTML**: `static/pages/`
  - `index.html` (login)
  - `register.html`
  - `dashboard.html`
  - `medicamentos.html`
- **CSS**: `static/css/`
  - `main.css`
  - `components.css`
  - `animations.css`
- **JS**: `static/js/`
  - `api.js` (status Supabase + fetch con token)
  - `auth.js` (login/register/logout)
- **SQL utilitario**: `static/sql/`
  - `ventas-table.sql`

El servidor monta:

- `/css` → `static/css`
- `/js` → `static/js`
- `/sql` → `static/sql`
- `/` → `static/pages` (con `html=True`)

## Tablas en Supabase

### Tabla `inventario`

Debe existir en `public` y tener al menos:

- `id` (bigint/bigserial, PK)
- `nombre` (text)
- `dosis` (text)
- `cantidad` (bigint o integer)
- `precio` (numeric/decimal/double precision)

### Tabla `ventas` (opcional, para gráficas)

Para habilitar estadísticas de ventas, ejecuta en Supabase SQL Editor:

- `static/sql/ventas-table.sql`

La API intenta insertar en `/ventas` cada vez que se registra una venta.

## API endpoints

### Sistema

- `GET /health`
- `GET /api/supabase-status`
  - Respuesta: `{ "connected": true|false }`
  - Lo usa el “badge” de estado en el panel.

### Auth (Supabase Auth)

- `POST /auth/login`
  - Body:
    - `email` (Email)
    - `password` (string)
  - Respuesta: `{ access_token, user }`
- `POST /auth/register`
  - Body:
    - `email` (Email)
    - `password` (mín. 8)
    - `nombre` (opcional)

El frontend guarda `access_token` en `localStorage` como `farmacia_token` (ver sección de seguridad).

### Medicamentos (inventario)

> **Requieren token** `Authorization: Bearer <jwt>` (ver seguridad).

- `GET /medicamentos`
- `GET /medicamentos/{id}`
- `POST /medicamentos/crear`
  - Body: `{ nombre, dosis, cantidad, precio }`
- `PUT /medicamentos/{id}`
  - Body parcial: `{ nombre?, dosis?, cantidad?, precio? }`
- `DELETE /medicamentos/{id}`
- `GET /medicamentos/inventario-bajo`
  - Filtra por `cantidad < 5`

### Ventas

> Requiere token.

- `POST /medicamentos/vender`
  - Body: `{ id, cantidad, monto }`
  - Valida:
    - que exista stock suficiente
    - que `monto >= precio * cantidad`
  - Si cantidad llega a 0: responde `message: "Sin stock"`

### Estadísticas

> Requieren token.

- `GET /estadisticas/inventario`
- `GET /estadisticas/ventas` (si existe tabla `ventas`)

## Seguridad (repasada)

### Hecho en el backend

- **Cabeceras OWASP**: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, etc.
- **CORS** restringido a `localhost`.
- **Rate limiting** (SlowAPI) para login/registro (mitiga brute-force).
- **Validación de inputs** (Pydantic):
  - emails válidos, contraseña mínima, cantidad/precio no negativos, etc.
- **Protección real de rutas**:
  - Se añadió `SupabaseAuthMiddleware` que **valida el JWT** contra `Supabase Auth /auth/v1/user`.
  - Esto evita que alguien llame endpoints de negocio solo “saltándose el frontend”.

### Cosas a tener en cuenta (mejoras futuras)

- **RLS en Supabase**: ahora mismo lo tienes desactivado para desarrollo. En producción:
  - habilita RLS
  - crea políticas para `authenticated`
  - usa el JWT de usuario para operar sobre su inventario/tenant
- **Token en localStorage**: es práctico, pero en producción es mejor usar cookies `HttpOnly` y CSRF.
- **Anon key**: es una clave pública, pero evita exponer claves de servicio. No uses `service_role` en el backend sin controles.
- **HTTPS**: obligatorio si lo despliegas fuera de localhost.

## Troubleshooting

- Si el panel muestra “Sin conexión a Supabase”:
  - revisa `.env` (URL/KEY)
  - revisa que tu tabla `inventario` exista
  - prueba `GET /api/supabase-status`
- Si recibes `401` en endpoints `/medicamentos` o `/estadisticas`:
  - inicia sesión en el panel para generar `farmacia_token`
  - o envía `Authorization: Bearer <token>` manualmente

