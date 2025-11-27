#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <painlessMesh.h>

#define MESH_PREFIX "RED_Nodos"
#define MESH_PASSWORD "Horus9876"
#define MESH_PORT 5555

#define WIFI_SSID "Doo"
#define WIFI_PASSWORD "1023374689"
#define MQTT_SERVER "10.21.139.182"
#define MQTT_PORT 1883

#define MQTT_TOPIC "Nodos/datos"
#define MQTT_TOPIC_CONTROL "Nodos/control"

Scheduler userScheduler;
painlessMesh mesh;
WiFiClient espClient;
PubSubClient client(espClient);

unsigned long lastIPReport = 0;
unsigned long lastWifiRetry = 0;
unsigned long lastWifiScan = 0;

// Escaneo de redes para diagnosticar si el SSID está visible (2.4GHz)
void scanAndReport() {
  Serial.println("[WiFi] Escaneando redes...");
  int n = WiFi.scanNetworks();
  if (n <= 0) {
    Serial.println("[WiFi] No se encontraron redes");
    return;
  }
  bool seen = false;
  for (int i = 0; i < n; i++) {
    String ssid = WiFi.SSID(i);
    int32_t rssi = WiFi.RSSI(i);
    int32_t channel = WiFi.channel(i);
    Serial.printf("  - %s (RSSI %d dBm, ch %d)\n", ssid.c_str(), rssi, channel);
    if (ssid == WIFI_SSID) seen = true;
  }
  if (!seen) {
    Serial.println("[WiFi] ATENCIÓN: No se ve el SSID objetivo en el escaneo. Probablemente es 5GHz o canal no soportado. Fuerza el hotspot a 2.4GHz (canal 1/6/11) y sin aislamiento de clientes.");
  } else {
    Serial.println("[WiFi] SSID objetivo detectado en el aire. Si no obtiene IP, revise DHCP/firewall del hotspot.");
  }
}

// WiFi event logging (ESP32 Arduino >=2.x)
void onWiFiEvent(WiFiEvent_t event, WiFiEventInfo_t info) {
  switch (event) {
    case ARDUINO_EVENT_WIFI_STA_START:
      Serial.println("[WiFi] STA start");
      break;
    case ARDUINO_EVENT_WIFI_STA_CONNECTED:
      Serial.println("[WiFi] Conectado al hotspot (ASSOCIATED)");
      break;
    case ARDUINO_EVENT_WIFI_STA_GOT_IP:
      Serial.printf("[WiFi] GOT_IP: %s\n", WiFi.localIP().toString().c_str());
      break;
    case ARDUINO_EVENT_WIFI_STA_DISCONNECTED:
      Serial.println("[WiFi] Desconectado del hotspot");
      break;
    default:
      break;
  }
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Conectando a MQTT...");
    String clientId = "ESP32Gateway-" + String(random(0xffff), HEX);
    if (client.connect(clientId.c_str())) {
      Serial.println("MQTT Conectado!");
      client.subscribe(MQTT_TOPIC_CONTROL);
      Serial.println("Suscrito a control");
    } else {
      Serial.printf("Fallo MQTT, rc=%d reintentando en 5s\n", client.state());
      delay(5000);
    }
  }
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String msg;
  for (int i = 0; i < length; i++) {
    msg += (char)payload[i];
  }
  Serial.printf("MQTT Control recibido: %s\n", msg.c_str());
  
  // Forward to mesh
  StaticJsonDocument<200> doc;
  DeserializationError err = deserializeJson(doc, msg);
  
  if (err == DeserializationError::Ok) {
    uint32_t to = doc["to"];
    if (to == 0) {
      mesh.sendBroadcast(msg);
      Serial.println("Enviado Broadcast a Mesh");
    } else {
      mesh.sendSingle(to, msg);
      Serial.printf("Enviado Unicast a %u\n", to);
    }
  } else {
    Serial.println("Error parseando JSON de control");
  }
}

void receivedCallback(uint32_t from, String &msg) {
  Serial.printf("Datos recibidos desde nodo %u: %s\n", from, msg.c_str());

  if (client.connected()) {
    String topic = String(MQTT_TOPIC) + "/" + String(from);
    if (client.publish(topic.c_str(), msg.c_str())) {
      Serial.println("Publicado en MQTT: " + msg);
    } else {
      Serial.println("Error al publicar en MQTT");
    }
  } else {
    Serial.println("MQTT desconectado - reintentando...");
  }
}

void changedConnectionCallback() {
  Serial.printf("Conexiones cambiadas. Nodos actuales: %d\n", mesh.getNodeList().size());
  
  auto nodes = mesh.getNodeList();
  if (nodes.size() > 0) {
    Serial.print("Nodos conectados: ");
    for (auto node : nodes) {
      Serial.printf("%u ", node);
    }
    Serial.println();
  } else {
    Serial.println("No hay nodos conectados al mesh");
  }
}

void newConnectionCallback(uint32_t nodeId) {
  Serial.printf("Nueva conexión mesh, nodeId = %u\n", nodeId);
  Serial.printf("Total nodos conectados: %d\n", mesh.getNodeList().size());
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("=== INICIANDO ESP32 GATEWAY ===");

  client.setServer(MQTT_SERVER, MQTT_PORT);
  client.setCallback(mqttCallback);

  mesh.setDebugMsgTypes(ERROR | STARTUP | CONNECTION);
  mesh.init(MESH_PREFIX, MESH_PASSWORD, &userScheduler, MESH_PORT);

  // Actuar como ROOT del mesh para permitir uso de estación WiFi
  mesh.setRoot(true);
  mesh.setContainsRoot(true);

  mesh.onReceive(&receivedCallback);
  mesh.onNewConnection(&newConnectionCallback);
  mesh.onChangedConnections(&changedConnectionCallback);  

  mesh.stationManual(WIFI_SSID, WIFI_PASSWORD);
  mesh.setHostname("ESP32-Gateway");
  // Registrar eventos de WiFi de la librería Arduino
  WiFi.onEvent(onWiFiEvent);
  // Recomendación: evitar ahorro de energía que puede retrasar la asociación
  WiFi.setSleep(false);
  
  Serial.printf("NODE ID: %u\n", mesh.getNodeId());
  Serial.println("Gateway configurado - Esperando conexiones mesh...");
}

void loop() {
  static unsigned long lastStatus = 0;
  mesh.update();
  
  // Solo intentar MQTT si hay conexión WiFi
  if(mesh.getStationIP() != IPAddress(0,0,0,0)) {
    if (!client.connected()) {
      reconnect();
    }
    client.loop();
  } else {
    // Si aún no hay IP, emitir diagnóstico periódico
    if (millis() - lastWifiRetry > 5000) {
      lastWifiRetry = millis();
      Serial.println("[WiFi] Aún sin IP (0.0.0.0). Verifique que el hotspot sea 2.4GHz y SSID/clave coincidan.");
    }
    if (millis() - lastWifiScan > 15000) {
      lastWifiScan = millis();
      scanAndReport();
    }
  }

  if (millis() - lastStatus > 30000) {
    lastStatus = millis();
    IPAddress ip = mesh.getStationIP();
    Serial.printf("Estado: IP=%s, Nodos=%d, MQTT=%s\n", 
                  ip.toString().c_str(), 
                  mesh.getNodeList().size(),
                  client.connected() ? "BIEN" : "MAL");
  }
  
  // Enviar IP del gateway cada 60 segundos via MQTT
  if (millis() - lastIPReport > 60000) {
    lastIPReport = millis();
    IPAddress ip = mesh.getStationIP();
    
    if (ip != IPAddress(0,0,0,0) && client.connected()) {
      StaticJsonDocument<200> doc;
      doc["nodeId"] = "gateway";
      doc["ip"] = ip.toString();
      doc["nodes"] = mesh.getNodeList().size();
      
      String payload;
      serializeJson(doc, payload);
      
      String topic = String(MQTT_TOPIC) + "/gateway";
      if (client.publish(topic.c_str(), payload.c_str())) {
        Serial.printf("[IP] IP enviada via MQTT: %s\n", ip.toString().c_str());
      }
    }
  }
}