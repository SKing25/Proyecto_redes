from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, select

db = SQLAlchemy()


# ==================== MODELOS ====================

class DatosSensor(db.Model):
    """Persistencia de lecturas de sensores."""
    __tablename__ = "datos_sensor"

    id = db.Column(db.Integer, primary_key=True)
    temperatura = db.Column(db.Float, nullable=True)
    humedad = db.Column(db.Float, nullable=True)
    soil_moisture = db.Column(db.Float, nullable=True)
    light = db.Column(db.Float, nullable=True)
    percentage = db.Column(db.Float, nullable=True)
    latitud = db.Column(db.Float, nullable=True)
    longitud = db.Column(db.Float, nullable=True)
    nodeId = db.Column(db.String(50), nullable=True, index=True)
    timestamp = db.Column(db.Integer, nullable=True, index=True)
    fecha_creacion = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    def to_dict(self) -> Dict[str, Any]:
        """Serializa el registro a diccionario, omitiendo campos None."""
        base = {
            "id": self.id,
            "nodeId": self.nodeId,
            "timestamp": self.timestamp,
            "fecha_creacion": self.fecha_creacion.isoformat() if self.fecha_creacion else None,
        }
        if self.temperatura is not None:
            base["temperatura"] = float(self.temperatura)
        if self.humedad is not None:
            base["humedad"] = float(self.humedad)
        if self.soil_moisture is not None:
            base["soil_moisture"] = float(self.soil_moisture)
        if self.light is not None:
            base["light"] = float(self.light)
        if self.percentage is not None:
            base["percentage"] = float(self.percentage)
        if self.latitud is not None:
            base["latitud"] = float(self.latitud)
        if self.longitud is not None:
            base["longitud"] = float(self.longitud)
        return base


class Configuracion(db.Model):
    """Parámetros de alertas / umbrales del sistema."""
    __tablename__ = "configuracion"

    id = db.Column(db.Integer, primary_key=True)
    min_temp = db.Column(db.Float, default=0.0, nullable=False)
    max_temp = db.Column(db.Float, default=40.0, nullable=False)
    min_hum = db.Column(db.Float, default=20.0, nullable=False)
    max_hum = db.Column(db.Float, default=80.0, nullable=False)
    min_soil = db.Column(db.Float, default=10.0, nullable=False)
    max_soil = db.Column(db.Float, default=90.0, nullable=False)

    def to_dict(self) -> Dict[str, float]:
        return {
            "min_temp": float(self.min_temp),
            "max_temp": float(self.max_temp),
            "min_hum": float(self.min_hum),
            "max_hum": float(self.max_hum),
            "min_soil": float(self.min_soil),
            "max_soil": float(self.max_soil),
        }


# ==================== INICIALIZACIÓN ====================

def inicializar_db(app) -> None:
    """
    Vincula la extensión SQLAlchemy a la aplicación Flask y crea las tablas.
    """
    db.init_app(app)
    with app.app_context():
        db.create_all()


# ==================== OPERACIONES CRUD Y CONSULTAS ====================

def guardar_dato_sensor(
    temperatura: Optional[float] = None,
    humedad: Optional[float] = None,
    soil_moisture: Optional[float] = None,
    light: Optional[float] = None,
    percentage: Optional[float] = None,
    latitud: Optional[float] = None,
    longitud: Optional[float] = None,
    node_id: str = "unknown",
    timestamp: Optional[int] = None,
) -> DatosSensor:
    """
    Inserta un nuevo registro de sensor en la base de datos.

    Convierte los valores a float cuando no son None. Devuelve el objeto persistido.
    Lanza la excepción original si ocurre un error (la sesión se revierte).
    """
    if timestamp is None:
        timestamp = int(datetime.now(timezone.utc).timestamp())

    # Normalizar / convertir solo si se recibieron valores
    temp_val = float(temperatura) if temperatura is not None else None
    hum_val = float(humedad) if humedad is not None else None
    soil_val = float(soil_moisture) if soil_moisture is not None else None
    light_val = float(light) if light is not None else None
    perc_val = float(percentage) if percentage is not None else None
    lat_val = float(latitud) if latitud is not None else None
    lon_val = float(longitud) if longitud is not None else None

    registro = DatosSensor(
        temperatura=temp_val,
        humedad=hum_val,
        soil_moisture=soil_val,
        light=light_val,
        percentage=perc_val,
        latitud=lat_val,
        longitud=lon_val,
        nodeId=node_id,
        timestamp=timestamp,
    )

    try:
        db.session.add(registro)
        db.session.commit()
        return registro
    except Exception:
        db.session.rollback()
        raise


def obtener_todos_datos(limit: int = 100) -> List[DatosSensor]:
    """
    Devuelve los últimos 'limit' registros ordenados por fecha de creación descendente.
    """
    return DatosSensor.query.order_by(DatosSensor.fecha_creacion.desc()).limit(limit).all()


def obtener_datos_paginados(limit: int = 100, offset: int = 0, node_id: Optional[str] = None) -> List[DatosSensor]:
    """
    Paginación simple con filtro opcional por nodeId.
    """
    q = DatosSensor.query.order_by(DatosSensor.fecha_creacion.desc())
    if node_id:
        q = q.filter_by(nodeId=node_id)
    return q.offset(offset).limit(limit).all()


def obtener_datos_por_fecha(fecha_inicio: datetime, fecha_fin: datetime) -> List[DatosSensor]:
    """
    Registros cuyo campo fecha_creacion está entre fecha_inicio y fecha_fin (inclusive).
    """
    return DatosSensor.query.filter(DatosSensor.fecha_creacion.between(fecha_inicio, fecha_fin)).order_by(DatosSensor.fecha_creacion).all()


def obtener_estadisticas() -> Dict[str, Any]:
    """
    Calcula estadísticas básicas (avg/max/min) para temperatura y humedad, total de registros
    y el último registro.
    """
    # Usamos func.coalesce para evitar valores None en DB engines que permitan nulls en agregados
    agg = db.session.query(
        func.avg(DatosSensor.temperatura).label("temp_promedio"),
        func.max(DatosSensor.temperatura).label("temp_maxima"),
        func.min(DatosSensor.temperatura).label("temp_minima"),
        func.avg(DatosSensor.humedad).label("hum_promedio"),
        func.max(DatosSensor.humedad).label("hum_maxima"),
        func.min(DatosSensor.humedad).label("hum_minima"),
        func.count(DatosSensor.id).label("total_registros"),
    ).one()

    ultimo = DatosSensor.query.order_by(DatosSensor.fecha_creacion.desc()).first()

    def _safe_float(val):
        return float(val) if val is not None else 0.0

    return {
        "temperatura": {
            "promedio": _safe_float(agg.temp_promedio),
            "maxima": _safe_float(agg.temp_maxima),
            "minima": _safe_float(agg.temp_minima),
        },
        "humedad": {
            "promedio": _safe_float(agg.hum_promedio),
            "maxima": _safe_float(agg.hum_maxima),
            "minima": _safe_float(agg.hum_minima),
        },
        "total_registros": int(agg.total_registros or 0),
        "ultimo_registro": ultimo.to_dict() if ultimo else None,
    }


def contar_registros(node_id: Optional[str] = None) -> int:
    """
    Cuenta registros totales, si se provee node_id filtra por ese nodo.
    """
    q = DatosSensor.query
    if node_id:
        q = q.filter_by(nodeId=node_id)
    return q.count()


def obtener_ultimo_dato(node_id: Optional[str] = None) -> Optional[DatosSensor]:
    """
    Retorna el registro más reciente, opcionalmente filtrado por nodo.
    """
    q = DatosSensor.query.order_by(DatosSensor.fecha_creacion.desc())
    if node_id:
        q = q.filter_by(nodeId=node_id)
    return q.first()


def obtener_nodos_unicos() -> List[str]:
    """
    Lista de nodeId distintos (no nulos), ordenada ascendentemente.
    """
    rows = db.session.query(DatosSensor.nodeId).distinct().order_by(DatosSensor.nodeId.asc()).all()
    return [r[0] for r in rows if r[0]]


def obtener_campos_nodo(node_id: str) -> Dict[str, bool]:
    """
    Inspecciona las últimas lecturas de un nodo para detectar qué sensores ha reportado.

    La estrategia replica el comportamiento anterior: lee hasta 10 últimas filas y marca
    los campos que contengan valores no nulos.
    """
    registros = DatosSensor.query.filter_by(nodeId=node_id).order_by(DatosSensor.fecha_creacion.desc()).limit(10).all()

    campos = {
        "temperatura": False,
        "humedad": False,
        "soil_moisture": False,
        "light": False,
        "percentage": False,
    }

    for r in registros:
        if r.temperatura is not None:
            campos["temperatura"] = True
        if r.humedad is not None:
            campos["humedad"] = True
        if r.soil_moisture is not None:
            campos["soil_moisture"] = True
        if r.light is not None:
            campos["light"] = True
        if r.percentage is not None:
            campos["percentage"] = True

        # early exit if todos los campos ya fueron detectados
        if all(campos.values()):
            break

    return campos


def obtener_resumen_nodos() -> List[Dict[str, Any]]:
    """
    Construye un resumen por nodo: id, lista de sensores activos detectados y last_seen (datetime).
    """
    nodos = obtener_nodos_unicos()
    resumen: List[Dict[str, Any]] = []
    for nid in nodos:
        campos = obtener_campos_nodo(nid)
        sensores: List[str] = []
        if campos["temperatura"]:
            sensores.append("Temperatura")
        if campos["humedad"]:
            sensores.append("Humedad")
        if campos["soil_moisture"]:
            sensores.append("Humedad Suelo")
        if campos["light"] or campos["percentage"]:
            sensores.append("Luz")

        ultimo = obtener_ultimo_dato(nid)
        last_seen = ultimo.fecha_creacion if ultimo else None

        resumen.append({
            "id": nid,
            "sensores": sensores,
            "last_seen": last_seen,
        })
    return resumen


def eliminar_dato(dato_id: int) -> bool:
    """
    Borra un registro por su id. Devuelve True si se eliminó, False si no existía.
    Re-lanza la excepción en caso de error de base de datos.
    """
    try:
        entidad = DatosSensor.query.get(dato_id)
        if not entidad:
            return False
        db.session.delete(entidad)
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        raise


def obtener_configuracion() -> Configuracion:
    """
    Recupera la configuración almacenada. Si no existe, crea una fila por defecto y la retorna.
    """
    config = Configuracion.query.first()
    if not config:
        config = Configuracion()
        try:
            db.session.add(config)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
    return config


def actualizar_configuracion(
    min_temp: float,
    max_temp: float,
    min_hum: float,
    max_hum: float,
    min_soil: float,
    max_soil: float,
) -> Configuracion:
    """
    Actualiza los parámetros de configuración de alertas y devuelve la entidad actualizada.
    """
    cfg = obtener_configuracion()
    cfg.min_temp = float(min_temp)
    cfg.max_temp = float(max_temp)
    cfg.min_hum = float(min_hum)
    cfg.max_hum = float(max_hum)
    cfg.min_soil = float(min_soil)
    cfg.max_soil = float(max_soil)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return cfg

