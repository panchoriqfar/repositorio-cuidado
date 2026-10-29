import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.auth import create_access_token

client = TestClient(app)


def test_unauthenticated_admin_endpoints_return_401():
    """Valida que endpoints administrativos retornen 401 Unauthorized con WWW-Authenticate si no hay token."""
    rutas_protegidas = [
        ("GET", "/api/admin/cuidadores"),
        ("GET", "/api/admin/medicos"),
        ("GET", "/api/admin/bloques"),
        ("POST", "/api/medicamentos/"),
        ("POST", "/api/medicamentos/1/horarios"),
        ("DELETE", "/api/medicamentos/1"),
        ("DELETE", "/api/medicamentos/horarios/1"),
        ("GET", "/api/admin/usuarios"),
    ]

    for metodo, ruta in rutas_protegidas:
        if metodo == "GET":
            resp = client.get(ruta)
        elif metodo == "POST":
            resp = client.post(ruta, json={})
        elif metodo == "DELETE":
            resp = client.delete(ruta)
        assert resp.status_code == 401, f"Fallo en {metodo} {ruta}: esperaba 401 y recibio {resp.status_code}"
        assert "WWW-Authenticate" in resp.headers


def test_login_invalid_credentials_returns_www_authenticate():
    """Valida que un login fallido retorne 401 con WWW-Authenticate: Bearer."""
    resp = client.post("/api/auth/login", json={"username": "fake_user", "password": "wrong_password"})
    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


def test_validar_formato_telefono_chileno_schemas():
    """Valida que los esquemas de cuidadores y personal médico apliquen el formato chileno +569XXXXXXXX."""
    from app.schemas import CuidadorCreate, PersonalMedicoCreate
    from pydantic import ValidationError

    # Telefono correcto
    cuid_valido = CuidadorCreate(
        nombre="Valeria",
        telefono_whatsapp="+56912345678",
        mail="valeria@test.com"
    )
    assert cuid_valido.telefono_whatsapp == "+56912345678"

    # Telefono chileno invalido en Cuidador
    with pytest.raises(ValidationError):
        CuidadorCreate(
            nombre="Valeria",
            telefono_whatsapp="123456",
            mail="valeria@test.com"
        )

    # Telefono chileno invalido en PersonalMedico
    with pytest.raises(ValidationError):
        PersonalMedicoCreate(
            nombre="Dr. Mario",
            especialidad="Cardiología",
            telefono_whatsapp="987654321"  # Falta +56
        )

    # Telefono opcional vacío o válido en PersonalMedico
    med_valido = PersonalMedicoCreate(
        nombre="Dr. Mario",
        especialidad="Cardiología",
        telefono_whatsapp="+56987654321"
    )
    assert med_valido.telefono_whatsapp == "+56987654321"
