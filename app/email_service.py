"""Módulo de Notificaciones por Correo Electrónico (Gmail SMTP).

Implementa envío manual y masivo de correos para cuidadores:
- Notificación Diaria: Turno y actividades médicas del día.
- Notificación Semanal: Planificación completa de turnos y actividades de la semana.
"""

import os
import smtplib
import ssl
import logging
from email.message import EmailMessage
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from app.models import AsignacionTurno, ActividadMedica, Cuidador, BloqueTurno

load_dotenv()

logger = logging.getLogger("email_service")
logging.basicConfig(level=logging.INFO)

# Configuración SMTP Gmail
MAIL_USERNAME = os.getenv("MAIL_USERNAME", "medturnospro@gmail.com")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "mdfe gdyl eswk acbi")
MAIL_FROM = os.getenv("MAIL_FROM", "medturnospro@gmail.com")
MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "MedTurnos Pro")

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


def crear_conexion_smtp():
    """Establece conexión autenticada con el servidor SMTP de Gmail con STARTTLS."""
    context = ssl.create_default_context()
    server = smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=15)
    server.ehlo()
    server.starttls(context=context)
    server.ehlo()
    server.login(MAIL_USERNAME, MAIL_PASSWORD)
    return server


def construir_mensaje_diario(
    cuidador: Cuidador,
    asignacion: AsignacionTurno,
    actividades: List[ActividadMedica]
) -> EmailMessage:
    """Construye correo diario según especificación."""
    nombre = format_nombre_cuidador(cuidador)
    fecha_str = asignacion.fecha.strftime("%d/%m/%Y")
    bloque_nombre = asignacion.bloque.nombre_bloque if asignacion.bloque else "Turno asignado"
    hora_ini = asignacion.hora_inicio.strftime("%H:%M")
    hora_fin = asignacion.hora_fin.strftime("%H:%M")

    # Texto plano según especificación exacta
    lineas_texto = [
        f"Hola {nombre},",
        f"Tu turno para el día de hoy {fecha_str} es en el bloque {bloque_nombre} ({hora_ini} - {hora_fin}).",
        ""
    ]

    if actividades:
        lineas_texto.append("Tus actividades del día son:")
        for act in actividades:
            hora_act = act.hora.strftime("%H:%M")
            desc = act.titulo
            if act.descripcion:
                desc += f" - {act.descripcion}"
            lineas_texto.append(f"- A las {hora_act} tienes {desc}.")
    else:
        lineas_texto.append("Hoy no tienes actividades médicas programadas. ¡Que tengas un excelente turno!")

    cuerpo_texto = "\n".join(lineas_texto)

    # HTML elegante
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
        actividades_html = "<p style='color: #047857; background: #ecfdf5; padding: 10px; border-radius: 8px;'>Hoy no tienes actividades médicas programadas. ¡Que tengas un excelente turno!</p>"

    cuerpo_html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: Arial, sans-serif; color: #1e293b; background-color: #f8fafc; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
            <div style="background: linear-gradient(135deg, #0284c7, #0d9488); color: white; padding: 20px 24px;">
                <h2 style="margin: 0; font-size: 20px;">MedTurnos Pro</h2>
                <p style="margin: 4px 0 0; font-size: 13px; opacity: 0.9;">Notificación Diaria de Turno</p>
            </div>
            <div style="padding: 24px;">
                <p style="font-size: 16px; margin-top: 0;">Hola <strong>{nombre}</strong>,</p>
                <div style="background: #f0f9ff; border-left: 4px solid #0284c7; padding: 12px 16px; border-radius: 6px; margin: 16px 0;">
                    <p style="margin: 0; font-size: 14px;">
                        Tu turno para el día de hoy <strong>{fecha_str}</strong> es en el bloque <strong>{bloque_nombre}</strong> (<strong>{hora_ini} - {hora_fin} hrs</strong>).
                    </p>
                </div>
                <h3 style="font-size: 15px; color: #334155; margin: 20px 0 8px;">Tus actividades del día son:</h3>
                {actividades_html}
            </div>
            <div style="background: #f1f5f9; padding: 12px 24px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0;">
                Sistema Web MedTurnos Pro &bull; Gestión de Cuidadores y Personal Médico
            </div>
        </div>
    </body>
    </html>
    """

    msg = EmailMessage()
    msg["Subject"] = f"MedTurnos Pro - Tu turno para hoy {fecha_str}"
    msg["From"] = f'"{MAIL_FROM_NAME}" <{MAIL_FROM}>'
    msg["To"] = cuidador.mail.strip()
    msg.set_content(cuerpo_texto)
    msg.add_alternative(cuerpo_html, subtype="html")
    return msg


def construir_mensaje_semanal(
    cuidador: Cuidador,
    asignaciones: List[AsignacionTurno],
    actividades_por_fecha: Dict[date, List[ActividadMedica]],
    inicio_semana: date,
    fin_semana: date
) -> EmailMessage:
    """Construye correo semanal según especificación."""
    nombre = format_nombre_cuidador(cuidador)

    # Ordenar turnos
    asigs_ordenadas = sorted(asignaciones, key=lambda a: (a.fecha, a.hora_inicio))

    # Formar listado de días y bloques
    dias_bloques_list = []
    for asig in asigs_ordenadas:
        dia_nom = DIAS_ESPANOL.get(asig.fecha.weekday(), "")
        fecha_str = asig.fecha.strftime("%d/%m")
        bloque = asig.bloque.nombre_bloque if asig.bloque else "Turno"
        hora_ini = asig.hora_inicio.strftime("%H:%M")
        hora_fin = asig.hora_fin.strftime("%H:%M")
        dias_bloques_list.append(f"{dia_nom} {fecha_str} en bloque {bloque} ({hora_ini} - {hora_fin})")

    dias_bloques_str = ", ".join(dias_bloques_list)

    # Recopilar actividades médicas de los días asignados
    todas_actividades = []
    for asig in asigs_ordenadas:
        acts_dia = actividades_por_fecha.get(asig.fecha, [])
        for act in acts_dia:
            todas_actividades.append((asig.fecha, act))

    # Texto plano según especificación
    lineas_texto = [
        f"Hola {nombre},",
        f"Esta semana tienes turnos asignados los días {dias_bloques_str}.",
        ""
    ]

    if todas_actividades:
        lineas_texto.append("Además, tus actividades médicas programadas son:")
        for fecha_act, act in todas_actividades:
            dia_nom = DIAS_ESPANOL.get(fecha_act.weekday(), "")
            f_str = f"{dia_nom} {fecha_act.strftime('%d/%m/%Y')}"
            h_str = act.hora.strftime("%H:%M")
            desc = act.titulo
            if act.descripcion:
                desc += f" ({act.descripcion})"
            lineas_texto.append(f"- El día {f_str} a las {h_str} tienes {desc}.")
    else:
        lineas_texto.append("No tienes actividades médicas adicionales programadas para esta semana.")

    cuerpo_texto = "\n".join(lineas_texto)

    # HTML elegante
    dias_items_html = "".join([f"<li style='margin-bottom: 4px;'>{item}</li>" for item in dias_bloques_list])

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
        actividades_html = "<p style='color: #047857; background: #ecfdf5; padding: 10px; border-radius: 8px;'>No tienes actividades médicas adicionales programadas para esta semana.</p>"

    rango_str = f"{inicio_semana.strftime('%d/%m/%Y')} al {fin_semana.strftime('%d/%m/%Y')}"

    cuerpo_html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: Arial, sans-serif; color: #1e293b; background-color: #f8fafc; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
            <div style="background: linear-gradient(135deg, #0284c7, #0d9488); color: white; padding: 20px 24px;">
                <h2 style="margin: 0; font-size: 20px;">MedTurnos Pro</h2>
                <p style="margin: 4px 0 0; font-size: 13px; opacity: 0.9;">Planificación Semanal ({rango_str})</p>
            </div>
            <div style="padding: 24px;">
                <p style="font-size: 16px; margin-top: 0;">Hola <strong>{nombre}</strong>,</p>
                <p style="font-size: 14px;">Esta semana tienes turnos asignados los siguientes días:</p>
                <ul style="background: #f0f9ff; border-left: 4px solid #0284c7; padding: 12px 16px 12px 30px; border-radius: 6px; margin: 16px 0; font-size: 14px;">
                    {dias_items_html}
                </ul>
                <h3 style="font-size: 15px; color: #334155; margin: 20px 0 8px;">Además, tus actividades médicas programadas son:</h3>
                {actividades_html}
            </div>
            <div style="background: #f1f5f9; padding: 12px 24px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0;">
                Sistema Web MedTurnos Pro &bull; Gestión de Cuidadores y Personal Médico
            </div>
        </div>
    </body>
    </html>
    """

    msg = EmailMessage()
    msg["Subject"] = f"MedTurnos Pro - Planificación semanal de turnos ({rango_str})"
    msg["From"] = f'"{MAIL_FROM_NAME}" <{MAIL_FROM}>'
    msg["To"] = cuidador.mail.strip()
    msg.set_content(cuerpo_texto)
    msg.add_alternative(cuerpo_html, subtype="html")
    return msg


def enviar_correos_del_dia(fecha_objetivo: date, db: Session) -> Dict[str, Any]:
    """Envía notificación diaria por correo a todos los cuidadores en turno hoy."""
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

    # Agrupar por cuidador para no enviar múltiples correos si tuviera más de 1 bloque
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

    # Conectar a SMTP
    smtp_conn = None
    try:
        smtp_conn = crear_conexion_smtp()
    except Exception as exc:
        logger.error(f"Error conectando con servidor SMTP: {exc}")
        # Registrar error para todos
        for cid, lista in asigs_por_cuidador.items():
            cuid = lista[0].cuidador
            resultado["detalles"].append({
                "id_cuidador": cuid.id_cuidador,
                "cuidador": format_nombre_cuidador(cuid),
                "mail": cuid.mail,
                "estado": "ERROR",
                "detalle": f"Error de conexión SMTP: {exc}"
            })
            resultado["errores"] += 1
        return resultado

    try:
        for cid, lista in asigs_por_cuidador.items():
            cuid = lista[0].cuidador
            nombre = format_nombre_cuidador(cuid)

            # Verificar email válido
            if not es_email_valido(cuid.mail):
                resultado["omitidos"] += 1
                resultado["detalles"].append({
                    "id_cuidador": cuid.id_cuidador,
                    "cuidador": nombre,
                    "mail": cuid.mail,
                    "estado": "OMITIDO",
                    "detalle": "El cuidador no tiene correo configurado o es inválido"
                })
                continue

            # Construir correo para la primera asignación (o combinadas)
            try:
                msg = construir_mensaje_diario(cuid, lista[0], actividades_dia)
                smtp_conn.send_message(msg)
                logger.info(f"Correo diario enviado a {cuid.mail}")
                resultado["enviados"] += 1
                resultado["detalles"].append({
                    "id_cuidador": cuid.id_cuidador,
                    "cuidador": nombre,
                    "mail": cuid.mail,
                    "estado": "ENVIADO",
                    "detalle": "Correo diario entregado exitosamente"
                })
            except Exception as exc:
                logger.error(f"Error enviando correo diario a {cuid.mail}: {exc}")
                resultado["errores"] += 1
                resultado["detalles"].append({
                    "id_cuidador": cuid.id_cuidador,
                    "cuidador": nombre,
                    "mail": cuid.mail,
                    "estado": "ERROR",
                    "detalle": str(exc)
                })
    finally:
        try:
            smtp_conn.quit()
        except Exception:
            pass

    return resultado


def enviar_correos_semana_completa(fecha_base: date, db: Session) -> Dict[str, Any]:
    """Envía notificación semanal por correo a todos los cuidadores con turnos en la semana."""
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

    smtp_conn = None
    try:
        smtp_conn = crear_conexion_smtp()
    except Exception as exc:
        logger.error(f"Error conectando con servidor SMTP: {exc}")
        for cid, lista in asigs_por_cuidador.items():
            cuid = lista[0].cuidador
            resultado["detalles"].append({
                "id_cuidador": cuid.id_cuidador,
                "cuidador": format_nombre_cuidador(cuid),
                "mail": cuid.mail,
                "estado": "ERROR",
                "detalle": f"Error de conexión SMTP: {exc}"
            })
            resultado["errores"] += 1
        return resultado

    try:
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
                    "detalle": "El cuidador no tiene correo configurado o es inválido"
                })
                continue

            try:
                msg = construir_mensaje_semanal(
                    cuidador=cuid,
                    asignaciones=lista,
                    actividades_por_fecha=actividades_por_fecha,
                    inicio_semana=inicio_semana,
                    fin_semana=fin_semana
                )
                smtp_conn.send_message(msg)
                logger.info(f"Correo semanal enviado a {cuid.mail}")
                resultado["enviados"] += 1
                resultado["detalles"].append({
                    "id_cuidador": cuid.id_cuidador,
                    "cuidador": nombre,
                    "mail": cuid.mail,
                    "estado": "ENVIADO",
                    "detalle": f"Planificación semanal enviada ({len(lista)} turnos)"
                })
            except Exception as exc:
                logger.error(f"Error enviando correo semanal a {cuid.mail}: {exc}")
                resultado["errores"] += 1
                resultado["detalles"].append({
                    "id_cuidador": cuid.id_cuidador,
                    "cuidador": nombre,
                    "mail": cuid.mail,
                    "estado": "ERROR",
                    "detalle": str(exc)
                })
    finally:
        try:
            smtp_conn.quit()
        except Exception:
            pass

    return resultado
