"""
Colector FUJI 500 — Paso 1 (Transporte)
=======================================
LEE: Puerto serie RS‑232 del analizador y vuelca datos crudos a una carpeta “inbox”.
Este paso NO interpreta el protocolo todavía; sólo desacopla el transporte del parser
que luego implementaremos dentro de SENAITE.

Por qué así (según el manual):
- El equipo declara soporte de LIS por **Serial o LAN** y muestra el **conector D‑SUB de 9 pines**
  con líneas RXD/TXD, RTS/CTS, DTR/DSR, CD y RI. Eso confirma que la vía RS‑232 es válida y que
  puede requerir control de flujo por hardware. (Ajustable abajo vía variables).

IMPORTANTE:
- Los parámetros exactos de comunicación (baudios, paridad, bits de parada, control de flujo)
  se deben **configurar de acuerdo con el equipo** (menú de servicio / documentación).
  Aquí proveemos valores por defecto que debes sobrescribir si difieren.
- Este proceso rota el archivo cuando detecta **inactividad** o cuando aparece un **byte EOT** (opcional).
- Si en lugar de RS‑232 usas **LAN**, cambia la lectura serial por un socket TCP y conserva el resto.

Variables de entorno (puedes declararlas en /etc/default/fuji500-collector):
  FUJI500_INBOX=/var/senaite/inbox/fuji500
  FUJI500_PORT=/dev/ttyUSB0
  FUJI500_BAUD=9600
  FUJI500_BYTESIZE=8     # 5,6,7,8
  FUJI500_PARITY=N       # N,E,O,M,S
  FUJI500_STOPBITS=1     # 1, 1.5, 2
  FUJI500_TIMEOUT=2      # seg de timeout de lectura
  FUJI500_IDLE_SECONDS=1.5
  FUJI500_EOT_HEX=       # ej. '04' para ASCII EOT
  FUJI500_RTSCTS=0       # 1 para habilitar control de flujo RTS/CTS si el equipo lo exige
  FUJI500_DSRDTR=0       # 1 para habilitar DSR/DTR si el equipo lo exige

Requisitos:
  pip install pyserial

Ejecución como servicio:
  Ver plantilla systemd “fuji500-collector.service” incluida en este paquete.
"""
import os
import time
import datetime
import pathlib
import binascii
import sys


def _get_env_int(name, default):
    """Lee un entero de variables de entorno, con valor por defecto si falta/está mal."""
    try:
        return int(os.environ.get(name, str(default)))
    except Exception:
        return default

def _get_env_float(name, default):
    """Lee un float de variables de entorno, con valor por defecto si falta/está mal."""
    try:
        return float(os.environ.get(name, str(default)))
    except Exception:
        return default

# --- Configuración por entorno (ajusta con los parámetros reales del equipo) ---
INBOX = os.environ.get("FUJI500_INBOX", "/var/senaite/inbox/fuji500")
PORT  = os.environ.get("FUJI500_PORT",  "/dev/ttyUSB0")
BAUD  = _get_env_int("FUJI500_BAUD", 9600)
BYTESIZE = _get_env_int("FUJI500_BYTESIZE", 8)  # 5,6,7,8
PARITY   = os.environ.get("FUJI500_PARITY", "N").upper()  # N,E,O,M,S
STOPBITS = float(os.environ.get("FUJI500_STOPBITS", "1"))  # 1, 1.5, 2
TIMEOUT  = _get_env_float("FUJI500_TIMEOUT", 2.0)  # seg para .read()
IDLE_SECONDS = _get_env_float("FUJI500_IDLE_SECONDS", 1.5)  # rota por inactividad
EOT_HEX = os.environ.get("FUJI500_EOT_HEX", "").strip()    # separador de fin de transmisión
RTSCTS  = bool(_get_env_int("FUJI500_RTSCTS", 0))  # Control de flujo por hardware RTS/CTS
DSRDTR  = bool(_get_env_int("FUJI500_DSRDTR", 0))  # Control de flujo por hardware DSR/DTR

# Carga perezosa de pyserial para evitar fallo si aún no está instalado
try:
    import serial
except Exception as e:
    print("[FUJI500] ERROR: pyserial no está instalado. Instala con: pip install pyserial", file=sys.stderr)
    raise

def _serial_params():
    """Mapea los parámetros lógicos a constantes de pyserial."""
    # Bits de datos
    if BYTESIZE == 5: bytesize = serial.FIVEBITS
    elif BYTESIZE == 6: bytesize = serial.SIXBITS
    elif BYTESIZE == 7: bytesize = serial.SEVENBITS
    else: bytesize = serial.EIGHTBITS

    # Paridad
    parity_map = {
        "N": serial.PARITY_NONE,
        "E": serial.PARITY_EVEN,
        "O": serial.PARITY_ODD,
        "M": serial.PARITY_MARK,
        "S": serial.PARITY_SPACE,
    }
    parity = parity_map.get(PARITY, serial.PARITY_NONE)

    # Bits de parada
    if STOPBITS == 1: stopbits = serial.STOPBITS_ONE
    elif STOPBITS == 1.5: stopbits = serial.STOPBITS_ONE_POINT_FIVE
    else: stopbits = serial.STOPBITS_TWO

    return bytesize, parity, stopbits

def _new_batch_path():
    """Genera un nombre de archivo único para cada “lote” recibido del analizador."""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return os.path.join(INBOX, f"fuji500_{ts}.raw")

def main():
    """
    Bucle principal:
    - Abre el puerto serie con los parámetros dados.
    - Acumula bytes en memoria hasta que:
        a) llegue el marcador EOT (opcional), o
        b) se supere el intervalo de inactividad (IDLE_SECONDS).
    - En ese momento, vuelca el bloque a un archivo en INBOX y comienza otro bloque.
    """
    # Asegura que la carpeta de entrada exista
    pathlib.Path(INBOX).mkdir(parents=True, exist_ok=True)

    bytesize, parity, stopbits = _serial_params()

    # Nota: En RS‑232, según el manual, existen líneas RTS/CTS y DTR/DSR (D‑SUB 9).
    # Si tu configuración de LIS exige control de flujo por hardware, habilítalo abajo
    # con FUJI500_RTSCTS=1 y/o FUJI500_DSRDTR=1.
    print(f"[FUJI500] Colector en {PORT} @ {BAUD} baudios (datos:{BYTESIZE}/paridad:{PARITY}/stop:{STOPBITS})")
    print(f"[FUJI500] RTS/CTS={'on' if RTSCTS else 'off'}  DSR/DTR={'on' if DSRDTR else 'off'}")
    print(f"[FUJI500] Inbox: {INBOX}")
    print(f"[FUJI500] Rotación por inactividad: {IDLE_SECONDS}s  EOT_HEX: {EOT_HEX or '(deshabilitado)'}")

    # Prepara EOT si está configurado (p. ej., '04' -> ASCII EOT)
    eot = None
    if EOT_HEX:
        try:
            eot = binascii.unhexlify(EOT_HEX)
        except Exception as e:
            print(f"[FUJI500] AVISO: EOT_HEX '{EOT_HEX}' no es válido; se ignora.", file=sys.stderr)
            eot = None

    # Abre el puerto serie
    with serial.Serial(
        PORT,
        BAUD,
        bytesize=bytesize,
        parity=parity,
        stopbits=stopbits,
        timeout=TIMEOUT,
        rtscts=RTSCTS,
        dsrdtr=DSRDTR,
    ) as ser:
        buf = bytearray()
        last_data = time.time()
        current_path = _new_batch_path()

        while True:
            # Lee hasta 1024 bytes o hasta agotar TIMEOUT
            chunk = ser.read(1024)
            now = time.time()

            if chunk:
                # Llegaron bytes: acumula en buffer y registra “último dato”
                buf.extend(chunk)
                last_data = now

                # Si hay un byte/paquete EOT configurado, dividimos allí
                if eot and eot in buf:
                    parts = buf.split(eot)
                    # Para cada bloque completo antes del EOT:
                    for part in parts[:-1]:
                        if part:
                            with open(current_path, "ab") as f:
                                f.write(part)
                            print(f"[FUJI500] Archivo (por EOT): {current_path} ({len(part)} bytes)")
                            current_path = _new_batch_path()
                    # Deja el remanente en el buffer
                    buf = bytearray(parts[-1])

            else:
                # No llegaron bytes en este ciclo; si hay inactividad suficiente,
                # persistimos lo que haya y comenzamos un nuevo archivo.
                if buf and (now - last_data) >= IDLE_SECONDS:
                    with open(current_path, "ab") as f:
                        f.write(buf)
                    print(f"[FUJI500] Archivo (por inactividad): {current_path} ({len(buf)} bytes)")
                    buf.clear()
                    current_path = _new_batch_path()
                # Pequeña espera para no atar el CPU
                time.sleep(0.05)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[FUJI500] Colector detenido por el usuario.")
