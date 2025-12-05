#include <WiFi.h>

const char* SSID = "iPhone";
const char* PASS = "87654321";

IPAddress localIP(172,20,10,13);
IPAddress gateway(172,20,10,1);
IPAddress subnet(255,255,255,240);
IPAddress dns(172,20,10,1);

WiFiServer server(8080);

void setup() {
  Serial.begin(115200);
  delay(100);

  WiFi.config(localIP, gateway, subnet, dns);
  WiFi.begin(SSID, PASS);

  Serial.print("Connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }

  Serial.println();
  Serial.print("Connected. IP: ");
  Serial.println(WiFi.localIP());

  server.begin();
  Serial.println("Server started");
}

void loop() {
  WiFiClient client = server.available();

  if (client) {
    Serial.println("Client connected");

    while (client.connected()) {
      if (client.available()) {
        String msg = client.readStringUntil('\n');  // read until newline or timeout
        msg.trim();
        if (msg.length() > 0) {
          Serial.print("Received: ");
          Serial.println(msg);

          // echo back
          client.println("ESP32: " + msg);
        }
      }
    }

    Serial.println("Client disconnected");
    client.stop();
  }
}
