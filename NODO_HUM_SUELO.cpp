#include <painlessMesh.h>
#include <ArduinoJson.h>
#include <TinyGPS++.h>

#define MESH_PREFIX "RED_Nodos"
#define MESH_PASSWORD "RED_Nodos_1023374689"
#define MESH_PORT 5555

#define SOIL_PIN 34  
#define GPS_BAUDRATE 9600

// Calibración del sensor (ajusta según tu sensor)
#define SOIL_DRY 3200    // Valor en aire (seco)
#define SOIL_WET 1200    // Valor en agua (húmedo)

Scheduler userScheduler;
painlessMesh mesh;
TinyGPSPlus gps;
HardwareSerial gpsSerial(2);  // Serial2 para GPS

Task taskSendData(TASK_SECOND * 10, TASK_FOREVER, []() {
  int rawValue = analogRead(SOIL_PIN);
  
  // Invertir la escala (valores más altos = más seco)
  // Mapear a porcentaje 0-100% (0% = seco, 100% = húmedo)
  int percentage = map(rawValue, SOIL_DRY, SOIL_WET, 0, 100);
  
  // Limitar entre 0-100%
  percentage = constrain(percentage, 0, 100);

  // Construir JSON con humedad + GPS
  #include <ArduinoJson.h>
#include <TinyGPS++.h>
#include <painlessMesh.h>

#define MESH_PREFIX "RED_Nodos"
#define MESH_PASSWORD "Horus9876"
#define MESH_PORT 5555

#define SOIL_PIN 34
#define GPS_BAUDRATE 9600

Scheduler userScheduler;
painlessMesh mesh;
TinyGPSPlus gps;
HardwareSerial gpsSerial(2);  // Serial2 para GPS

void newConnectionCallback(uint32_t nodeId) {
  Serial.printf("Nueva conexión: %u\n", nodeId);
}

void changedConnectionCallback() {
  Serial.printf("Conexiones: %d nodos\n", mesh.getNodeList().size());
}

void receivedCallback(uint32_t from, String &msg) {
  // Debug crudo de mensaje recibido
  Serial.printf("[RX] de %u: %s\n", from, msg.c_str());
  
  // Intentar parsear como JSON de control
  StaticJsonDocument<512> doc;
  DeserializationError err = deserializeJson(doc, msg);
  
  if (err == DeserializationError::Ok) {
    const char* type = doc["type"];
    if (type) {
      // PING: responder con PONG si dirigido a este nodo
      if (strcmp(type, "PING") == 0) {
        uint32_t to = doc["to"].as<uint32_t>();
        uint32_t seq = doc["seq"].as<uint32_t>();
        uint32_t requester = doc["from"].as<uint32_t>();
        uint32_t myId = mesh.getNodeId();
        
        if (to == myId) {
          StaticJsonDocument<128> pong;
          pong["type"] = "PONG";
          pong["seq"] = seq;
          pong["from"] = myId;
          String out;
          serializeJson(pong, out);
          mesh.sendSingle(requester, out);
          Serial.printf("[PING] seq=%u de %u -> PONG enviado\n", seq, requester);
        }
        return;
      }
      
      // TOPO_REQ: responder con lista de vecinos
      else if (strcmp(type, "TOPO_REQ") == 0) {
        uint32_t requester = doc["from"].as<uint32_t>();
        auto list = mesh.getNodeList();
        StaticJsonDocument<256> topo;
        topo["type"] = "TOPO";
        JsonArray arr = topo.createNestedArray("neighbors");
        for (auto id : list) arr.add(id);
        String out;
        serializeJson(topo, out);
        mesh.sendSingle(requester, out);
        Serial.printf("[TOPO_REQ] de %u -> TOPO enviado (%d vecinos)\n", requester, list.size());
        return;
      }
      
      // PONG: normalmente el nodo no inicia pings, solo log
      else if (strcmp(type, "PONG") == 0) {
        uint32_t seq = doc["seq"].as<uint32_t>();
        Serial.printf("[PONG] Recibido seq=%u desde %u\n", seq, from);
        return;
      }
      
      // TRACE: agregar mi ID a la ruta y responder o reenviar
      else if (strcmp(type, "TRACE") == 0) {
        uint32_t to = doc["to"].as<uint32_t>();
        uint32_t seq = doc["seq"].as<uint32_t>();
        uint32_t originator = doc["from"].as<uint32_t>();
        uint32_t myId = mesh.getNodeId();
        
        // Agregar mi ID al array de hops
        JsonArray hops = doc["hops"].as<JsonArray>();
        hops.add(myId);
        
        if (to == myId) {
          // Soy el destino: responder con TRACE_REPLY
          StaticJsonDocument<384> reply;
          reply["type"] = "TRACE_REPLY";
          reply["seq"] = seq;
          reply["from"] = myId;
          JsonArray replyHops = reply.createNestedArray("hops");
          for(uint32_t hop : hops) replyHops.add(hop);
          String out;
          serializeJson(reply, out);
          mesh.sendSingle(originator, out);
          Serial.printf("[TRACE] Destino alcanzado seq=%u, TRACE_REPLY enviado a %u\n", seq, originator);
        } else {
          // Soy intermediario: reenviar con mi hop agregado
          String out;
          serializeJson(doc, out);
          mesh.sendSingle(to, out);
          Serial.printf("[TRACE] Reenviado seq=%u hacia %u (saltos=%d)\n", seq, to, hops.size());
        }
        return;
      }
    }
  }
  
  // Mensaje normal (datos de sensor u otro tipo)
  Serial.printf("[INFO] Mensaje no de control: %s\n", msg.c_str());
}

Task taskSendData(TASK_SECOND * 10, TASK_FOREVER, []() {
  int rawValue = analogRead(SOIL_PIN);
  float soilMoisture = map(rawValue, 4095, 0, 0, 100);

  StaticJsonDocument<192> doc;
  doc["soil_moisture"] = soilMoisture;
  if (gps.location.isValid()) {
    doc["lat"] = gps.location.lat();
    doc["lon"] = gps.location.lng();
    Serial.printf("[GPS] OK - Sat: %d\n", gps.satellites.value());
  } else {
    doc["lat"] = "no data";
    doc["lon"] = "no data";
    Serial.printf("[GPS] Sin fix - Sat: %d, Chars: %d\n", gps.satellites.value(), gps.charsProcessed());
  }
  String payload;
  serializeJson(doc, payload);
  mesh.sendBroadcast(payload);
  Serial.printf("[TX] HUMEDAD_SUELO -> %s\n", payload.c_str());
  Serial.printf("[MESH] Nodos conectados: %d\n", mesh.getNodeList().size());
});

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("=== INICIANDO NODO HUMEDAD SUELO + GPS ===");
  
  pinMode(SOIL_PIN, INPUT);
  Serial.println("Sensor Humedad Suelo configurado");
  
  // Inicializar GPS
  gpsSerial.begin(GPS_BAUDRATE, SERIAL_8N1, 16, 17);

  mesh.setDebugMsgTypes(ERROR | STARTUP | CONNECTION);
  mesh.init(MESH_PREFIX, MESH_PASSWORD, &userScheduler, MESH_PORT);
  
  mesh.onReceive(&receivedCallback);
  mesh.onNewConnection(&newConnectionCallback);
  mesh.onChangedConnections(&changedConnectionCallback);

  Serial.printf("NODE ID: %u\n", mesh.getNodeId());

  userScheduler.addTask(taskSendData);
  taskSendData.enable();
  
  Serial.println("Mesh configurado - Enviando datos cada 10s");
}

void loop() {
  mesh.update();
  userScheduler.execute();
  
  // Leer datos del GPS continuamente
  while (gpsSerial.available() > 0) {
    gps.encode(gpsSerial.read());
  }
}
  
  // Agregar coordenadas GPS
  if (gps.location.isValid()) {
    msg += ",\"lat\":" + String(gps.location.lat(), 6);
    msg += ",\"lon\":" + String(gps.location.lng(), 6);
    Serial.printf("GPS OK - Sat: %d\n", gps.satellites.value());
  } else {
    msg += ",\"lat\":\"no data\"";
    msg += ",\"lon\":\"no data\"";
    Serial.printf("GPS sin fix - Sat: %d, Chars: %d\n", 
                  gps.satellites.value(), gps.charsProcessed());
  }
  
  msg += "}";
  
  mesh.sendBroadcast(msg);
  Serial.println("Enviado: " + msg);
    Serial.printf("Nodos conectados: %d\n", mesh.getNodeList().size());
});

void receivedCallback(uint32_t from, String &msg) {
  // Debug crudo de mensaje recibido
  Serial.printf("[RX] de %u: %s\n", from, msg.c_str());
  
  // Intentar parsear como JSON de control
  StaticJsonDocument<512> doc;
  DeserializationError err = deserializeJson(doc, msg);
  
  Serial.printf("[DEBUG] DeserializationError: %s\n", err.c_str());
  
  if (err == DeserializationError::Ok) {
    const char* type = doc["type"];
    Serial.printf("[DEBUG] type extraído: %s (null=%d)\n", type ? type : "NULL", type == nullptr);
    if (type) {
      // PING: responder con PONG si dirigido a este nodo
      if (strcmp(type, "PING") == 0) {
        uint32_t to = doc["to"].as<uint32_t>();
        uint32_t seq = doc["seq"].as<uint32_t>();
        uint32_t requester = doc["from"].as<uint32_t>();
        uint32_t myId = mesh.getNodeId();
        
        if (to == myId) {
          StaticJsonDocument<128> pong;
          pong["type"] = "PONG";
          pong["seq"] = seq;
          pong["from"] = myId;
          String out;
          serializeJson(pong, out);
          mesh.sendSingle(requester, out);
          Serial.printf("[PING] seq=%u de %u -> PONG enviado: %s\n", seq, requester, out.c_str());
        } else {
          Serial.printf("[PING] dirigido a %u, yo soy %u. Ignorado.\n", to, myId);
        }
        return;
      }
      
      // TOPO_REQ: responder con lista de vecinos
      else if (strcmp(type, "TOPO_REQ") == 0) {
        uint32_t requester = doc["from"].as<uint32_t>();
        auto list = mesh.getNodeList();
        StaticJsonDocument<256> topo;
        topo["type"] = "TOPO";
        JsonArray arr = topo.createNestedArray("neighbors");
        for (auto id : list) arr.add(id);
        String out;
        serializeJson(topo, out);
        mesh.sendSingle(requester, out);
        Serial.printf("[TOPO_REQ] de %u -> TOPO enviado (%d vecinos)\n", requester, list.size());
        return;
      }
      
      // PONG: normalmente el nodo no inicia pings, solo log
      else if (strcmp(type, "PONG") == 0) {
        uint32_t seq = doc["seq"].as<uint32_t>();
        Serial.printf("[PONG] Recibido seq=%u desde %u\n", seq, from);
        return;
      }
      
      // TRACE: agregar mi ID a la ruta y responder o reenviar
      else if (strcmp(type, "TRACE") == 0) {
        uint32_t to = doc["to"].as<uint32_t>();
        uint32_t seq = doc["seq"].as<uint32_t>();
        uint32_t originator = doc["from"].as<uint32_t>();
        uint32_t myId = mesh.getNodeId();
        
        // Agregar mi ID al array de hops
        JsonArray hops = doc["hops"].as<JsonArray>();
        hops.add(myId);
        
        if (to == myId) {
          // Soy el destino: responder con TRACE_REPLY
          StaticJsonDocument<384> reply;
          reply["type"] = "TRACE_REPLY";
          reply["seq"] = seq;
          reply["from"] = myId;
          JsonArray replyHops = reply.createNestedArray("hops");
          for(uint32_t hop : hops) replyHops.add(hop);
          String out;
          serializeJson(reply, out);
          mesh.sendSingle(originator, out);
          Serial.printf("[TRACE] Destino alcanzado seq=%u, TRACE_REPLY enviado a %u\n", seq, originator);
        } else {
          // Soy intermediario: reenviar con mi hop agregado
          String out;
          serializeJson(doc, out);
          mesh.sendSingle(to, out);
          Serial.printf("[TRACE] Reenviado seq=%u hacia %u (saltos=%d)\n", seq, to, hops.size());
        }
        return;
      }
    }
  }
  
  // Mensaje normal (datos de sensor u otro tipo)
  Serial.printf("[INFO] Mensaje no de control: %s\n", msg.c_str());
}

void newConnectionCallback(uint32_t nodeId) {
  Serial.printf("Nueva conexión: %u\n", nodeId);
}

void changedConnectionCallback() {
  Serial.printf("Conexiones: %d nodos\n", mesh.getNodeList().size());
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=== INICIANDO NODO HUMEDAD DE SUELO (SEN0193) + GPS ===");
  
  // Inicializar GPS
  gpsSerial.begin(GPS_BAUDRATE, SERIAL_8N1, 16, 17);
  
  pinMode(SOIL_PIN, INPUT);
  analogSetAttenuation(ADC_11db);  // Rango completo 0-3.3V
    
  mesh.setDebugMsgTypes(ERROR | STARTUP | CONNECTION);
  mesh.init(MESH_PREFIX, MESH_PASSWORD, &userScheduler, MESH_PORT);
  
  Serial.printf("NODE ID: %u\n", mesh.getNodeId());
  
  mesh.onReceive(&receivedCallback);
  mesh.onNewConnection(&newConnectionCallback);
  mesh.onChangedConnections(&changedConnectionCallback);

  userScheduler.addTask(taskSendData);
  taskSendData.enable();
  
  Serial.printf("NODE ID: %u\n", mesh.getNodeId());
}

void loop() {
  // Leer datos del GPS continuamente
  while (gpsSerial.available() > 0) {
    gps.encode(gpsSerial.read());
  }
  
  mesh.update();
  userScheduler.execute();
}