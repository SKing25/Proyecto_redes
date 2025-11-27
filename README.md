# Proyecto_redes · SensorHub

Panel web con Flask + Socket.IO para monitoreo de nodos ESP32 en una red mesh (painlessMesh), pasarela (gateway) hacia MQTT y puente a servidor HTTP. Incluye una terminal de control en tiempo real y un mapa con la ubicación base marcada.

## 🗺️ Mapa y ubicación base

- El mapa de la página principal Aparecen los Nodos
- Se muestra un marcador llamado “Nodo#(depende del número)” en esas coordenadas, visible al cargar.

## 🔌 Arquitectura

- Frontend: HTML/CSS + Socket.IO (templates en `templates/` y estilos en `static/`).
- Backend: Flask + Flask-SocketIO (`app.py`), SQLite (`database.py`).
- MQTT Bridge (local): `Puente.py` suscrito a `Nodos/datos/+` y reenvía a Flask (`/datos`). También reinyecta respuestas de control a `/api/control_response`.
- Firmware ESP32:
	- Gateway: `GATEWAY.cpp` (mesh root, WiFi STA, MQTT hacia broker, reenvío control ↔ mesh).
	- Nodos: `NODO_TEMPERATURA.cpp`, `NODO_HUMEDAD.cpp`, `NODO_LUZ.cpp`, `NODO_HUM_SUELO.cpp` (envían datos por mesh; responden a PING/TOPO/TRACE).

## 🌐 Redes y credenciales

- WiFi del hotspot (Gateway):
	- SSID: `Doo`
	- Password: `1023374689`
- Red mesh interna (painlessMesh):
	- Prefijo: `RED_Nodos`
	- Password: `RED_Nodos_1023374689`
	- Puerto: `5555`

Notas:
- En `GATEWAY.cpp`, el broker MQTT está configurado en `MQTT_SERVER` (por defecto `10.21.139.182`) y puerto `1883`. Ajusta a la IP de tu broker.
- En `Puente.py`, `BROKER = "localhost"` y `SERVER_URL` apunta al backend desplegado. Cambia a tu URL/local según tu entorno.

## 🧩 Tópicos y mensajes MQTT

- Datos: `Nodos/datos/<nodeId>`
	- Ejemplos de payload (JSON):
		- Temperatura: `{ "temperatura": 24.1, "lat": 4.66, "lon": -74.05 }`
		- Humedad aire: `{ "humidity": 55.3, "lat": ..., "lon": ... }`
		- Luz: `{ "light": 123.45, "percentage": 42.0, ... }`
		- Suelo: `{ "soil_moisture": 63.0, ... }`
- Control (publish desde Flask): `Nodos/control`
	- Peticiones: `{ "type": "PING"|"TOPO_REQ"|"TRACE", "to": <id|0>, "from": 0, "seq": <ts> }`
	- Respuestas (reenviadas al UI): `PONG`, `TOPO`, `TRACE_REPLY`.

## 🖥️ Páginas clave

- `index.html` (Panel): métricas, actividad, mapa (con marcador “Nodo”).
- `control.html` (Control):
	- Terminal en tiempo real (Socket.IO) con comandos: `ping`, `nodes`, `status`, `mesh`, y JSON directo.
	- Selector de nodos con filtro para autocompletar el destino.
	- Ping RTT con clasificación: cerca (≤120 ms), medio (≤450 ms), lejos (>450 ms).

## ▶️ Puesta en marcha (local)

1) Backend Flask
- Requisitos: Python 3.10+.
- Instalar dependencias:
	- `pip install -r requirements.txt`
- Ejecutar servidor:
	- `python app.py`
- El servidor expone HTTP y Socket.IO en `http://localhost:5000`.

2) Broker MQTT
- Instala y arranca Mosquitto (u otro broker) en la máquina o red accesible por la gateway.
- Ajusta `MQTT_SERVER` en `GATEWAY.cpp` a la IP del broker.

3) Puente MQTT → HTTP (`Puente.py`)
- Ajusta `SERVER_URL` a tu backend (local o desplegado).
- Ejecuta: `python Puente.py`

4) Firmware ESP32
- Librerías utilizadas:
	- `painlessMesh`, `ArduinoJson`, `TinyGPS++`, `DHT` (nodos), `WiFi`, `PubSubClient` (gateway).
- Compila y carga `GATEWAY.cpp` (ESP32, modo STA) y al menos un nodo (`NODO_*`).
- Asegura hotspot 2.4GHz y credenciales WiFi correctas.

## ⚙️ Configuración de alertas

- En la página “Alertas” puedes definir umbrales min/max para temperatura, humedad y suelo.
- Las alertas se emiten al UI en tiempo real vía Socket.IO.

## 🧪 Control rápido

- En “Control”, prueba:
	- `PING` a un ID de nodo y observa el RTT.
	- `TOPO_REQ` para ver vecinos.
	- `TRACE` para ruta hacia un nodo.

## 🛠️ Solución de problemas

- Gateway sin IP: verifica que el hotspot sea 2.4GHz, DHCP activo y SSID/clave correctos (logs lo indican).
- Sin datos en el panel: confirma que `Puente.py` está suscrito al broker correcto y `SERVER_URL` apunta al backend vivo.
- Sin respuestas de control: valida que el gateway esté suscrito a `Nodos/control` y reenvíe hacia el mesh.

---

© 2025
