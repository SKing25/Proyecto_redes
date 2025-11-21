from flask import Flask, request, jsonify, render_template
from datetime import datetime
from flask_socketio import SocketIO, emit
from database import (
    inicializar_db,
    guardar_dato_sensor,
    obtener_todos_datos,
    obtener_datos_paginados,
    obtener_datos_por_fecha,
    obtener_estadisticas,
    contar_registros,
    obtener_ultimo_dato,
    obtener_nodos_unicos,
    obtener_campos_nodo,
    eliminar_dato
)
import folium

app = Flask(__name__, static_folder='static', template_folder='templates')

# Configuración de la BD (se mantiene la variable y comportamiento)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///datos_sensores.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inicializar la base de datos
inicializar_db(app)

# Forzar modo threading para evitar problemas en ciertos entornos
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')


def crear_mapa(latitud, longitud):
    """
    Genera un HTML embebible con folium. Si falla devuelve cadena vacía.
    """
    try:
        m = folium.Map(location=[latitud, longitud], zoom_start=16, control_scale=True)
        folium.TileLayer('OpenStreetMap').add_to(m)
        folium.CircleMarker([latitud, longitud], radius=7, color='#6dd3b6', fill=True, fill_opacity=0.9,
                            popup='Nodo').add_to(m)
        return m._repr_html_()
    except Exception:
        return ''


def _common_context():
    """Contexto común para templates: nodos, total_registros y ultimo_dato"""
    nodos = obtener_nodos_unicos() or []
    total_registros = contar_registros() or 0
    ultimo_registro = obtener_ultimo_dato()
    return {
        'nodos': nodos,
        'total_registros': total_registros,
        'ultimo_dato': ultimo_registro
    }


# RUTAS

@app.route('/')
def home():
    try:
        ctx = _common_context()
        mapa_html = crear_mapa(4.660753, -74.059945)
        ctx.update({'mapa': mapa_html})
        return render_template('index.html', **ctx)
    except Exception as e:
        return f"Servidor activo. Error: {str(e)}"


@app.route('/nodo/<string:node_id>')
def ver_por_nodo(node_id: str):
    try:
        datos = obtener_datos_paginados(limit=100, offset=0, node_id=node_id)
        dato = obtener_ultimo_dato(node_id=node_id)
        total_registros = contar_registros(node_id=node_id)
        nodos = obtener_nodos_unicos()
        campos = obtener_campos_nodo(node_id)

        datos_dict = [d.to_dict() for d in datos]

        return render_template('nodo.html',
                               node_id=node_id,
                               datos=datos,
                               datos_json=datos_dict,
                               total_registros=total_registros,
                               ultimo_dato=dato,
                               nodos=nodos,
                               campos=campos)
    except Exception as e:
        return f"Error: {e}", 500


@app.route('/ver')
def ver_datos():
    try:
        datos = obtener_todos_datos(limit=100)
        nodos = obtener_nodos_unicos()
        return render_template('tabla.html', datos=datos, nodos=nodos)
    except Exception as e:
        return f"Error: {e}", 500


@app.route('/datos', methods=['POST'])
def recibir_datos():
    try:
        data = request.get_json(silent=True)
        print(f"Datos recibidos: {data}")

        if not data:
            return jsonify({"status": "error", "mensaje": "No se recibió JSON"}), 400

        # Normalización de nombres (se mantienen variables originales)
        if 'temperatura' not in data:
            for alt in ('temperature', 'temp', 't'):
                if alt in data:
                    try:
                        data['temperatura'] = float(data.pop(alt))
                    except Exception:
                        data.setdefault('temperatura', data.pop(alt))
                    break

        if 'humedad' not in data:
            for alt in ('humidity', 'hum', 'h'):
                if alt in data:
                    try:
                        data['humedad'] = float(data.pop(alt))
                    except Exception:
                        data.setdefault('humedad', data.pop(alt))
                    break

        if 'light' not in data:
            for alt in ('luz', 'lux', 'l'):
                if alt in data:
                    try:
                        data['light'] = float(data.pop(alt))
                    except Exception:
                        data.setdefault('light', data.pop(alt))
                    break

        if 'percentage' not in data:
            for alt in ('luz_porcentaje', 'light_percentage', 'porcentaje', 'pct'):
                if alt in data:
                    try:
                        data['percentage'] = float(data.pop(alt))
                    except Exception:
                        data.setdefault('percentage', data.pop(alt))
                    break

        temperatura = data.get('temperatura')
        humedad = data.get('humedad')
        soil_moisture = data.get('soil_moisture')
        light = data.get('light')
        percentage = data.get('percentage')
        node_id = data.get('nodeId') or data.get('node_id') or 'unknown'
        timestamp = data.get('timestamp')

        nuevo_dato = guardar_dato_sensor(
            temperatura=temperatura,
            humedad=humedad,
            soil_moisture=soil_moisture,
            light=light,
            percentage=percentage,
            node_id=node_id,
            timestamp=timestamp
        )

        print(f"Dato guardado en BD: ID={nuevo_dato.id}")

        try:
            payload = nuevo_dato.to_dict()
            socketio.emit('nuevo_dato', payload)
        except Exception as _e:
            print(f"Advertencia: no se pudo emitir por SocketIO: {_e}")

        return jsonify({
            "status": "ok",
            "mensaje": "Dato guardado en BD",
            "id": nuevo_dato.id
        }), 200

    except Exception as e:
        print(f"Error guardando dato: {e}")
        return jsonify({"status": "error", "mensaje": str(e)}), 500


@app.route('/api/datos')
def api_datos():
    try:
        limit = request.args.get('limit', 100, type=int)
        datos = obtener_todos_datos(limit=limit)
        return jsonify([dato.to_dict() for dato in datos])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# SOCKET.IO EVENTS

@socketio.on('connect')
def handle_connect():
    print('Cliente conectado')
    try:
        ultimos_datos = obtener_todos_datos(limit=10)
        emit('datos_iniciales', {
            'datos': [dato.to_dict() for dato in ultimos_datos],
            'mensaje': f'Conectado al servidor. {len(ultimos_datos)} registros enviados.'
        })
    except Exception as e:
        emit('error', {'mensaje': f'Error al obtener datos iniciales: {str(e)}'})


@socketio.on('disconnect')
def handle_disconnect():
    print('Cliente desconectado')


@socketio.on('solicitar_datos')
def handle_solicitar_datos(data):
    try:
        limit = data.get('limit', 100)
        offset = data.get('offset', 0)
        node_id = data.get('nodeId')

        datos = obtener_datos_paginados(limit=limit, offset=offset, node_id=node_id)

        emit('resultado_datos', {
            'datos': [dato.to_dict() for dato in datos],
            'total': len(datos),
            'offset': offset,
            'limit': limit
        })
    except Exception as e:
        emit('error', {'mensaje': f'Error al obtener datos: {str(e)}'})


@socketio.on('filtrar_por_fecha')
def handle_filtrar_por_fecha(data):
    try:
        fecha_inicio = datetime.fromisoformat(data.get('fecha_inicio', ''))
        fecha_fin = datetime.fromisoformat(data.get('fecha_fin', ''))

        if not fecha_inicio or not fecha_fin:
            emit('error', {'mensaje': 'Formato de fechas inválido'})
            return

        datos = obtener_datos_por_fecha(fecha_inicio, fecha_fin)

        emit('resultado_filtrado', {
            'datos': [dato.to_dict() for dato in datos],
            'total': len(datos),
            'fecha_inicio': fecha_inicio.isoformat(),
            'fecha_fin': fecha_fin.isoformat()
        })
    except Exception as e:
        emit('error', {'mensaje': f'Error al filtrar por fechas: {str(e)}'})


@socketio.on('obtener_estadisticas')
def handle_estadisticas(data):
    try:
        estadisticas = obtener_estadisticas()
        emit('resultado_estadisticas', estadisticas)
    except Exception as e:
        emit('error', {'mensaje': f'Error al obtener estadísticas: {str(e)}'})


@socketio.on('eliminar_dato')
def handle_eliminar_dato(data):
    try:
        id_dato = data.get('id')
        if not id_dato:
            emit('error', {'mensaje': 'ID no proporcionado'})
            return

        eliminado = eliminar_dato(id_dato)
        if not eliminado:
            emit('error', {'mensaje': f'Dato con ID {id_dato} no encontrado'})
            return

        emit('dato_eliminado', {
            'id': id_dato,
            'mensaje': f'Dato con ID {id_dato} eliminado correctamente'
        })

        socketio.emit('actualizacion_datos', {
            'accion': 'eliminar',
            'id': id_dato
        })

    except Exception as e:
        emit('error', {'mensaje': f'Error al eliminar dato: {str(e)}'})


if __name__ == '__main__':
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, allow_unsafe_werkzeug=True)