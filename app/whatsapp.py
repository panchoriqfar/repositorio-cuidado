"""Twilio WhatsApp notification service.

The original implementation mixed production and simulated behaviour and
performed only minimal validation of the required environment variables.  This
revision:

* Validates that ``TWILIO_ACCOUNT_SID``, ``TWILIO_AUTH_TOKEN`` and
  ``TWILIO_WHATSAPP_NUMBER`` are present – otherwise it raises a clear error.
* Normalises phone numbers with ``format_whatsapp_number``.
* Builds a richer, markdown‑friendly message for the caregiver.
* Sends the message via the Twilio client; any exception is captured and the
  assignment record is updated with ``ERROR`` status.
* Returns the same ``Dict`` structure used by the API but the function now has
  a proper return type annotation.
"""

import os
import logging
from datetime import date, datetime
from typing import List, Dict, Any

from sqlalchemy.orm import Session
from dotenv import load_dotenv

from app.models import AsignacionTurno, ActividadMedica, Cuidador, BloqueTurno
from app.schemas import NotificacionDiaResponse, DetalleEnvio

# ---------------------------------------------------------------------------
# Load environment variables
# ---------------------------------------------------------------------------
load_dotenv()

logger = logging.getLogger("whatsapp_service")
logging.basicConfig(level=logging.INFO)

# Required Twilio credentials – raise early if they are missing.
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")

if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER]):
    raise RuntimeError(
        "Twilio configuration missing: ensure TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_WHATSAPP_NUMBER are set in .env"
    )

# Initialise the Twilio client once – any import error will be raised at start‑up.
try:
    from twilio.rest import Client

    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
except Exception as exc:
    logger.error(f"Failed to initialise Twilio client: {exc}")
    raise RuntimeError("Unable to create Twilio client – aborting notification service") from exc


def format_whatsapp_number(raw_number: str) -> str:
    """Normalise a phone number for Twilio.

    The function strips spaces and hyphens and ensures the ``whatsapp:`` prefix
    required by the Twilio API.
    """
    clean = raw_number.strip().replace(" ", "").replace("-", "")
    if not clean.startswith("whatsapp:"):
        return f"whatsapp:{clean}"
    return clean


def build_whatsapp_message(
    cuidador: Cuidador, asignacion: AsignacionTurno, actividades: List[ActividadMedica]
) -> str:
    """Create the markdown‑styled WhatsApp message for a caregiver.

    Parameters
    ----------
    cuidador: Cuidador
        The caregiver who will receive the notification.
    asignacion: AsignacionTurno
        The shift assignment for the selected date.
    actividades: List[ActividadMedica]
        All medical activities scheduled for the same day (the caller may filter
        them if needed).
    """
    hora_ini = asignacion.hora_inicio.strftime("%H:%M")
    hora_fin = asignacion.hora_fin.strftime("%H:%M")
    fecha_str = asignacion.fecha.strftime("%d/%m/%Y")
    bloque_nombre = (
        asignacion.bloque.nombre_bloque if asignacion.bloque else "Turno asignado"
    )

    mensaje = (
        f"🏥 *SISTEMA DE GESTIÓN DE CUIDADOS*\n\n"
        f"Hola *{cuidador.nombre} {cuidador.apellido}*,\n\n"
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


def enviar_notificaciones_del_dia(
    fecha_seleccionada: date, db: Session
) -> Dict[str, Any]:
    """Send WhatsApp notifications for *all* active caregiver assignments.

    The function aggregates assignments for the given date, fetches any medical
    activities scheduled that day, builds a personalised message for each active
    caregiver and sends it via Twilio.  The DB rows are updated with the send
    status and a summary dictionary is returned (compatible with the original
    ``NotificacionDiaResponse`` schema).
    """
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
            # Skip inactive caregivers – they should not receive notifications.
            continue

        mensaje_texto = build_whatsapp_message(asig.cuidador, asig, actividades_dia)
        destino_whatsapp = format_whatsapp_number(asig.cuidador.telefono_whatsapp)

        detalle: Dict[str, Any] = {
            "id_asignacion": asig.id_asignacion,
            "personal": f"{asig.cuidador.nombre} {asig.cuidador.apellido} (Cuidador)",
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
            logger.info(f"WhatsApp enviado a {destino_whatsapp}. SID: {message.sid}")
            asig.estado_notificacion = "ENVIADO"
            asig.fecha_envio_whatsapp = datetime.utcnow()
            detalle["estado"] = "ENVIADO"
            resultados["enviados"] += 1
        except Exception as exc:
            logger.error(f"Error enviando WhatsApp a {destino_whatsapp}: {exc}")
            asig.estado_notificacion = "ERROR"
            detalle["estado"] = "ERROR"
            detalle["detalle_error"] = str(exc)
            resultados["errores"] += 1

        db.commit()
        db.refresh(asig)
        resultados["detalles"].append(detalle)

    return resultados
