"""
Módulo de base de datos
Contiene modelos SQLAlchemy y funciones de acceso a datos
"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
from sqlalchemy import func

db = SQLAlchemy()


# ==================== MODELO DE DATOS ====================

class DatosSensor(db.Model):
    """Modelo para almacenar datos de sensores"""
    id = db.Column(db.Integer, primary_key=True)
    temperatura = db.Column(db.Float, nullable=True)
    humedad = db.Column(db.Float, nullable=True)
    soil_moisture = db.Column(db.Float, nullable=True)  # Humedad del suelo
    light = db.Column(db.Float, nullable=True)  # Nivel de luz
    percentage = db.Column(db.Float, nullable=True)  # Porcentaje de luz
    nodeId = db.Column(db.String(50), nullable=True)
    timestamp = db.Column(db.Integer, nullable=True)
    fecha_creacion = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        """Convierte el objeto a diccionario para serialización JSON"""
        resultado = {
            'id': self.id,
            'nodeId': self.nodeId,
            'timestamp': self.timestamp,
            'fecha_creacion': self.fecha_creacion.strftime('%Y-%m-%d %H:%M:%S %Z')
        }

        # Solo incluir campos con valores no None
        if self.temperatura is not None:
            resultado['temperatura'] = float(self.temperatura)
        if self.humedad is not None:
            resultado['humedad'] = float(self.humedad)
        if self.soil_moisture is not None:
            resultado['soil_moisture'] = float(self.soil_moisture)
        if self.light is not None:
            resultado['light'] = float(self.light)
        if self.percentage is not None:
            resultado['percentage'] = float(self.percentage)

        return resultado


# ==================== FUNCIONES DE ACCESO A DATOS ====================

def inicializar_db(app):
    """Inicializa la base de datos con la aplicación Flask"""
    db.init_app(app)
    with app.app_context():
        db.create_all()


def guardar_dato_sensor(temperatura=None, humedad=None, soil_moisture=None, light=None, percentage=None, node_id='unknown', timestamp=None):
    """
    Guarda un nuevo dato de sensor en la base de datos
    
    Args:
        temperatura: Temperatura en °C o None
        humedad: Humedad en % o None
        soil_moisture: Humedad del suelo o None
        light: Nivel de luz o None
        percentage: Porcentaje luz o None
        node_id: ID del nodo sensor
        timestamp: Timestamp Unix (opcional)
    
    Returns:
        DatosSensor: El objeto guardado
    
    Raises:
        Exception: Si hay error al guardar
    """
    try:
        if timestamp is None:
            timestamp = int(datetime.now().timestamp())
        
        # Convertir a float sólo si no es None
        temp_val = float(temperatura) if temperatura is not None else None
        hum_val = float(humedad) if humedad is not None else None
        soil_val = float(soil_moisture) if soil_moisture is not None else None
        light_val = float(light) if light is not None else None
        percentage = float(percentage) if percentage is not None else None

        nuevo_dato = DatosSensor(
            temperatura=temp_val,
            humedad=hum_val,
            soil_moisture=soil_val,
            light=light_val,
            percentage=percentage,
            nodeId=node_id,
            timestamp=timestamp
        )
        
        db.session.add(nuevo_dato)
        db.session.commit()
        
        return nuevo_dato
    except Exception as e:
        db.session.rollback()
        raise e


def obtener_todos_datos(limit=100):
    """
    Obtiene los últimos N datos ordenados por fecha
    
    Args:
        limit: Número máximo de registros a retornar
    
    Returns:
        list: Lista de objetos DatosSensor
    """
    return DatosSensor.query.order_by(DatosSensor.fecha_creacion.desc()).limit(limit).all()


def obtener_datos_paginados(limit=100, offset=0, node_id=None):
    """
    Obtiene datos con paginación y filtro opcional por nodo
    
    Args:
        limit: Número de registros por página
        offset: Desplazamiento desde el inicio
        node_id: Filtrar por ID de nodo (opcional)
    
    Returns:
        list: Lista de objetos DatosSensor
    """
    query = DatosSensor.query.order_by(DatosSensor.fecha_creacion.desc())
    
    if node_id:
        query = query.filter_by(nodeId=node_id)
    
    return query.offset(offset).limit(limit).all()


def obtener_datos_por_fecha(fecha_inicio, fecha_fin):
    """
    Obtiene datos dentro de un rango de fechas
    
    Args:
        fecha_inicio: datetime objeto de inicio
        fecha_fin: datetime objeto de fin
    
    Returns:
        list: Lista de objetos DatosSensor
    """
    return DatosSensor.query.filter(
        DatosSensor.fecha_creacion.between(fecha_inicio, fecha_fin)
    ).order_by(DatosSensor.fecha_creacion).all()


def obtener_estadisticas():
    """
    Calcula estadísticas de temperatura y humedad
    
    Returns:
        dict: Diccionario con promedios, máximos y mínimos
    """
    stats = db.session.query(
        func.avg(DatosSensor.temperatura).label('temp_promedio'),
        func.max(DatosSensor.temperatura).label('temp_maxima'),
        func.min(DatosSensor.temperatura).label('temp_minima'),
        func.avg(DatosSensor.humedad).label('hum_promedio'),
        func.max(DatosSensor.humedad).label('hum_maxima'),
        func.min(DatosSensor.humedad).label('hum_minima'),
        func.count(DatosSensor.id).label('total_registros')
    ).one()
    
    ultimo_registro = DatosSensor.query.order_by(DatosSensor.fecha_creacion.desc()).first()
    
    return {
        'temperatura': {
            'promedio': float(stats.temp_promedio) if stats.temp_promedio else 0,
            'maxima': float(stats.temp_maxima) if stats.temp_maxima else 0,
            'minima': float(stats.temp_minima) if stats.temp_minima else 0
        },
        'humedad': {
            'promedio': float(stats.hum_promedio) if stats.hum_promedio else 0,
            'maxima': float(stats.hum_maxima) if stats.hum_maxima else 0,
            'minima': float(stats.hum_minima) if stats.hum_minima else 0
        },
        'total_registros': stats.total_registros,
        'ultimo_registro': ultimo_registro.to_dict() if ultimo_registro else None
    }


def contar_registros(node_id=None):
    """
    Cuenta el total de registros, opcionalmente filtrado por nodo
    
    Args:
        node_id: Filtrar por ID de nodo (opcional)
    
    Returns:
        int: Número de registros
    """
    query = DatosSensor.query
    if node_id:
        query = query.filter_by(nodeId=node_id)
    return query.count()


def obtener_ultimo_dato(node_id=None):
    """
    Obtiene el último dato registrado
    
    Args:
        node_id: Filtrar por ID de nodo (opcional)
    
    Returns:
        DatosSensor: Último registro o None
    """
    query = DatosSensor.query.order_by(DatosSensor.fecha_creacion.desc())
    if node_id:
        query = query.filter_by(nodeId=node_id)
    return query.first()


def obtener_nodos_unicos():
    """
    Obtiene lista de IDs de nodos únicos
    
    Returns:
        list: Lista de strings con IDs de nodos
    """
    return [row[0] for row in db.session.query(DatosSensor.nodeId).distinct().order_by(DatosSensor.nodeId.asc()).all() if row[0]]


def obtener_campos_nodo(node_id):
    """
    Detecta qué campos de sensores tiene datos un nodo específico

    Args:
        node_id: ID del nodo a analizar

    Returns:
        dict: Diccionario con campos como claves y True si tiene datos
    """
    datos = DatosSensor.query.filter_by(nodeId=node_id).order_by(DatosSensor.fecha_creacion.desc()).limit(10).all()

    campos = {
        'temperatura': False,
        'humedad': False,
        'soil_moisture': False,
        'light': False,
        'percentage': False
    }

    for dato in datos:
        if dato.temperatura is not None:
            campos['temperatura'] = True
        if dato.humedad is not None:
            campos['humedad'] = True
        if dato.soil_moisture is not None:
            campos['soil_moisture'] = True
        if dato.light is not None:
            campos['light'] = True
        if dato.percentage is not None:
            campos['percentage'] = True

    return campos


def eliminar_dato(dato_id):
    """
    Elimina un dato por ID
    
    Args:
        dato_id: ID del registro a eliminar
    
    Returns:
        bool: True si se eliminó, False si no se encontró
    
    Raises:
        Exception: Si hay error al eliminar
    """
    try:
        dato = DatosSensor.query.get(dato_id)
        if not dato:
            return False
        
        db.session.delete(dato)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        raise e