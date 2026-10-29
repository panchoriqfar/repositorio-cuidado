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
    to_date_obj,
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
    medicamentos: Optional[Union[List[Any], Dict[date, List[Any]]]] = None
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
    tomas_diarias = []
    if medicamentos:
        if isinstance(medicamentos, dict):
            for d, ml in medicamentos.items():
                tomas_diarias.extend(ml)
        elif isinstance(medicamentos, (list, tuple)):
            tomas_diarias = list(medicamentos)

    meds_fmt = formatear_pauta_medicamentos(tomas_diarias) if tomas_diarias else []

    if meds_fmt:
        lineas_texto.append("Medicamentos a administrar:")
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
    if meds_fmt:
        medicamentos_html = "<div style='background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 16px; margin: 16px 0;'>"
        medicamentos_html += "<ul style='margin: 0; padding-left: 20px; line-height: 1.7;'>"
        for item in meds_fmt:
            medicamentos_html += f"<li style='margin-bottom: 8px;'>{item['texto_html']}</li>"
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
    medicamentos_por_fecha: Optional[Union[Dict[date, List[Any]], List[Any]]] = None
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

    # Pauta completa de medicamentos de la semana (idéntica lógica al botón de medicamentos)
    tomas_semana = []
    if medicamentos_por_fecha:
        if isinstance(medicamentos_por_fecha, dict):
            for d in sorted(medicamentos_por_fecha.keys()):
                d_obj = to_date_obj(d) or (d if isinstance(d, date) else None)
                if d_obj is None or (inicio_semana <= d_obj <= fin_semana):
                    tomas_semana.extend(medicamentos_por_fecha[d])
        elif isinstance(medicamentos_por_fecha, (list, tuple)):
            for m in medicamentos_por_fecha:
                d_val = getattr(m, "dia", None)
                d_obj = to_date_obj(d_val) or (d_val if isinstance(d_val, date) else None)
                if d_obj is None or (inicio_semana <= d_obj <= fin_semana):
                    tomas_semana.append(m)

    meds_fmt_sem = formatear_pauta_medicamentos(tomas_semana) if tomas_semana else []

    rango_str = f"{inicio_semana.strftime('%d/%m/%Y')} al {fin_semana.strftime('%d/%m/%Y')}"
    hora_actual = datetime.now().strftime("%H:%M:%S")
    subject = f"MedTurnos Pro - Planificación semanal de turnos ({rango_str}) [{hora_actual}]"

    lineas_texto = [
        f"Hola {nombre},",
        f"Esta semana tienes turnos asignados los días {dias_bloques_str}.",
        ""
    ]

    # Pauta de medicamentos agrupada para toda la semana
    if meds_fmt_sem:
        lineas_texto.append("Medicamentos a administrar:")
        for item in meds_fmt_sem:
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
    if meds_fmt_sem:
        medicamentos_html = "<div style='background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 16px; margin: 16px 0;'>"
        medicamentos_html += "<ul style='margin: 0; padding-left: 20px; line-height: 1.7;'>"
        for item in meds_fmt_sem:
            medicamentos_html += f"<li style='margin-bottom: 8px;'>{item['texto_html']}</li>"
        medicamentos_html += "</ul></div>"
    else:
        medicamentos_html = "<p style='color: #475569; background: #f8fafc; padding: 12px; border-radius: 8px; margin: 12px 0;'>No tienes administración de medicamentos programada en tus turnos.</p>"

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

    inicio_sem = fecha_objetivo - timedelta(days=fecha_objetivo.weekday())
    fin_sem = inicio_sem + timedelta(days=6)
    medicamentos_dia: List[TomaMedicamento] = obtener_medicamentos_programados(
        db=db,
        fecha_inicio=inicio_sem,
        fecha_fin=fin_sem
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
        # Pauta completa de medicamentos para el cuidador a cargo
        meds_turno = medicamentos_dia

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
        fecha_fin=fin_semana
    )

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
                medicamentos_por_fecha=medicamentos
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



# ---------------------------------------------------------------------------
# Notificaciones exclusivas de Pauta de Medicamentos (Solo Medicamentos)
# ---------------------------------------------------------------------------

def construir_contenido_solo_medicamentos(
    tomas: List[TomaMedicamento],
    titulo_periodo: str,
    nombre_destinatario: str = "Equipo"
) -> Tuple[str, str, str]:
    """
    Construye el asunto, texto plano y HTML exclusivo para la pauta de medicamentos
    (sin incluir turnos ni actividades), con el formato agrupado por medicamento y horario.
    """
    asunto = f"MedTurnos Pro - Pauta de Medicamentos ({titulo_periodo})"

    lineas_texto = [
        f"Hola {nombre_destinatario},",
        f"A continuación te compartimos la pauta farmacológica y horarios de medicamentos para el periodo {titulo_periodo}:",
        ""
    ]

    if tomas:
        lineas_texto.append("Medicamentos a administrar:")
        meds_fmt = formatear_pauta_medicamentos(tomas)
        for item in meds_fmt:
            lineas_texto.append(f"- {item['texto_plano']}")
        lineas_texto.append("")
    else:
        lineas_texto.append("No hay administración de medicamentos programada para este periodo.")
        lineas_texto.append("")

    lineas_texto.append("Sistema Web MedTurnos Pro • Gestión de Medicamentos")
    cuerpo_texto = "\n".join(lineas_texto)

    # HTML
    medicamentos_html = ""
    if tomas:
        meds_fmt = formatear_pauta_medicamentos(tomas)
        medicamentos_html = "<div style='background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 16px; margin: 16px 0;'>"
        medicamentos_html += "<ul style='margin: 0; padding-left: 20px; line-height: 1.7;'>"
        for item in meds_fmt:
            medicamentos_html += f"<li style='margin-bottom: 8px;'>{item['texto_html']}</li>"
        medicamentos_html += "</ul></div>"
    else:
        medicamentos_html = "<p style='color: #475569; background: #f8fafc; padding: 12px; border-radius: 8px; margin: 12px 0;'>No hay administración de medicamentos programada para este periodo.</p>"

    cuerpo_html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; background-color: #f8fafc; padding: 20px; margin: 0;">
        <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
            <div style="background: linear-gradient(135deg, #e11d48, #be123c); color: white; padding: 22px 24px;">
                <h2 style="margin: 0; font-size: 20px; letter-spacing: -0.025em;">MedTurnos Pro</h2>
                <p style="margin: 4px 0 0; font-size: 13px; opacity: 0.9;">Pauta de Medicamentos &bull; {titulo_periodo}</p>
            </div>
            <div style="padding: 24px;">
                <p style="font-size: 16px; margin-top: 0;">Hola <strong>{nombre_destinatario}</strong>,</p>
                <div style="background: #fff1f2; border-left: 4px solid #e11d48; padding: 12px 16px; border-radius: 6px; margin: 16px 0;">
                    <p style="margin: 0; font-size: 14px; color: #9f1239;">
                        A continuación te compartimos la pauta farmacológica y horarios de medicamentos para: <strong>{titulo_periodo}</strong>.
                    </p>
                </div>
                <h3 style="font-size: 15px; color: #334155; margin: 20px 0 8px;">💊 Medicamentos y Horarios de Administración:</h3>
                {medicamentos_html}
            </div>
            <div style="background: #f1f5f9; padding: 12px 24px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0;">
                Sistema Web MedTurnos Pro &bull; Gestión y Pauta de Medicamentos
            </div>
        </div>
    </body>
    </html>
    """

    return asunto, cuerpo_texto, cuerpo_html


def enviar_correos_solo_medicamentos_periodo(
    db: Session,
    fecha_inicio: date,
    fecha_fin: date,
    destinatario_tipo: str = "todos",
    id_cuidador: Optional[int] = None,
    email_manual: Optional[str] = None
) -> Dict[str, Any]:
    """
    Envía la pauta de medicamentos por correo electrónico vía Resend
    exclusivamente con la lista de medicamentos y sus horarios (sin turnos ni actividades).
    """
    tomas = obtener_medicamentos_programados(db, fecha_inicio, fecha_fin)

    if fecha_inicio == fecha_fin:
        dia_nom = DIAS_ESPANOL.get(fecha_inicio.weekday(), "")
        titulo_periodo = f"{dia_nom} {fecha_inicio.strftime('%d/%m/%Y')}"
    else:
        titulo_periodo = f"Semana del {fecha_inicio.strftime('%d/%m/%Y')} al {fecha_fin.strftime('%d/%m/%Y')}"

    destinatarios_lista = []

    if destinatario_tipo == "manual":
        if not email_manual or not es_email_valido(email_manual):
            return {
                "tipo": "medicamentos",
                "periodo": titulo_periodo,
                "total_cuidadores": 0,
                "enviados": 0,
                "omitidos": 1,
                "errores": 1,
                "detalles": [{
                    "id_cuidador": 0,
                    "cuidador": "Destinatario Manual",
                    "mail": email_manual or "",
                    "estado": "ERROR",
                    "detalle": "Correo electrónico manual no válido."
                }]
            }
        destinatarios_lista.append(("Estimado(a)", email_manual.strip(), 0))

    elif destinatario_tipo == "cuidador" and id_cuidador:
        cuid = db.query(Cuidador).filter_by(id_cuidador=id_cuidador).first()
        if not cuid or not es_email_valido(cuid.mail):
            return {
                "tipo": "medicamentos",
                "periodo": titulo_periodo,
                "total_cuidadores": 1,
                "enviados": 0,
                "omitidos": 1,
                "errores": 0,
                "detalles": [{
                    "id_cuidador": id_cuidador,
                    "cuidador": cuid.nombre if cuid else "Desconocido",
                    "mail": cuid.mail if cuid else None,
                    "estado": "OMITIDO",
                    "detalle": "El cuidador seleccionado no posee un correo electrónico válido."
                }]
            }
        nombre = format_nombre_cuidador(cuid)
        destinatarios_lista.append((nombre, cuid.mail.strip(), cuid.id_cuidador))

    else:
        # "todos"
        cuidadores = db.query(Cuidador).filter_by(activo=True).all()
        for c in cuidadores:
            if es_email_valido(c.mail):
                destinatarios_lista.append((format_nombre_cuidador(c), c.mail.strip(), c.id_cuidador))

    resultado: Dict[str, Any] = {
        "tipo": "medicamentos",
        "periodo": titulo_periodo,
        "total_cuidadores": len(destinatarios_lista),
        "enviados": 0,
        "omitidos": 0,
        "errores": 0,
        "detalles": []
    }

    if not destinatarios_lista:
        resultado["detalles"].append({
            "id_cuidador": 0,
            "cuidador": "Sin destinatarios",
            "mail": None,
            "estado": "OMITIDO",
            "detalle": "No se encontraron destinatarios con correo electrónico válido."
        })
        return resultado

    for nombre, mail, cuid_id in destinatarios_lista:
        asunto, texto, html = construir_contenido_solo_medicamentos(tomas, titulo_periodo, nombre)
        try:
            resend_resp = enviar_email_via_resend(mail, asunto, texto, html)
            if isinstance(resend_resp, dict) and resend_resp.get("status") == "error":
                resultado["errores"] += 1
                resultado["detalles"].append({
                    "id_cuidador": cuid_id,
                    "cuidador": nombre,
                    "mail": mail,
                    "estado": "ERROR",
                    "detalle": resend_resp.get("error", "Error desconocido")
                })
                continue

            resp_id = getattr(resend_resp, "id", None) or (resend_resp.get("id") if isinstance(resend_resp, dict) else "")
            resultado["enviados"] += 1
            resultado["detalles"].append({
                "id_cuidador": cuid_id,
                "cuidador": nombre,
                "mail": mail,
                "estado": "ENVIADO",
                "detalle": f"Pauta de medicamentos enviada vía Resend API (ID: {resp_id})"
            })
        except Exception as exc:
            logger.error(f"Error enviando correo de medicamentos a {mail}: {exc}")
            resultado["errores"] += 1
            resultado["detalles"].append({
                "id_cuidador": cuid_id,
                "cuidador": nombre,
                "mail": mail,
                "estado": "ERROR",
                "detalle": str(exc)
            })

    return resultado



# ---------------------------------------------------------------------------
# Notificaciones exclusivas de Actividades Médicas (Solo Actividades)
# ---------------------------------------------------------------------------

def construir_contenido_solo_actividades(
    actividades: List[ActividadMedica],
    titulo_periodo: str,
    nombre_destinatario: str = "Equipo"
) -> Tuple[str, str, str]:
    """
    Construye el asunto, texto plano y HTML exclusivo para actividades y visitas médicas
    (sin incluir turnos ni medicamentos).
    """
    asunto = f"MedTurnos Pro - Actividades y Visitas Médicas ({titulo_periodo})"

    lineas_texto = [
        f"Hola {nombre_destinatario},",
        f"A continuación te compartimos las actividades y visitas médicas programadas para el periodo {titulo_periodo}:",
        ""
    ]

    if actividades:
        lineas_texto.append("Actividades médicas programadas:")
        for idx, act in enumerate(actividades, 1):
            dia_nom = DIAS_ESPANOL.get(act.fecha.weekday(), "")
            f_str = f"{dia_nom} {act.fecha.strftime('%d/%m/%Y')}"
            h_str = act.hora.strftime("%H:%M") if isinstance(act.hora, time) else str(act.hora)[:5]
            med_info = ""
            if act.medico_asignado:
                nombre_med = f"{act.medico_asignado.nombre} {act.medico_asignado.apellido or ''}".strip()
                med_info = f" (A cargo: {nombre_med})"
            desc_info = f" - {act.descripcion.strip()}" if act.descripcion else ""
            lineas_texto.append(f"{idx}. {act.titulo.strip()}: {f_str} a las {h_str} hrs{med_info}{desc_info}")
        lineas_texto.append("")
    else:
        lineas_texto.append("No hay actividades médicas programadas para este periodo.")
        lineas_texto.append("")

    lineas_texto.append("Sistema Web MedTurnos Pro • Gestión de Actividades Médicas")
    cuerpo_texto = "\n".join(lineas_texto)

    # HTML
    actividades_html = ""
    if actividades:
        actividades_html = "<div style='background: #f0fdfa; border: 1px solid #ccfbf1; border-radius: 8px; padding: 14px 16px; margin: 16px 0;'>"
        actividades_html += "<ul style='margin: 0; padding-left: 20px; line-height: 1.7;'>"
        for act in actividades:
            dia_nom = DIAS_ESPANOL.get(act.fecha.weekday(), "")
            f_str = f"{dia_nom} {act.fecha.strftime('%d/%m/%Y')}"
            h_str = act.hora.strftime("%H:%M") if isinstance(act.hora, time) else str(act.hora)[:5]
            medico_html = ""
            if act.medico_asignado:
                nombre_med = f"{act.medico_asignado.nombre} {act.medico_asignado.apellido or ''}".strip()
                medico_html = f" &bull; <span style='color: #0f766e;'>Personal a cargo: <strong>{nombre_med}</strong></span>"
            desc_html = f"<br><span style='color: #475569; font-size: 13px;'>{act.descripcion.strip()}</span>" if act.descripcion else ""
            actividades_html += f"<li style='margin-bottom: 10px;'><strong>{act.titulo.strip()}</strong> &bull; <span style='color: #0d9488; font-weight: 600;'>{f_str} a las {h_str} hrs</span>{medico_html}{desc_html}</li>"
        actividades_html += "</ul></div>"
    else:
        actividades_html = "<p style='color: #475569; background: #f0fdfa; padding: 12px; border-radius: 8px; margin: 12px 0;'>No hay actividades médicas programadas para este periodo.</p>"

    cuerpo_html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; background-color: #f8fafc; padding: 20px; margin: 0;">
        <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
            <div style="background: linear-gradient(135deg, #0d9488, #0f766e); color: white; padding: 22px 24px;">
                <h2 style="margin: 0; font-size: 20px; letter-spacing: -0.025em;">MedTurnos Pro</h2>
                <p style="margin: 4px 0 0; font-size: 13px; opacity: 0.9;">Actividades y Visitas Médicas &bull; {titulo_periodo}</p>
            </div>
            <div style="padding: 24px;">
                <p style="font-size: 16px; margin-top: 0;">Hola <strong>{nombre_destinatario}</strong>,</p>
                <div style="background: #f0fdfa; border-left: 4px solid #0d9488; padding: 12px 16px; border-radius: 6px; margin: 16px 0;">
                    <p style="margin: 0; font-size: 14px; color: #115e59;">
                        A continuación te compartimos las actividades y visitas médicas programadas para: <strong>{titulo_periodo}</strong>.
                    </p>
                </div>
                <h3 style="font-size: 15px; color: #334155; margin: 20px 0 8px;">🩺 Actividades y Procedimientos:</h3>
                {actividades_html}
            </div>
            <div style="background: #f1f5f9; padding: 12px 24px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0;">
                Sistema Web MedTurnos Pro &bull; Gestión de Actividades Médicas
            </div>
        </div>
    </body>
    </html>
    """

    return asunto, cuerpo_texto, cuerpo_html


def enviar_correos_solo_actividades_periodo(
    db: Session,
    fecha_inicio: date,
    fecha_fin: date,
    destinatario_tipo: str = "todos",
    id_cuidador: Optional[int] = None,
    email_manual: Optional[str] = None
) -> Dict[str, Any]:
    """
    Envía las actividades y visitas médicas por correo electrónico vía Resend
    exclusivamente con la lista de actividades (sin turnos ni medicamentos).
    """
    actividades = (
        db.query(ActividadMedica)
        .filter(
            ActividadMedica.fecha >= fecha_inicio,
            ActividadMedica.fecha <= fecha_fin
        )
        .order_by(ActividadMedica.fecha.asc(), ActividadMedica.hora.asc())
        .all()
    )

    if fecha_inicio == fecha_fin:
        dia_nom = DIAS_ESPANOL.get(fecha_inicio.weekday(), "")
        titulo_periodo = f"{dia_nom} {fecha_inicio.strftime('%d/%m/%Y')}"
    else:
        titulo_periodo = f"Semana del {fecha_inicio.strftime('%d/%m/%Y')} al {fecha_fin.strftime('%d/%m/%Y')}"

    destinatarios_lista = []

    if destinatario_tipo == "manual":
        if not email_manual or not es_email_valido(email_manual):
            return {
                "tipo": "actividades",
                "periodo": titulo_periodo,
                "total_cuidadores": 0,
                "enviados": 0,
                "omitidos": 1,
                "errores": 1,
                "detalles": [{
                    "id_cuidador": 0,
                    "cuidador": "Destinatario Manual",
                    "mail": email_manual or "",
                    "estado": "ERROR",
                    "detalle": "Correo electrónico manual no válido."
                }]
            }
        destinatarios_lista.append(("Estimado(a)", email_manual.strip(), 0))

    elif destinatario_tipo == "cuidador" and id_cuidador:
        cuid = db.query(Cuidador).filter_by(id_cuidador=id_cuidador).first()
        if not cuid or not es_email_valido(cuid.mail):
            return {
                "tipo": "actividades",
                "periodo": titulo_periodo,
                "total_cuidadores": 1,
                "enviados": 0,
                "omitidos": 1,
                "errores": 0,
                "detalles": [{
                    "id_cuidador": id_cuidador,
                    "cuidador": cuid.nombre if cuid else "Desconocido",
                    "mail": cuid.mail if cuid else None,
                    "estado": "OMITIDO",
                    "detalle": "El cuidador seleccionado no posee un correo electrónico válido."
                }]
            }
        nombre = format_nombre_cuidador(cuid)
        destinatarios_lista.append((nombre, cuid.mail.strip(), cuid.id_cuidador))

    else:
        # "todos"
        cuidadores = db.query(Cuidador).filter_by(activo=True).all()
        for c in cuidadores:
            if es_email_valido(c.mail):
                destinatarios_lista.append((format_nombre_cuidador(c), c.mail.strip(), c.id_cuidador))

    resultado: Dict[str, Any] = {
        "tipo": "actividades",
        "periodo": titulo_periodo,
        "total_cuidadores": len(destinatarios_lista),
        "enviados": 0,
        "omitidos": 0,
        "errores": 0,
        "detalles": []
    }

    if not destinatarios_lista:
        resultado["detalles"].append({
            "id_cuidador": 0,
            "cuidador": "Sin destinatarios",
            "mail": None,
            "estado": "OMITIDO",
            "detalle": "No se encontraron destinatarios con correo electrónico válido."
        })
        return resultado

    for nombre, mail, cuid_id in destinatarios_lista:
        asunto, texto, html = construir_contenido_solo_actividades(actividades, titulo_periodo, nombre)
        try:
            resend_resp = enviar_email_via_resend(mail, asunto, texto, html)
            if isinstance(resend_resp, dict) and resend_resp.get("status") == "error":
                resultado["errores"] += 1
                resultado["detalles"].append({
                    "id_cuidador": cuid_id,
                    "cuidador": nombre,
                    "mail": mail,
                    "estado": "ERROR",
                    "detalle": resend_resp.get("error", "Error desconocido")
                })
                continue

            resp_id = getattr(resend_resp, "id", None) or (resend_resp.get("id") if isinstance(resend_resp, dict) else "")
            resultado["enviados"] += 1
            resultado["detalles"].append({
                "id_cuidador": cuid_id,
                "cuidador": nombre,
                "mail": mail,
                "estado": "ENVIADO",
                "detalle": f"Actividades médicas enviadas vía Resend API (ID: {resp_id})"
            })
        except Exception as exc:
            logger.error(f"Error enviando correo de actividades a {mail}: {exc}")
            resultado["errores"] += 1
            resultado["detalles"].append({
                "id_cuidador": cuid_id,
                "cuidador": nombre,
                "mail": mail,
                "estado": "ERROR",
                "detalle": str(exc)
            })

    return resultado



# ---------------------------------------------------------------------------
# Notificaciones unificadas de Horarios y Turnos (Día o Semana, Todos o Individual)
# ---------------------------------------------------------------------------

def enviar_correos_horario_periodo(
    db: Session,
    fecha_base: Optional[date] = None,
    tipo: str = "semana",
    destinatario_tipo: str = "todos",
    id_cuidador: Optional[int] = None,
    email_manual: Optional[str] = None,
    fecha_inicio: Optional[date] = None,
    fecha_fin: Optional[date] = None
) -> Dict[str, Any]:
    """
    Envía la planificación de horarios y turnos por correo electrónico vía Resend,
    con las actividades médicas y la pauta completa de medicamentos asignada a cada cuidador según corresponda.
    Aprovecha la misma lógica robusta del botón de medicamentos para asegurar que todas las tomas
    y pautas farmacológicas sean incluidas sin omisión.
    """
    if tipo == "dia":
        fecha_objetivo = fecha_inicio or fecha_base or date.today()
        dia_nom = DIAS_ESPANOL.get(fecha_objetivo.weekday(), "")
        titulo_periodo = f"{dia_nom} {fecha_objetivo.strftime('%d/%m/%Y')}"
        dia_siguiente = fecha_objetivo + timedelta(days=1)

        q = (
            db.query(AsignacionTurno)
            .join(Cuidador)
            .outerjoin(BloqueTurno)
            .filter(AsignacionTurno.fecha == fecha_objetivo, Cuidador.activo == True)
        )
        if destinatario_tipo == "cuidador" and id_cuidador:
            q = q.filter(AsignacionTurno.id_cuidador == id_cuidador)

        asignaciones: List[AsignacionTurno] = q.order_by(AsignacionTurno.hora_inicio.asc()).all()

        actividades_dia: List[ActividadMedica] = (
            db.query(ActividadMedica)
            .filter(ActividadMedica.fecha.in_([fecha_objetivo, dia_siguiente]))
            .order_by(ActividadMedica.fecha.asc(), ActividadMedica.hora.asc())
            .all()
        )

        # Misma lógica que el botón de medicamentos: obtener todas las tomas programadas y arrastradas
        medicamentos_dia: List[TomaMedicamento] = obtener_medicamentos_programados(
            db=db,
            fecha_inicio=fecha_objetivo,
            fecha_fin=fecha_objetivo
        )

        asigs_por_cuidador: Dict[int, List[AsignacionTurno]] = {}
        for asig in asignaciones:
            asigs_por_cuidador.setdefault(asig.id_cuidador, []).append(asig)

        # Caso cuidador específico sin turnos hoy
        if destinatario_tipo == "cuidador" and id_cuidador and id_cuidador not in asigs_por_cuidador:
            cuid = db.query(Cuidador).filter_by(id_cuidador=id_cuidador).first()
            nombre_cuid = format_nombre_cuidador(cuid) if cuid else "Cuidador"
            return {
                "tipo": "diario",
                "periodo": titulo_periodo,
                "total_cuidadores": 1,
                "enviados": 0,
                "omitidos": 1,
                "errores": 0,
                "detalles": [{
                    "id_cuidador": id_cuidador,
                    "cuidador": nombre_cuid,
                    "mail": cuid.mail if cuid else None,
                    "estado": "OMITIDO",
                    "detalle": f"{nombre_cuid} no tiene turnos asignados para el día {titulo_periodo}."
                }]
            }

        resultado: Dict[str, Any] = {
            "tipo": "diario",
            "periodo": titulo_periodo,
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
            destino_mail = email_manual.strip() if (destinatario_tipo == "manual" and email_manual) else (cuid.mail or "").strip()

            if not es_email_valido(destino_mail):
                resultado["omitidos"] += 1
                resultado["detalles"].append({
                    "id_cuidador": cuid.id_cuidador,
                    "cuidador": nombre,
                    "mail": destino_mail or None,
                    "estado": "OMITIDO",
                    "detalle": "El cuidador no tiene correo configurado o el formato es inválido."
                })
                continue

            acts_turno = [
                act for act in actividades_dia
                if any(esta_en_jornada_asig(act.fecha, act.hora, a) for a in lista_ordenada)
            ]
            meds_turno = medicamentos_dia

            try:
                subject, text, html = construir_contenido_diario(cuid, lista_ordenada, acts_turno, meds_turno)
                resend_resp = enviar_email_via_resend(destino_mail, subject, text, html)
                if isinstance(resend_resp, dict) and resend_resp.get("status") == "error":
                    raise RuntimeError(resend_resp.get("error") or "Error enviando correo vía Resend API")

                resp_id = getattr(resend_resp, "id", None) or (resend_resp.get("id") if isinstance(resend_resp, dict) else "")
                resultado["enviados"] += 1
                resultado["detalles"].append({
                    "id_cuidador": cuid.id_cuidador,
                    "cuidador": nombre,
                    "mail": destino_mail,
                    "estado": "ENVIADO",
                    "detalle": f"Correo diario entregado exitosamente vía Resend API (ID: {resp_id})" if resp_id else "Correo diario entregado exitosamente vía Resend API"
                })
            except Exception as exc:
                logger.error(f"Error enviando correo diario a {destino_mail}: {exc}")
                resultado["errores"] += 1
                resultado["detalles"].append({
                    "id_cuidador": cuid.id_cuidador,
                    "cuidador": nombre,
                    "mail": destino_mail,
                    "estado": "ERROR",
                    "detalle": str(exc)
                })

        return resultado

    else:
        # tipo == "semana"
        if fecha_inicio and fecha_fin:
            inicio_semana = fecha_inicio
            fin_semana = fecha_fin
        else:
            base = fecha_base or date.today()
            inicio_semana = base - timedelta(days=base.weekday())
            fin_semana = inicio_semana + timedelta(days=6)

        dia_extra = fin_semana + timedelta(days=1)
        titulo_periodo = f"Semana del {inicio_semana.strftime('%d/%m/%Y')} al {fin_semana.strftime('%d/%m/%Y')}"

        q = (
            db.query(AsignacionTurno)
            .join(Cuidador)
            .outerjoin(BloqueTurno)
            .filter(
                AsignacionTurno.fecha >= inicio_semana,
                AsignacionTurno.fecha <= fin_semana,
                Cuidador.activo == True
            )
        )
        if destinatario_tipo == "cuidador" and id_cuidador:
            q = q.filter(AsignacionTurno.id_cuidador == id_cuidador)

        asignaciones = q.order_by(AsignacionTurno.fecha.asc(), AsignacionTurno.hora_inicio.asc()).all()

        actividades = (
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

        # Misma lógica que el botón de medicamentos: obtener todas las tomas programadas y arrastradas de la semana
        medicamentos: List[TomaMedicamento] = obtener_medicamentos_programados(
            db=db,
            fecha_inicio=inicio_semana,
            fecha_fin=fin_semana
        )

        asigs_por_cuidador: Dict[int, List[AsignacionTurno]] = {}
        for asig in asignaciones:
            asigs_por_cuidador.setdefault(asig.id_cuidador, []).append(asig)

        # Caso cuidador específico sin turnos en la semana
        if destinatario_tipo == "cuidador" and id_cuidador and id_cuidador not in asigs_por_cuidador:
            cuid = db.query(Cuidador).filter_by(id_cuidador=id_cuidador).first()
            nombre_cuid = format_nombre_cuidador(cuid) if cuid else "Cuidador"
            return {
                "tipo": "semanal",
                "periodo": titulo_periodo,
                "total_cuidadores": 1,
                "enviados": 0,
                "omitidos": 1,
                "errores": 0,
                "detalles": [{
                    "id_cuidador": id_cuidador,
                    "cuidador": nombre_cuid,
                    "mail": cuid.mail if cuid else None,
                    "estado": "OMITIDO",
                    "detalle": f"{nombre_cuid} no tiene turnos asignados para la semana ({titulo_periodo})."
                }]
            }

        resultado = {
            "tipo": "semanal",
            "periodo": titulo_periodo,
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
            destino_mail = email_manual.strip() if (destinatario_tipo == "manual" and email_manual) else (cuid.mail or "").strip()

            if not es_email_valido(destino_mail):
                resultado["omitidos"] += 1
                resultado["detalles"].append({
                    "id_cuidador": cuid.id_cuidador,
                    "cuidador": nombre,
                    "mail": destino_mail or None,
                    "estado": "OMITIDO",
                    "detalle": "El cuidador no tiene correo configurado o el formato es inválido."
                })
                continue

            try:
                subject, text, html = construir_contenido_semanal(
                    cuidador=cuid,
                    asignaciones=lista,
                    actividades_por_fecha=actividades_por_fecha,
                    inicio_semana=inicio_semana,
                    fin_semana=fin_semana,
                    medicamentos_por_fecha=medicamentos
                )
                resend_resp = enviar_email_via_resend(destino_mail, subject, text, html)
                if isinstance(resend_resp, dict) and resend_resp.get("status") == "error":
                    raise RuntimeError(resend_resp.get("error") or "Error enviando correo vía Resend API")

                resp_id = getattr(resend_resp, "id", None) or (resend_resp.get("id") if isinstance(resend_resp, dict) else "")
                resultado["enviados"] += 1
                resultado["detalles"].append({
                    "id_cuidador": cuid.id_cuidador,
                    "cuidador": nombre,
                    "mail": destino_mail,
                    "estado": "ENVIADO",
                    "detalle": f"Planificación semanal enviada vía Resend API ({len(lista)} turnos)"
                })
            except Exception as exc:
                logger.error(f"Error enviando correo semanal a {destino_mail}: {exc}")
                resultado["errores"] += 1
                resultado["detalles"].append({
                    "id_cuidador": cuid.id_cuidador,
                    "cuidador": nombre,
                    "mail": destino_mail,
                    "estado": "ERROR",
                    "detalle": str(exc)
                })

        return resultado
