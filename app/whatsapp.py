"""Twilio WhatsApp notification service.

Gestión de notificaciones por WhatsApp para cuidadores:
- Notificación diaria (Actualización Diaria).
- Notificación semanal consolidada (todos los cuidadores de la semana con sus turnos y actividades).
"""

import os
import logging
from datetime import date, datetime, timedelta
from typing import List, Dict, Any

from sqlalchemy.orm import Session
from dotenv import load_dotenv

from app.models import AsignacionTurno, ActividadMedica, Cuidador, BloqueTurno
from app.schemas import NotificacionDiaResponse, DetalleEnvio

# ---------------------------------------------------------------------------
# Cargar variables de entorno
# ---------------------------------------------------------------------------
load_dotenv()

logger = logging.getLogger("whatsapp_service")
logging.basicConfig(level=logging.INFO)

# Credenciales de Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")

if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER]):
    raise RuntimeError(
        "Twilio configuration missing: ensure TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_WHATSAPP_NUMBER are set in .env"
    )

# Inicializar cliente Twilio
try:
    from twilio.rest import Client

    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
except Exception as exc:
    logger.error(f"Failed to initialise Twilio client: {exc}")
    raise RuntimeError("Unable to create Twilio client – aborting notification service") from exc


def format_whatsapp_number(raw_number: str) -> str:
    """Normaliza un número telefónico para Twilio WhatsApp (whatsapp:+569...)."""
    clean = raw_number.strip().replace(" ", "").replace("-", "")
    if not clean.startswith("whatsapp:"):
        return f"whatsapp:{clean}"
    return clean


def format_nombre_cuidador(cuidador: Cuidador) -> str:
    """Retorna el nombre completo o solo el nombre si no tiene apellido."""
    apellido = (cuidador.apellido or "").strip()
    return f"{cuidador.nombre.strip()} {apellido}".strip() if apellido else cuidador.nombre.strip()


def build_whatsapp_message(
    cuidador: Cuidador, asignacion: AsignacionTurno, actividades: List[ActividadMedica]
) -> str:
    """Crea el mensaje de WhatsApp para notificación del día."""
    hora_ini = asignacion.hora_inicio.strftime("%H:%M")
    hora_fin = asignacion.hora_fin.strftime("%H:%M")
    fecha_str = asignacion.fecha.strftime("%d/%m/%Y")
    bloque_nombre = (
        asignacion.bloque.nombre_bloque if asignacion.bloque else "Turno asignado"
    )
    nombre = format_nombre_cuidador(cuidador)

    mensaje = (
        f"🏥 *SISTEMA DE GESTIÓN DE CUIDADOS*\n\n"
        f"Hola *{nombre}*,\n\n"
        f"Te informamos tu turno de cuidador/a para hoy (*{fecha_str}*):\n"
        f"📌 *Bloque:* {bloque_nombre}\n"
        f"⏰ *Horario Asignado:* {hora_ini} - {hora_fin} hrs\n"
    )

    if actividades:
        mensaje += "\n📋 *Actividades y Visitas Médicas Programadas Hoy:*\n"
        for idx, act in enumerate(actividades, 1):
            hora_act = act.hora.strftime("%H:%M")
            medico_info = (
                f" (A cargo: {act.medico_asignado.nombre} {act.medico_asignado.apellido})"
                if act.medico_asignado
                else ""
            )
            mensaje += f"  {idx}. [{hora_act}] *{act.titulo}*{medico_info}"
            if act.descripcion:
                mensaje += f" - {act.descripcion}"
            mensaje += "\n"
    else:
        mensaje += "\n📋 *Actividades:* No hay actividades médicas especiales programadas para hoy.\n"

    mensaje += "\n_Por favor confirma la recepción de este mensaje. ¡Buen turno!_"
    return mensaje


DIAS_ESPANOL = {
    0: "Lunes",
    1: "Martes",
    2: "Miércoles",
    3: "Jueves",
    4: "Viernes",
    5: "Sábado",
    6: "Domingo"
}


def build_whatsapp_message_semanal(
    cuidador: Cuidador,
    asignaciones: List[AsignacionTurno],
    actividades_por_fecha: Dict[date, List[ActividadMedica]],
    inicio_semana: date,
    fin_semana: date
) -> str:
    """
    Construye el mensaje de WhatsApp semanal para un cuidador con todos sus turnos
    de la semana y las actividades médicas programadas en sus días asignados.
    """
    nombre = format_nombre_cuidador(cuidador)
    rango_str = f"{inicio_semana.strftime('%d/%m/%Y')} al {fin_semana.strftime('%d/%m/%Y')}"

    mensaje = (
        f"🏥 *SISTEMA DE GESTIÓN DE CUIDADOS*\n"
        f"📅 *Cronograma Semanal de Turnos*\n"
        f"🗓️ *Semana:* {rango_str}\n\n"
        f"Hola *{nombre}*,\n"
        f"A continuación te compartimos tus turnos y actividades programadas para toda la semana:\n\n"
    )

    asignaciones_ordenadas = sorted(asignaciones, key=lambda a: (a.fecha, a.hora_inicio))

    for asig in asignaciones_ordenadas:
        dia_nom = DIAS_ESPANOL.get(asig.fecha.weekday(), "")
        fecha_str = asig.fecha.strftime("%d/%m/%Y")
        hora_ini = asig.hora_inicio.strftime("%H:%M")
        hora_fin = asig.hora_fin.strftime("%H:%M")
        bloque_nombre = asig.bloque.nombre_bloque if asig.bloque else "Turno"

        mensaje += f"📌 *{dia_nom} {fecha_str}*:\n"
        mensaje += f"   ⏰ *Horario:* {hora_ini} - {hora_fin} hrs ({bloque_nombre})\n"

        actividades_dia = actividades_por_fecha.get(asig.fecha, [])
        if actividades_dia:
            mensaje += "   📋 *Actividades Médicas del Día:*\n"
            for idx, act in enumerate(actividades_dia, 1):
                hora_act = act.hora.strftime("%H:%M")
                med_info = f" (A cargo: {act.medico_asignado.nombre} {act.medico_asignado.apellido})" if act.medico_asignado else ""
                mensaje += f"      {idx}. [{hora_act}] {act.titulo}{med_info}"
                if act.descripcion:
                    mensaje += f" - {act.descripcion}"
                mensaje += "\n"
        else:
            mensaje += "   📋 *Actividades:* Sin actividades médicas programadas para este día.\n"
        mensaje += "\n"

    mensaje += "_Por favor confirma la recepción de tu cronograma semanal. ¡Muchas gracias!_"
    return mensaje


def enviar_notificaciones_del_dia(
    fecha_seleccionada: date, db: Session
) -> Dict[str, Any]:
    """Envía notificaciones de actualización diaria por WhatsApp a cuidadores en turno hoy."""
    asignaciones: List[AsignacionTurno] = (
        db.query(AsignacionTurno)
        .join(Cuidador)
        .join(BloqueTurno)
        .filter(AsignacionTurno.fecha == fecha_seleccionada)
        .all()
    )

    actividades_dia: List[ActividadMedica] = (
        db.query(ActividadMedica)
        .filter(ActividadMedica.fecha == fecha_seleccionada)
        .order_by(ActividadMedica.hora.asc())
        .all()
    )

    resultados: Dict[str, Any] = {
        "fecha": fecha_seleccionada,
        "total_asignaciones": len(asignaciones),
        "enviados": 0,
        "errores": 0,
        "detalles": [],
    }

    if not asignaciones:
        return resultados

    for asig in asignaciones:
        if not asig.cuidador.activo:
            continue

        mensaje_texto = build_whatsapp_message(asig.cuidador, asig, actividades_dia)
        destino_whatsapp = format_whatsapp_number(asig.cuidador.telefono_whatsapp)
        nombre_cuid = format_nombre_cuidador(asig.cuidador)

        detalle: Dict[str, Any] = {
            "id_asignacion": asig.id_asignacion,
            "personal": f"{nombre_cuid} (Cuidador)",
            "telefono": asig.cuidador.telefono_whatsapp,
            "bloque": asig.bloque.nombre_bloque if asig.bloque else "Personalizado",
            "horario": f"{asig.hora_inicio.strftime('%H:%M')} - {asig.hora_fin.strftime('%H:%M')}",
            "mensaje": mensaje_texto,
            "estado": "PENDIENTE",
            "detalle_error": None,
        }

        try:
            message = twilio_client.messages.create(
                body=mensaje_texto,
                from_=TWILIO_WHATSAPP_NUMBER,
                to=destino_whatsapp,
            )
            logger.info(f"WhatsApp diario enviado a {destino_whatsapp}. SID: {message.sid}")
            asig.estado_notificacion = "ENVIADO"
            asig.fecha_envio_whatsapp = datetime.utcnow()
            detalle["estado"] = "ENVIADO"
            resultados["enviados"] += 1
        except Exception as exc:
            logger.error(f"Error enviando WhatsApp diario a {destino_whatsapp}: {exc}")
            asig.estado_notificacion = "ERROR"
            detalle["estado"] = "ERROR"
            detalle["detalle_error"] = str(exc)
            resultados["errores"] += 1

        db.commit()
        db.refresh(asig)
        resultados["detalles"].append(detalle)

    return resultados


def enviar_notificaciones_semana_completa(
    fecha_base: date, db: Session
) -> Dict[str, Any]:
    """
    Envía mensaje consolidado de WhatsApp a TODOS los cuidadores asignados
    en la semana completa, con sus horarios y actividades médicas de sus turnos.
    """
    inicio_semana = fecha_base - timedelta(days=fecha_base.weekday())
    fin_semana = inicio_semana + timedelta(days=6)

    # Buscar asignaciones de la semana para cuidadores activos
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

    # Buscar actividades médicas de la semana
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

    # Agrupar asignaciones por cuidador
    asigs_por_cuidador: Dict[int, List[AsignacionTurno]] = {}
    for asig in asignaciones:
        asigs_por_cuidador.setdefault(asig.id_cuidador, []).append(asig)

    resultados: Dict[str, Any] = {
        "semana_inicio": inicio_semana.isoformat(),
        "semana_fin": fin_semana.isoformat(),
        "total_cuidadores": len(asigs_por_cuidador),
        "total_asignaciones": len(asignaciones),
        "enviados": 0,
        "errores": 0,
        "detalles": []
    }

    if not asigs_por_cuidador:
        return resultados

    for id_cuidador, lista_asigs in asigs_por_cuidador.items():
        cuidador = lista_asigs[0].cuidador
        mensaje_texto = build_whatsapp_message_semanal(
            cuidador=cuidador,
            asignaciones=lista_asigs,
            actividades_por_fecha=actividades_por_fecha,
            inicio_semana=inicio_semana,
            fin_semana=fin_semana
        )
        destino_whatsapp = format_whatsapp_number(cuidador.telefono_whatsapp)
        nombre_cuid = format_nombre_cuidador(cuidador)

        detalle: Dict[str, Any] = {
            "id_cuidador": cuidador.id_cuidador,
            "cuidador": nombre_cuid,
            "telefono": cuidador.telefono_whatsapp,
            "total_turnos": len(lista_asigs),
            "estado": "PENDIENTE",
            "detalle_error": None
        }

        try:
            message = twilio_client.messages.create(
                body=mensaje_texto,
                from_=TWILIO_WHATSAPP_NUMBER,
                to=destino_whatsapp
            )
            logger.info(f"WhatsApp semanal enviado a {destino_whatsapp}. SID: {message.sid}")
            detalle["estado"] = "ENVIADO"
            resultados["enviados"] += 1
            ahora = datetime.utcnow()
            for asig in lista_asigs:
                asig.estado_notificacion = "ENVIADO"
                asig.fecha_envio_whatsapp = ahora
        except Exception as exc:
            logger.error(f"Error enviando WhatsApp semanal a {destino_whatsapp}: {exc}")
            detalle["estado"] = "ERROR"
            detalle["detalle_error"] = str(exc)
            resultados["errores"] += 1
            for asig in lista_asigs:
                asig.estado_notificacion = "ERROR"

        db.commit()
        resultados["detalles"].append(detalle)

    return resultados
