"""Módulo de Notificaciones por Correo Electrónico vía API HTTP (Resend).

Diseñado específicamente para despliegues en la nube (Render, Railway, Fly.io)
donde los puertos SMTP convencionales (25, 465, 587) se encuentran bloqueados.
Utiliza HTTPS (puerto 443) a través del cliente oficial de Resend.
"""

import os
import logging
from datetime import date, time, datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple, Union
from sqlalchemy.orm import Session, joinedload
from dotenv import load_dotenv
import resend

from app.models import AsignacionTurno, ActividadMedica, Cuidador, BloqueTurno, TratamientoMedicamento, MedicamentoHorario
from app.medicamentos_service import (
    TomaMedicamento,
    obtener_medicamentos_programados,
    esta_en_jornada_asig,
    corresponde_medicamento_a_cuidador,
    formatear_pauta_medicamentos,
)

load_dotenv()

logger = logging.getLogger("email_service")
logging.basicConfig(level=logging.INFO)

# Configuración de Resend y Remitente de Producción
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
DEFAULT_SENDER_EMAIL = "notificaciones@medturnospro.tech"
SENDER_EMAIL = os.getenv("SENDER_EMAIL", DEFAULT_SENDER_EMAIL).strip() or DEFAULT_SENDER_EMAIL
DEFAULT_FROM_NAME = "Sistema MedTurnos"
RESEND_FROM = os.getenv("RESEND_FROM", f"{DEFAULT_FROM_NAME} <{SENDER_EMAIL}>").strip()

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


def esta_en_jornada_asig(dia_item: date, hora_item: time, asig: AsignacionTurno) -> bool:
    """Verifica si la fecha y hora corresponden al rango exacto de la jornada del turno asignado."""
    dt_item = datetime.combine(dia_item, hora_item)
    dt_inicio = datetime.combine(asig.fecha, asig.hora_inicio)
    if asig.hora_inicio <= asig.hora_fin:
        dt_fin = datetime.combine(asig.fecha, asig.hora_fin)
    else:
        # Turno nocturno que cruza medianoche (ej: 21:00 a 07:00 del día siguiente)
        dt_fin = datetime.combine(asig.fecha + timedelta(days=1), asig.hora_fin)
    return dt_inicio <= dt_item <= dt_fin


def format_turnos_diarios_texto(
    asignaciones: Union[AsignacionTurno, List[AsignacionTurno]],
    estilo: str = "texto"
) -> str:
    """
    Formatea la descripción consolidada de los turnos de un cuidador para el día.
    estilo: 'texto' (plano), 'whatsapp' (con asteriscos *negrita*), 'html' (con <strong>)
    """
    if isinstance(asignaciones, (list, tuple, set)):
        lista = list(asignaciones)
    else:
        lista = [asignaciones]

    if not lista:
        return "sin turno asignado"

    lista_ordenada = sorted(lista, key=lambda a: a.hora_inicio)

    frases = []
    for asig in lista_ordenada:
        bloque = asig.bloque.nombre_bloque if asig.bloque else "Turno asignado"
        h_ini = asig.hora_inicio.strftime("%H:%M")
        h_fin = asig.hora_fin.strftime("%H:%M")
        es_rf = bool(getattr(asig, "reunion_familiar", False))

        if estilo == "html":
            extra_rf = " <span style='color:#b45309;font-weight:bold;'>[REUNION FAMILIAR]</span>" if es_rf else ""
            frases.append(f"<strong>{bloque}</strong> (<strong>{h_ini} - {h_fin} hrs</strong>){extra_rf}")
        elif estilo == "whatsapp":
            extra_rf = " *[REUNION FAMILIAR]*" if es_rf else ""
            frases.append(f"*{bloque}* (*{h_ini} - {h_fin} hrs*){extra_rf}")
        else:
            extra_rf = " [REUNION FAMILIAR]" if es_rf else ""
            frases.append(f"{bloque} ({h_ini} - {h_fin} hrs){extra_rf}")

    if len(frases) == 1:
        return f"el bloque {frases[0]}"
    elif len(frases) == 2:
        return f"el bloque {frases[0]} y luego {frases[1]}"
    else:
        primeros = ", luego ".join(frases[:-1])
        return f"el bloque {primeros} y luego {frases[-1]}"


def construir_contenido_diario(
    cuidador: Cuidador,
    asignacion: Union[AsignacionTurno, List[AsignacionTurno]],
    actividades: List[ActividadMedica],
    medicamentos: Optional[List[MedicamentoHorario]] = None
) -> Tuple[str, str, str]:
    """
    Construye el asunto, texto plano y HTML del correo diario
    según el formato consolidado para uno o varios turnos en el día,
    incluyendo lista detallada de medicamentos y actividades de los horarios asignados.
    """
    if isinstance(asignacion, (list, tuple, set)):
        lista = list(asignacion)
    else:
        lista = [asignacion]

    nombre = format_nombre_cuidador(cuidador)
    fecha_obj = lista[0].fecha if lista else date.today()
    fecha_str = fecha_obj.strftime("%d/%m/%Y")
    dia_nom = DIAS_ESPANOL.get(fecha_obj.weekday(), "")

    turnos_txt = format_turnos_diarios_texto(lista, estilo="texto")
    turnos_html = format_turnos_diarios_texto(lista, estilo="html")

    hora_actual = datetime.now().strftime("%H:%M:%S")
    subject = f"MedTurnos Pro - Tu turno para hoy [{hora_actual}]"

    lineas_texto = [
        f"Hola {nombre},",
        f"Tu turno para el día de hoy {fecha_str} es en {turnos_txt}.",
        ""
    ]

    # Sección de Medicamentos de la Jornada (Pauta Agrupada Fluida)
    if medicamentos:
        lineas_texto.append("Medicamentos a administrar en tu turno:")
        meds_fmt = formatear_pauta_medicamentos(medicamentos)
        for item in meds_fmt:
            lineas_texto.append(f"- {item['texto_plano']}")
        lineas_texto.append("")
    else:
        lineas_texto.append("No tienes administración de medicamentos programada para tu turno.")
        lineas_texto.append("")

    # Sección de Actividades Médicas
    acts_agrupadas: Dict[str, Dict[str, Any]] = {}
    if actividades:
        lineas_texto.append("Tus actividades médicas programadas en el turno son:")
        for act in actividades:
            tit = act.titulo.strip()
            if tit not in acts_agrupadas:
                medico_info = ""
                if act.medico_asignado:
                    nombre_med = f"{act.medico_asignado.nombre} {act.medico_asignado.apellido or ''}".strip()
                    medico_info = f" (A cargo: {nombre_med})"
                desc_info = f" - {act.descripcion.strip()}" if act.descripcion else ""
                acts_agrupadas[tit] = {
                    "horas": [],
                    "medico_info": medico_info,
                    "desc_info": desc_info
                }
            h_act = act.hora.strftime("%H:%M")
            if h_act not in acts_agrupadas[tit]["horas"]:
                acts_agrupadas[tit]["horas"].append(h_act)

        for tit, data in acts_agrupadas.items():
            horas_str = ", ".join(data["horas"])
            lineas_texto.append(f"- {tit}: {horas_str} hrs{data['medico_info']}{data['desc_info']}.")
    else:
        lineas_texto.append("No tienes actividades médicas programadas durante tu horario de turno. ¡Que tengas un excelente turno!")

    cuerpo_texto = "\n".join(lineas_texto)

    # HTML elegante para medicamentos (Pauta Agrupada Fluida)
    medicamentos_html = ""
    if medicamentos:
        meds_fmt = formatear_pauta_medicamentos(medicamentos)
        medicamentos_html = "<div style='background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 14px; margin: 12px 0;'>"
        medicamentos_html += "<ul style='margin: 0; padding-left: 20px; line-height: 1.6;'>"
        for item in meds_fmt:
            medicamentos_html += f"<li style='margin-bottom: 4px;'>{item['texto_html']}</li>"
        medicamentos_html += "</ul></div>"
    else:
        medicamentos_html = "<p style='color: #475569; background: #f8fafc; padding: 12px; border-radius: 8px; margin: 12px 0;'>No tienes administración de medicamentos programada para tu turno.</p>"

    # HTML elegante para actividades
    actividades_html = ""
    if actividades:
        actividades_html = "<ul style='margin: 10px 0; padding-left: 20px; line-height: 1.6;'>"
        for tit, data in acts_agrupadas.items():
            horas_str = ", ".join(data["horas"])
            medico_html = f" <span style='color: #64748b;'>&bull; {data['medico_info'].strip(' ()')}</span>" if data["medico_info"] else ""
            desc_html = f" &bull; {data['desc_info'].replace(' - ', '')}" if data["desc_info"] else ""
            actividades_html += f"<li><strong>{tit}</strong>: <strong>{horas_str} hrs</strong>{medico_html}{desc_html}</li>"
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
                        Tu turno para el día de hoy <strong>{fecha_str}</strong> es en {turnos_html}.
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

    # Cruce estricto: solo actividades y medicamentos que caen dentro del horario de sus turnos (incluyendo cruce de medianoche)
    todas_actividades = []
    todos_medicamentos = []
    vistos_actividades = set()
    vistos_medicamentos = set()

    for asig in asigs_ordenadas:
        dias_turno = [asig.fecha]
        if asig.hora_inicio > asig.hora_fin:
            dias_turno.append(asig.fecha + timedelta(days=1))

        # Actividades que coincidan con la jornada de este turno
        for d in dias_turno:
            for act in actividades_por_fecha.get(d, []):
                if esta_en_jornada_asig(act.fecha, act.hora, asig):
                    clave_act = (act.fecha, act.hora, act.titulo)
                    if clave_act not in vistos_actividades:
                        vistos_actividades.add(clave_act)
                        todas_actividades.append((act.fecha, act))

        # Medicamentos que coincidan con la jornada de este turno o correspondan a este día
        if medicamentos_por_fecha:
            for d in dias_turno:
                for m in medicamentos_por_fecha.get(d, []):
                    if corresponde_medicamento_a_cuidador(m.dia, m.hora, asig):
                        nom_m = m.tratamiento.nombre_medicamento if m.tratamiento else "Medicamento"
                        clave_med = (m.dia, m.hora, nom_m)
                        if clave_med not in vistos_medicamentos:
                            vistos_medicamentos.add(clave_med)
                            todos_medicamentos.append((m.dia, m))

    rango_str = f"{inicio_semana.strftime('%d/%m/%Y')} al {fin_semana.strftime('%d/%m/%Y')}"
    hora_actual = datetime.now().strftime("%H:%M:%S")
    subject = f"MedTurnos Pro - Planificación semanal de turnos ({rango_str}) [{hora_actual}]"

    lineas_texto = [
        f"Hola {nombre},",
        f"Esta semana tienes turnos asignados los días {dias_bloques_str}.",
        ""
    ]

    # Pauta de medicamentos agrupada para toda la semana
    if todos_medicamentos:
        lineas_texto.append("Medicamentos a administrar en tus turnos de la semana:")
        meds_fmt = formatear_pauta_medicamentos([m for d, m in todos_medicamentos])
        for item in meds_fmt:
            lineas_texto.append(f"- {item['texto_plano']}")
        lineas_texto.append("")
    else:
        lineas_texto.append("No tienes administración de medicamentos programada en tus turnos.")
        lineas_texto.append("")

    acts_sem_map: Dict[Tuple[date, str], List[str]] = {}
    if todas_actividades:
        lineas_texto.append("Tus actividades médicas programadas en turno son:")
        for fecha_act, act in todas_actividades:
            tit = act.titulo.strip()
            h_str = act.hora.strftime("%H:%M")
            if h_str not in acts_sem_map.setdefault((fecha_act, tit), []):
                acts_sem_map[(fecha_act, tit)].append(h_str)

        for (fecha_act, tit), h_list in acts_sem_map.items():
            dia_nom = DIAS_ESPANOL.get(fecha_act.weekday(), "")
            f_str = f"{dia_nom} {fecha_act.strftime('%d/%m/%Y')}"
            lineas_texto.append(f"- El día {f_str}: {tit} a las {', '.join(h_list)} hrs.")
    else:
        lineas_texto.append("No tienes actividades médicas programadas en tus horarios de turno para esta semana.")

    cuerpo_texto = "\n".join(lineas_texto)

    dias_items_html = "".join([f"<li style='margin-bottom: 6px;'>{item}</li>" for item in dias_bloques_list])

    medicamentos_html = ""
    if todos_medicamentos:
        meds_fmt = formatear_pauta_medicamentos([m for d, m in todos_medicamentos])
        medicamentos_html = "<div style='background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 14px; margin: 12px 0;'>"
        medicamentos_html += "<ul style='margin: 0; padding-left: 20px; line-height: 1.6;'>"
        for item in meds_fmt:
            medicamentos_html += f"<li style='margin-bottom: 6px;'>{item['texto_html']}</li>"
        medicamentos_html += "</ul></div>"
    else:
        medicamentos_html = "<p style='color: #475569; background: #f8fafc; padding: 10px 14px; border-radius: 8px; margin: 10px 0; font-size: 13px;'>No tienes administración de medicamentos programada en tus turnos.</p>"

    actividades_html = ""
    if todas_actividades:
        actividades_html = "<ul style='margin: 10px 0; padding-left: 20px; line-height: 1.6;'>"
        for (fecha_act, tit), h_list in acts_sem_map.items():
            dia_nom = DIAS_ESPANOL.get(fecha_act.weekday(), "")
            f_str = f"{dia_nom} {fecha_act.strftime('%d/%m/%Y')}"
            actividades_html += f"<li>El día <strong>{f_str}</strong>: <strong>{tit}</strong> a las <strong>{', '.join(h_list)} hrs</strong></li>"
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


def enviar_email_via_resend(destinatario: str, asunto: str, texto: str, html: str) -> Dict[str, Any]:
    """
    Envía un correo electrónico a través de la API REST HTTPS de Resend (puerto 443).
    Bypassa cualquier bloqueo de puertos SMTP (25, 465, 587) en Render o la nube.
    Utiliza las variables de entorno de producción:
      - RESEND_API_KEY para autenticar el cliente.
      - SENDER_EMAIL (por defecto: notificaciones@medturnospro.tech)
      - "from" con formato: f"Sistema MedTurnos <{sender_email}>"
    Captura excepciones y retorna una respuesta JSON estructurada con status: success / status: error.
    """
    api_key_actual = os.getenv("RESEND_API_KEY", RESEND_API_KEY).strip()
    if not api_key_actual or api_key_actual.startswith("re_tu_api_key"):
        error_msg = (
            "RESEND_API_KEY no está configurada o contiene el valor de ejemplo. "
            "Por favor genera tu API Key en https://resend.com y agrégala a las variables de entorno de producción (.env)."
        )
        logger.error(error_msg)
        return {
            "status": "error",
            "error": error_msg,
            "detail": error_msg
        }

    resend.api_key = api_key_actual

    sender_email = os.getenv("SENDER_EMAIL", SENDER_EMAIL).strip() or DEFAULT_SENDER_EMAIL
    from_address = os.getenv("RESEND_FROM", f"Sistema MedTurnos <{sender_email}>").strip()

    params: resend.Emails.SendParams = {
        "from": from_address,
        "to": [destinatario.strip()],
        "subject": asunto,
        "text": texto,
        "html": html,
    }

    try:
        response = resend.Emails.send(params)
        resp_id = getattr(response, "id", None) or (response.get("id") if isinstance(response, dict) else "")
        logger.info(f"Correo entregado exitosamente vía Resend a {destinatario}. ID: {resp_id}")
        return {
            "status": "success",
            "id": resp_id,
            "data": response
        }
    except Exception as exc:
        logger.error(f"Error al enviar correo vía Resend a {destinatario}: {exc}")
        return {
            "status": "error",
            "error": str(exc),
            "detail": str(exc)
        }


def enviar_correos_del_dia(fecha_objetivo: date, db: Session) -> Dict[str, Any]:
    """
    Envía notificación diaria vía Resend API (HTTP) a los cuidadores en turno hoy,
    incluyendo pauta de medicamentos y actividades de la jornada.
    """
    asignaciones: List[AsignacionTurno] = (
        db.query(AsignacionTurno)
        .join(Cuidador)
        .outerjoin(BloqueTurno)
        .filter(AsignacionTurno.fecha == fecha_objetivo, Cuidador.activo == True)
        .all()
    )

    dia_siguiente = fecha_objetivo + timedelta(days=1)

    actividades_dia: List[ActividadMedica] = (
        db.query(ActividadMedica)
        .filter(ActividadMedica.fecha.in_([fecha_objetivo, dia_siguiente]))
        .order_by(ActividadMedica.fecha.asc(), ActividadMedica.hora.asc())
        .all()
    )

    medicamentos_dia: List[TomaMedicamento] = obtener_medicamentos_programados(
        db=db,
        fecha_inicio=fecha_objetivo,
        fecha_fin=dia_siguiente
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
        lista_ordenada = sorted(lista, key=lambda a: a.hora_inicio)
        cuid = lista_ordenada[0].cuidador
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

        # 2. Cruce por jornada y día del turno del cuidador:
        # Se envían actividades dentro de la jornada y todos los medicamentos correspondientes a sus turnos de hoy
        acts_turno = [
            act for act in actividades_dia
            if any(esta_en_jornada_asig(act.fecha, act.hora, a) for a in lista_ordenada)
        ]
        meds_turno = [
            m for m in medicamentos_dia
            if any(corresponde_medicamento_a_cuidador(m.dia, m.hora, a) for a in lista_ordenada)
        ]

        # 3. Construir y enviar vía Resend HTTP API
        try:
            subject, text, html = construir_contenido_diario(cuid, lista_ordenada, acts_turno, meds_turno)
            resend_resp = enviar_email_via_resend(cuid.mail, subject, text, html)
            if isinstance(resend_resp, dict) and resend_resp.get("status") == "error":
                raise RuntimeError(resend_resp.get("error") or "Error enviando correo vía Resend API")

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
    dia_extra = fin_semana + timedelta(days=1)

    asignaciones: List[AsignacionTurno] = (
        db.query(AsignacionTurno)
        .join(Cuidador)
        .outerjoin(BloqueTurno)
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
            ActividadMedica.fecha <= dia_extra
        )
        .order_by(ActividadMedica.fecha.asc(), ActividadMedica.hora.asc())
        .all()
    )

    actividades_por_fecha: Dict[date, List[ActividadMedica]] = {}
    for act in actividades:
        actividades_por_fecha.setdefault(act.fecha, []).append(act)

    # Buscar medicamentos de la semana (incluye arrastre continuo y tomas cruzadas)
    medicamentos: List[TomaMedicamento] = obtener_medicamentos_programados(
        db=db,
        fecha_inicio=inicio_semana,
        fecha_fin=dia_extra
    )

    medicamentos_por_fecha: Dict[date, List[TomaMedicamento]] = {}
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
            if isinstance(resend_resp, dict) and resend_resp.get("status") == "error":
                raise RuntimeError(resend_resp.get("error") or "Error enviando correo vía Resend API")

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
