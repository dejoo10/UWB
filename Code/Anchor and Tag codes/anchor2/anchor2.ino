// ------------------ ANCHOR 1 ------------------
#include <SPI.h>
#include <DW1000Ranging.h>
#include <DW1000.h>

#define SPI_SCK   18
#define SPI_MISO  19
#define SPI_MOSI  23
#define DW_CS      4
#define PIN_RST   27
#define PIN_IRQ   34

// Unique EUI for this anchor
const char ANCHOR_EUI[] = "82:17:5B:D5:A9:9A:E2:9C";

// Prefer accuracy profile (64 MHz PRF, longer preamble)
const byte* UWB_MODE = DW1000.MODE_LONGDATA_RANGE_ACCURACY;

// Each board needs its own antenna delay (tune!)
static const uint16_t ANTENNA_DELAY_A1 = 16436; // <- adjust after calibration

// Stagger reply time (different from A2)
static const uint16_t REPLY_TIME_US = 2800;

void onRange() {
  DW1000Device* dev = DW1000Ranging.getDistantDevice();
  if (!dev) return;
  Serial.print("[A1] RANGE to 0x");
  Serial.print(dev->getShortAddress(), HEX);
  Serial.print(" = ");
  Serial.print(dev->getRange(), 3);
  Serial.println(" m");
}

void onNew(DW1000Device* d){ Serial.print("[A1] New 0x"); Serial.println(d->getShortAddress(),HEX); }
void onInactive(DW1000Device* d){ Serial.print("[A1] Inactive 0x"); Serial.println(d->getShortAddress(),HEX); }

void setup() {
  Serial.begin(115200);
  delay(100);

  SPI.begin(SPI_SCK, SPI_MISO, SPI_MOSI);
  DW1000Ranging.initCommunication(PIN_RST, DW_CS, PIN_IRQ);

  // Per-device antenna delay
  DW1000.setAntennaDelay(ANTENNA_DELAY_A1);

  // Unique reply spacing to avoid collisions
  DW1000Ranging.setReplyTime(REPLY_TIME_US);

  DW1000Ranging.attachNewRange(onRange);
  DW1000Ranging.attachNewDevice(onNew);
  DW1000Ranging.attachInactiveDevice(onInactive);

  DW1000Ranging.startAsAnchor((char*)ANCHOR_EUI, (byte*)UWB_MODE, false);

  Serial.println("### ANCHOR 1 READY (accuracy mode) ###");
}

void loop() { DW1000Ranging.loop(); }
