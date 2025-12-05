#include <WiFi.h>

const char* SSID = "iPhone";
const char* PASS = "87654321";

IPAddress localIP(172,20,10,3);
IPAddress gateway(172,20,10,1);
IPAddress subnet(255,255,255,240);
IPAddress dns(172,20,10,1);

WiFiServer server(8080);

void setup() {
  Serial.begin(115200);
  delay(100);

  if (!WiFi.config(localIP, gateway, subnet, dns)) {
    Serial.println("⚠️ Static IP config failed, using DHCP");
  }
  WiFi.mode(WIFI_STA);
  WiFi.begin(SSID, PASS);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("✅ Connected! IP: ");
  Serial.println(WiFi.localIP());

  server.begin();
  Serial.println("📡 TCP server listening on port 8080");
}

void loop() {
  WiFiClient client = server.available();
  if (!client) return;

  Serial.println("🔗 Client connected");
  client.println("ESP32 READY");   // visible in your Python UI
  client.setTimeout(200);          // timeout for reads

  String line;
  unsigned long lastData = millis();

  while (client.connected()) {
    while (client.available()) {
      char c = client.read();
      if (c == '\r') continue;     // ignore CR
      if (c == '\n') {
        // complete line
        if (line.length()) {
          Serial.print("Received: ");
          Serial.println(line);
          client.println("ACK: " + line);   // echo back to UI
          line = "";
        } else {
          // empty line; ignore
        }
        lastData = millis();
      } else {
        line += c;
        lastData = millis();
      }
    }

    // Flush a partial line if no newline arrives for 2 seconds
    if (line.length() && (millis() - lastData > 2000)) {
      Serial.print("Received (no-\\n): ");
      Serial.println(line);
      client.println("ACK: " + line);
      line = "";
      lastData = millis();
    }
    // small idle delay
    delay(5);
  }

  // flush any remaining partial when client disconnects
  if (line.length()) {
    Serial.print("Received (at close): ");
    Serial.println(line);
  }

  Serial.println("❌ Client disconnected");
  client.stop();
}
