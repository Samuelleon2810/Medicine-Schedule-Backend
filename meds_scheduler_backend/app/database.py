import os

from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def _validate_env() -> None:
    """Valida que las variables necesarias para Supabase estén configuradas."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError(
            "Faltan SUPABASE_URL o SUPABASE_KEY en el archivo .env. "
            "Configura las variables en .env con los datos de tu proyecto Supabase."
        )


def get_supabase_rest_url() -> str:
    """
    Devuelve la URL base del API REST de Supabase (rest/v1).
    """
    _validate_env()
    # Ejemplo: https://xyzcompany.supabase.co/rest/v1
    return f"{SUPABASE_URL.rstrip('/')}/rest/v1"


def get_supabase_headers() -> dict:
    """
    Devuelve los headers necesarios para autenticarse contra el API REST.
    Incluye apikey y Authorization: Bearer usando la clave pública (anon).
    """
    _validate_env()
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def get_supabase_auth_url() -> str:
    """URL base del API de autenticación de Supabase."""
    _validate_env()
    return f"{SUPABASE_URL.rstrip('/')}/auth/v1"
