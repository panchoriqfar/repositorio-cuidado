"""Módulo de Servicios y Resolución de Medicamentos.

Gestiona la consulta, cruce de jornadas y 'arrastre' continuo de tratamientos
de medicamentos para cuidadores tanto en turnos diurnos como nocturnos (cruce de medianoche).
Garantiza compatibilidad total de datos con las notificaciones por correo electrónico y WhatsApp.
"""

import logging
from datetime import date, time, datetime, timedelta
from typing import List, Dict, Any, Optional, Union, Tuple
from sqlalchemy.orm import Session, joinedload

from app.models import TratamientoMedicamento, MedicamentoHorario, AsignacionTurno

logger = logging.getLogger("medicamentos_service")


def to_date_obj(val: Any) -> Optional[date]:
    """Convierte de forma segura cadenas ISO ('YYYY-MM-DD') o fechas a objetos date."""
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        try:
            return datetime.strptime(val.split("T")[0].strip(), "%Y-%m-%d").date()
        except Exception:
            return None
    return None


def to_time_obj(val: Any) -> Optional[time]:
    """Convierte de forma segura cadenas ('HH:MM' o 'HH:MM:SS') o tiempos a objetos time."""
    if isinstance(val, time):
        return val
    if isinstance(val, str):
        try:
            partes = val.strip().split(":")
            h = int(partes[0])
            m = int(partes[1])
            s = int(float(partes[2])) if len(partes) > 2 else 0
            return time(h, m, s)
        except Exception:
            return None
    return None


class TomaMedicamento:
    """
    Representa una toma programada o arrastrada de un medicamento para una fecha y hora específicas.
    Proporciona compatibilidad total en atributos con MedicamentoHorario (.dia, .hora, .tratamiento, .id)
    para el renderizado de correos electrónicos y mensajes de WhatsApp.
    """
    def __init__(
        self,
        dia: date,
        hora: time,
        tratamiento: TratamientoMedicamento,
        es_arrastrado: bool = False,
        id_horario: Optional[int] = None
    ):
        self.id = id_horario or 0
        self.medicamento_id = tratamiento.id if tratamiento else None
        self.dia = dia
        self.hora = hora
        self.tratamiento = tratamiento
        self.es_arrastrado = es_arrastrado

    def __repr__(self) -> str:
        nom = self.tratamiento.nombre_medicamento if self.tratamiento else "Desconocido"
        arr = " [arrastrado]" if self.es_arrastrado else ""
        return f"<TomaMedicamento {nom} {self.dia} {self.hora.strftime('%H:%M')}{arr}>"


def esta_en_jornada_asig(dia_item: date, hora_item: time, asig: AsignacionTurno) -> bool:
    """
    Verifica si una fecha y hora específicas caen dentro del intervalo exacto
    de la jornada laboral asignada a un cuidador.
    Soporta turnos diurnos estándar y turnos nocturnos que cruzan la medianoche (ej: 21:00 a 10:00).
    """
    d_item = to_date_obj(dia_item) or dia_item
    h_item = to_time_obj(hora_item) or hora_item
    a_fecha = to_date_obj(asig.fecha) or asig.fecha
    a_hini = to_time_obj(asig.hora_inicio) or asig.hora_inicio
    a_hfin = to_time_obj(asig.hora_fin) or asig.hora_fin

    dt_item = datetime.combine(d_item, h_item)
    dt_inicio = datetime.combine(a_fecha, a_hini)
    if a_hini <= a_hfin:
        dt_fin = datetime.combine(a_fecha, a_hfin)
    else:
        # Turno nocturno que cruza medianoche hacia el día siguiente
        dt_fin = datetime.combine(a_fecha + timedelta(days=1), a_hfin)
    return dt_inicio <= dt_item <= dt_fin


def corresponde_medicamento_a_cuidador(
    med_dia: date,
    med_hora: time,
    asig: AsignacionTurno
) -> bool:
    """
    Determina si una toma de medicamento (fecha y hora) debe incluirse en la pauta
    notificada a un cuidador con turno asignado.
    
    Regla de negocio:
    1. Turno exacto (diurno o nocturno que cruza medianoche): Si la toma cae dentro del
       horario exacto de la jornada del cuidador (ej. 21:00 a 10:00 del día siguiente).
    2. Cuidador en turno en la misma fecha (med_dia == asig.fecha): Si el cuidador está
       asignado en la fecha de la toma, se le incluyen las tomas programadas o arrastradas
       de ese día, garantizando que el cuidador a cargo del día reciba todos los medicamentos
       del día martes creados el lunes o en pauta continua.
    """
    med_d = to_date_obj(med_dia) or med_dia
    med_h = to_time_obj(med_hora) or med_hora
    asig_d = to_date_obj(asig.fecha) or asig.fecha

    # 1. Rango de jornada estricto (incluye turno nocturno cruzando medianoche)
    if esta_en_jornada_asig(med_d, med_h, asig):
        return True

    # 2. Asignado en la misma fecha calendario de la toma
    if asig_d == med_d:
        return True

    return False


def obtener_medicamentos_programados(
    db: Session,
    fecha_inicio: date,
    fecha_fin: date
) -> List[TomaMedicamento]:
    """
    Obtiene todas las tomas de medicamentos (explícitas y arrastradas) en el rango [fecha_inicio, fecha_fin].
    
    Regla de negocio:
    1. Para cada tratamiento registrado en la base de datos con dia_inicial <= fecha_fin:
       - Recorre la pauta cronológicamente manteniendo de forma activa las tomas más recientes.
       - Si una fecha D tiene horarios explícitos en MedicamentoHorario, se aplican y actualizan
         la pauta activa (arrastre continuo sin pérdida de tomas).
       - Si una fecha D NO tiene horarios explícitos, se arrastra la pauta horaria activa previa.
    """
    f_inicio = to_date_obj(fecha_inicio) or fecha_inicio
    f_fin = to_date_obj(fecha_fin) or fecha_fin

    tratamientos: List[TratamientoMedicamento] = (
        db.query(TratamientoMedicamento)
        .options(
            joinedload(TratamientoMedicamento.personal_medico),
            joinedload(TratamientoMedicamento.horarios)
        )
        .filter(TratamientoMedicamento.dia_inicial <= f_fin)
        .all()
    )

    tomas_totales: List[TomaMedicamento] = []

    for t in tratamientos:
        t_dia_inicial = to_date_obj(t.dia_inicial) or t.dia_inicial

        # Agrupar horarios explícitos existentes por fecha
        explicit_por_fecha: Dict[date, List[MedicamentoHorario]] = {}
        for h in (t.horarios or []):
            h_dia = to_date_obj(h.dia)
            if h_dia:
                explicit_por_fecha.setdefault(h_dia, []).append(h)

        # Determinar horarios iniciales del tratamiento
        horas_activas: List[time] = []
        if t_dia_inicial in explicit_por_fecha:
            horas_activas = sorted({to_time_obj(h.hora) for h in explicit_por_fecha[t_dia_inicial] if to_time_obj(h.hora)})
        elif t.horarios:
            horas_activas = sorted({to_time_obj(h.hora) for h in t.horarios if to_time_obj(h.hora)})

        if not horas_activas and not explicit_por_fecha:
            continue

        # Punto de partida para el arrastre continuo
        dias_expl = list(explicit_por_fecha.keys())
        dia_origen = min([t_dia_inicial] + dias_expl) if dias_expl else t_dia_inicial

        # Simular cronológicamente día a día hasta f_fin para mantener el estado exacto de horas activas
        dias_a_recorrer = (f_fin - dia_origen).days + 1
        for i in range(dias_a_recorrer):
            curr_date = dia_origen + timedelta(days=i)

            # Si el día actual tiene registros explícitos en la base de datos, actualiza la pauta activa
            if curr_date in explicit_por_fecha:
                expl_horas = sorted({to_time_obj(h.hora) for h in explicit_por_fecha[curr_date] if to_time_obj(h.hora)})
                if expl_horas:
                    horas_activas = expl_horas

            # Solo generar tomas si curr_date cae en el intervalo consultado [f_inicio, f_fin]
            # y es mayor o igual al día inicial del tratamiento
            if curr_date >= f_inicio and curr_date >= t_dia_inicial:
                if curr_date in explicit_por_fecha:
                    for h in sorted(explicit_por_fecha[curr_date], key=lambda x: to_time_obj(x.hora) or time(0, 0)):
                        h_time = to_time_obj(h.hora)
                        if h_time:
                            tomas_totales.append(
                                TomaMedicamento(
                                    dia=curr_date,
                                    hora=h_time,
                                    tratamiento=t,
                                    es_arrastrado=False,
                                    id_horario=h.id
                                )
                            )
                else:
                    for hora_act in horas_activas:
                        tomas_totales.append(
                            TomaMedicamento(
                                dia=curr_date,
                                hora=hora_act,
                                tratamiento=t,
                                es_arrastrado=True
                            )
                        )

    tomas_totales.sort(key=lambda x: (x.dia, x.hora))
    return tomas_totales


# ---------------------------------------------------------------------------
# Formateo agrupado de pautas de medicamentos (Días y Horarios Consolidados)
# ---------------------------------------------------------------------------

DIAS_SEMANA_ORDEN = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def format_horas_espanol(horas_list: List[str]) -> str:
    """
    Formatea una lista de strings de horas ['12:00', '16:00', '23:59'] a formato fluido:
    'a las 12:00, 16:00 y 23:59 hrs'.
    """
    if not horas_list:
        return ""
    horas_ordenadas = sorted(list(set(horas_list)))
    if len(horas_ordenadas) == 1:
        return f"a las {horas_ordenadas[0]} hrs"
    elif len(horas_ordenadas) == 2:
        return f"a las {horas_ordenadas[0]} y {horas_ordenadas[1]} hrs"
    else:
        todas_menos_ultima = ", ".join(horas_ordenadas[:-1])
        return f"a las {todas_menos_ultima} y {horas_ordenadas[-1]} hrs"


def format_grupo_dias(dias_nombres: List[str]) -> str:
    """
    Formatea una lista ordenada de nombres de días de la semana.
    Ejemplos:
    - ['Lunes'] -> 'Lunes'
    - ['Lunes', 'Martes'] -> 'Lunes y Martes'
    - ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes'] -> 'de Lunes a Viernes'
    - ['Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'] -> 'de Martes a Domingo'
    - ['Lunes', 'Miércoles', 'Viernes'] -> 'Lunes, Miércoles y Viernes'
    """
    if not dias_nombres:
        return ""

    dias_unicos = [d for d in DIAS_SEMANA_ORDEN if d in dias_nombres]
    if not dias_unicos:
        dias_unicos = dias_nombres

    if len(dias_unicos) == 1:
        return dias_unicos[0]

    indices = [DIAS_SEMANA_ORDEN.index(d) for d in dias_unicos if d in DIAS_SEMANA_ORDEN]
    rangos = []
    if indices:
        r_actual = [indices[0]]
        for idx in indices[1:]:
            if idx == r_actual[-1] + 1:
                r_actual.append(idx)
            else:
                rangos.append(r_actual)
                r_actual = [idx]
        rangos.append(r_actual)
    else:
        rangos = [[0]]

    # Días completamente individuales o discontinuos
    if all(len(r) == 1 for r in rangos):
        if len(dias_unicos) == 2:
            return f"{dias_unicos[0]} y {dias_unicos[1]}"
        return ", ".join(dias_unicos[:-1]) + f" y {dias_unicos[-1]}"

    # Un único bloque consecutivo
    if len(rangos) == 1:
        r = rangos[0]
        if len(r) == 2:
            return f"{DIAS_SEMANA_ORDEN[r[0]]} y {DIAS_SEMANA_ORDEN[r[1]]}"
        else:
            return f"de {DIAS_SEMANA_ORDEN[r[0]]} a {DIAS_SEMANA_ORDEN[r[-1]]}"

    # Varios bloques consecutivos
    partes = []
    for r in rangos:
        if len(r) == 1:
            partes.append(DIAS_SEMANA_ORDEN[r[0]])
        elif len(r) == 2:
            partes.append(f"{DIAS_SEMANA_ORDEN[r[0]]} y {DIAS_SEMANA_ORDEN[r[1]]}")
        else:
            partes.append(f"de {DIAS_SEMANA_ORDEN[r[0]]} a {DIAS_SEMANA_ORDEN[r[-1]]}")

    if len(partes) == 2:
        return f"{partes[0]} y {partes[1]}"
    return ", ".join(partes[:-1]) + f" y {partes[-1]}"


def formatear_pauta_medicamentos(
    tomas: List[Union[TomaMedicamento, MedicamentoHorario, Any]]
) -> List[Dict[str, Any]]:
    """
    Agrupa y formatea la pauta de tomas de medicamentos según el formato requerido:
    [nombre de pastilla] de lunes a viernes (o los días que correspondan en los siguientes horarios;
    si un día solo son algunos horarios, ese día se separa. Ej: amlodipino lunes 16:00 y 23:59
    de martes a domingo a las 12:00, 16:00 y 23:59).
    
    Aplica uniformemente a:
    - Notificaciones diarias y semanales
    - Correo electrónico (texto plano y HTML)
    - Mensajes de WhatsApp
    """
    if not tomas:
        return []

    # 1. Agrupar tomas por medicamento preservando orden de aparición
    meds_map: Dict[str, Dict[str, Any]] = {}
    for t in tomas:
        nom = t.tratamiento.nombre_medicamento if t.tratamiento else "Medicamento"
        medico_nom = ""
        if t.tratamiento and getattr(t.tratamiento, "personal_medico", None):
            pm = t.tratamiento.personal_medico
            medico_nom = f"{pm.nombre} {pm.apellido or ''}".strip()

        if nom not in meds_map:
            meds_map[nom] = {
                "medico": medico_nom,
                "dias": {}  # date -> set of "HH:MM"
            }
        elif medico_nom and not meds_map[nom]["medico"]:
            meds_map[nom]["medico"] = medico_nom

        d_obj = to_date_obj(t.dia) or (t.dia if isinstance(t.dia, date) else None)
        if not d_obj:
            try:
                d_obj = date.fromisoformat(str(t.dia).split("T")[0])
            except Exception:
                continue

        h_obj = to_time_obj(t.hora) or (t.hora if isinstance(t.hora, time) else None)
        h_str = h_obj.strftime("%H:%M") if hasattr(h_obj, "strftime") else str(t.hora)[:5]

        meds_map[nom]["dias"].setdefault(d_obj, set()).add(h_str)

    resultado: List[Dict[str, Any]] = []

    for nom, data in meds_map.items():
        dias_dict = data["dias"]
        if not dias_dict:
            continue

        fechas_ordenadas = sorted(dias_dict.keys())
        patrones: Dict[Tuple[str, ...], List[str]] = {}

        for f in fechas_ordenadas:
            dia_nom = DIAS_SEMANA_ORDEN[f.weekday()]
            horas_tuple = tuple(sorted(list(dias_dict[f])))
            if not horas_tuple:
                continue
            if horas_tuple not in patrones:
                patrones[horas_tuple] = []
            if dia_nom not in patrones[horas_tuple]:
                patrones[horas_tuple].append(dia_nom)

        pautas = []
        for horas_tuple, dias_lista in patrones.items():
            str_dias = format_grupo_dias(dias_lista)
            str_horas = format_horas_espanol(list(horas_tuple))
            pautas.append(f"{str_dias} {str_horas}")

        pautas_unidas = "; ".join(pautas)
        medico_txt = f" - Indicado por: {data['medico']}" if data["medico"] else ""
        medico_wa = f" (Indicado por: {data['medico']})" if data["medico"] else ""
        medico_html = f" <span style='color: #64748b;'>&bull; Indicado por: {data['medico']}</span>" if data["medico"] else ""

        resultado.append({
            "nombre": nom,
            "medico": data["medico"],
            "pautas": pautas,
            "texto_plano": f"{nom}: {pautas_unidas}{medico_txt}.",
            "texto_whatsapp": f"*{nom}*: {pautas_unidas}{medico_wa}",
            "texto_html": f"<strong>{nom}</strong>: {pautas_unidas}{medico_html}"
        })

    return resultado

