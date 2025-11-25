#include <painlessMesh.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

#define MESH_PREFIX "Mesh"
#define MESH_PASSWORD "12345678"
#define MESH_PORT 5555

#define WIFI_SSID "Doofenshmirtz M.A"
#define WIFI_PASSWORD "1023374689"
#define MQTT_SERVER "10.42.0.1"
#define MQTT_PORT 1883
#define MQTT_TOPIC "dht22/datos"

Scheduler userScheduler;
painlessMesh mesh;
WiFiClient espClient;
PubSubClient client(espClient);

unsigned long lastIPReport = 0;

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

void newConnectionCallback(uint32_t nodeId) {
  Serial.printf("Nueva conexión mesh, nodeId = %u\n", nodeId);
  Serial.printf("Total nodos conectados: %d\n", mesh.getNodeList().size());
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

void reconnect() {
  while (!client.connected()) {
    Serial.print("Conectando a MQTT...");
    String clientId = "ESP32Gateway-" + String(random(0xffff), HEX);
    if (client.connect(clientId.c_str())) {
      Serial.println("MQTT Conectado!");
    } else {
      Serial.printf("Fallo MQTT, rc=%d reintentando en 5s\n", client.state());
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("=== INICIANDO ESP32 GATEWAY ===");

  mesh.setDebugMsgTypes(ERROR | STARTUP | CONNECTION);
  mesh.init(MESH_PREFIX, MESH_PASSWORD, &userScheduler, MESH_PORT);

  Serial.printf("NODE ID: %u\n", mesh.getNodeId());
  
  mesh.onReceive(&receivedCallback);
  mesh.onNewConnection(&newConnectionCallback);
  mesh.onChangedConnections(&changedConnectionCallback);  

  mesh.stationManual(WIFI_SSID, WIFI_PASSWORD);
  mesh.setHostname("ESP32-Gateway");

  client.setServer(MQTT_SERVER, MQTT_PORT);
  
  Serial.println("Gateway configurado - Esperando conexiones mesh...");
}

void loop() {
  static unsigned long lastStatus = 0;
  mesh.update();
  
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
  
  // Solo intentar MQTT si hay conexión WiFi
  if(mesh.getStationIP() != IPAddress(0,0,0,0)) {
    if (!client.connected()) {
      reconnect();
    }
    client.loop();
  }
}