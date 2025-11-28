from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import re
import signal
import sys
import threading
import time
from typing import Any, Dict, Optional

import paho.mqtt.client as mqtt
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_BROKER = os.getenv("MQTT_BROKER", "localhost")
DEFAULT_PORT = int(os.getenv("MQTT_PORT", "1883"))
DEFAULT_TOPIC = os.getenv("MQTT_TOPIC", "Nodos/datos/+")
DEFAULT_SERVER_URL = os.getenv(
    "SERVER_URL", "https://proyecto-redes-5b146a15d8b6.herokuapp.com"
)
HTTP_TIMEOUT = 10  


logger = logging.getLogger("mqtt_bridge")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
)
logger.addHandler(handler)


class HTTPClient:
    """Small wrapper around requests.Session with retry/backoff configured."""

    def __init__(self, base_url: str, timeout: int = HTTP_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
      
        retries = Retry(
            total=3,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST", "PUT", "DELETE", "PATCH"]),
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def post(self, path: str, json_payload: Dict[str, Any]) -> Optional[requests.Response]:
        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        try:
            logger.debug("HTTP POST %s payload=%s", url, json_payload)
            resp = self.session.post(url, json=json_payload, timeout=self.timeout)
            return resp
        except requests.RequestException as exc:
            logger.warning("HTTP request to %s failed: %s", url, exc)
            return None


class MQTTBridge:
    """Main bridge class that manages MQTT connection, message processing, and HTTP forwarding."""

    CONTROL_TYPES = {"PONG", "TOPO", "TRACE_REPLY"}
    NODE_TOPIC_RE = re.compile(r"([^/]+)$") 

    def __init__(self, broker: str, port: int, topic: str, server_url: str):
        self.broker = broker
        self.port = port
        self.topic = topic
        self.server_url = server_url.rstrip("/")
        self._stop_event = threading.Event()

        self._http = HTTPClient(self.server_url)
        self._node_cache: Dict[str, Dict[str, Any]] = {}
        self._mqtt = mqtt.Client()
      
        self._mqtt.on_connect = self._on_connect
        self._mqtt.on_message = self._on_message
      
        self._work_q: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)

   
    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("Connected to MQTT broker %s:%d (rc=%s)", self.broker, self.port, rc)
            client.subscribe(self.topic)
            logger.info("Subscribed to topic pattern: %s", self.topic)
        else:
            logger.error("MQTT connection failed with rc=%s", rc)

    def _on_message(self, client, userdata, msg):
        payload = msg.payload.decode("utf-8", errors="replace")
        topic = msg.topic
        logger.debug("Received message on %s : %s", topic, payload)
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            logger.error("Failed to parse JSON from %s. Payload: %s", topic, payload)
            return

        node_id = self._extract_node_id(topic)
        envelope = {"topic": topic, "node_id": node_id, "data": parsed, "raw_payload": payload}
        
        try:
            self._work_q.put_nowait(envelope)
        except queue.Full:
            logger.error("Work queue full; dropping message from %s", node_id)

 
    def _worker_loop(self):
        while not self._stop_event.is_set():
            try:
                job = self._work_q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._process_envelope(job)
            except Exception as exc:
                logger.exception("Unexpected error processing message: %s", exc)
            finally:
                self._work_q.task_done()

    def _process_envelope(self, envelope: Dict[str, Any]):
        topic = envelope["topic"]
        node_id = envelope["node_id"]
        data = envelope["data"]

        logger.info("Processing message from node=%s topic=%s", node_id, topic)

        # Control messages
        if isinstance(data, dict) and "type" in data and data["type"] in self.CONTROL_TYPES:
            logger.info("Detected control message type=%s -> forwarding to control endpoint", data["type"])
            self._forward_control_message(data)
            return

     
        if node_id == "gateway" and isinstance(data, dict) and "ip" in data:
            logger.info("Gateway report received: ip=%s", data.get("ip"))
            self._handle_gateway_report(data)
            return

   
        self._update_cache_with_sensor_data(node_id, data)
        complete_payload = {"nodeId": node_id, "timestamp": int(time.time())}
        complete_payload.update(self._node_cache.get(node_id, {}))

        logger.info("Forwarding aggregated data to server: %s", complete_payload)
        resp = self._http.post(self.server_url, complete_payload)
        if resp is None:
            logger.warning("Failed to POST sensor data for node %s", node_id)
        else:
            if resp.status_code == 200:
                logger.info("Server accepted data for node %s", node_id)
            else:
                logger.warning("Server responded %s: %s", resp.status_code, resp.text)

    # ---------- Helpers ----------
    def _extract_node_id(self, topic: str) -> str:
        m = self.NODE_TOPIC_RE.search(topic)
        return m.group(1) if m else "unknown"

    def _forward_control_message(self, data: Dict[str, Any]):
        
        base = self.server_url.replace("/datos", "")
        endpoint = f"{base}/api/control_response"
        resp = self._http.post(endpoint, data)
        if resp is None:
            logger.warning("Failed to forward control message to %s", endpoint)
        else:
            logger.info("Control forward returned %s", resp.status_code)

    def _handle_gateway_report(self, data: Dict[str, Any]):
        payload = {
            "nodeId": "gateway",
            "ip": data.get("ip"),
            "nodes": data.get("nodes", 0),
            "timestamp": int(time.time()),
        }
        resp = self._http.post(self.server_url, payload)
        if resp is None:
            logger.warning("Failed to send gateway info to %s", self.server_url)
        else:
            logger.info("Gateway info POST status=%s", resp.status_code)

    def _update_cache_with_sensor_data(self, node_id: str, data: Dict[str, Any]):
        if node_id not in self._node_cache:
            self._node_cache[node_id] = {}

        cache = self._node_cache[node_id]

        
        if "temperature" in data or "temperatura" in data:
            cache["temperatura"] = data.get("temperature") or data.get("temperatura")
            logger.debug("Node %s - temperatura=%s", node_id, cache["temperatura"])

        
        if "humidity" in data or "humedad" in data:
            cache["humedad"] = data.get("humidity") or data.get("humedad")
            logger.debug("Node %s - humedad=%s", node_id, cache["humedad"])

       
        if "light" in data:
            cache["luz"] = data["light"]
            logger.debug("Node %s - luz=%s", node_id, data["light"])

        
        if "percentage" in data and "light" in data:
            cache["luz_porcentaje"] = data["percentage"]
            logger.debug("Node %s - luz_porcentaje=%s", node_id, data["percentage"])

        
        if "soil_moisture" in data or "humedad_suelo" in data:
            cache["soil_moisture"] = data.get("soil_moisture") or data.get("humedad_suelo")
            logger.debug("Node %s - soil_moisture=%s", node_id, cache["soil_moisture"])

        
        if "lat" in data and "lon" in data:
            cache["lat"] = data["lat"]
            cache["lon"] = data["lon"]
            logger.debug("Node %s - gps=%s,%s", node_id, cache["lat"], cache["lon"])

   
    def start(self):
        logger.info("Starting bridge (broker=%s:%d topic=%s server=%s)", self.broker, self.port, self.topic, self.server_url)
        self._worker_thread.start()
        try:
            self._mqtt.connect(self.broker, self.port, keepalive=60)
        except Exception as exc:
            logger.exception("Could not connect to MQTT broker: %s", exc)
            raise
        self._mqtt.loop_start()

    def stop(self):
        logger.info("Stopping bridge...")
        self._stop_event.set()
        
        try:
            self._mqtt.loop_stop()
            self._mqtt.disconnect()
        except Exception:
            logger.debug("MQTT disconnect had an error (ignored).", exc_info=True)
       
        self._worker_thread.join(timeout=2.0)
        logger.info("Bridge stopped.")


def _install_signal_handlers(bridge: MQTTBridge):
    def _handler(signum, frame):
        logger.info("Signal %s received: shutting down...", signum)
        bridge.stop()

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


def parse_args():
    p = argparse.ArgumentParser(description="MQTT -> HTTP Bridge (refactored)")
    p.add_argument("--broker", default=DEFAULT_BROKER, help="MQTT broker address")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help="MQTT broker port")
    p.add_argument("--topic", default=DEFAULT_TOPIC, help="MQTT topic pattern to subscribe to")
    p.add_argument("--server", default=DEFAULT_SERVER_URL, help="HTTP server base URL")
    p.add_argument("--debug", action="store_true", help="Enable debug logging")
    return p.parse_args()


def main():
    args = parse_args()
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")

    bridge = MQTTBridge(broker=args.broker, port=args.port, topic=args.topic, server_url=args.server)
    _install_signal_handlers(bridge)

    try:
        bridge.start()
       
        while not bridge._stop_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received; stopping.")
        bridge.stop()
    except Exception:
        logger.exception("Unhandled exception in main loop.")
        bridge.stop()


if __name__ == "__main__":
    main()
