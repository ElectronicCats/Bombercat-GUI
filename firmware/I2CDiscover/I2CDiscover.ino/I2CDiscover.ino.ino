#include <Wire.h>
#define VEN_PIN 13
#define IRQ_PIN 11

void setup() {
  Serial.begin(115200);
  while (!Serial);

  // Activar PN7150 via VEN (igual que connectNCI)
  pinMode(IRQ_PIN, INPUT);
  pinMode(VEN_PIN, OUTPUT);
  digitalWrite(VEN_PIN, HIGH); delay(1);
  digitalWrite(VEN_PIN, LOW);  delay(1);
  digitalWrite(VEN_PIN, HIGH); delay(10);

  // Escanear Wire (A4/A5)
  Wire.begin();
  Serial.println("Escaneando Wire (A4/A5)...");
  int found = 0;
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.print("  Wire: 0x"); Serial.println(addr, HEX);
      found++;
    }
  }

  // Escanear Wire1 (pines alternativos)
  Wire1.begin();
  Serial.println("Escaneando Wire1...");
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire1.beginTransmission(addr);
    if (Wire1.endTransmission() == 0) {
      Serial.print("  Wire1: 0x"); Serial.println(addr, HEX);
      found++;
    }
  }

  if (!found) Serial.println("Ningun dispositivo encontrado en ninguno de los dos buses.");
  else { Serial.print(found); Serial.println(" dispositivo(s) total."); }
}
void loop() {}