#define BLYNK_PRINT Serial

// ======== BLYNK DEFINES (MUST BE FIRST) ========
#define BLYNK_TEMPLATE_ID   "TMPL6391zqRPz"
#define BLYNK_TEMPLATE_NAME "masss"
#define BLYNK_AUTH_TOKEN    "FphjdleehPPuBAJY24h6s2nDS9fDBdLG"

// ======== INCLUDES ========
#include <WiFi.h>
#include <WiFiManager.h>
#include <BlynkSimpleEsp32.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ================= HARDWARE =================
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64

#define SDA_PIN 21
#define SCL_PIN 22

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// ================= PINS =================
const int sensorPin = 34;   // RAW sensor input
const int relayK1   = 26;   // Pump (ACTIVE LOW)
const int relayK2   = 27;   // Feeder (ACTIVE LOW)
const int ledPin    = 2;

// ================= STATE =================
String pumpStatus   = "OFF";
String feederStatus = "READY";
int sensorValue     = 0;

// ================= OLED =================
void updateDisplay() {
  display.clearDisplay();
  display.setTextColor(WHITE);
  display.setTextSize(1);

  display.setCursor(0, 0);
  display.println("VJU SMART FISH TANK");
  display.drawLine(0, 10, 128, 10, WHITE);

  display.setCursor(0, 18);
  display.print("SENSOR: ");
  display.println(sensorValue);

  display.print("PUMP: ");
  display.println(pumpStatus);

  display.print("FEEDER: ");
  display.println(feederStatus);

  display.display();
}

// ================= BLYNK =================

// Pump ON/OFF (V0)
BLYNK_WRITE(V0) {
  int value = param.asInt();
  digitalWrite(relayK1, value ? LOW : HIGH);
  pumpStatus = value ? "ON" : "OFF";
  updateDisplay();
}

// Feeder HOLD (V1)
BLYNK_WRITE(V1) {
  int value = param.asInt();
  digitalWrite(relayK2, value ? LOW : HIGH);
  feederStatus = value ? "FEEDING" : "READY";
  updateDisplay();
}

// Sync buttons on reconnect
BLYNK_CONNECTED() {
  Blynk.syncVirtual(V0, V1);
}

// ================= SETUP =================
void setup() {
  Serial.begin(115200);

  pinMode(relayK1, OUTPUT);
  pinMode(relayK2, OUTPUT);
  pinMode(ledPin, OUTPUT);
  pinMode(sensorPin, INPUT);

  digitalWrite(relayK1, HIGH);
  digitalWrite(relayK2, HIGH);

  // ---- OLED ----
  Wire.begin(SDA_PIN, SCL_PIN);
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("OLED failed");
    while (true);
  }
  display.clearDisplay();
  display.display();

  // ---- ADC ----
  analogReadResolution(12);
  analogSetPinAttenuation(sensorPin, ADC_11db);

  // ---- WiFi ----
  WiFiManager wm;
  wm.autoConnect("VJU_FishTank");

  // ---- Blynk ----
  Blynk.config(BLYNK_AUTH_TOKEN);
  Blynk.connect();
}

// ================= LOOP =================
void loop() {
  Blynk.run();

  static unsigned long lastUI = 0;

  if (millis() - lastUI > 1000) {
    lastUI = millis();

    sensorValue = analogRead(sensorPin);

    Blynk.virtualWrite(V5, sensorValue);
    digitalWrite(ledPin, !digitalRead(ledPin));
    updateDisplay();
  }
}
