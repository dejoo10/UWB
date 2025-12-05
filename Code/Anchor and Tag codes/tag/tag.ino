// ---------------------- TAG ----------------------
#include <SPI.h>
#include <WiFi.h>
#include <DW1000Ranging.h>
#include <DW1000.h>

// ---------- Wi-Fi / TCP ----------
#define WIFI_SSID "iPhone"
#define WIFI_PASS "87654321"
const char*   SERVER_IP    = "172.20.10.3";
const uint16_t SERVER_PORT = 8080;
// ---------------------------------

// --------- DW1000 pins -----------
#define SPI_SCK   18
#define SPI_MISO  19
#define SPI_MOSI  23
#define DW_CS      4
#define PIN_RST   27
#define PIN_IRQ   34
// ---------------------------------

// Tag EUI (unique)
char TAG_EUI[] = "DE:CA:F2:11:22:33:44:55";

// Higher-accuracy UWB profile
const byte* UWB_MODE = DW1000.MODE_LONGDATA_RANGE_ACCURACY;

// Per-board antenna delay for THIS TAG (tune!)
static const uint16_t ANTENNA_DELAY_TAG = 16436; // <- adjust during calibration

WiFiClient client;
unsigned long lastConnTry = 0;

// Keep latest link metrics per anchor
struct Link {
  uint16_t shortAddr;
  float    range_raw;   // from DW1000Ranging
  float    range_corr;  // after bias correction
  int      rssi;
  int      fpPower;
  uint8_t  quality;
  unsigned long updatedMs;
};
#define MAX_LINKS 8
Link links[MAX_LINKS];
size_t linkCount = 0;

// ------------- Per-anchor bias table (meters) -------------
// Set after your 1.00 m calibration for each anchor short address.
// Example: if raw=1.23 m @ 1.00 m, bias = 1.00 - 1.23 = -0.23f
// Fill these with YOUR measured values.
static float BIAS_A1 = 0.00f; // shortAddr 0x1781 -> set after calibration
static float BIAS_A2 = 0.00f; // shortAddr 0x1782 -> set after calibration

static float rangeBiasFor(uint16_t sa) {
  switch (sa) {
    case 0x1781: return BIAS_A1; // Anchor 1 short address
    case 0x1782: return BIAS_A2; // Anchor 2 short address
    default:     return 0.00f;
  }
}
// ----------------------------------------------------------

int findLink(uint16_t sa){
  for(size_t i=0;i<linkCount;++i) if(links[i].shortAddr==sa) return (int)i;
  return -1;
}
void upsertLink(uint16_t sa,float r_raw,int rssi,int fp,uint8_t q){
  int idx=findLink(sa);
  if(idx<0){
    if(linkCount<MAX_LINKS){ idx=(int)linkCount++; links[idx].shortAddr=sa; }
    else { // replace oldest
      unsigned long old=links[0].updatedMs; int oi=0;
      for(size_t i=1;i<linkCount;++i) if(links[i].updatedMs<old){old=links[i].updatedMs; oi=(int)i;}
      idx=oi; links[idx].shortAddr=sa;
    }
  }
  links[idx].range_raw  = r_raw;
  float bias            = rangeBiasFor(sa);
  links[idx].range_corr = max(0.0f, r_raw + bias);
  links[idx].rssi       = rssi;
  links[idx].fpPower    = fp;
  links[idx].quality    = q;
  links[idx].updatedMs  = millis();
}

void connectWiFi(){
  if(WiFi.status()==WL_CONNECTED) return;
  Serial.print("Wi-Fi connecting to "); Serial.println(WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  WiFi.setSleep(false);
  unsigned long start=millis();
  while(WiFi.status()!=WL_CONNECTED && millis()-start<15000){ delay(250); Serial.print("."); }
  Serial.println();
  if(WiFi.status()==WL_CONNECTED){ Serial.print("Wi-Fi OK: "); Serial.println(WiFi.localIP()); }
  else { Serial.println("Wi-Fi FAILED"); }
}

void connectServer(){
  if(client.connected()) return;
  unsigned long now=millis();
  if(now-lastConnTry<2000) return;
  lastConnTry=now;
  Serial.printf("Connecting to %s:%u\n", SERVER_IP, SERVER_PORT);
  client.stop();
  if(client.connect(SERVER_IP, SERVER_PORT)) Serial.println("Server connected");
  else Serial.println("Server connect failed");
}

// ---------- DW1000 callbacks ----------
void newRange(){
  DW1000Device* dev = DW1000Ranging.getDistantDevice();
  if(!dev) return;
  uint16_t sa = dev->getShortAddress();
  float r     = dev->getRange();        // meters (raw)
  int rssi    = (int)dev->getRXPower();
  int fp      = (int)dev->getFPPower();
  uint8_t q   = dev->getQuality();

  upsertLink(sa, r, rssi, fp, q);

  Serial.print("RANGE 0x"); Serial.print(sa, HEX);
  Serial.print(" raw=");    Serial.print(r, 3);
  Serial.print(" corr=");   Serial.print(max(0.0f, r + rangeBiasFor(sa)), 3);
  Serial.print("  RSSI=");  Serial.print(rssi);
  Serial.print("  FP=");    Serial.print(fp);
  Serial.print("  Q=");     Serial.println(q);
}
void newDevice(DW1000Device* d){ Serial.print("New device 0x"); Serial.println(d->getShortAddress(),HEX); }
void inactiveDevice(DW1000Device* d){ Serial.print("Inactive 0x"); Serial.println(d->getShortAddress(),HEX); }

// -------------- setup/loop --------------
unsigned long lastSend=0;

void setup(){
  Serial.begin(115200);
  delay(100);

  connectWiFi();

  SPI.begin(SPI_SCK, SPI_MISO, SPI_MOSI);
  DW1000Ranging.initCommunication(PIN_RST, DW_CS, PIN_IRQ);

  // Per-device antenna delay for tag
  DW1000.setAntennaDelay(ANTENNA_DELAY_TAG);

  DW1000Ranging.attachNewRange(newRange);
  DW1000Ranging.attachNewDevice(newDevice);
  DW1000Ranging.attachInactiveDevice(inactiveDevice);

  // Tag in discovery mode; anchors’ reply times prevent collisions
  DW1000Ranging.startAsTag((char*)TAG_EUI, (byte*)UWB_MODE, true);

  connectServer();

  Serial.println("### TAG READY (accuracy mode) ###");
  Serial.println("Tip: calibrate BIAS_A1 / BIAS_A2 and ANTENNA_DELAY_* for best accuracy.");
}

void loop(){
  DW1000Ranging.loop();
  connectWiFi();
  connectServer();

  // Stream JSON every ~500 ms (includes corrected distances)
  unsigned long now = millis();
  if(now - lastSend >= 500){
    lastSend = now;
    if(client.connected()){
      client.print("{\"links\":[");
      bool first=true;
      for(size_t i=0;i<linkCount;++i){
        if(now - links[i].updatedMs > 2000) continue;
        if(!first) client.print(",");
        first=false;
        client.print("{\"aid\":\"0x");
        char buf[6]; sprintf(buf, "%04X", links[i].shortAddr);
        client.print(buf);
        client.print("\",\"range\":");      client.print(links[i].range_corr,3);   // corrected
        client.print(",\"raw\":");          client.print(links[i].range_raw,3);    // raw for debugging
        client.print(",\"rssi\":");         client.print(links[i].rssi);
        client.print(",\"fpPower\":");      client.print(links[i].fpPower);
        client.print(",\"quality\":");      client.print(links[i].quality);
        client.print("}");
      }
      client.print("]}\n");
      client.flush();
    }
  }
}
