import pytest
from datetime import date, time, datetime, timedelta
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Cuidador, PersonalMedico, BloqueTurno, AsignacionTurno, ActividadMedica, Usuario
from app.email_service import enviar_correos_horario_periodo
from app.schemas import NotificacionEmailHorarioRequest
from app.main import enviar_email_horario


@pytest.fixture
def db_session():
    """Crea una sesión SQLite en memoria aislada para pruebas."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    b1 = BloqueTurno(id_bloque=1, codigo_bloque="AM", nombre_bloque="Mañana", hora_inicio=time(8, 0), hora_fin=time(14, 0))
    b2 = BloqueTurno(id_bloque=2, codigo_bloque="PM", nombre_bloque="Tarde", hora_inicio=time(14, 0), hora_fin=time(21, 0))
    session.add_all([b1, b2])

    cuid1 = Cuidador(id_cuidador=1, nombre="Claudia", apellido="Valenzuela", mail="claudia@test.com", telefono_whatsapp="+56911112222", activo=True)
    cuid2 = Cuidador(id_cuidador=2, nombre="Manuel", apellido="Reyes", mail="manuel@test.com", telefono_whatsapp="+56933334444", activo=True)
    cuid3 = Cuidador(id_cuidador=3, nombre="Camila", apellido="Soto", mail="camila@test.com", telefono_whatsapp="+56955556666", activo=True)
    session.add_all([cuid1, cuid2, cuid3])

    session.commit()
    yield session
    session.close()


def test_enviar_correos_horario_dia_todos_y_cuidador(db_session):
    """Verifica envío de correo diario de horarios tanto para todos los asignados como para un cuidador específico."""
    lunes = date(2026, 10, 26)
    bloque1 = db_session.query(BloqueTurno).filter_by(id_bloque=1).first()

    # Claudia tiene turno el lunes; Manuel no tiene turno el lunes; Camila tiene turno el martes
    asig1 = AsignacionTurno(id_cuidador=1, fecha=lunes, hora_inicio=time(8, 0), hora_fin=time(14, 0), id_bloque=1, bloque=bloque1)
    db_session.add(asig1)
    db_session.commit()

    with patch("app.email_service.enviar_email_via_resend") as mock_resend:
        mock_resend.return_value = {"status": "success", "id": "res_horario_dia_1"}

        # 1. Enviar a todos los cuidadores en turno del día (solo Claudia debe recibir)
        res_todos = enviar_correos_horario_periodo(
            db=db_session,
            fecha_base=lunes,
            tipo="dia",
            destinatario_tipo="todos"
        )
        assert res_todos["tipo"] == "diario"
        assert res_todos["total_cuidadores"] == 1
        assert res_todos["enviados"] == 1
        assert mock_resend.called
        assert mock_resend.call_args[0][0] == "claudia@test.com"

        mock_resend.reset_mock()

        # 2. Enviar a un cuidador específico que SÍ tiene turno (Claudia)
        res_cuid1 = enviar_correos_horario_periodo(
            db=db_session,
            fecha_base=lunes,
            tipo="dia",
            destinatario_tipo="cuidador",
            id_cuidador=1
        )
        assert res_cuid1["enviados"] == 1
        assert mock_resend.call_args[0][0] == "claudia@test.com"

        mock_resend.reset_mock()

        # 3. Enviar a un cuidador específico que NO tiene turno ese día (Manuel)
        res_cuid2 = enviar_correos_horario_periodo(
            db=db_session,
            fecha_base=lunes,
            tipo="dia",
            destinatario_tipo="cuidador",
            id_cuidador=2
        )
        assert res_cuid2["enviados"] == 0
        assert res_cuid2["omitidos"] == 1
        assert not mock_resend.called
        assert "no tiene turnos asignados" in res_cuid2["detalles"][0]["detalle"]


def test_enviar_correos_horario_semana_todos_y_cuidador(db_session):
    """Verifica envío semanal consolidado a cada quien con lo que le corresponde."""
    lunes = date(2026, 10, 26)
    martes = date(2026, 10, 27)
    bloque1 = db_session.query(BloqueTurno).filter_by(id_bloque=1).first()

    # Claudia turno lunes; Manuel turno martes; Camila sin turnos en la semana
    asig1 = AsignacionTurno(id_cuidador=1, fecha=lunes, hora_inicio=time(8, 0), hora_fin=time(14, 0), id_bloque=1, bloque=bloque1)
    asig2 = AsignacionTurno(id_cuidador=2, fecha=martes, hora_inicio=time(8, 0), hora_fin=time(14, 0), id_bloque=1, bloque=bloque1)
    db_session.add_all([asig1, asig2])
    db_session.commit()

    with patch("app.email_service.enviar_email_via_resend") as mock_resend:
        mock_resend.return_value = {"status": "success", "id": "res_horario_sem_1"}

        # 1. Enviar a todos en la semana (Claudia y Manuel)
        res_todos = enviar_correos_horario_periodo(
            db=db_session,
            fecha_base=lunes,
            tipo="semana",
            destinatario_tipo="todos"
        )
        assert res_todos["tipo"] == "semanal"
        assert res_todos["total_cuidadores"] == 2
        assert res_todos["enviados"] == 2
        assert mock_resend.call_count == 2

        mock_resend.reset_mock()

        # 2. Enviar solo a Manuel
        res_manuel = enviar_correos_horario_periodo(
            db=db_session,
            fecha_base=lunes,
            tipo="semana",
            destinatario_tipo="cuidador",
            id_cuidador=2
        )
        assert res_manuel["enviados"] == 1
        assert mock_resend.call_count == 1
        assert mock_resend.call_args[0][0] == "manuel@test.com"

        mock_resend.reset_mock()

        # 3. Enviar a Camila que no tiene turnos en la semana
        res_camila = enviar_correos_horario_periodo(
            db=db_session,
            fecha_base=lunes,
            tipo="semana",
            destinatario_tipo="cuidador",
            id_cuidador=3
        )
        assert res_camila["enviados"] == 0
        assert res_camila["omitidos"] == 1
        assert not mock_resend.called


def test_endpoint_enviar_email_horario(db_session):
    """Verifica la función endpoint de FastAPI para el envío de horario unificado."""
    lunes = date(2026, 10, 26)
    bloque1 = db_session.query(BloqueTurno).filter_by(id_bloque=1).first()
    asig1 = AsignacionTurno(id_cuidador=1, fecha=lunes, hora_inicio=time(8, 0), hora_fin=time(14, 0), id_bloque=1, bloque=bloque1)
    db_session.add(asig1)
    db_session.commit()

    admin_user = Usuario(id_usuario=99, username="admin_horario", rol="admin", must_change_password=False)

    with patch("app.email_service.enviar_email_via_resend") as mock_resend:
        mock_resend.return_value = {"status": "success", "id": "email_endpoint_horario"}

        payload = NotificacionEmailHorarioRequest(
            tipo="semana",
            fecha=lunes,
            destinatario_tipo="cuidador",
            id_cuidador=1
        )
        res = enviar_email_horario(payload=payload, current_user=admin_user, db=db_session)
        assert res["tipo"] == "semanal"
        assert res["enviados"] == 1
        assert mock_resend.called
