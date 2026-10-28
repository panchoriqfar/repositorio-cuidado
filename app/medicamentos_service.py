"""Módulo de Servicios y Resolución de Medicamentos.

Gestiona la consulta, cruce de jornadas y 'arrastre' continuo de tratamientos
de medicamentos para cuidadores tanto en turnos diurnos como nocturnos (cruce de medianoche).
Garantiza compatibilidad total de datos con las notificaciones por correo electrónico y WhatsApp.
"""

import logging
from datetime import date, time, datetime, timedelta
from typing import List, Dict, Any, Optional, Union
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
       - Para cada fecha D en el intervalo [max(fecha_inicio, t.dia_inicial), fecha_fin]:
         a) Si existen horarios específicos en MedicamentoHorario para esa fecha D, se utilizan.
         b) Si NO existen horarios específicos en MedicamentoHorario para esa fecha D, las tomas
            se arrastran automáticamente a partir de la pauta horaria habitual del tratamiento
            (definida en su día inicial o conjunto de horarios del tratamiento).
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

        # Determinar horarios base habituales a replicar en días arrastrados
        horas_base: List[time] = []
        if t_dia_inicial in explicit_por_fecha:
            horas_base = sorted({to_time_obj(h.hora) for h in explicit_por_fecha[t_dia_inicial] if to_time_obj(h.hora)})
        elif t.horarios:
            horas_base = sorted({to_time_obj(h.hora) for h in t.horarios if to_time_obj(h.hora)})

        if not horas_base:
            continue

        dia_desde = max(f_inicio, t_dia_inicial)
        total_dias = (f_fin - dia_desde).days + 1

        for i in range(total_dias):
            curr_date = dia_desde + timedelta(days=i)
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
                for hora_base in horas_base:
                    tomas_totales.append(
                        TomaMedicamento(
                            dia=curr_date,
                            hora=hora_base,
                            tratamiento=t,
                            es_arrastrado=True
                        )
                    )

    tomas_totales.sort(key=lambda x: (x.dia, x.hora))
    return tomas_totales
