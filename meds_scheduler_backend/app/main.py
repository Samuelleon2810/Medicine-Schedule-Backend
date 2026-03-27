from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, field_validator
import httpx
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.database import (
    get_supabase_auth_url,
    get_supabase_headers,
    get_supabase_rest_url,
)

limiter = Limiter(key_func=get_remote_address)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Cabeceras de seguridad recomendadas (OWASP)."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response


class SupabaseAuthMiddleware(BaseHTTPMiddleware):
    """
    Protege endpoints sensibles validando el JWT de Supabase (Authorization: Bearer).
    Nota: El frontend envía el token, pero este middleware hace cumplir la verificación en el backend.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Permitir assets/páginas y endpoints públicos
        public_prefixes = ("/css/", "/js/", "/sql/", "/pages/")
        public_paths = ("/", "/health", "/api/supabase-status", "/auth/login", "/auth/register")
        if path in public_paths or path.startswith(public_prefixes):
            return await call_next(request)

        # Proteger APIs de negocio
        protected_prefixes = ("/medicamentos", "/estadisticas")
        if not path.startswith(protected_prefixes):
            return await call_next(request)

        # Permitir preflight CORS
        if request.method.upper() == "OPTIONS":
            return await call_next(request)

        auth = request.headers.get("authorization") or ""
        if not auth.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Falta Authorization Bearer token")

        token = auth.split(" ", 1)[1].strip()
        if not token:
            raise HTTPException(status_code=401, detail="Token vacío")

        # Verificar token contra Supabase Auth
        auth_url = get_supabase_auth_url()
        headers = {
            "apikey": get_supabase_headers()["apikey"],
            "Authorization": f"Bearer {token}",
        }
        try:
            async with httpx.AsyncClient(base_url=auth_url, headers=headers, timeout=8) as client:
                r = await client.get("/user")
            if r.status_code >= 400:
                raise HTTPException(status_code=401, detail="Token inválido o expirado")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=401, detail="No se pudo validar el token")

        return await call_next(request)


class AuthLogin(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("La contraseña no puede estar vacía")
        return v.strip()


class AuthRegister(BaseModel):
    email: EmailStr
    password: str
    nombre: str | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres")
        return v

    @field_validator("nombre")
    @classmethod
    def nombre_max_length(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 120:
            raise ValueError("Nombre demasiado largo")
        return v.strip() if v else None


class MedicamentoCrear(BaseModel):
    nombre: str
    dosis: str
    cantidad: int
    precio: float

    @field_validator("nombre", "dosis")
    @classmethod
    def strip_str(cls, v: str) -> str:
        return v.strip() if v else ""

    @field_validator("nombre")
    @classmethod
    def nombre_length(cls, v: str) -> str:
        if len(v) > 200:
            raise ValueError("Nombre demasiado largo")
        return v

    @field_validator("cantidad")
    @classmethod
    def cantidad_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("La cantidad no puede ser negativa")
        return v

    @field_validator("precio")
    @classmethod
    def precio_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("El precio no puede ser negativo")
        return v


class MedicamentoActualizar(BaseModel):
    nombre: str | None = None
    dosis: str | None = None
    cantidad: int | None = None
    precio: float | None = None

    @field_validator("cantidad")
    @classmethod
    def cantidad_non_negative(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("La cantidad no puede ser negativa")
        return v

    @field_validator("precio")
    @classmethod
    def precio_non_negative(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError("El precio no puede ser negativo")
        return v


class MedicamentoVenta(BaseModel):
    id: int
    cantidad: int
    monto: float

    @field_validator("cantidad")
    @classmethod
    def cantidad_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("La cantidad debe ser mayor que 0")
        return v


def create_app() -> FastAPI:
    app = FastAPI(title="Plataforma de Agendamiento de Medicamentos", version="0.1.0")

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(SupabaseAuthMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["Sistema"])
    async def health_check():
        return {"status": "ok", "message": "API de agendamiento de medicamentos lista"}

    @app.get("/api/supabase-status", tags=["Sistema"])
    async def supabase_status():
        """Comprueba si la API puede conectar con Supabase. Usado por el indicador del panel."""
        try:
            base_url = get_supabase_rest_url()
            headers = get_supabase_headers()
            async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=5) as client:
                r = await client.get("/inventario", params={"select": "id", "limit": "1"})
            return {"connected": r.status_code < 400}
        except Exception:
            return {"connected": False}

    @app.post("/auth/login", tags=["Auth"])
    @limiter.limit("8/minute")
    async def login(request: Request, body: AuthLogin):
        """Inicio de sesión con Supabase Auth (email + contraseña)."""
        try:
            auth_url = get_supabase_auth_url()
            headers = {
                "apikey": get_supabase_headers()["apikey"],
                "Content-Type": "application/json",
            }
            async with httpx.AsyncClient(base_url=auth_url, headers=headers, timeout=10) as client:
                r = await client.post(
                    "/token?grant_type=password",
                    json={"grant_type": "password", "email": body.email, "password": body.password},
                )
            if r.status_code >= 400:
                detail = (r.json() or {}).get("error_description") or r.text
                raise HTTPException(status_code=401, detail=detail)
            data = r.json()
            return {"access_token": data.get("access_token"), "user": data.get("user")}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/auth/register", tags=["Auth"])
    @limiter.limit("5/minute")
    async def register(request: Request, body: AuthRegister):
        """Registro de usuario con Supabase Auth."""
        try:
            auth_url = get_supabase_auth_url()
            headers = {
                "apikey": get_supabase_headers()["apikey"],
                "Content-Type": "application/json",
            }
            payload = {"email": body.email, "password": body.password}
            if body.nombre:
                payload["data"] = {"nombre": body.nombre}
            async with httpx.AsyncClient(base_url=auth_url, headers=headers, timeout=10) as client:
                r = await client.post("/signup", json=payload)
            if r.status_code >= 400:
                detail = (r.json() or {}).get("msg") or (r.json() or {}).get("error_description") or r.text
                raise HTTPException(status_code=400, detail=detail)
            data = r.json()
            return {"access_token": data.get("access_token"), "user": data.get("user")}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/medicamentos", tags=["Medicamentos"])
    async def listar_medicamentos():
        """Lista todo el inventario."""
        try:
            base_url = get_supabase_rest_url()
            headers = get_supabase_headers()
            async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=10) as client:
                r = await client.get("/inventario", params={"select": "*", "order": "id.asc"})
            if r.status_code >= 400:
                raise HTTPException(status_code=500, detail=r.text)
            return {"status": "ok", "data": r.json()}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/medicamentos/{medicamento_id:int}", tags=["Medicamentos"])
    async def obtener_medicamento(medicamento_id: int):
        """Obtiene un medicamento por ID."""
        try:
            base_url = get_supabase_rest_url()
            headers = get_supabase_headers()
            async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=10) as client:
                r = await client.get("/inventario", params={"select": "*", "id": f"eq.{medicamento_id}"})
            if r.status_code >= 400:
                raise HTTPException(status_code=500, detail=r.text)
            rows = r.json()
            if not rows:
                raise HTTPException(status_code=404, detail="Medicamento no encontrado")
            return {"status": "ok", "data": rows[0]}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.put("/medicamentos/{medicamento_id:int}", tags=["Medicamentos"])
    async def actualizar_medicamento(medicamento_id: int, body: MedicamentoActualizar):
        """Actualiza un medicamento. Solo se envían los campos que se desean cambiar."""
        try:
            base_url = get_supabase_rest_url()
            headers = get_supabase_headers()
            payload = {k: v for k, v in body.model_dump().items() if v is not None}
            if not payload:
                raise HTTPException(status_code=400, detail="No hay campos para actualizar")
            if "cantidad" in payload:
                payload["cantidad"] = int(payload["cantidad"])
            if "precio" in payload:
                payload["precio"] = float(payload["precio"])
            async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=10) as client:
                r = await client.patch(
                    "/inventario",
                    params={"id": f"eq.{medicamento_id}"},
                    json=payload,
                )
            if r.status_code >= 400:
                raise HTTPException(status_code=500, detail=r.text)
            updated = r.json()
            return {"status": "ok", "data": updated[0] if updated else {"id": medicamento_id}}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.delete("/medicamentos/{medicamento_id:int}", tags=["Medicamentos"])
    async def eliminar_medicamento(medicamento_id: int):
        """Elimina un medicamento del inventario."""
        try:
            base_url = get_supabase_rest_url()
            headers = get_supabase_headers()
            async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=10) as client:
                r = await client.delete("/inventario", params={"id": f"eq.{medicamento_id}"})
            if r.status_code >= 400:
                raise HTTPException(status_code=500, detail=r.text)
            return {"status": "ok", "message": "Medicamento eliminado"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/medicamentos/crear", tags=["Medicamentos"])
    async def crear_medicamento(body: MedicamentoCrear):
        """
        Crea un medicamento en la tabla 'inventario' de Supabase usando la API REST.
        """
        try:
            base_url = get_supabase_rest_url()
            headers = get_supabase_headers()

            async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=10) as client:
                response = await client.post(
                    "/inventario",
                    json={
                        "nombre": body.nombre,
                        "dosis": body.dosis,
                        "cantidad": int(body.cantidad),
                        "precio": float(body.precio),
                    },
                )

            if response.status_code >= 400:
                raise HTTPException(
                    status_code=500,
                    detail=f"Error desde Supabase ({response.status_code}): {response.text}",
                )

            data = response.json()
            return {"status": "ok", "data": data}
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error al guardar: {e!s}")

    @app.get("/medicamentos/inventario-bajo", tags=["Medicamentos"])
    async def medicamentos_inventario_bajo():
        """
        Devuelve medicamentos con cantidad < 5 desde la tabla 'inventario'.
        Requiere que la columna 'cantidad' exista en la tabla.
        """
        try:
            base_url = get_supabase_rest_url()
            headers = get_supabase_headers()

            params = {
                "select": "*",
                "cantidad": "lt.5",
            }

            async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=10) as client:
                response = await client.get("/inventario", params=params)

            if response.status_code >= 400:
                raise HTTPException(
                    status_code=500,
                    detail=f"Error desde Supabase ({response.status_code}): {response.text}",
                )

            data = response.json()
            return {"status": "ok", "data": data}
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error al consultar inventario: {e!s}")

    @app.post("/medicamentos/vender", tags=["Medicamentos"])
    async def vender_medicamento(body: MedicamentoVenta):
        """
        Resta la cantidad vendida al medicamento indicado.
        Valida que el monto entrante sea suficiente (precio * cantidad).
        Si la cantidad llega a 0, devuelve un mensaje de 'Sin stock'.
        Requiere columnas 'id', 'cantidad' y 'precio' en la tabla 'inventario'.
        """
        try:
            base_url = get_supabase_rest_url()
            headers = get_supabase_headers()

            async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=10) as client:
                # 1) Obtener el medicamento actual
                get_params = {
                    "select": "*",
                    "id": f"eq.{body.id}",
                }
                get_response = await client.get("/inventario", params=get_params)

                if get_response.status_code >= 400:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Error al buscar medicamento ({get_response.status_code}): {get_response.text}",
                    )

                rows = get_response.json()
                if not rows:
                    raise HTTPException(status_code=404, detail="Medicamento no encontrado")

                medicamento = rows[0]
                cantidad_actual = medicamento.get("cantidad")
                precio = medicamento.get("precio")
                if cantidad_actual is None:
                    raise HTTPException(
                        status_code=500,
                        detail="La columna 'cantidad' no existe o es nula en la tabla 'inventario'",
                    )

                if precio is None:
                    raise HTTPException(
                        status_code=500,
                        detail="La columna 'precio' no existe o es nula en la tabla 'inventario'",
                    )

                cantidad_actual = int(cantidad_actual)
                total_venta = float(precio) * body.cantidad
                if body.monto < total_venta:
                    raise HTTPException(
                        status_code=400,
                        detail="Monto insuficiente para realizar la venta",
                    )

                nueva_cantidad = cantidad_actual - body.cantidad
                if nueva_cantidad < 0:
                    raise HTTPException(
                        status_code=400,
                        detail="No hay suficiente stock para realizar la venta",
                    )

                # 2) Actualizar la cantidad en Supabase
                patch_params = {
                    "id": f"eq.{body.id}",
                }
                patch_response = await client.patch(
                    "/inventario",
                    params=patch_params,
                    json={"cantidad": int(nueva_cantidad)},
                )

                if patch_response.status_code >= 400:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Error al actualizar inventario ({patch_response.status_code}): {patch_response.text}",
                    )

                updated_rows = patch_response.json()
                updated = updated_rows[0] if updated_rows else {"id": body.id, "cantidad": nueva_cantidad}

                # Registrar venta en tabla ventas (si existe)
                try:
                    await client.post(
                        "/ventas",
                        json={
                            "medicamento_id": body.id,
                            "cantidad": body.cantidad,
                            "monto_total": round(total_venta, 2),
                        },
                    )
                except Exception:
                    pass

                if nueva_cantidad == 0:
                    return {
                        "status": "ok",
                        "message": "Sin stock",
                        "data": updated,
                    }

                return {
                    "status": "ok",
                    "message": "Venta registrada",
                    "data": updated,
                }
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error al vender medicamento: {e!s}")

    @app.get("/estadisticas/ventas", tags=["Estadísticas"])
    async def estadisticas_ventas():
        """Ventas agrupadas por día para gráficos. Requiere tabla 'ventas' con created_at."""
        try:
            base_url = get_supabase_rest_url()
            headers = get_supabase_headers()
            async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=10) as client:
                r = await client.get(
                    "/ventas",
                    params={"select": "id,cantidad,monto_total,created_at", "order": "created_at.asc"},
                )
            if r.status_code >= 400:
                return {"status": "ok", "data": []}
            rows = r.json()
            from collections import defaultdict
            by_date = defaultdict(lambda: {"cantidad": 0, "monto": 0.0})
            for row in rows:
                created = row.get("created_at") or ""
                day = created[:10] if isinstance(created, str) else str(created)[:10]
                by_date[day]["cantidad"] += int(row.get("cantidad") or 0)
                by_date[day]["monto"] += float(row.get("monto_total") or 0)
            data = [{"fecha": k, **v} for k, v in sorted(by_date.items())]
            return {"status": "ok", "data": data}
        except Exception:
            return {"status": "ok", "data": []}

    @app.get("/estadisticas/inventario", tags=["Estadísticas"])
    async def estadisticas_inventario():
        """Inventario actual para gráficos (nombre y cantidad)."""
        try:
            base_url = get_supabase_rest_url()
            headers = get_supabase_headers()
            async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=10) as client:
                r = await client.get("/inventario", params={"select": "id,nombre,cantidad,precio", "order": "nombre.asc"})
            if r.status_code >= 400:
                raise HTTPException(status_code=500, detail=r.text)
            return {"status": "ok", "data": r.json()}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    static_dir = Path(__file__).parent.parent / "static"
    pages_dir = static_dir / "pages"
    css_dir = static_dir / "css"
    js_dir = static_dir / "js"
    sql_dir = static_dir / "sql"

    # Servir assets
    if css_dir.exists():
        app.mount("/css", StaticFiles(directory=str(css_dir), html=False), name="css")
    if js_dir.exists():
        app.mount("/js", StaticFiles(directory=str(js_dir), html=False), name="js")
    if sql_dir.exists():
        app.mount("/sql", StaticFiles(directory=str(sql_dir), html=False), name="sql")

    # Servir páginas HTML
    if pages_dir.exists():
        app.mount("/", StaticFiles(directory=str(pages_dir), html=True), name="pages")

    return app


app = create_app()

