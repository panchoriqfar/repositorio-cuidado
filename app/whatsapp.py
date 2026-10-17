import os
import logging
from datetime import date, datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from app.models import AsignacionTurno, ActividadMedica, Cuidador, BloqueTurno

load_dotenv()

logger = logging.getLogger("whatsapp_service")
logging.basicConfig(level=logging.INFO)

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

def format_whatsapp_number(raw_number: str) -> str:
    """Asegura que el número tenga el prefijo 'whatsapp:' requerido por Twilio."""
    clean = raw_number.strip().replace(" ", "").replace("-", "")
    if not clean.startswith("whatsapp:"):
        return f"whatsapp:{clean}"
    return clean

def build_whatsapp_message(cuidador: Cuidador, asignacion: AsignacionTurno, actividades: List[ActividadMedica]) -> str:
    """
    Construye el mensaje personalizado para el cuidador con el horario exacto asignado (00:00 a 23:59)
    y el bloque horario correspondiente.
    """
    hora_ini = asignacion.hora_inicio.strftime("%H:%M")
    hora_fin = asignacion.hora_fin.strftime("%H:%M")
    fecha_str = asignacion.fecha.strftime("%d/%m/%Y")
    bloque_nombre = asignacion.bloque.nombre_bloque if asignacion.bloque else "Turno Asignado"

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
            medico_info = f" (A cargo: {act.medico_asignado.nombre} {act.medico_asignado.apellido})" if act.medico_asignado else ""
            mensaje += f"  {idx}. [{hora_act}] *{act.titulo}*{medico_info}"
            if act.descripcion:
                mensaje += f" - {act.descripcion}"
            mensaje += "\n"
    else:
        mensaje += "\n📋 *Actividades:* No hay actividades médicas especiales programadas para hoy.\n"

    mensaje += "\n_Por favor confirma la recepción de este mensaje. ¡Buen turno!_"
    return mensaje

def enviar_notificaciones_del_dia(fecha_seleccionada: date, db: Session) -> Dict[str, Any]:
    """
    Consulta las asignaciones de turno de cuidadores para la fecha,
    las actividades médicas asociadas y envía las notificaciones vía WhatsApp Twilio API.
    """
    asignaciones = (
        db.query(AsignacionTurno)
        .join(Cuidador)
        .join(BloqueTurno)
        .filter(AsignacionTurno.fecha == fecha_seleccionada)
        .all()
    )

    actividades_dia = (
        db.query(ActividadMedica)
        .filter(ActividadMedica.fecha == fecha_seleccionada)
        .order_by(ActividadMedica.hora.asc())
        .all()
    )

    resultados = {
        "fecha": fecha_seleccionada,
        "total_asignaciones": len(asignaciones),
        "enviados": 0,
        "errores": 0,
        "detalles": []
    }

    if not asignaciones:
        return resultados

    client = None
    modo_simulacion = False
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and not TWILIO_ACCOUNT_SID.startswith("tu_sid"):
        try:
            from twilio.rest import Client
            client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        except Exception as e:
            logger.error(f"Error inicializando cliente Twilio: {e}")
            modo_simulacion = True
    else:
        modo_simulacion = True
        logger.warning("Twilio en modo simulación local.")

    for asig in asignaciones:
        cuidador = asig.cuidador
        if not cuidador.activo:
            continue

        mensaje_texto = build_whatsapp_message(cuidador, asig, actividades_dia)
        destino_whatsapp = format_whatsapp_number(cuidador.telefono_whatsapp)
        hora_ini = asig.hora_inicio.strftime("%H:%M")
        hora_fin = asig.hora_fin.strftime("%H:%M")

        detalle = {
            "id_asignacion": asig.id_asignacion,
            "personal": f"{cuidador.nombre} {cuidador.apellido} (Cuidador)",
            "telefono": cuidador.telefono_whatsapp,
            "bloque": asig.bloque.nombre_bloque if asig.bloque else "Personalizado",
            "horario": f"{hora_ini} - {hora_fin}",
            "mensaje": mensaje_texto,
            "estado": "PENDIENTE",
            "detalle_error": None
        }

        try:
            if not modo_simulacion and client:
                message = client.messages.create(
                    body=mensaje_texto,
                    from_=TWILIO_WHATSAPP_NUMBER,
                    to=destino_whatsapp
                )
                logger.info(f"WhatsApp enviado a {destino_whatsapp}. SID: {message.sid}")
                asig.estado_notificacion = "ENVIADO"
                asig.fecha_envio_whatsapp = datetime.utcnow()
                detalle["estado"] = "ENVIADO"
                resultados["enviados"] += 1
            else:
                asig.estado_notificacion = "ENVIADO"
                asig.fecha_envio_whatsapp = datetime.utcnow()
                detalle["estado"] = "ENVIADO (SIMULADO)"
                detalle["detalle_error"] = "Modo simulación local activo"
                resultados["enviados"] += 1
        except Exception as exc:
            logger.error(f"Error enviando WhatsApp: {exc}")
            asig.estado_notificacion = "ERROR"
            detalle["estado"] = "ERROR"
            detalle["detalle_error"] = str(exc)
            resultados["errores"] += 1

        db.commit()
        db.refresh(asig)
        resultados["detalles"].append(detalle)

    return resultados
