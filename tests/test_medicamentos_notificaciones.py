import pytest
from datetime import date, time, datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Cuidador, PersonalMedico, BloqueTurno, AsignacionTurno, ActividadMedica, TratamientoMedicamento, MedicamentoHorario
from app.medicamentos_service import (
    TomaMedicamento,
    obtener_medicamentos_programados,
    esta_en_jornada_asig,
)
from app.email_service import (
    construir_contenido_diario,
    construir_contenido_semanal,
    enviar_correos_del_dia,
    enviar_correos_semana_completa,
)
from app.whatsapp import (
    build_whatsapp_message,
    build_whatsapp_message_semanal,
)


@pytest.fixture
def db_session():
    """Crea una sesión de base de datos SQLite en memoria aislada para pruebas."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Sembrar datos base
    bloque_am = BloqueTurno(id_bloque=1, codigo_bloque="AM", nombre_bloque="AM", hora_inicio=time(8, 0), hora_fin=time(14, 0))
    bloque_pm = BloqueTurno(id_bloque=2, codigo_bloque="PM1", nombre_bloque="PM1", hora_inicio=time(10, 0), hora_fin=time(14, 30))
    bloque_n = BloqueTurno(id_bloque=3, codigo_bloque="N", nombre_bloque="N", hora_inicio=time(21, 0), hora_fin=time(10, 0))
    session.add_all([bloque_am, bloque_pm, bloque_n])

    medico = PersonalMedico(id_medico=1, nombre="Dr. Carlos", apellido="Gómez", especialidad="Geriatría", activo=True)
    session.add(medico)

    cuid_martes = Cuidador(id_cuidador=1, nombre="Claudia", apellido="Valenzuela", mail="claudia@test.com", telefono_whatsapp="+56911112222", activo=True)
    cuid_lunes_noc = Cuidador(id_cuidador=2, nombre="Manuel", apellido="Reyes", mail="manuel@test.com", telefono_whatsapp="+56933334444", activo=True)
    session.add_all([cuid_martes, cuid_lunes_noc])

    session.commit()
    yield session
    session.close()


def test_obtener_medicamentos_programados_arrastre(db_session):
    """
    Verifica que un medicamento creado el lunes (sin duración explícita)
    genere automáticamente tomas arrastradas el martes y miércoles con sus horarios base.
    """
    lunes = date(2026, 10, 26)
    martes = date(2026, 10, 27)
    miercoles = date(2026, 10, 28)

    # Tratamiento creado el lunes con 3 tomas solo el día inicial
    trat = TratamientoMedicamento(
        id=1,
        personal_medico_id=1,
        nombre_medicamento="Paracetamol 500mg",
        dia_inicial=lunes
    )
    db_session.add(trat)
    db_session.flush()

    h1 = MedicamentoHorario(medicamento_id=1, dia=lunes, hora=time(8, 0))
    h2 = MedicamentoHorario(medicamento_id=1, dia=lunes, hora=time(12, 0))
    h3 = MedicamentoHorario(medicamento_id=1, dia=lunes, hora=time(22, 0))
    db_session.add_all([h1, h2, h3])
    db_session.commit()

    # Consultar rango lunes a miércoles
    tomas = obtener_medicamentos_programados(db_session, lunes, miercoles)

    # Total esperado: 3 tomas x 3 días = 9 tomas
    assert len(tomas) == 9

    # Verificar tomas del lunes (explícitas)
    tomas_lunes = [t for t in tomas if t.dia == lunes]
    assert len(tomas_lunes) == 3
    assert all(not t.es_arrastrado for t in tomas_lunes)

    # Verificar tomas del martes (arrastradas automáticamente)
    tomas_martes = [t for t in tomas if t.dia == martes]
    assert len(tomas_martes) == 3
    assert all(t.es_arrastrado for t in tomas_martes)
    assert [t.hora for t in tomas_martes] == [time(8, 0), time(12, 0), time(22, 0)]
    assert tomas_martes[0].tratamiento.nombre_medicamento == "Paracetamol 500mg"

    # Verificar tomas del miércoles (arrastradas automáticamente)
    tomas_miercoles = [t for t in tomas if t.dia == miercoles]
    assert len(tomas_miercoles) == 3
    assert all(t.es_arrastrado for t in tomas_miercoles)


def test_esta_en_jornada_asig_diurno_y_nocturno():
    """
    Verifica que la función determine con precisión si una toma cae en turnos diurnos
    y en turnos nocturnos que cruzan la medianoche.
    """
    lunes = date(2026, 10, 26)
    martes = date(2026, 10, 27)

    # Turno diurno martes: 10:00 - 14:30
    asig_diurna = AsignacionTurno(fecha=martes, hora_inicio=time(10, 0), hora_fin=time(14, 30))
    assert esta_en_jornada_asig(martes, time(12, 0), asig_diurna) is True
    assert esta_en_jornada_asig(martes, time(10, 0), asig_diurna) is True
    assert esta_en_jornada_asig(martes, time(14, 30), asig_diurna) is True
    assert esta_en_jornada_asig(martes, time(8, 0), asig_diurna) is False
    assert esta_en_jornada_asig(martes, time(22, 0), asig_diurna) is False
    assert esta_en_jornada_asig(lunes, time(12, 0), asig_diurna) is False

    # Turno nocturno lunes: 21:00 - 10:00 del martes
    asig_nocturna = AsignacionTurno(fecha=lunes, hora_inicio=time(21, 0), hora_fin=time(10, 0))
    assert esta_en_jornada_asig(lunes, time(22, 0), asig_nocturna) is True
    assert esta_en_jornada_asig(martes, time(8, 0), asig_nocturna) is True
    assert esta_en_jornada_asig(martes, time(10, 0), asig_nocturna) is True
    assert esta_en_jornada_asig(lunes, time(8, 0), asig_nocturna) is False
    assert esta_en_jornada_asig(martes, time(12, 0), asig_nocturna) is False


def test_cuidador_martes_recibe_medicamento_arrastrado_diario(db_session):
    """
    Verifica que el cuidador del martes reciba en su correo y mensaje diario
    los medicamentos creados el lunes que se arrastran al martes.
    """
    lunes = date(2026, 10, 26)
    martes = date(2026, 10, 27)

    trat = TratamientoMedicamento(
        id=1,
        personal_medico_id=1,
        nombre_medicamento="Enalapril 10mg",
        dia_inicial=lunes
    )
    db_session.add(trat)
    db_session.flush()

    h1 = MedicamentoHorario(medicamento_id=1, dia=lunes, hora=time(12, 0))
    db_session.add(h1)

    cuid = db_session.query(Cuidador).filter_by(id_cuidador=1).first() # Claudia
    asig_martes = AsignacionTurno(
        id_cuidador=cuid.id_cuidador,
        fecha=martes,
        hora_inicio=time(10, 0),
        hora_fin=time(14, 30),
        id_bloque=2
    )
    db_session.add(asig_martes)
    db_session.commit()

    # Obtener tomas para el martes
    tomas_martes = obtener_medicamentos_programados(db_session, martes, martes + timedelta(days=1))
    meds_turno = [m for m in tomas_martes if esta_en_jornada_asig(m.dia, m.hora, asig_martes)]

    assert len(meds_turno) == 1
    assert meds_turno[0].hora == time(12, 0)
    assert meds_turno[0].tratamiento.nombre_medicamento == "Enalapril 10mg"

    # Generar contenido diario de email
    subject, text, html = construir_contenido_diario(cuid, asig_martes, [], meds_turno)
    assert "Enalapril 10mg: Martes a las 12:00 hrs" in text
    assert "Enalapril 10mg" in html
    assert "12:00 hrs" in html
    assert "No tienes administración de medicamentos programada" not in text

    # Generar WhatsApp diario
    msg_wa = build_whatsapp_message(cuid, asig_martes, [], meds_turno)
    assert "Enalapril 10mg" in msg_wa
    assert "12:00" in msg_wa


def test_cuidador_recibe_medicamentos_semanal_arrastrados(db_session):
    """
    Verifica que en el correo y WhatsApp semanal consolidado, los cuidadores con turnos
    en martes reciban los medicamentos arrastrados y los cuidadores nocturnos reciban
    las tomas de la mañana siguiente.
    """
    lunes = date(2026, 10, 26)
    martes = date(2026, 10, 27)
    domingo = date(2026, 11, 1)

    trat = TratamientoMedicamento(
        id=1,
        personal_medico_id=1,
        nombre_medicamento="Omeprazol 20mg",
        dia_inicial=lunes
    )
    db_session.add(trat)
    db_session.flush()

    # Tomas creadas el lunes: 08:00 y 12:00
    h1 = MedicamentoHorario(medicamento_id=1, dia=lunes, hora=time(8, 0))
    h2 = MedicamentoHorario(medicamento_id=1, dia=lunes, hora=time(12, 0))
    db_session.add_all([h1, h2])

    cuid = db_session.query(Cuidador).filter_by(id_cuidador=1).first() # Claudia
    bloque = db_session.query(BloqueTurno).filter_by(id_bloque=2).first()

    # Asignación de Claudia el martes 10:00 - 14:30
    asig_martes = AsignacionTurno(
        id_cuidador=cuid.id_cuidador,
        fecha=martes,
        hora_inicio=time(10, 0),
        hora_fin=time(14, 30),
        id_bloque=2,
        bloque=bloque
    )
    db_session.add(asig_martes)
    db_session.commit()

    # Obtener medicamentos de la semana completa
    tomas_semana = obtener_medicamentos_programados(db_session, lunes, domingo + timedelta(days=1))
    meds_por_fecha = {}
    for t in tomas_semana:
        meds_por_fecha.setdefault(t.dia, []).append(t)

    # Generar contenido semanal de email
    subject, text, html = construir_contenido_semanal(
        cuidador=cuid,
        asignaciones=[asig_martes],
        actividades_por_fecha={},
        inicio_semana=lunes,
        fin_semana=domingo,
        medicamentos_por_fecha=meds_por_fecha
    )

    assert "Omeprazol 20mg" in text
    assert "12:00 hrs" in text
    assert "Omeprazol 20mg" in html
    assert "No tienes administración de medicamentos programada en tus turnos" not in text

    # Generar WhatsApp semanal
    msg_wa = build_whatsapp_message_semanal(
        cuidador=cuid,
        asignaciones=[asig_martes],
        actividades_por_fecha={},
        inicio_semana=lunes,
        fin_semana=domingo,
        medicamentos_por_fecha=meds_por_fecha
    )
    assert "Omeprazol 20mg" in msg_wa
    assert "12:00" in msg_wa


def test_cuidador_nocturno_recibe_toma_manana_siguiente(db_session):
    """
    Verifica que un cuidador asignado en turno de noche (Lunes 21:00 a Martes 10:00)
    reciba correctamente la toma de medicamento de las 08:00 AM del martes (cruce de medianoche).
    """
    lunes = date(2026, 10, 26)
    martes = date(2026, 10, 27)
    domingo = date(2026, 11, 1)

    trat = TratamientoMedicamento(
        id=2,
        personal_medico_id=1,
        nombre_medicamento="Aspirina 100mg",
        dia_inicial=lunes
    )
    db_session.add(trat)
    db_session.flush()

    # Tomas: 22:00 (lunes noche) y 08:00 (mañana)
    h1 = MedicamentoHorario(medicamento_id=2, dia=lunes, hora=time(22, 0))
    h2 = MedicamentoHorario(medicamento_id=2, dia=lunes, hora=time(8, 0))
    db_session.add_all([h1, h2])

    cuid_noc = db_session.query(Cuidador).filter_by(id_cuidador=2).first() # Manuel
    bloque_noc = db_session.query(BloqueTurno).filter_by(id_bloque=3).first()

    asig_noc = AsignacionTurno(
        id_cuidador=cuid_noc.id_cuidador,
        fecha=lunes,
        hora_inicio=time(21, 0),
        hora_fin=time(10, 0),
        id_bloque=3,
        bloque=bloque_noc
    )
    db_session.add(asig_noc)
    db_session.commit()

    # Tomas de la semana
    tomas_semana = obtener_medicamentos_programados(db_session, lunes, domingo + timedelta(days=1))
    meds_por_fecha = {}
    for t in tomas_semana:
        meds_por_fecha.setdefault(t.dia, []).append(t)

    # Verificar que las tomas del martes a las 08:00 caigan dentro de la jornada nocturna
    tomas_martes = meds_por_fecha.get(martes, [])
    tomas_en_jornada = [m for m in tomas_martes if esta_en_jornada_asig(m.dia, m.hora, asig_noc)]
    assert len(tomas_en_jornada) == 1
    assert tomas_en_jornada[0].hora == time(8, 0)

    # Verificar contenido semanal
    subject, text, html = construir_contenido_semanal(
        cuidador=cuid_noc,
        asignaciones=[asig_noc],
        actividades_por_fecha={},
        inicio_semana=lunes,
        fin_semana=domingo,
        medicamentos_por_fecha=meds_por_fecha
    )

    assert "Aspirina 100mg" in text
    assert "22:00" in text
    assert "08:00" in text

    # Verificar WhatsApp semanal
    msg_wa = build_whatsapp_message_semanal(
        cuidador=cuid_noc,
        asignaciones=[asig_noc],
        actividades_por_fecha={},
        inicio_semana=lunes,
        fin_semana=domingo,
        medicamentos_por_fecha=meds_por_fecha
    )
    assert "Aspirina 100mg" in msg_wa
    assert "22:00" in msg_wa
    assert "08:00" in msg_wa


def test_enviar_correos_del_dia_y_semanal_medicamento_arrastrado_martes(db_session):
    """
    Verifica que enviar_correos_del_dia y enviar_correos_semana_completa incluyan
    exitosamente para el cuidador del día martes los medicamentos creados el lunes
    (tanto arrastrados como con tomas a horas variadas).
    """
    from unittest.mock import patch

    lunes = date(2026, 10, 26)
    martes = date(2026, 10, 27)

    cuid = db_session.query(Cuidador).filter_by(id_cuidador=1).first() # Claudia
    bloque = db_session.query(BloqueTurno).filter_by(id_bloque=2).first() # AM (10:00 - 14:30)

    # Asignar a Claudia el martes en bloque AM
    asig_martes = AsignacionTurno(
        id_cuidador=cuid.id_cuidador,
        fecha=martes,
        hora_inicio=time(10, 0),
        hora_fin=time(14, 30),
        id_bloque=2,
        bloque=bloque
    )
    db_session.add(asig_martes)

    # Medicamento creado el lunes a las 08:00 y 12:00
    trat = TratamientoMedicamento(
        id=10,
        personal_medico_id=1,
        nombre_medicamento="Losartan 50mg",
        dia_inicial=lunes
    )
    db_session.add(trat)
    db_session.flush()

    h1 = MedicamentoHorario(medicamento_id=10, dia=lunes, hora=time(8, 0))
    h2 = MedicamentoHorario(medicamento_id=10, dia=lunes, hora=time(12, 0))
    db_session.add_all([h1, h2])
    db_session.commit()

    with patch("app.email_service.enviar_email_via_resend") as mock_resend:
        mock_resend.return_value = {"status": "success", "id": "email_test_123"}

        # 1. Probar Correo Diario del Martes
        res_diario = enviar_correos_del_dia(martes, db_session)
        assert res_diario["enviados"] == 1
        assert len(mock_resend.call_args_list) == 1

        call_args = mock_resend.call_args[0]
        destinatario = call_args[0]
        asunto = call_args[1]
        cuerpo_texto = call_args[2]
        cuerpo_html = call_args[3]

        assert destinatario == cuid.mail
        assert "Losartan 50mg" in cuerpo_texto
        assert "12:00 hrs" in cuerpo_texto
        assert "08:00" in cuerpo_texto
        assert "Losartan 50mg" in cuerpo_html
        assert "No tienes administración de medicamentos programada" not in cuerpo_texto

        mock_resend.reset_mock()

        # 2. Probar Correo Semanal
        res_semanal = enviar_correos_semana_completa(lunes, db_session)
        assert res_semanal["enviados"] >= 1
        assert mock_resend.called

        llamada_claudia = [c for c in mock_resend.call_args_list if c[0][0] == cuid.mail][0]
        texto_sem = llamada_claudia[0][2]
        html_sem = llamada_claudia[0][3]

        assert "Losartan 50mg" in texto_sem
        assert "Losartan 50mg" in html_sem
        assert "Martes 27/10" in texto_sem
        assert "08:00 y 12:00 hrs" in texto_sem
        assert "No tienes administración de medicamentos programada" not in texto_sem


def test_tratamiento_sin_personal_medico_opcional(db_session):
    """
    Verifica que la indicación médica (personal_medico_id) sea completamente opcional.
    Un tratamiento registrado sin médico debe persistir correctamente con personal_medico_id=None
    y reflejarse en correos diarios, correos semanales y mensajes de WhatsApp.
    """
    from unittest.mock import patch

    martes = date(2026, 10, 27)
    cuid = db_session.query(Cuidador).filter_by(id_cuidador=1).first()

    # Asignación del cuidador el martes
    asig = AsignacionTurno(
        id_asignacion=201,
        id_cuidador=cuid.id_cuidador,
        fecha=martes,
        id_bloque=1,
        hora_inicio=time(8, 0),
        hora_fin=time(14, 0)
    )
    db_session.add(asig)

    # Tratamiento sin médico (personal_medico_id=None)
    trat_sin_medico = TratamientoMedicamento(
        id=50,
        personal_medico_id=None,
        nombre_medicamento="Omeprazol 20mg",
        dia_inicial=martes
    )
    db_session.add(trat_sin_medico)
    db_session.flush()

    h1 = MedicamentoHorario(medicamento_id=50, dia=martes, hora=time(8, 30))
    db_session.add(h1)
    db_session.commit()

    # 1. Comprobar que en base de datos personal_medico_id es None
    trat_recuperado = db_session.query(TratamientoMedicamento).filter_by(id=50).first()
    assert trat_recuperado.personal_medico_id is None
    assert trat_recuperado.personal_medico is None

    # 2. Comprobar que obtener_medicamentos_programados incluye la toma sin médico
    tomas = obtener_medicamentos_programados(db_session, martes, martes)
    nombres_tomas = [t.tratamiento.nombre_medicamento for t in tomas]
    assert "Omeprazol 20mg" in nombres_tomas

    # 3. Comprobar que construir_contenido_diario genera el correo sin error
    asunto, texto_diario, html_diario = construir_contenido_diario(cuid, [asig], [], tomas)
    assert "Omeprazol 20mg" in texto_diario
    assert "08:30 hrs" in texto_diario
    assert "Omeprazol 20mg" in html_diario

    # 4. Comprobar envío diario y semanal completo con mock
    with patch("app.email_service.enviar_email_via_resend") as mock_resend:
        mock_resend.return_value = {"status": "success", "id": "email_test_sin_medico"}
        res_d = enviar_correos_del_dia(martes, db_session)
        assert res_d["enviados"] == 1
        call_text = mock_resend.call_args[0][2]
        assert "Omeprazol 20mg" in call_text

        mock_resend.reset_mock()
        res_s = enviar_correos_semana_completa(martes, db_session)
        assert res_s["enviados"] >= 1
        call_text_sem = mock_resend.call_args[0][2]
        assert "Omeprazol 20mg" in call_text_sem

    # 5. Comprobar WhatsApp diario y semanal
    wa_diario = build_whatsapp_message(cuid, [asig], [], tomas)
    assert "Omeprazol 20mg" in wa_diario
    assert "08:30 hrs" in wa_diario



def test_arrastre_continuo_actualizacion_martes(db_session):
    """
    Verifica que si un tratamiento inicia el lunes con un horario y el martes se modifica/agregan
    horarios explícitos, los días siguientes (miércoles a domingo) arrastren la pauta actualizada
    del martes y no reviertan a la pauta del lunes.
    """
    lunes = date(2026, 10, 26)
    domingo = date(2026, 11, 1)

    trat = TratamientoMedicamento(
        id=99,
        personal_medico_id=1,
        nombre_medicamento="Amlodipino",
        dia_inicial=lunes
    )
    db_session.add(trat)
    db_session.flush()

    # Lunes: 16:00 y 23:59
    h_lun1 = MedicamentoHorario(medicamento_id=99, dia=lunes, hora=time(16, 0))
    h_lun2 = MedicamentoHorario(medicamento_id=99, dia=lunes, hora=time(23, 59))

    # Martes: 12:00, 16:00 y 23:59 (cambio de pauta)
    martes = date(2026, 10, 27)
    h_mar1 = MedicamentoHorario(medicamento_id=99, dia=martes, hora=time(12, 0))
    h_mar2 = MedicamentoHorario(medicamento_id=99, dia=martes, hora=time(16, 0))
    h_mar3 = MedicamentoHorario(medicamento_id=99, dia=martes, hora=time(23, 59))

    db_session.add_all([h_lun1, h_lun2, h_mar1, h_mar2, h_mar3])
    db_session.commit()

    # Consultar toda la semana
    tomas = obtener_medicamentos_programados(db_session, lunes, domingo)

    # Verificar que lunes tiene 2 tomas
    tomas_lunes = [t for t in tomas if t.dia == lunes]
    assert len(tomas_lunes) == 2
    assert [t.hora for t in tomas_lunes] == [time(16, 0), time(23, 59)]

    # Verificar que martes tiene 3 tomas
    tomas_martes = [t for t in tomas if t.dia == martes]
    assert len(tomas_martes) == 3
    assert [t.hora for t in tomas_martes] == [time(12, 0), time(16, 0), time(23, 59)]

    # Verificar que miércoles en adelante arrastran las 3 tomas del martes
    for offset in range(2, 7):
        dia_check = lunes + timedelta(days=offset)
        tomas_dia = [t for t in tomas if t.dia == dia_check]
        assert len(tomas_dia) == 3, f"Fallo en {dia_check}: esperadas 3 tomas arrastradas"
        assert [t.hora for t in tomas_dia] == [time(12, 0), time(16, 0), time(23, 59)]
        assert all(t.es_arrastrado for t in tomas_dia)


def test_formato_agrupado_ejemplo_usuario(db_session):
    """
    Verifica que el formato agrupado coincida exactamente con el ejemplo solicitado por el usuario:
    'Amlodipino: Lunes a las 16:00 y 23:59 hrs; de Martes a Domingo a las 12:00, 16:00 y 23:59 hrs'
    tanto para correo (texto y HTML) como para WhatsApp (diario y semanal).
    """
    from app.medicamentos_service import formatear_pauta_medicamentos

    lunes = date(2026, 10, 26)
    domingo = date(2026, 11, 1)

    trat = TratamientoMedicamento(
        id=100,
        personal_medico_id=1,
        nombre_medicamento="Amlodipino",
        dia_inicial=lunes
    )
    db_session.add(trat)
    db_session.flush()

    # Lunes: 16:00 y 23:59
    h_lun1 = MedicamentoHorario(medicamento_id=100, dia=lunes, hora=time(16, 0))
    h_lun2 = MedicamentoHorario(medicamento_id=100, dia=lunes, hora=time(23, 59))

    # Martes: 12:00, 16:00 y 23:59
    martes = date(2026, 10, 27)
    h_mar1 = MedicamentoHorario(medicamento_id=100, dia=martes, hora=time(12, 0))
    h_mar2 = MedicamentoHorario(medicamento_id=100, dia=martes, hora=time(16, 0))
    h_mar3 = MedicamentoHorario(medicamento_id=100, dia=martes, hora=time(23, 59))

    db_session.add_all([h_lun1, h_lun2, h_mar1, h_mar2, h_mar3])

    cuid = db_session.query(Cuidador).filter_by(id_cuidador=1).first() # Claudia
    bloque = db_session.query(BloqueTurno).filter_by(id_bloque=1).first()

    # Asignar a Claudia toda la semana
    asigs_semana = []
    for d_offset in range(7):
        f = lunes + timedelta(days=d_offset)
        asig = AsignacionTurno(
            id_cuidador=cuid.id_cuidador,
            fecha=f,
            hora_inicio=time(8, 0),
            hora_fin=time(23, 59),
            id_bloque=1,
            bloque=bloque
        )
        asigs_semana.append(asig)
    db_session.add_all(asigs_semana)
    db_session.commit()

    # 1. Obtener tomas de la semana
    tomas_semana = obtener_medicamentos_programados(db_session, lunes, domingo)
    assert len(tomas_semana) == 2 + 3 * 6 # 2 (lunes) + 18 (martes a domingo) = 20 tomas

    # 2. Verificar formato agrupado directamente con formatear_pauta_medicamentos
    resultado_fmt = formatear_pauta_medicamentos(tomas_semana)
    assert len(resultado_fmt) == 1
    item_med = resultado_fmt[0]

    assert item_med["nombre"] == "Amlodipino"
    assert "Lunes a las 16:00 y 23:59 hrs" in item_med["texto_plano"]
    assert "de Martes a Domingo a las 12:00, 16:00 y 23:59 hrs" in item_med["texto_plano"]
    assert "*Amlodipino*: Lunes a las 16:00 y 23:59 hrs; de Martes a Domingo a las 12:00, 16:00 y 23:59 hrs" in item_med["texto_whatsapp"]
    assert "<strong>Amlodipino</strong>: Lunes a las 16:00 y 23:59 hrs; de Martes a Domingo a las 12:00, 16:00 y 23:59 hrs" in item_med["texto_html"]

    # 3. Verificar en Correo Semanal
    meds_por_fecha = {}
    for t in tomas_semana:
        meds_por_fecha.setdefault(t.dia, []).append(t)

    asunto, texto_sem, html_sem = construir_contenido_semanal(
        cuidador=cuid,
        asignaciones=asigs_semana,
        actividades_por_fecha={},
        inicio_semana=lunes,
        fin_semana=domingo,
        medicamentos_por_fecha=meds_por_fecha
    )
    assert "Amlodipino: Lunes a las 16:00 y 23:59 hrs; de Martes a Domingo a las 12:00, 16:00 y 23:59 hrs" in texto_sem
    assert "<strong>Amlodipino</strong>: Lunes a las 16:00 y 23:59 hrs; de Martes a Domingo a las 12:00, 16:00 y 23:59 hrs" in html_sem

    # 4. Verificar en WhatsApp Semanal
    msg_wa_sem = build_whatsapp_message_semanal(
        cuidador=cuid,
        asignaciones=asigs_semana,
        actividades_por_fecha={},
        inicio_semana=lunes,
        fin_semana=domingo,
        medicamentos_por_fecha=meds_por_fecha
    )
    assert "*Amlodipino*: Lunes a las 16:00 y 23:59 hrs; de Martes a Domingo a las 12:00, 16:00 y 23:59 hrs" in msg_wa_sem

    # 5. Verificar en Correo y WhatsApp Diario (Día Lunes)
    tomas_lunes = [t for t in tomas_semana if t.dia == lunes]
    _, texto_diario_lun, html_diario_lun = construir_contenido_diario(cuid, asigs_semana[0], [], tomas_lunes)
    assert "Amlodipino: Lunes a las 16:00 y 23:59 hrs" in texto_diario_lun
    assert "<strong>Amlodipino</strong>: Lunes a las 16:00 y 23:59 hrs" in html_diario_lun

    msg_wa_diario_lun = build_whatsapp_message(cuid, asigs_semana[0], [], tomas_lunes)
    assert "*Amlodipino*: Lunes a las 16:00 y 23:59 hrs" in msg_wa_diario_lun


def test_construir_y_enviar_solo_medicamentos(db_session):
    """
    Verifica que la notificación exclusiva de pauta de medicamentos:
    1. Incluya la lista completa de medicamentos agrupada en el formato exacto requerido.
    2. NO contenga turnos de cuidadores ni actividades médicas.
    3. Funcione correctamente tanto para cuidadores individuales como para envío manual.
    """
    from unittest.mock import patch
    from app.email_service import (
        construir_contenido_solo_medicamentos,
        enviar_correos_solo_medicamentos_periodo,
    )

    lunes = date(2026, 10, 26)
    domingo = date(2026, 11, 1)

    trat = TratamientoMedicamento(
        id=200,
        personal_medico_id=1,
        nombre_medicamento="Amlodipino",
        dia_inicial=lunes
    )
    db_session.add(trat)
    db_session.flush()

    h1 = MedicamentoHorario(medicamento_id=200, dia=lunes, hora=time(16, 0))
    h2 = MedicamentoHorario(medicamento_id=200, dia=lunes, hora=time(23, 59))
    db_session.add_all([h1, h2])
    db_session.commit()

    tomas = obtener_medicamentos_programados(db_session, lunes, domingo)

    # 1. Probar construcción de contenido
    asunto, texto, html = construir_contenido_solo_medicamentos(tomas, "Semana de Prueba", "Claudia")
    assert "Amlodipino: de Lunes a Domingo a las 16:00 y 23:59 hrs" in texto
    assert "Indicado por: Dr. Carlos Gómez" in texto
    # Garantizar que NO incluya turnos ni actividades
    assert "Tu turno para el día" not in texto
    assert "actividades médicas programadas" not in texto
    assert "bloque" not in texto.lower()

    # 2. Probar envío vía Resend con mock
    with patch("app.email_service.enviar_email_via_resend") as mock_resend:
        mock_resend.return_value = {"status": "success", "id": "email_meds_test_1"}

        # Envío manual
        res_manual = enviar_correos_solo_medicamentos_periodo(
            db=db_session,
            fecha_inicio=lunes,
            fecha_fin=domingo,
            destinatario_tipo="manual",
            email_manual="familiar@test.com"
        )
        assert res_manual["enviados"] == 1
        assert mock_resend.called
        assert mock_resend.call_args[0][0] == "familiar@test.com"
        assert "Amlodipino" in mock_resend.call_args[0][2]

        mock_resend.reset_mock()

        # Envío a cuidador específico
        cuid = db_session.query(Cuidador).filter_by(id_cuidador=1).first()
        res_cuid = enviar_correos_solo_medicamentos_periodo(
            db=db_session,
            fecha_inicio=lunes,
            fecha_fin=domingo,
            destinatario_tipo="cuidador",
            id_cuidador=cuid.id_cuidador
        )
        assert res_cuid["enviados"] == 1
        assert mock_resend.called
        assert mock_resend.call_args[0][0] == cuid.mail


def test_pauta_semanal_completa_sin_recortar_dias_sin_turno(db_session):
    """
    Verifica que si un paciente tiene tomas de lunes a sábado y un cuidador solo tiene
    turnos lunes, martes, miércoles y sábado (sin turno jueves ni viernes), la notificación
    semanal y diaria del cuidador NO recorte jueves ni viernes y muestre correctamente
    'de Lunes a Sábado' (en vez de 'de Lunes a Miércoles y Sábado').
    """
    lunes = date(2026, 10, 26)
    sabado = date(2026, 10, 31)
    domingo = date(2026, 11, 1)

    trat = TratamientoMedicamento(
        id=300,
        personal_medico_id=1,
        nombre_medicamento="Amlodipino",
        dia_inicial=lunes
    )
    db_session.add(trat)
    db_session.flush()

    # Tomas explícitas de lunes a sábado a las 08:00 y 20:00
    for offset in range(6): # lunes (0) a sábado (5)
        d = lunes + timedelta(days=offset)
        h1 = MedicamentoHorario(medicamento_id=300, dia=d, hora=time(8, 0))
        h2 = MedicamentoHorario(medicamento_id=300, dia=d, hora=time(20, 0))
        db_session.add_all([h1, h2])

    cuid = db_session.query(Cuidador).filter_by(id_cuidador=1).first() # Claudia
    bloque = db_session.query(BloqueTurno).filter_by(id_bloque=1).first()

    # Claudia solo tiene turnos: Lunes, Martes, Miércoles y Sábado (NO Jueves, NO Viernes)
    dias_turno_claudia = [
        lunes,
        lunes + timedelta(days=1), # Martes
        lunes + timedelta(days=2), # Miércoles
        lunes + timedelta(days=5), # Sábado
    ]
    asigs_claudia = []
    for d in dias_turno_claudia:
        asigs_claudia.append(
            AsignacionTurno(
                id_cuidador=cuid.id_cuidador,
                fecha=d,
                hora_inicio=time(8, 0),
                hora_fin=time(14, 0),
                id_bloque=1,
                bloque=bloque
            )
        )
    db_session.add_all(asigs_claudia)
    db_session.commit()

    # Obtener medicamentos de la semana completa
    tomas_semana = obtener_medicamentos_programados(db_session, lunes, domingo)
    meds_por_fecha = {}
    for t in tomas_semana:
        meds_por_fecha.setdefault(t.dia, []).append(t)

    # 1. Probar Correo Semanal
    asunto, texto_sem, html_sem = construir_contenido_semanal(
        cuidador=cuid,
        asignaciones=asigs_claudia,
        actividades_por_fecha={},
        inicio_semana=lunes,
        fin_semana=sabado,
        medicamentos_por_fecha=meds_por_fecha
    )
    # Debe decir 'de Lunes a Sábado' y NO omitir Jueves ni Viernes
    assert "Amlodipino: de Lunes a Sábado a las 08:00 y 20:00 hrs" in texto_sem
    assert "de Lunes a Miércoles y Sábado" not in texto_sem

    # 2. Probar WhatsApp Semanal
    msg_wa_sem = build_whatsapp_message_semanal(
        cuidador=cuid,
        asignaciones=asigs_claudia,
        actividades_por_fecha={},
        inicio_semana=lunes,
        fin_semana=sabado,
        medicamentos_por_fecha=meds_por_fecha
    )
    assert "*Amlodipino*: de Lunes a Sábado a las 08:00 y 20:00 hrs" in msg_wa_sem
    assert "de Lunes a Miércoles y Sábado" not in msg_wa_sem
