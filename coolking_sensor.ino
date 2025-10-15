/*
 * Coolking Temperature Monitor - ESP32 Multi-Sensor Client
 * Connects to Taj InnerCircle WiFi and sends multiple DS18B20 sensor data to coolkingengineering.in
 *
 * Hardware Requirements:
 * - ESP32 Development Board
 * - Multiple DS18B20 Temperature Sensors (up to 10 supported)
 * - 4.7k Ohm Pull-up Resistor
 * - OLED Display (128x64, I2C)
 *
 * Wiring:
 * DS18B20 VCC -> ESP32 3.3V
 * DS18B20 GND -> ESP32 GND
 * DS18B20 Data -> ESP32 GPIO 4 (with 4.7k pull-up to 3.3V)
 * OLED VCC -> ESP32 3.3V
 * OLED GND -> ESP32 GND
 * OLED SDA -> ESP32 GPIO 21
 * OLED SCL -> ESP32 GPIO 22
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <time.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Preferences.h>

// WiFi Configuration
const char* ssid = "Taj InnerCircle";
const char* password = "";  // Empty password as specified

// Server Configuration
const char* serverURL = "https://coolkingengineering.in/api/data";
// API Key bypassed for testing
// const char* apiKey = "YOUR_ESP32_API_KEY_HERE";  // Commented out for testing

// Hardware Configuration
#define ONE_WIRE_BUS 4           // GPIO pin for DS18B20 data line
#define TEMPERATURE_PRECISION 12  // DS18B20 precision (9-12 bits)
#define MAX_SENSORS 10           // Maximum number of DS18B20 sensors supported
#define OLED_WIDTH 128           // OLED display width in pixels
#define OLED_HEIGHT 64           // OLED display height in pixels
#define OLED_RESET -1            // Reset pin (or -1 if sharing Arduino reset pin)

// Timing Configuration
const unsigned long READING_INTERVAL = 1000;     // 1 second between readings
const unsigned long SEND_INTERVAL = 300000;      // 5 minutes (300,000 ms)
const unsigned long DISPLAY_UPDATE_INTERVAL = 2000; // 2 seconds between display updates
const unsigned long BOOTLOOP_RESET_TIME = 120000;   // 2 minutes before considering bootloop
const int READINGS_PER_BATCH = 5;                // Number of readings to collect

// OneWire and Dallas Temperature setup
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

// OLED Display setup
Adafruit_SSD1306 display(OLED_WIDTH, OLED_HEIGHT, &Wire, OLED_RESET);

// Preferences for storing boot count and error recovery
Preferences preferences;

// Sensor Management
struct SensorInfo {
  String address;
  String name;
  float currentTemp;
  bool isConnected;
  int errorCount;
  float readings[READINGS_PER_BATCH];
};

SensorInfo sensorList[MAX_SENSORS];
int totalSensors = 0;
DeviceAddress deviceAddresses[MAX_SENSORS];

// Global Variables
unsigned long lastSendTime = 0;
unsigned long lastReadingTime = 0;
unsigned long lastDisplayUpdate = 0;
unsigned long bootTime = 0;
int readingCount = 0;
bool wifiConnected = false;
bool displayConnected = false;
int bootCount = 0;
int wifiFailCount = 0;
int currentDisplayPage = 0;
String systemErrors[10];
int errorCount = 0;

// NTP Configuration for timestamps
const char* ntpServer = "pool.ntp.org";
const long gmtOffset_sec = 19800;     // GMT+5:30 (India Standard Time)
const int daylightOffset_sec = 0;

void setup() {
  Serial.begin(115200);
  delay(2000); // Give time for Serial to initialize

  bootTime = millis();

  // Initialize preferences for bootloop detection
  preferences.begin("coolking", false);
  bootCount = preferences.getInt("bootCount", 0) + 1;
  preferences.putInt("bootCount", bootCount);

  Serial.println("\n=== Coolking Multi-Sensor Monitor Starting ===");
  Serial.println("Boot Count: " + String(bootCount));
  Serial.println("ESP32 MAC: " + WiFi.macAddress());

  // Check for potential bootloop
  if (bootCount > 5) {
    addSystemError("BOOTLOOP_DETECTED", "Boot count: " + String(bootCount));
    Serial.println("WARNING: Potential bootloop detected!");
    delay(10000); // Wait 10 seconds to break potential rapid bootloop
  }

  // Initialize OLED Display
  initializeDisplay();

  // Initialize DS18B20 sensors
  initializeSensors();

  // Connect to WiFi
  connectToWiFi();

  // Initialize NTP for timestamps
  if (wifiConnected) {
    configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
    Serial.println("NTP time synchronization initialized");
  }

  // Reset boot count after successful initialization
  if (millis() - bootTime > BOOTLOOP_RESET_TIME) {
    preferences.putInt("bootCount", 0);
  }

  updateDisplay(); // Initial display update

  Serial.println("Setup complete. Monitoring " + String(totalSensors) + " temperature sensors");
  Serial.println("Data will be sent every 5 minutes to: " + String(serverURL));
}

void loop() {
  unsigned long currentTime = millis();

  // Check WiFi connection
  if (WiFi.status() != WL_CONNECTED) {
    if (wifiConnected) {
      wifiConnected = false;
      wifiFailCount++;
      addSystemError("WIFI_DISCONNECTED", "Reconnection attempt #" + String(wifiFailCount));
      Serial.println("WiFi disconnected. Attempting reconnection...");
    }

    // Try to reconnect every 30 seconds
    static unsigned long lastWifiAttempt = 0;
    if (currentTime - lastWifiAttempt > 30000) {
      connectToWiFi();
      lastWifiAttempt = currentTime;
    }
  } else if (!wifiConnected) {
    wifiConnected = true;
    Serial.println("WiFi reconnected successfully!");
  }

  // Take temperature readings from all sensors every second
  if (currentTime - lastReadingTime >= READING_INTERVAL && readingCount < READINGS_PER_BATCH) {
    readAllSensors();
    readingCount++;
    lastReadingTime = currentTime;

    Serial.println("Reading batch " + String(readingCount) + "/" + String(READINGS_PER_BATCH) + " completed");
  }

  // Update OLED display every 2 seconds
  if (currentTime - lastDisplayUpdate >= DISPLAY_UPDATE_INTERVAL) {
    updateDisplay();
    lastDisplayUpdate = currentTime;
  }

  // Send data every 5 minutes (when we have 5 readings)
  if (readingCount >= READINGS_PER_BATCH && (currentTime - lastSendTime >= SEND_INTERVAL)) {
    if (wifiConnected) {
      sendDataToServer();
      lastSendTime = currentTime;
      readingCount = 0; // Reset reading counter

      // Clear old error messages after successful transmission
      if (errorCount > 5) {
        clearOldErrors();
      }

      Serial.println("Waiting 5 seconds before next reading cycle...");
      delay(5000);
      lastReadingTime = millis();
    } else {
      addSystemError("SEND_FAILED", "WiFi not connected for data transmission");
      Serial.println("Cannot send data - WiFi not connected");
      readingCount = 0; // Reset counter to try again
    }
  }

  // Watchdog - reset bootloop counter after successful operation
  if (currentTime - bootTime > BOOTLOOP_RESET_TIME && bootCount > 1) {
    preferences.putInt("bootCount", 0);
    bootCount = 0;
    Serial.println("System stable - bootloop counter reset");
  }

  delay(100); // Small delay to prevent overwhelming the processor
}

void connectToWiFi() {
  Serial.println("Connecting to WiFi: " + String(ssid));
  Serial.println("MAC Address: " + WiFi.macAddress());

  WiFi.begin(ssid, password);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) { // 30 second timeout
    delay(1000);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    wifiConnected = true;
    Serial.println("\nWiFi Connected Successfully!");
    Serial.println("IP Address: " + WiFi.localIP().toString());
    Serial.println("MAC Address: " + WiFi.macAddress());
    Serial.println("Signal Strength: " + String(WiFi.RSSI()) + " dBm");
  } else {
    wifiConnected = false;
    Serial.println("\nFailed to connect to WiFi!");
    Serial.println("Check if MAC address is whitelisted: " + WiFi.macAddress());
  }
}

// ========== SENSOR INITIALIZATION AND MANAGEMENT ==========

void initializeSensors() {
  Serial.println("Initializing DS18B20 sensors...");
  sensors.begin();

  totalSensors = sensors.getDeviceCount();
  Serial.println("Found " + String(totalSensors) + " DS18B20 sensor(s)");

  if (totalSensors == 0) {
    addSystemError("NO_SENSORS", "No DS18B20 sensors detected on bus");
    return;
  }

  if (totalSensors > MAX_SENSORS) {
    totalSensors = MAX_SENSORS;
    addSystemError("TOO_MANY_SENSORS", "More than " + String(MAX_SENSORS) + " sensors detected");
  }

  // Initialize each sensor
  for (int i = 0; i < totalSensors; i++) {
    if (sensors.getAddress(deviceAddresses[i], i)) {
      sensorList[i].address = getAddressString(deviceAddresses[i]);
      sensorList[i].name = "Sensor_" + String(i + 1);
      sensorList[i].isConnected = true;
      sensorList[i].errorCount = 0;
      sensorList[i].currentTemp = DEVICE_DISCONNECTED_C;

      // Set sensor resolution
      sensors.setResolution(deviceAddresses[i], TEMPERATURE_PRECISION);

      Serial.println("Sensor " + String(i + 1) + ": " + sensorList[i].address);
    } else {
      sensorList[i].isConnected = false;
      sensorList[i].errorCount++;
      addSystemError("SENSOR_ADDRESS_ERROR", "Could not get address for sensor " + String(i + 1));
    }
  }
}

void readAllSensors() {
  sensors.requestTemperatures();

  // Wait for conversion to complete
  delay(750 / (1 << (12 - TEMPERATURE_PRECISION)));

  int successCount = 0;
  for (int i = 0; i < totalSensors; i++) {
    if (sensorList[i].isConnected) {
      float temperature = sensors.getTempC(deviceAddresses[i]);

      if (temperature != DEVICE_DISCONNECTED_C && temperature > -50 && temperature < 85) {
        sensorList[i].currentTemp = temperature;
        sensorList[i].readings[readingCount] = temperature;
        sensorList[i].errorCount = 0; // Reset error count on successful read
        successCount++;

        Serial.println(sensorList[i].name + ": " + String(temperature, 2) + "°C");
      } else {
        sensorList[i].errorCount++;
        sensorList[i].currentTemp = DEVICE_DISCONNECTED_C;

        if (sensorList[i].errorCount > 3) {
          sensorList[i].isConnected = false;
          addSystemError("SENSOR_DISCONNECTED", sensorList[i].name + " - " + sensorList[i].address);
        }

        Serial.println("ERROR: Failed to read " + sensorList[i].name);
      }
    }
  }

  if (successCount == 0) {
    addSystemError("ALL_SENSORS_FAILED", "No sensors responding");
  }
}

// ========== OLED DISPLAY FUNCTIONS ==========

void initializeDisplay() {
  Serial.println("Initializing OLED display...");

  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("ERROR: OLED display initialization failed!");
    displayConnected = false;
    addSystemError("DISPLAY_INIT_FAILED", "SSD1306 display not found at 0x3C");
    return;
  }

  displayConnected = true;
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(WHITE);
  display.setCursor(0, 0);
  display.println("Coolking Monitor");
  display.println("Initializing...");
  display.display();

  Serial.println("OLED display initialized successfully");
}

void updateDisplay() {
  if (!displayConnected) return;

  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(WHITE);
  display.setCursor(0, 0);

  // Display different pages based on currentDisplayPage
  switch (currentDisplayPage % 3) {
    case 0:
      displayMainPage();
      break;
    case 1:
      displaySensorPage();
      break;
    case 2:
      displaySystemPage();
      break;
  }

  display.display();

  // Auto-cycle through pages
  static unsigned long lastPageSwitch = 0;
  if (millis() - lastPageSwitch > 8000) { // Switch every 8 seconds
    currentDisplayPage++;
    lastPageSwitch = millis();
  }
}

void displayMainPage() {
  // Header
  display.setTextSize(1);
  display.println("Coolking Monitor");
  display.println("================");

  // WiFi Status
  display.print("WiFi: ");
  if (wifiConnected) {
    display.println("Connected");
    display.println("IP: " + WiFi.localIP().toString());
  } else {
    display.println("Disconnected");
  }

  // Sensor count
  int activeSensors = 0;
  for (int i = 0; i < totalSensors; i++) {
    if (sensorList[i].isConnected) activeSensors++;
  }

  display.println("Sensors: " + String(activeSensors) + "/" + String(totalSensors));

  // Next send time
  unsigned long nextSend = (SEND_INTERVAL - (millis() - lastSendTime)) / 60000;
  display.println("Next TX: " + String(nextSend) + "min");

  // Boot info
  display.println("Boot: #" + String(bootCount));
}

void displaySensorPage() {
  display.setTextSize(1);
  display.println("Temperature Sensors");
  display.println("==================");

  if (!wifiConnected) {
    display.println("WiFi: OFFLINE");
    display.println("----------------");
  }

  int displayedSensors = 0;
  for (int i = 0; i < totalSensors && displayedSensors < 4; i++) {
    if (sensorList[i].isConnected && sensorList[i].currentTemp != DEVICE_DISCONNECTED_C) {
      display.print(sensorList[i].name + ":");
      display.println(String(sensorList[i].currentTemp, 1) + "C");
      displayedSensors++;
    }
  }

  if (displayedSensors == 0) {
    display.println("No active sensors");
  }

  display.println("Page 2/3 - Auto");
}

void displaySystemPage() {
  display.setTextSize(1);
  display.println("System Status");
  display.println("=============");

  // Memory info
  display.println("RAM: " + String(ESP.getFreeHeap() / 1024) + "KB");

  // Error count
  display.println("Errors: " + String(errorCount));

  // Uptime
  unsigned long uptime = millis() / 60000;
  display.println("Uptime: " + String(uptime) + "min");

  // Recent errors (if any)
  if (errorCount > 0) {
    display.println("Last Error:");
    String lastError = systemErrors[(errorCount - 1) % 10];
    if (lastError.length() > 16) {
      lastError = lastError.substring(0, 16);
    }
    display.println(lastError);
  }

  display.println("Page 3/3 - Auto");
}

// ========== ERROR MANAGEMENT ==========

void addSystemError(String errorType, String errorMessage) {
  String timestamp = getCurrentTimestamp();
  String fullError = timestamp + " " + errorType + ": " + errorMessage;

  systemErrors[errorCount % 10] = fullError;
  errorCount++;

  Serial.println("ERROR: " + fullError);

  // Log to preferences for persistence
  preferences.putString("lastError", fullError);
  preferences.putInt("errorCount", errorCount);
}

void clearOldErrors() {
  errorCount = min(errorCount, 5); // Keep only recent errors
  Serial.println("Cleared old error messages");
}

void sendDataToServer() {
  Serial.println("\n=== Sending Multi-Sensor Data to Server ===");

  if (!wifiConnected) {
    addSystemError("SEND_FAILED", "WiFi not connected");
    return;
  }

  HTTPClient http;
  http.begin(serverURL);
  http.addHeader("Content-Type", "application/json");
  // API Key header removed for testing
  // http.addHeader("X-API-Key", apiKey);
  http.setTimeout(10000); // 10 second timeout

  // Create simplified JSON payload compatible with server
  DynamicJsonDocument doc(1024);
  doc["esp32_mac"] = WiFi.macAddress();

  // Add readings array - server expects only sensor_id and temperature
  JsonArray readings = doc.createNestedArray("readings");

  int totalReadingsAdded = 0;
  for (int sensorIndex = 0; sensorIndex < totalSensors; sensorIndex++) {
    if (!sensorList[sensorIndex].isConnected) continue;

    for (int readingIndex = 0; readingIndex < READINGS_PER_BATCH; readingIndex++) {
      float temp = sensorList[sensorIndex].readings[readingIndex];

      if (temp != DEVICE_DISCONNECTED_C && temp > -50 && temp < 85) {
        JsonObject reading = readings.createNestedObject();
        reading["sensor_id"] = sensorList[sensorIndex].address;
        reading["temperature"] = round(temp * 10) / 10.0; // Round to 1 decimal
        totalReadingsAdded++;
      }
    }
  }

  // Convert JSON to string
  String jsonString;
  serializeJson(doc, jsonString);

  Serial.println("Sending " + String(totalReadingsAdded) + " readings from " + String(totalSensors) + " sensors");
  Serial.println("JSON Payload: " + jsonString);

  // Send HTTP POST request
  int httpResponseCode = http.POST(jsonString);

  if (httpResponseCode > 0) {
    String response = http.getString();
    Serial.println("HTTP Response Code: " + String(httpResponseCode));
    Serial.println("Server Response: " + response);

    if (httpResponseCode == 200) {
      Serial.println("✓ Data sent successfully!");

      // Clear some errors after successful transmission
      if (errorCount > 10) {
        clearOldErrors();
      }
    } else {
      addSystemError("SERVER_ERROR", "HTTP " + String(httpResponseCode) + ": " + response);
      Serial.println("⚠ Server returned error code: " + String(httpResponseCode));
    }
  } else {
    addSystemError("HTTP_FAILED", "Request failed with code: " + String(httpResponseCode));
    Serial.println("✗ HTTP Request failed! Error: " + String(httpResponseCode));
    Serial.println("Check server URL and network connection");
  }

  http.end();
  Serial.println("=== Multi-Sensor Data Transmission Complete ===\n");
}

String getAddressString(DeviceAddress deviceAddress) {
  String addressString = "";
  for (uint8_t i = 0; i < 8; i++) {
    if (deviceAddress[i] < 16) addressString += "0";
    addressString += String(deviceAddress[i], HEX);
  }
  addressString.toUpperCase();
  return addressString;
}

String getCurrentTimestamp() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) {
    Serial.println("Failed to obtain time from NTP");
    return "1970-01-01 00:00:00"; // Fallback timestamp
  }

  char timestamp[20];
  strftime(timestamp, sizeof(timestamp), "%Y-%m-%d %H:%M:%S", &timeinfo);
  return String(timestamp);
}

void printSystemStatus() {
  Serial.println("\n=== System Status ===");
  Serial.println("WiFi SSID: " + String(ssid));
  Serial.println("WiFi Status: " + (wifiConnected ? "Connected" : "Disconnected"));
  if (wifiConnected) {
    Serial.println("IP Address: " + WiFi.localIP().toString());
    Serial.println("Signal Strength: " + String(WiFi.RSSI()) + " dBm");
  }
  Serial.println("MAC Address: " + WiFi.macAddress());
  Serial.println("Sensor Address: " + sensorAddress);
  Serial.println("Server URL: " + String(serverURL));
  Serial.println("Current Time: " + getCurrentTimestamp());
  Serial.println("Free Heap: " + String(ESP.getFreeHeap()) + " bytes");
  Serial.println("====================\n");
}

// Optional: Print system status every 30 seconds for debugging
void printStatusPeriodically() {
  static unsigned long lastStatusPrint = 0;
  if (millis() - lastStatusPrint >= 30000) { // Every 30 seconds
    printSystemStatus();
    lastStatusPrint = millis();
  }
}