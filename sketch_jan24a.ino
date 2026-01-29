#include <WiFiManager.h>
#include <PubSubClient.h>
#include <ESPmDNS.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ArduinoJson.h>

// --- HARDWARE CONFIG ---
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

const int tdsPin  = 35; 
const int pumpPin = 2;

String pumpStatus = "OFF";
int sensorValue = 0;

// --- MQTT CONFIG ---
const char* mqtt_server   = "broker.hivemq.com";
const char* topic_status  = "vju/dung_luong/fish_tank/status";
const char* topic_command = "vju/dung_luong/fish_tank/command";

WiFiClient espClient;
PubSubClient client(espClient);

// --- TDS FILTER CONFIG ---
#define SCOUNT 30
int analogBuffer[SCOUNT];
int analogBufferIndex = 0;
int stableValue = 0;

// ---------- MEDIAN FILTER ----------
int getMedianNum(int bArray[], int iFilterLen) {
  int bTab[iFilterLen];
  for (int i = 0; i < iFilterLen; i++) bTab[i] = bArray[i];

  for (int j = 0; j < iFilterLen - 1; j++) {
    for (int i = 0; i < iFilterLen - j - 1; i++) {
      if (bTab[i] > bTab[i + 1]) {
        int temp = bTab[i];
        bTab[i] = bTab[i + 1];
        bTab[i + 1] = temp;
      }
    }
  }
  return bTab[iFilterLen / 2];
}

// ---------- SAFE ADC READ ----------
int readStableTDS() {
  analogBuffer[analogBufferIndex++] = analogRead(tdsPin);
  if (analogBufferIndex >= SCOUNT) analogBufferIndex = 0;

  int medianValue = getMedianNum(analogBuffer, SCOUNT);

  // Loại nhiễu cực đoan
  if (medianValue < 50 || medianValue > 4000) return stableValue;

  // EMA filter (làm mượt thêm)
  stableValue = stableValue * 0.7 + medianValue * 0.3;

  return stableValue;
}

// ---------- OLED ----------
void updateDisplay() {
  display.clearDisplay();
  display.setTextColor(WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("VJU SMART SYSTEM");
  display.drawLine(0, 10, 128, 10, WHITE);
  
  display.setTextSize(2);
  display.setCursor(0, 20);
  display.print("TDS: ");
  display.println(sensorValue);
  
  display.setTextSize(1);
  display.setCursor(0, 45);
  display.print("Pump: ");
  display.print(pumpStatus);

  display.setCursor(0, 55);
  display.print("IP: ");
  display.print(WiFi.localIP());

  display.display();
}

// ---------- MQTT CALLBACK ----------
void callback(char* topic, byte* payload, unsigned int length) {
  String message;
  for (int i = 0; i < length; i++) message += (char)payload[i];

  if (message == "PUMP_ON") {
    digitalWrite(pumpPin, HIGH);
    pumpStatus = "ON";
  } 
  else if (message == "PUMP_OFF") {
    digitalWrite(pumpPin, LOW);
    pumpStatus = "OFF";
  }
}

// ---------- MQTT RECONNECT ----------
void reconnect() {
  while (!client.connected()) {
    String clientId = "ESP32-Dung-" + String(random(0xffff), HEX);
    if (client.connect(clientId.c_str())) {
      client.subscribe(topic_command);
    } else {
      delay(3000);
    }
  }
}

// ---------- SETUP ----------
void setup() {
  Serial.begin(115200);

  pinMode(pumpPin, OUTPUT);
  digitalWrite(pumpPin, LOW);

  // OLED
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("OLED Fail");
  }

  // ADC CONFIG (RẤT QUAN TRỌNG)
  analogReadResolution(12);  
  analogSetPinAttenuation(tdsPin, ADC_11db);   // đo ổn định tới 3.3V

  // WIFI MANAGER
  WiFiManager wm;
  wm.autoConnect("Dung_FishTank_Setup");

  // MQTT
  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);

  // Khởi tạo buffer ADC
  for (int i = 0; i < SCOUNT; i++) {
    analogBuffer[i] = analogRead(tdsPin);
  }

  updateDisplay();
}

// ---------- LOOP (ADC & MQTT TÁCH RIÊNG) ----------
void loop() {
  if (!client.connected()) reconnect();
  client.loop();

  static unsigned long lastSample  = 0;
  static unsigned long lastPublish = 0;

  // ---- ĐO ADC RIÊNG (KHÔNG WIFI, KHÔNG PUBLISH) ----
  if (millis() - lastSample > 10) {   // mỗi 1 giây
    lastSample = millis();
    readStableTDS();   // chỉ đọc & lọc, không gửi
  }

  // ---- PUBLISH RIÊNG (KHÔNG ĐỌC ADC LÚC NÀY) ----
  if (millis() - lastPublish > 10) {  // mỗi 1 giây
    lastPublish = millis();

    sensorValue = stableValue;

    StaticJsonDocument<128> doc;
    doc["sensor_value"] = sensorValue;
    doc["pump_status"] = pumpStatus;

    char buffer[128];
    serializeJson(doc, buffer);

    client.publish(topic_status, buffer);

    updateDisplay();
  }
}
