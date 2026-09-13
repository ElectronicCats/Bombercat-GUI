#!/usr/bin/env bash
# Construye el AppImage de EMVy Controller con Docker y lo deja en dist/.
# Uso:  packaging/build-appimage.sh
set -euo pipefail
cd "$(dirname "$0")/.."

command -v docker >/dev/null || { echo "Falta docker"; exit 1; }
mkdir -p dist

echo "== Construyendo imagen (Ubuntu 22.04 + PyInstaller + appimagetool) =="
docker build -f packaging/Dockerfile.appimage -t emvy-appimage .

echo "== Extrayendo el AppImage a dist/ =="
docker run --rm -v "$PWD/dist:/out" emvy-appimage
# el contenedor escribe como root; devolver la propiedad al usuario del host
docker run --rm -v "$PWD/dist:/out" --entrypoint chown emvy-appimage \
    -R "$(id -u):$(id -g)" /out
chmod +x dist/*.AppImage

echo "== Listo =="
ls -la dist/*.AppImage
echo "Ejecuta:  chmod +x dist/*.AppImage && ./dist/EMVy_Controller-*-x86_64.AppImage"
