#!/usr/bin/env bash
# Compila (y opcionalmente sube) el firmware EMVyBomberCat con arduino-cli.
# Uso:  ./build.sh            # solo compila
#       ./build.sh upload     # compila y sube al puerto detectado
#       FQBN=... PORT=... ./build.sh upload
set -euo pipefail
cd "$(dirname "$0")"

FQBN="${FQBN:-electroniccats:mbed_rp2040:bombercat}"
INDEX_URL="https://electroniccats.github.io/Arduino_Boards_Index/package_electroniccats_index.json"

command -v arduino-cli >/dev/null || { echo "Falta arduino-cli"; exit 1; }

echo "== Core / librerías =="
arduino-cli config init --overwrite >/dev/null 2>&1 || true
arduino-cli config add board_manager.additional_urls "$INDEX_URL" >/dev/null 2>&1 || true
arduino-cli core update-index
arduino-cli core install electroniccats:mbed_rp2040 || true
# Instala cada librería por su nombre de registro (individual, tolerante a fallos):
arduino-cli lib install "Electronic Cats PN7150" || true
arduino-cli lib install "WiFiNINA" || true
arduino-cli lib install "ArduinoJson" || true

echo "== Compilando ($FQBN) =="
# --output-dir deja el .uf2 en ./build para que la TUI (pestaña BomberCat) lo
# descubra y puedas flashearlo como firmware propio.
arduino-cli compile --fqbn "$FQBN" --output-dir build .
echo "== Artefactos en $(pwd)/build =="
ls -1 build/*.uf2 2>/dev/null || echo "(sin .uf2; revisa la salida de compilación)"

if [ "${1:-}" = "upload" ]; then
  PORT="${PORT:-$(arduino-cli board list | awk '/ttyACM|ttyUSB/{print $1; exit}')}"
  [ -n "$PORT" ] || { echo "No detecté puerto; pasa PORT=/dev/ttyACMx"; exit 1; }
  echo "== Subiendo a $PORT =="
  arduino-cli upload --fqbn "$FQBN" -p "$PORT" .
fi
