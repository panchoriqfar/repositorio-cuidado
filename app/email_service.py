"""Módulo de Notificaciones por Correo Electrónico vía API HTTP (Resend).

Diseñado específicamente para despliegues en la nube (Render, Railway, Fly.io)
donde los puertos SMTP convencionales (25, 465, 587) se encuentran bloqueados.
Utiliza HTTPS (puerto 443) a través del cliente oficial de Resend.
"""

import os
import logging
from datetime import date, time, datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session, joinedload
from dotenv import load_dotenv
import resend

from app.models import AsignacionTurno, ActividadMedica, Cuidador, BloqueTurno, TratamientoMedicamento, MedicamentoHorario

load_dotenv()

logger = logging.getLogger("email_service")
logging.basicConfig(level=logging.INFO)

# Configuración de Resend
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
RESEND_FROM = os.getenv("RESEND_FROM", "MedTurnos Pro <onboarding@resend.dev>").strip()

if RESEND_API_KEY and not RESEND_API_KEY.startswith("re_tu_api_key"):
    resend.api_key = RESEND_API_KEY

DIAS_ESPANOL = {
    0: "Lunes",
    1: "Martes",
    2: "Miércoles",
    3: "Jueves",
    4: "Viernes",
    5: "Sábado",
    6: "Domingo"
}


def es_email_valido(email: Optional[str]) -> bool:
    """Valida si la cadena tiene estructura básica de email."""
    if not email:
        return False
    email_clean = email.strip()
    if len(email_clean) < 5 or "@" not in email_clean or "." not in email_clean:
        return False
    return True


def format_nombre_cuidador(cuidador: Cuidador) -> str:
    apellido = (cuidador.apellido or "").strip()
    return f"{cuidador.nombre.strip()} {apellido}".strip() if apellido else cuidador.nombre.strip()


def esta_en_jornada(hora_med: time, hora_inicio: time, hora_fin: time) -> bool:
    """Verifica si la hora del medicamento corresponde al rango de la jornada del turno."""
    if hora_inicio <= hora_fin:
        return hora_inicio <= hora_med <= hora_fin
    else:
        # Turno nocturno que cruza medianoche (ej: 21:00 a 07:00)
        return hora_med >= hora_inicio or hora_med <= hora_fin


def construir_contenido_diario(
    cuidador: Cuidador,
    asignacion: AsignacionTurno,
    actividades: List[ActividadMedica],
    medicamentos: Optional[List[MedicamentoHorario]] = None
) -> Tuple[str, str, str]:
    """
    Construye el asunto, texto plano y HTML del correo diario
    según el formato requerido por el sistema, incluyendo lista detallada de
    medicamentos, días y horarios activos correspondientes a la jornada del turno.
    """
    nombre = format_nombre_cuidador(cuidador)
    fecha_str = asignacion.fecha.strftime("%d/%m/%Y")
    bloque_nombre = asignacion.bloque.nombre_bloque if asignacion.bloque else "Turno asignado"
    hora_ini = asignacion.hora_inicio.strftime("%H:%M")
    hora_fin = asignacion.hora_fin.strftime("%H:%M")

    subject = f"MedTurnos Pro - Tu turno para hoy {fecha_str}"

    lineas_texto = [
        f"Hola {nombre},",
        f"Tu turno para el día de hoy {fecha_str} es en el bloque {bloque_nombre} ({hora_ini} - {hora_fin}).",
        ""
    ]

    # Sección de Medicamentos de la Jornada
    if medicamentos:
        lineas_texto.append("Medicamentos a administrar en tu turno:")
        for med in medicamentos:
            h_med = med.hora.strftime("%H:%M")
            d_med = med.dia.strftime("%d/%m/%Y")
            n_med = med.tratamiento.nombre_medicamento if med.tratamiento else "Medicamento"
            medico_info = ""
            if med.tratamiento and med.tratamiento.personal_medico:
                pm = med.tratamiento.personal_medico
                nombre_prof = f"{pm.nombre} {pm.apellido or ''}".strip()
                medico_info = f" - Indicado por: {nombre_prof}"
            lineas_texto.append(f"- A las {h_med} hrs: {n_med} (Día: {d_med}{medico_info}).")
        lineas_texto.append("")
    else:
        lineas_texto.append("No tienes administración de medicamentos programada para tu turno.")
        lineas_texto.append("")

    # Sección de Actividades Médicas
    if actividades:
        lineas_texto.append("Tus actividades médicas programadas en el turno son:")
        for act in actividades:
            hora_act = act.hora.strftime("%H:%M")
            desc = act.titulo
            if act.descripcion:
                desc += f" - {act.descripcion}"
            lineas_texto.append(f"- A las {hora_act} tienes {desc}.")
    else:
        lineas_texto.append("No tienes actividades médicas programadas durante tu horario de turno. ¡Que tengas un excelente turno!")

    cuerpo_texto = "\n".join(lineas_texto)

    # HTML elegante para medicamentos
    medicamentos_html = ""
    if medicamentos:
        medicamentos_html = "<ul style='margin: 10px 0; padding-left: 20px; line-height: 1.6;'>"
        for med in medicamentos:
            h_med = med.hora.strftime("%H:%M")
            d_med = med.dia.strftime("%d/%m/%Y")
            n_med = med.tratamiento.nombre_medicamento if med.tratamiento else "Medicamento"
            medico_info = ""
            if med.tratamiento and med.tratamiento.personal_medico:
                pm = med.tratamiento.personal_medico
                nombre_prof = f"{pm.nombre} {pm.apellido or ''}".strip()
                medico_info = f" &bull; Indicado por: {nombre_prof}"
            medicamentos_html += f"<li>A las <strong>{h_med} hrs</strong>: <strong>{n_med}</strong> (Día: {d_med}{medico_info})</li>"
        medicamentos_html += "</ul>"
    else:
        medicamentos_html = "<p style='color: #475569; background: #f8fafc; padding: 12px; border-radius: 8px; margin: 12px 0;'>No tienes administración de medicamentos programada para tu turno.</p>"

    # HTML elegante para actividades
    actividades_html = ""
    if actividades:
        actividades_html = "<ul style='margin: 10px 0; padding-left: 20px; line-height: 1.6;'>"
        for act in actividades:
            hora_act = act.hora.strftime("%H:%M")
            desc = f"<strong>{act.titulo}</strong>"
            if act.descripcion:
                desc += f" &bull; {act.descripcion}"
            actividades_html += f"<li>A las <strong>{hora_act}</strong> tienes {desc}.</li>"
        actividades_html += "</ul>"
    else:
        actividades_html = "<p style='color: #047857; background: #ecfdf5; padding: 12px; border-radius: 8px; margin: 12px 0;'>No tienes actividades médicas programadas durante tu horario de turno. ¡Que tengas un excelente turno!</p>"

    cuerpo_html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; background-color: #f8fafc; padding: 20px; margin: 0;">
        <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
            <div style="background: linear-gradient(135deg, #0284c7, #0d9488); color: white; padding: 22px 24px;">
                <h2 style="margin: 0; font-size: 20px; letter-spacing: -0.025em;">MedTurnos Pro</h2>
                <p style="margin: 4px 0 0; font-size: 13px; opacity: 0.9;">Notificación Diaria de Turno</p>
            </div>
            <div style="padding: 24px;">
                <p style="font-size: 16px; margin-top: 0;">Hola <strong>{nombre}</strong>,</p>
                <div style="background: #f0f9ff; border-left: 4px solid #0284c7; padding: 12px 16px; border-radius: 6px; margin: 16px 0;">
                    <p style="margin: 0; font-size: 14px; color: #0369a1;">
                        Tu turno para el día de hoy <strong>{fecha_str}</strong> es en el bloque <strong>{bloque_nombre}</strong> (<strong>{hora_ini} - {hora_fin} hrs</strong>).
                    </p>
                </div>
                <h3 style="font-size: 15px; color: #334155; margin: 20px 0 8px;">💊 Pauta de Medicamentos en tu Turno:</h3>
                {medicamentos_html}
                <h3 style="font-size: 15px; color: #334155; margin: 20px 0 8px;">📋 Tus actividades del turno son:</h3>
                {actividades_html}
            </div>
            <div style="background: #f1f5f9; padding: 12px 24px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0;">
                Sistema Web MedTurnos Pro &bull; Gestión de Cuidadores y Personal Médico
            </div>
        </div>
    </body>
    </html>
    """

    return subject, cuerpo_texto, cuerpo_html


# Alias descriptivo para la preparación del resumen diario de correo
preparar_resumen_diario_email = construir_contenido_diario


def construir_contenido_semanal(
    cuidador: Cuidador,
    asignaciones: List[AsignacionTurno],
    actividades_por_fecha: Dict[date, List[ActividadMedica]],
    inicio_semana: date,
    fin_semana: date,
    medicamentos_por_fecha: Optional[Dict[date, List[MedicamentoHorario]]] = None
) -> Tuple[str, str, str]:
    """
    Construye el asunto, texto plano y HTML del correo semanal
    cruzando estrictamente las actividades y medicamentos correspondientes al turno de cada jornada.
    """
    nombre = format_nombre_cuidador(cuidador)

    asigs_ordenadas = sorted(asignaciones, key=lambda a: (a.fecha, a.hora_inicio))

    dias_bloques_list = []
    for asig in asigs_ordenadas:
        dia_nom = DIAS_ESPANOL.get(asig.fecha.weekday(), "")
        fecha_str = asig.fecha.strftime("%d/%m")
        bloque = asig.bloque.nombre_bloque if asig.bloque else "Turno"
        hora_ini = asig.hora_inicio.strftime("%H:%M")
        hora_fin = asig.hora_fin.strftime("%H:%M")
        dias_bloques_list.append(f"{dia_nom} {fecha_str} en bloque {bloque} ({hora_ini} - {hora_fin})")

    dias_bloques_str = ", ".join(dias_bloques_list)

    # Cruce estricto: solo actividades que caen dentro del horario de sus turnos
    todas_actividades = []
    todos_medicamentos = []
    for asig in asigs_ordenadas:
        acts_dia = actividades_por_fecha.get(asig.fecha, [])
        for act in acts_dia:
            if esta_en_jornada(act.hora, asig.hora_inicio, asig.hora_fin):
                todas_actividades.append((asig.fecha, act))

        if medicamentos_por_fecha:
            meds_dia = medicamentos_por_fecha.get(asig.fecha, [])
            for m in meds_dia:
                if esta_en_jornada(m.hora, asig.hora_inicio, asig.hora_fin):
                    todos_medicamentos.append((asig.fecha, m))

    rango_str = f"{inicio_semana.strftime('%d/%m/%Y')} al {fin_semana.strftime('%d/%m/%Y')}"
    subject = f"MedTurnos Pro - Planificación semanal de turnos ({rango_str})"

    lineas_texto = [
        f"Hola {nombre},",
        f"Esta semana tienes turnos asignados los días {dias_bloques_str}.",
        ""
    ]

    if todos_medicamentos:
        lineas_texto.append("Medicamentos a administrar en tus turnos:")
        for fecha_med, med in todos_medicamentos:
            dia_nom = DIAS_ESPANOL.get(fecha_med.weekday(), "")
            f_str = f"{dia_nom} {fecha_med.strftime('%d/%m/%Y')}"
            h_str = med.hora.strftime("%H:%M")
            n_str = med.tratamiento.nombre_medicamento if med.tratamiento else "Medicamento"
            lineas_texto.append(f"- El día {f_str} a las {h_str} hrs: {n_str}.")
        lineas_texto.append("")

    if todas_actividades:
        lineas_texto.append("Tus actividades médicas programadas en turno son:")
        for fecha_act, act in todas_actividades:
            dia_nom = DIAS_ESPANOL.get(fecha_act.weekday(), "")
            f_str = f"{dia_nom} {fecha_act.strftime('%d/%m/%Y')}"
            h_str = act.hora.strftime("%H:%M")
            desc = act.titulo
            if act.descripcion:
                desc += f" ({act.descripcion})"
            lineas_texto.append(f"- El día {f_str} a las {h_str} tienes {desc}.")
    else:
        lineas_texto.append("No tienes actividades médicas programadas en tus horarios de turno para esta semana.")

    cuerpo_texto = "\n".join(lineas_texto)

    dias_items_html = "".join([f"<li style='margin-bottom: 6px;'>{item}</li>" for item in dias_bloques_list])

    medicamentos_html = ""
    if todos_medicamentos:
        medicamentos_html = "<ul style='margin: 10px 0; padding-left: 20px; line-height: 1.6;'>"
        for fecha_med, med in todos_medicamentos:
            dia_nom = DIAS_ESPANOL.get(fecha_med.weekday(), "")
            f_str = f"{dia_nom} {fecha_med.strftime('%d/%m/%Y')}"
            h_str = med.hora.strftime("%H:%M")
            n_str = med.tratamiento.nombre_medicamento if med.tratamiento else "Medicamento"
            medicamentos_html += f"<li>El día <strong>{f_str}</strong> a las <strong>{h_str} hrs</strong>: {n_str}</li>"
        medicamentos_html += "</ul>"
    else:
        medicamentos_html = "<p style='color: #475569; background: #f8fafc; padding: 10px 14px; border-radius: 8px; margin: 10px 0; font-size: 13px;'>No tienes administración de medicamentos programada en tus turnos.</p>"

    actividades_html = ""
    if todas_actividades:
        actividades_html = "<ul style='margin: 10px 0; padding-left: 20px; line-height: 1.6;'>"
        for fecha_act, act in todas_actividades:
            dia_nom = DIAS_ESPANOL.get(fecha_act.weekday(), "")
            f_str = f"{dia_nom} {fecha_act.strftime('%d/%m/%Y')}"
            h_str = act.hora.strftime("%H:%M")
            desc = f"<strong>{act.titulo}</strong>"
            if act.descripcion:
                desc += f" &bull; {act.descripcion}"
            actividades_html += f"<li>El día <strong>{f_str}</strong> a las <strong>{h_str}</strong> tienes {desc}.</li>"
        actividades_html += "</ul>"
    else:
        actividades_html = "<p style='color: #047857; background: #ecfdf5; padding: 12px; border-radius: 8px; margin: 12px 0;'>No tienes actividades médicas programadas en tus horarios de turno para esta semana.</p>"

    cuerpo_html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; background-color: #f8fafc; padding: 20px; margin: 0;">
        <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
            <div style="background: linear-gradient(135deg, #0284c7, #0d9488); color: white; padding: 22px 24px;">
                <h2 style="margin: 0; font-size: 20px; letter-spacing: -0.025em;">MedTurnos Pro</h2>
                <p style="margin: 4px 0 0; font-size: 13px; opacity: 0.9;">Planificación Semanal ({rango_str})</p>
            </div>
            <div style="padding: 24px;">
                <p style="font-size: 16px; margin-top: 0;">Hola <strong>{nombre}</strong>,</p>
                <p style="font-size: 14px; color: #334155;">Esta semana tienes turnos asignados los siguientes días:</p>
                <ul style="background: #f0f9ff; border-left: 4px solid #0284c7; padding: 12px 16px 12px 30px; border-radius: 6px; margin: 16px 0; font-size: 14px; color: #0369a1;">
                    {dias_items_html}
                </ul>
                <h3 style="font-size: 15px; color: #334155; margin: 20px 0 8px;">💊 Pauta de Medicamentos en tus Turnos:</h3>
                {medicamentos_html}
                <h3 style="font-size: 15px; color: #334155; margin: 20px 0 8px;">📋 Actividades Médicas en tus Turnos:</h3>
                {actividades_html}
            </div>
            <div style="background: #f1f5f9; padding: 12px 24px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0;">
                Sistema Web MedTurnos Pro &bull; Gestión de Cuidadores y Personal Médico
            </div>
        </div>
    </body>
    </html>
    """

    return subject, cuerpo_texto, cuerpo_html

    return subject, cuerpo_texto, cuerpo_html


def enviar_email_via_resend(destinatario: str, asunto: str, texto: str, html: str) -> Dict[str, Any]:
    """
    Envía un correo electrónico a través de la API REST HTTPS de Resend (puerto 443).
    Bypassa cualquier bloqueo de puertos SMTP (25, 465, 587) en Render o la nube.
    """
    api_key_actual = os.getenv("RESEND_API_KEY", "").strip()
    if not api_key_actual or api_key_actual.startswith("re_tu_api_key"):
        raise RuntimeError(
            "RESEND_API_KEY no está configurada o contiene el valor de ejemplo. "
            "Por favor genera tu API Key en https://resend.com y agrégala a las variables de entorno de Render (.env)."
        )

    resend.api_key = api_key_actual
    from_address = os.getenv("RESEND_FROM", RESEND_FROM).strip()

    params: resend.Emails.SendParams = {
        "from": from_address,
        "to": [destinatario.strip()],
        "subject": asunto,
        "text": texto,
        "html": html,
    }

    return resend.Emails.send(params)


def enviar_correos_del_dia(fecha_objetivo: date, db: Session) -> Dict[str, Any]:
    """
    Envía notificación diaria vía Resend API (HTTP) a los cuidadores en turno hoy,
    incluyendo pauta de medicamentos y actividades de la jornada.
    """
    asignaciones: List[AsignacionTurno] = (
        db.query(AsignacionTurno)
        .join(Cuidador)
        .join(BloqueTurno)
        .filter(AsignacionTurno.fecha == fecha_objetivo, Cuidador.activo == True)
        .all()
    )

    actividades_dia: List[ActividadMedica] = (
        db.query(ActividadMedica)
        .filter(ActividadMedica.fecha == fecha_objetivo)
        .order_by(ActividadMedica.hora.asc())
        .all()
    )

    medicamentos_dia: List[MedicamentoHorario] = (
        db.query(MedicamentoHorario)
        .join(TratamientoMedicamento)
        .options(joinedload(MedicamentoHorario.tratamiento).joinedload(TratamientoMedicamento.personal_medico))
        .filter(MedicamentoHorario.dia == fecha_objetivo)
        .order_by(MedicamentoHorario.hora.asc())
        .all()
    )

    asigs_por_cuidador: Dict[int, List[AsignacionTurno]] = {}
    for asig in asignaciones:
        asigs_por_cuidador.setdefault(asig.id_cuidador, []).append(asig)

    resultado = {
        "tipo": "diario",
        "periodo": fecha_objetivo.isoformat(),
        "total_cuidadores": len(asigs_por_cuidador),
        "enviados": 0,
        "omitidos": 0,
        "errores": 0,
        "detalles": []
    }

    if not asigs_por_cuidador:
        return resultado

    for cid, lista in asigs_por_cuidador.items():
        cuid = lista[0].cuidador
        asig_principal = lista[0]
        nombre = format_nombre_cuidador(cuid)

        # 1. Validar que tenga correo
        if not es_email_valido(cuid.mail):
            resultado["omitidos"] += 1
            resultado["detalles"].append({
                "id_cuidador": cuid.id_cuidador,
                "cuidador": nombre,
                "mail": cuid.mail,
                "estado": "OMITIDO",
                "detalle": "El cuidador no tiene correo configurado o el formato es inválido"
            })
            continue

        # 2. Cruce estricto por horario del turno del cuidador:
        # Solo se envían actividades y medicamentos que coincidan exactamente con su jornada
        acts_turno = [
            act for act in actividades_dia
            if any(esta_en_jornada(act.hora, a.hora_inicio, a.hora_fin) for a in lista)
        ]
        meds_turno = [
            m for m in medicamentos_dia
            if any(esta_en_jornada(m.hora, a.hora_inicio, a.hora_fin) for a in lista)
        ]

        # 3. Construir y enviar vía Resend HTTP API
        try:
            subject, text, html = construir_contenido_diario(cuid, asig_principal, acts_turno, meds_turno)
            resend_resp = enviar_email_via_resend(cuid.mail, subject, text, html)
            resp_id = getattr(resend_resp, "id", None) or (resend_resp.get("id") if isinstance(resend_resp, dict) else "")
            logger.info(f"Correo diario enviado vía Resend a {cuid.mail}. ID: {resp_id}")

            resultado["enviados"] += 1
            resultado["detalles"].append({
                "id_cuidador": cuid.id_cuidador,
                "cuidador": nombre,
                "mail": cuid.mail,
                "estado": "ENVIADO",
                "detalle": f"Correo entregado exitosamente vía Resend API (ID: {resp_id})" if resp_id else "Correo entregado exitosamente vía Resend API"
            })
        except Exception as exc:
            logger.error(f"Error enviando correo diario vía Resend a {cuid.mail}: {exc}")
            resultado["errores"] += 1
            resultado["detalles"].append({
                "id_cuidador": cuid.id_cuidador,
                "cuidador": nombre,
                "mail": cuid.mail,
                "estado": "ERROR",
                "detalle": str(exc)
            })

    return resultado


def enviar_correos_semana_completa(fecha_base: date, db: Session) -> Dict[str, Any]:
    """
    Envía planificación semanal consolidada vía Resend API (HTTP) a todos los
    cuidadores con turnos asignados en la semana objetivo.
    """
    inicio_semana = fecha_base - timedelta(days=fecha_base.weekday())
    fin_semana = inicio_semana + timedelta(days=6)

    asignaciones: List[AsignacionTurno] = (
        db.query(AsignacionTurno)
        .join(Cuidador)
        .join(BloqueTurno)
        .filter(
            AsignacionTurno.fecha >= inicio_semana,
            AsignacionTurno.fecha <= fin_semana,
            Cuidador.activo == True
        )
        .order_by(AsignacionTurno.fecha.asc(), AsignacionTurno.hora_inicio.asc())
        .all()
    )

    actividades: List[ActividadMedica] = (
        db.query(ActividadMedica)
        .filter(
            ActividadMedica.fecha >= inicio_semana,
            ActividadMedica.fecha <= fin_semana
        )
        .order_by(ActividadMedica.fecha.asc(), ActividadMedica.hora.asc())
        .all()
    )

    actividades_por_fecha: Dict[date, List[ActividadMedica]] = {}
    for act in actividades:
        actividades_por_fecha.setdefault(act.fecha, []).append(act)

    # Buscar medicamentos de la semana
    medicamentos: List[MedicamentoHorario] = (
        db.query(MedicamentoHorario)
        .join(TratamientoMedicamento)
        .options(joinedload(MedicamentoHorario.tratamiento).joinedload(TratamientoMedicamento.personal_medico))
        .filter(
            MedicamentoHorario.dia >= inicio_semana,
            MedicamentoHorario.dia <= fin_semana
        )
        .order_by(MedicamentoHorario.dia.asc(), MedicamentoHorario.hora.asc())
        .all()
    )

    medicamentos_por_fecha: Dict[date, List[MedicamentoHorario]] = {}
    for m in medicamentos:
        medicamentos_por_fecha.setdefault(m.dia, []).append(m)

    asigs_por_cuidador: Dict[int, List[AsignacionTurno]] = {}
    for asig in asignaciones:
        asigs_por_cuidador.setdefault(asig.id_cuidador, []).append(asig)

    resultado = {
        "tipo": "semanal",
        "periodo": f"{inicio_semana.isoformat()} al {fin_semana.isoformat()}",
        "total_cuidadores": len(asigs_por_cuidador),
        "enviados": 0,
        "omitidos": 0,
        "errores": 0,
        "detalles": []
    }

    if not asigs_por_cuidador:
        return resultado

    for cid, lista in asigs_por_cuidador.items():
        cuid = lista[0].cuidador
        nombre = format_nombre_cuidador(cuid)

        if not es_email_valido(cuid.mail):
            resultado["omitidos"] += 1
            resultado["detalles"].append({
                "id_cuidador": cuid.id_cuidador,
                "cuidador": nombre,
                "mail": cuid.mail,
                "estado": "OMITIDO",
                "detalle": "El cuidador no tiene correo configurado o el formato es inválido"
            })
            continue

        try:
            subject, text, html = construir_contenido_semanal(
                cuidador=cuid,
                asignaciones=lista,
                actividades_por_fecha=actividades_por_fecha,
                inicio_semana=inicio_semana,
                fin_semana=fin_semana,
                medicamentos_por_fecha=medicamentos_por_fecha
            )
            resend_resp = enviar_email_via_resend(cuid.mail, subject, text, html)
            resp_id = getattr(resend_resp, "id", None) or (resend_resp.get("id") if isinstance(resend_resp, dict) else "")
            logger.info(f"Correo semanal enviado vía Resend a {cuid.mail}. ID: {resp_id}")

            resultado["enviados"] += 1
            resultado["detalles"].append({
                "id_cuidador": cuid.id_cuidador,
                "cuidador": nombre,
                "mail": cuid.mail,
                "estado": "ENVIADO",
                "detalle": f"Planificación semanal enviada vía Resend API ({len(lista)} turnos)"
            })
        except Exception as exc:
            logger.error(f"Error enviando correo semanal vía Resend a {cuid.mail}: {exc}")
            resultado["errores"] += 1
            resultado["detalles"].append({
                "id_cuidador": cuid.id_cuidador,
                "cuidador": nombre,
                "mail": cuid.mail,
                "estado": "ERROR",
                "detalle": str(exc)
            })

    return resultado
