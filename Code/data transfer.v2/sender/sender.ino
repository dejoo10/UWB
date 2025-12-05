#include <WiFi.h>

const char* SSID = "iPhone";
const char* PASS = "87654321";

const char* SERVER_IP = "172.20.10.13";
const uint16_t SERVER_PORT = 8080;

WiFiClient client;

// --- simple line editor state ---
String inputLine;
bool showedPrompt = false;

void printPrompt() {
  Serial.println();
  Serial.println("Type message and press ENTER (or /quit):");
  Serial.print("> ");
  showedPrompt = true;
}

void handleSerialInputAndSend() {
  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c == '\r') {
      // ignore CR (Serial Monitor may send CRLF)
      continue;
    }

    if (c == '\n') {
      Serial.println(); // move to next line in the console
      String msg = inputLine;
      inputLine = "";

      if (msg.length() == 0) {
        // empty line, just re-prompt
        printPrompt();
        return;
      }

      if (msg == "/quit") {
        Serial.println("Closing connection by request.");
        client.stop();
        printPrompt();
        return;
      }

      if (!client.connected()) {
        Serial.println("⚠️ Not connected to server; message not sent.");
      } else {
        client.println(msg);
        Serial.print("📤 Sent: ");
        Serial.println(msg);
      }

      printPrompt();
      return;
    }

    // handle backspace / delete
    if (c == 8 || c == 127) {
      if (inputLine.length() > 0) {
        inputLine.remove(inputLine.length() - 1);
        Serial.print("\b \b"); // erase last char on console
      }
      continue;
    }

    // regular printable char
    inputLine += c;
    Serial.print(c);
  }
}

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(SSID, PASS);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("✅ Connected! My IP: ");
  Serial.println(WiFi.localIP());
}

bool connectServer() {
  Serial.print("Connecting to server ");
  Serial.print(SERVER_IP);
  Serial.print(":");
  Serial.println(SERVER_PORT);
  if (client.connect(SERVER_IP, SERVER_PORT)) {
    Serial.println("🔗 Connected to server!");
    return true;
  } else {
    Serial.println("❌ Connection failed!");
    return false;
  }
}

void setup() {
  Serial.begin(115200);
  delay(100);
  connectWifi();
  connectServer();
  printPrompt();

  // Optional: don’t block if server drops; set a short timeout for reads
  client.setTimeout(50);
}

void loop() {
  // keep Wi-Fi alive
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("⚠️ WiFi dropped. Reconnecting...");
    connectWifi();
    // after Wi-Fi comes back, we’ll try the server below
  }

  // keep TCP alive
  if (!client.connected()) {
    static unsigned long lastAttempt = 0;
    if (millis() - lastAttempt > 2000) {
      Serial.println("⚠️ Server disconnected. Reconnecting...");
      connectServer();
      lastAttempt = millis();
    }
  }

  // show prompt again after reconnect
  if (!showedPrompt) {
    printPrompt();
  }

  // read from Serial and send to server on newline
  handleSerialInputAndSend();

  // (optional) read any server replies and print them
  if (client.connected() && client.available()) {
    String line = client.readStringUntil('\n');
    if (line.length()) {
      Serial.print("📩 Server: ");
      Serial.println(line);
    }
  }
}
