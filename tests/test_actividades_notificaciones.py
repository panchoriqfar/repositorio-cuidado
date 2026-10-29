import pytest
from datetime import date, time, datetime, timedelta
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Cuidador, PersonalMedico, BloqueTurno, ActividadMedica
from app.email_service import (
    construir_contenido_solo_actividades,
    enviar_correos_solo_actividades_periodo,
)


@pytest.fixture
def db_session():
    """Crea una sesión de base de datos SQLite en memoria aislada para pruebas."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    medico = PersonalMedico(id_medico=1, nombre="Dr. Carlos", apellido="Gómez", especialidad="Geriatría", activo=True)
    session.add(medico)

    cuid1 = Cuidador(id_cuidador=1, nombre="Claudia", apellido="Valenzuela", mail="claudia@test.com", telefono_whatsapp="+56911112222", activo=True)
    cuid2 = Cuidador(id_cuidador=2, nombre="Manuel", apellido="Reyes", mail="manuel@test.com", telefono_whatsapp="+56933334444", activo=True)
    cuid_inactivo = Cuidador(id_cuidador=3, nombre="Inactivo", apellido="Pérez", mail="inactivo@test.com", telefono_whatsapp="+56955556666", activo=False)
    session.add_all([cuid1, cuid2, cuid_inactivo])

    session.commit()
    yield session
    session.close()


def test_construir_contenido_solo_actividades_vacio():
    """Verifica que si no hay actividades, el contenido indique adecuadamente que no hay actividades programadas."""
    asunto, texto, html = construir_contenido_solo_actividades([], "Semana de Prueba", "Equipo")
    assert "Actividades y Visitas Médicas (Semana de Prueba)" in asunto
    assert "No hay actividades médicas programadas para este periodo." in texto
    assert "No hay actividades médicas programadas para este periodo." in html
    assert "tu turno para el día" not in texto.lower()
    assert "bloque" not in texto.lower()
    assert "medicamento" not in texto.lower()


def test_construir_contenido_solo_actividades_con_datos(db_session):
    """Verifica la construcción del asunto, texto y HTML con actividades médicas y médicos asignados."""
    medico = db_session.query(PersonalMedico).filter_by(id_medico=1).first()

    act1 = ActividadMedica(
        id_actividad=1,
        fecha=date(2026, 10, 28),
        hora=time(10, 30),
        titulo="Curación avanzada de herida",
        descripcion="Limpieza y cambio de apósitos estériles",
        id_medico=medico.id_medico,
        medico_asignado=medico
    )
    act2 = ActividadMedica(
        id_actividad=2,
        fecha=date(2026, 10, 29),
        hora=time(16, 0),
        titulo="Kinesiología motora",
        descripcion=None,
        id_medico=None,
        medico_asignado=None
    )

    asunto, texto, html = construir_contenido_solo_actividades([act1, act2], "Semana del 26/10/2026 al 01/11/2026", "Claudia")
    assert "Actividades y Visitas Médicas (Semana del 26/10/2026 al 01/11/2026)" in asunto
    assert "Hola Claudia" in texto
    assert "Curación avanzada de herida" in texto
    assert "10:30 hrs" in texto
    assert "A cargo: Dr. Carlos Gómez" in texto
    assert "Limpieza y cambio de apósitos estériles" in texto
    assert "Kinesiología motora" in texto
    assert "16:00 hrs" in texto

    # Garantizar exclusividad (sin turnos ni medicamentos)
    assert "Tu turno para el día" not in texto
    assert "farmacológica" not in texto.lower()
    assert "pauta de medicamentos" not in texto.lower()

    # HTML
    assert "Curación avanzada de herida" in html
    assert "Dr. Carlos Gómez" in html


def test_enviar_correos_solo_actividades_manual(db_session):
    """Verifica el envío de correo de actividades médicas a un destinatario manual."""
    act = ActividadMedica(
        id_actividad=10,
        fecha=date(2026, 10, 28),
        hora=time(11, 0),
        titulo="Visita Médica de Control",
        descripcion="Revisión general",
        id_medico=1
    )
    db_session.add(act)
    db_session.commit()

    with patch("app.email_service.enviar_email_via_resend") as mock_resend:
        mock_resend.return_value = {"status": "success", "id": "email_act_test_1"}

        res = enviar_correos_solo_actividades_periodo(
            db=db_session,
            fecha_inicio=date(2026, 10, 28),
            fecha_fin=date(2026, 10, 28),
            destinatario_tipo="manual",
            email_manual="familiar@test.com"
        )

        assert res["tipo"] == "actividades"
        assert res["enviados"] == 1
        assert res["errores"] == 0
        assert mock_resend.called
        assert mock_resend.call_args[0][0] == "familiar@test.com"
        assert "Visita Médica de Control" in mock_resend.call_args[0][2]


def test_enviar_correos_solo_actividades_cuidador_y_todos(db_session):
    """Verifica el envío a un cuidador específico y a todos los cuidadores activos."""
    act = ActividadMedica(
        id_actividad=20,
        fecha=date(2026, 10, 28),
        hora=time(9, 0),
        titulo="Toma de muestras de sangre",
        id_medico=None
    )
    db_session.add(act)
    db_session.commit()

    with patch("app.email_service.enviar_email_via_resend") as mock_resend:
        mock_resend.return_value = {"status": "success", "id": "email_act_test_2"}

        # 1. Cuidador específico
        cuid1 = db_session.query(Cuidador).filter_by(id_cuidador=1).first()
        res_cuid = enviar_correos_solo_actividades_periodo(
            db=db_session,
            fecha_inicio=date(2026, 10, 26),
            fecha_fin=date(2026, 11, 1),
            destinatario_tipo="cuidador",
            id_cuidador=cuid1.id_cuidador
        )
        assert res_cuid["enviados"] == 1
        assert mock_resend.call_args[0][0] == cuid1.mail

        mock_resend.reset_mock()

        # 2. Todos los cuidadores activos (Claudia y Manuel, Inactivo excluido)
        res_todos = enviar_correos_solo_actividades_periodo(
            db=db_session,
            fecha_inicio=date(2026, 10, 26),
            fecha_fin=date(2026, 11, 1),
            destinatario_tipo="todos"
        )
        assert res_todos["enviados"] == 2
        assert mock_resend.call_count == 2


def test_enviar_correos_solo_actividades_email_invalido(db_session):
    """Verifica manejo de errores ante correo manual inválido."""
    res = enviar_correos_solo_actividades_periodo(
        db=db_session,
        fecha_inicio=date(2026, 10, 28),
        fecha_fin=date(2026, 10, 28),
        destinatario_tipo="manual",
        email_manual="correo-invalido-sin-arroba"
    )
    assert res["enviados"] == 0
    assert res["errores"] == 1
    assert "no válido" in res["detalles"][0]["detalle"]


def test_endpoint_enviar_email_actividades(db_session):
    """Verifica la función endpoint de FastAPI para el envío de actividades médicas."""
    from app.main import enviar_email_actividades
    from app.schemas import NotificacionEmailActividadesRequest
    from app.models import Usuario

    admin_user = Usuario(id_usuario=99, username="admin_test", rol="admin", must_change_password=False)

    with patch("app.email_service.enviar_email_via_resend") as mock_resend:
        mock_resend.return_value = {"status": "success", "id": "email_endpoint_test"}

        payload = NotificacionEmailActividadesRequest(
            tipo="dia",
            fecha=date(2026, 10, 28),
            destinatario_tipo="manual",
            destinatario_email="test@endpoint.com"
        )
        res = enviar_email_actividades(payload=payload, current_user=admin_user, db=db_session)
        assert res["tipo"] == "actividades"
        assert res["enviados"] == 1
