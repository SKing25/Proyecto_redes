import paho.mqtt.client as mqtt
import time
import requests
import json

BROKER = "localhost"   
PORT = 1883
TOPIC = "Nodos/datos/+" 


SERVER_URL = "https://proyecto-redes-5b146a15d8b6.herokuapp.com" #CAMBIAR POR LINK DE HEROKU

node_cache = {}

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Conectado a Mosquitto")
        client.subscribe(TOPIC)
        print(f"Suscrito al tópico: {TOPIC}")
    else:
        print(f"Error de conexión con código {rc}")

def on_message(client, userdata, msg):
    try:
        topic = msg.topic
        payload = msg.payload.decode("utf-8")
        print(f"Mensaje de {topic}: {payload}")

        data = json.loads(payload)
        node_id = topic.split("/")[-1] if "/" in topic else "unknown"
        
        # Detectar mensajes de control y reenviar sin procesar
        if "type" in data and data["type"] in ["PONG", "TOPO", "TRACE_REPLY"]:
            print(f"Control Msg detectado: {data['type']}")
            base_url = SERVER_URL.replace("/datos", "")
            try:
                requests.post(f"{base_url}/api/control_response", json=data, timeout=5)
            except Exception as e:
                print(f"Error enviando respuesta de control: {e}")
            return

        # Caso especial: Gateway reportando su IP
        if node_id == "gateway" and "ip" in data:
            gateway_data = {
                "nodeId": "gateway",
                "ip": data["ip"],
                "nodes": data.get("nodes", 0),
                "timestamp": int(time.time())
            }
            print(f"Gateway IP: {data['ip']} - Nodos conectados: {data.get('nodes', 0)}")
            response = requests.post(SERVER_URL, json=gateway_data, timeout=10)
            if response.status_code == 200:
                print("IP del gateway enviada al servidor\n")
            else:
                print(f"Error al enviar IP: {response.status_code}\n")
            return
        
        # Inicializar cache del nodo si no existe
        if node_id not in node_cache:
            node_cache[node_id] = {}
        
        # Guardar cada tipo de dato en el cache (acepta español e inglés)
        if "temperature" in data or "temperatura" in data:
            temp = data.get("temperature") or data.get("temperatura")
            node_cache[node_id]["temperatura"] = temp
            print(f"Temperatura: {temp}°C")
        
        if "humidity" in data or "humedad" in data:
            hum = data.get("humidity") or data.get("humedad")
            node_cache[node_id]["humedad"] = hum
            print(f"Humedad aire: {hum}%")
        
        if "light" in data:
            node_cache[node_id]["luz"] = data["light"]
            print(f"Luz: {data['light']} lux")
        
        if "percentage" in data and "light" in data:
            node_cache[node_id]["luz_porcentaje"] = data["percentage"]
            print(f"Luz %: {data['percentage']}%")
        
        if "soil_moisture" in data or "humedad_suelo" in data:
            node_cache[node_id]["soil_moisture"] = data["soil_moisture"]
            print(f"soil_moisture: {data['soil_moisture']}%")
        
        # GPS coordinates (nuevos campos)
        if "lat" in data and "lon" in data:
            node_cache[node_id]["lat"] = data["lat"]
            node_cache[node_id]["lon"] = data["lon"]
            print(f"GPS: {data['lat']}, {data['lon']}")
        
        # Preparar datos para enviar
        complete_data = {
            "nodeId": node_id,
            "timestamp": int(time.time())
        }
        
        # Agregar todos los datos del cache del nodo
        complete_data.update(node_cache[node_id])
        
        print(f"Enviando al servidor: {complete_data}")

        # Enviar a servidor
        response = requests.post(SERVER_URL, json=complete_data, timeout=10)
        if response.status_code == 200:
            print("Datos enviados al servidor exitosamente\n")
        else:
            print(f"Error al enviar: {response.status_code} - {response.text}\n")

    except json.JSONDecodeError as e:
        print(f"Error parseando JSON: {e}")
        print(f"Payload recibido: {payload}\n")
    except Exception as e:
        print(f"Error procesando mensaje: {e}\n")

# Configuración del cliente MQTT
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

print("Iniciando puente MQTT -> Servidor")
print(f"Broker: {BROKER}:{PORT}")
print(f"Servidor: {SERVER_URL}")

try:
    client.connect(BROKER, PORT, 60)
    print("Iniciando loop...")
    client.loop_forever()
except KeyboardInterrupt:
    print("\nPuente detenido por usuario")
except Exception as e:
    print(f"Error en puente: {e}")
