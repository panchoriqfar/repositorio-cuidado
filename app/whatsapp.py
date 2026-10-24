"""Twilio WhatsApp notification service.

Gestión de notificaciones por WhatsApp para cuidadores:
- Notificación diaria (Actualización Diaria).
- Notificación semanal consolidada (todos los cuidadores de la semana con sus turnos y actividades).
"""

import os
import logging
from datetime import date, time, datetime, timedelta
from typing import List, Dict, Any, Optional, Union

from sqlalchemy.orm import Session, joinedload
from dotenv import load_dotenv

from app.models import AsignacionTurno, ActividadMedica, Cuidador, BloqueTurno, TratamientoMedicamento, MedicamentoHorario
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

        if estilo == "whatsapp":
            extra_rf = " *[REUNION FAMILIAR]*" if es_rf else ""
            frases.append(f"*{bloque}* (*{h_ini} - {h_fin} hrs*){extra_rf}")
        elif estilo == "html":
            extra_rf = " <span style='color:#b45309;font-weight:bold;'>[REUNION FAMILIAR]</span>" if es_rf else ""
            frases.append(f"<strong>{bloque}</strong> (<strong>{h_ini} - {h_fin} hrs</strong>){extra_rf}")
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


def build_whatsapp_message(
    cuidador: Cuidador,
    asignacion: Union[AsignacionTurno, List[AsignacionTurno]],
    actividades: List[ActividadMedica],
    medicamentos: Optional[List[MedicamentoHorario]] = None
) -> str:
    """
    Crea el mensaje de WhatsApp para notificación del día, consolidando todos los turnos
    del cuidador en la jornada e incluyendo lista detallada de medicamentos y actividades
    correspondientes a cualquiera de sus turnos del día.
    """
    if isinstance(asignacion, (list, tuple, set)):
        lista = list(asignacion)
    else:
        lista = [asignacion]

    lista_ordenada = sorted(lista, key=lambda a: a.hora_inicio)
    fecha_obj = lista_ordenada[0].fecha if lista_ordenada else date.today()
    fecha_str = fecha_obj.strftime("%d/%m/%Y")
    nombre = format_nombre_cuidador(cuidador)

    turnos_wa = format_turnos_diarios_texto(lista_ordenada, estilo="whatsapp")

    mensaje = (
        f"🏥 *SISTEMA DE GESTIÓN DE CUIDADOS*\n\n"
        f"Hola *{nombre}*,\n\n"
        f"Tu turno para el día de hoy *{fecha_str}* es en {turnos_wa}.\n"
    )

    # Detalle de Medicamentos de la Jornada
    if medicamentos:
        mensaje += "\n💊 *Pauta de Medicamentos en tu Turno:*\n"
        meds_agrupados: Dict[str, Dict[str, Any]] = {}
        for med in medicamentos:
            nom_med = med.tratamiento.nombre_medicamento if med.tratamiento else "Medicamento"
            if nom_med not in meds_agrupados:
                medico_info = ""
                if med.tratamiento and med.tratamiento.personal_medico:
                    pm = med.tratamiento.personal_medico
                    nombre_prof = f"{pm.nombre} {pm.apellido or ''}".strip()
                    medico_info = f" (Indicado por: {nombre_prof})"
                meds_agrupados[nom_med] = {
                    "horas": [],
                    "medico_info": medico_info
                }
            h_str = med.hora.strftime("%H:%M")
            if h_str not in meds_agrupados[nom_med]["horas"]:
                meds_agrupados[nom_med]["horas"].append(h_str)

        for idx, (nom_med, data) in enumerate(meds_agrupados.items(), 1):
            horas_str = ", ".join(data["horas"])
            mensaje += f"  {idx}. *{nom_med}*: {horas_str} hrs{data['medico_info']}\n"
    else:
        mensaje += "\n💊 *Medicamentos:* No tienes administración de medicamentos programada para tu turno.\n"

    # Detalle de Actividades Médicas
    if actividades:
        mensaje += "\n📋 *Actividades Médicas en tu Turno:*\n"
        acts_agrupadas: Dict[str, Dict[str, Any]] = {}
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
            h_str = act.hora.strftime("%H:%M")
            if h_str not in acts_agrupadas[tit]["horas"]:
                acts_agrupadas[tit]["horas"].append(h_str)

        for idx, (tit, data) in enumerate(acts_agrupadas.items(), 1):
            horas_str = ", ".join(data["horas"])
            mensaje += f"  {idx}. *{tit}*: {horas_str} hrs{data['medico_info']}{data['desc_info']}\n"
    else:
        mensaje += "\n📋 *Actividades:* No tienes actividades médicas programadas durante tu horario de turno.\n"

    mensaje += "\n_Por favor confirma la recepción de este mensaje. ¡Buen turno!_"
    return mensaje


# Alias descriptivo para la preparación del resumen diario de WhatsApp
preparar_resumen_diario_whatsapp = build_whatsapp_message



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
    fin_semana: date,
    medicamentos_por_fecha: Optional[Dict[date, List[MedicamentoHorario]]] = None
) -> str:
    """
    Construye el mensaje de WhatsApp semanal para un cuidador con todos sus turnos
    de la semana y cruzando estrictamente las actividades y medicamentos de sus horarios asignados.
    """
    nombre = format_nombre_cuidador(cuidador)
    rango_str = f"{inicio_semana.strftime('%d/%m/%Y')} al {fin_semana.strftime('%d/%m/%Y')}"

    mensaje = (
        f"🏥 *SISTEMA DE GESTIÓN DE CUIDADOS*\n"
        f"📅 *Cronograma Semanal de Turnos*\n"
        f"🗓️ *Semana:* {rango_str}\n\n"
        f"Hola *{nombre}*,\n"
        f"A continuación te compartimos tus turnos, medicamentos y actividades programadas para toda la semana:\n\n"
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

        # Cruce estricto: solo medicamentos dentro de este horario de turno
        meds_turno = []
        if medicamentos_por_fecha:
            meds_dia = medicamentos_por_fecha.get(asig.fecha, [])
            meds_turno = [m for m in meds_dia if esta_en_jornada(m.hora, asig.hora_inicio, asig.hora_fin)]
            if meds_turno:
                mensaje += "   💊 *Medicamentos en tu Turno:*\n"
                meds_agrupados_sem: Dict[str, List[str]] = {}
                for m in meds_turno:
                    nom = m.tratamiento.nombre_medicamento if m.tratamiento else "Medicamento"
                    h_str = m.hora.strftime("%H:%M")
                    if h_str not in meds_agrupados_sem.setdefault(nom, []):
                        meds_agrupados_sem[nom].append(h_str)
                for idx, (nom, h_list) in enumerate(meds_agrupados_sem.items(), 1):
                    mensaje += f"      {idx}. {nom}: {', '.join(h_list)} hrs\n"

        # Cruce estricto: solo actividades dentro de este horario de turno
        actividades_dia = actividades_por_fecha.get(asig.fecha, [])
        acts_turno = [act for act in actividades_dia if esta_en_jornada(act.hora, asig.hora_inicio, asig.hora_fin)]
        if acts_turno:
            mensaje += "   📋 *Actividades Médicas en tu Turno:*\n"
            acts_agrupadas_sem: Dict[str, Dict[str, Any]] = {}
            for act in acts_turno:
                tit = act.titulo.strip()
                if tit not in acts_agrupadas_sem:
                    med_info = ""
                    if act.medico_asignado:
                        nom_med = f"{act.medico_asignado.nombre} {act.medico_asignado.apellido or ''}".strip()
                        med_info = f" (A cargo: {nom_med})"
                    acts_agrupadas_sem[tit] = {"horas": [], "med_info": med_info}
                h_str = act.hora.strftime("%H:%M")
                if h_str not in acts_agrupadas_sem[tit]["horas"]:
                    acts_agrupadas_sem[tit]["horas"].append(h_str)
            for idx, (tit, data) in enumerate(acts_agrupadas_sem.items(), 1):
                mensaje += f"      {idx}. {tit}: {', '.join(data['horas'])} hrs{data['med_info']}\n"

        if not acts_turno and not meds_turno:
            mensaje += "   📋 Sin actividades médicas ni administración de medicamentos en este turno.\n"
        mensaje += "\n"

    mensaje += "_Por favor confirma la recepción de tu cronograma semanal. ¡Muchas gracias!_"
    return mensaje


def enviar_notificaciones_del_dia(
    fecha_seleccionada: date, db: Session
) -> Dict[str, Any]:
    """
    Envía notificaciones de actualización diaria por WhatsApp a cuidadores en turno hoy.
    Consolida múltiples turnos de un mismo cuidador en un único mensaje y cruza estrictamente
    las actividades y medicamentos correspondientes a cualquiera de sus turnos del día.
    """
    asignaciones: List[AsignacionTurno] = (
        db.query(AsignacionTurno)
        .join(Cuidador)
        .join(BloqueTurno)
        .filter(AsignacionTurno.fecha == fecha_seleccionada)
        .all()
    )

    dia_siguiente = fecha_seleccionada + timedelta(days=1)

    actividades_dia: List[ActividadMedica] = (
        db.query(ActividadMedica)
        .filter(ActividadMedica.fecha.in_([fecha_seleccionada, dia_siguiente]))
        .order_by(ActividadMedica.fecha.asc(), ActividadMedica.hora.asc())
        .all()
    )

    medicamentos_dia: List[MedicamentoHorario] = (
        db.query(MedicamentoHorario)
        .join(TratamientoMedicamento)
        .options(joinedload(MedicamentoHorario.tratamiento).joinedload(TratamientoMedicamento.personal_medico))
        .filter(MedicamentoHorario.dia.in_([fecha_seleccionada, dia_siguiente]))
        .order_by(MedicamentoHorario.dia.asc(), MedicamentoHorario.hora.asc())
        .all()
    )

    # Agrupar asignaciones por cuidador (solo activos)
    asigs_por_cuidador: Dict[int, List[AsignacionTurno]] = {}
    for asig in asignaciones:
        if asig.cuidador and asig.cuidador.activo:
            asigs_por_cuidador.setdefault(asig.id_cuidador, []).append(asig)

    resultados: Dict[str, Any] = {
        "fecha": fecha_seleccionada,
        "total_asignaciones": len(asignaciones),
        "total_cuidadores": len(asigs_por_cuidador),
        "enviados": 0,
        "errores": 0,
        "detalles": [],
    }

    if not asigs_por_cuidador:
        return resultados

    for id_cuidador, lista_asigs in asigs_por_cuidador.items():
        lista_ordenada = sorted(lista_asigs, key=lambda a: a.hora_inicio)
        cuidador = lista_ordenada[0].cuidador

        # Cruce estricto por horario del turno del cuidador:
        # Solo se envían actividades y medicamentos que coincidan exactamente con cualquiera de sus jornadas de hoy
        acts_turno = [
            act for act in actividades_dia
            if any(esta_en_jornada_asig(act.fecha, act.hora, a) for a in lista_ordenada)
        ]
        meds_turno = [
            m for m in medicamentos_dia
            if any(esta_en_jornada_asig(m.dia, m.hora, a) for a in lista_ordenada)
        ]

        mensaje_texto = build_whatsapp_message(cuidador, lista_ordenada, acts_turno, meds_turno)
        destino_whatsapp = format_whatsapp_number(cuidador.telefono_whatsapp)
        nombre_cuid = format_nombre_cuidador(cuidador)

        bloques_str = " / ".join([a.bloque.nombre_bloque if a.bloque else "Turno" for a in lista_ordenada])
        horarios_str = " y ".join([f"{a.hora_inicio.strftime('%H:%M')} - {a.hora_fin.strftime('%H:%M')}" for a in lista_ordenada])

        detalle: Dict[str, Any] = {
            "id_asignacion": lista_ordenada[0].id_asignacion,
            "personal": f"{nombre_cuid} (Cuidador)",
            "telefono": cuidador.telefono_whatsapp,
            "bloque": bloques_str,
            "horario": horarios_str,
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
            ahora = datetime.utcnow()
            for a in lista_ordenada:
                a.estado_notificacion = "ENVIADO"
                a.fecha_envio_whatsapp = ahora
            detalle["estado"] = "ENVIADO"
            resultados["enviados"] += 1
        except Exception as exc:
            logger.error(f"Error enviando WhatsApp diario a {destino_whatsapp}: {exc}")
            for a in lista_ordenada:
                a.estado_notificacion = "ERROR"
            detalle["estado"] = "ERROR"
            detalle["detalle_error"] = str(exc)
            resultados["errores"] += 1

        db.commit()
        for a in lista_ordenada:
            db.refresh(a)
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
            fin_semana=fin_semana,
            medicamentos_por_fecha=medicamentos_por_fecha
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
