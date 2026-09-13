# Política de seguridad y uso responsable

## Uso previsto

EMVy Controller es una herramienta de **pruebas de seguridad autorizadas** para tarjetas de pago:
pentest, laboratorio, CTF e investigación. Está diseñada para **leer y explorar** tarjetas y para
**perfilar terminales/POS** en escenarios controlados.

**Solo debes usarla con:**

- Tarjetas **propias** o de **laboratorio** (tarjetas de prueba, JCOP, etc.).
- Terminales/POS/switches para los que tengas **autorización explícita por escrito**.
- Datos de "terminal" **de laboratorio**, que no generan transacciones válidas.

**Nunca la uses para:**

- Leer, clonar o manipular tarjetas de **terceros** sin consentimiento.
- Realizar o intentar **transacciones fraudulentas**.
- Cualquier actividad ilegal en tu jurisdicción.

El uso indebido es **responsabilidad exclusiva** de quien lo realiza. Los autores y contribuidores
no se hacen responsables del mal uso de esta herramienta.

## Datos sensibles

- Las **capturas** de tarjeta y los datos de **engagements** (clientes) **nunca** se versionan ni se
  empaquetan. Viven en el directorio XDG del sistema (`~/.local/share/emvy`) o en
  `engagements/<cliente>/`, ambos excluidos por `.gitignore` y `.dockerignore`.
- Antes de compartir un dump o una captura, **anonimiza** o elimina el PAN, la fecha de caducidad y
  cualquier dato del titular.
- No subas capturas, PANs, tracks ni claves a issues, PRs ni al repositorio.

## Reportar una vulnerabilidad

Si encuentras una vulnerabilidad **en esta herramienta** (no en tarjetas/terminales de terceros):

1. **No** abras un issue público con detalles explotables.
2. Contacta al mantenedor de forma privada a través del perfil de GitHub
   [@Glitchboi-sudo](https://github.com/Glitchboi-sudo).
3. Incluye pasos de reproducción y versión afectada. Se te responderá lo antes posible.

## Versiones soportadas

El proyecto está en **BETA**; solo la última versión publicada recibe correcciones.
