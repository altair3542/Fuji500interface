# -*- coding: utf-8 -*-
"""
Parser de resultados para FUJI 500 (esqueleto)
----------------------------------------------
Este módulo recibe el contenido de un archivo crudo (*.raw) capturado desde el
puerto serie/LAN del equipo (Paso 1) y devuelve una estructura normalizada que
SENAITE puede consumir para publicar resultados.

Notas alineadas al manual:
- El equipo soporta LIS mediante **Serial (RS-232, D-SUB 9 pines)** y **LAN**.
- En RS-232 existen líneas RTS/CTS y DSR/DTR; el colector ya contempla habilitarlas si se requieren.
- El protocolo específico (ASTM/CSV/propietario) debe confirmarse y codificarse aquí.

Estrategia de parsing:
1) Decodificar los bytes (`raw`) según la codificación del equipo (comúnmente ascii/latin-1).
2) Segmentar registros: por línea o por bloques ASTM (H/P/O/R/L, si aplica).
3) Extraer:
   - `SampleID` (ID de la muestra/AR que SENAITE reconocerá)
   - Pares (código_de_prueba → valor, unidad, flags)
4) Mapear códigos a `keyword` de tus Analysis Services en SENAITE usando `TEST_MAP`.

El resultado del parser es una lista de diccionarios, uno por determinación, p. ej.:
[
  {
    "SampleID": "WB-00012",
    "keyword": "glucose",
    "result": "92",
    "unit": "mg/dL",
    "flags": null,
    "meta": {"raw": "R|..."}  # opcional
  }
]
"""
from typing import List, Dict

# Mapa provisional: código del equipo -> keyword del Analysis Service
# Rellena esto cuando tengas el listado de servicios en SENAITE.
TEST_MAP = {
    # "GLU": "glucose",
    # "UREA": "urea",
    # "CREA": "creatinine",
}

def decode_lines(raw: bytes) -> List[str]:
    """
    Devuelve una lista de líneas textual a partir de bytes.
    Ajusta `encoding`/normalización según el manual del equipo.
    """
    text = raw.decode("latin-1", errors="ignore")
    # Normalización básica CR/LF
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    return lines

def parse_results(lines: List[str]) -> List[Dict]:
    """
    Parsea las líneas a resultados normalizados (placeholder).
    Ajusta a tu protocolo real: ASTM (registros H/P/O/R/L), CSV, etc.
    """
    out: List[Dict] = []
    current_sid = None

    for ln in lines:
        # ---- PLACEHOLDERS DE EJEMPLO ----
        # Supón formato sencillo:
        # SID,<id_muestra>
        # RES,<codigo>,<valor>,<unidad>[,<flags>]
        if ln.startswith("SID,"):
            current_sid = ln.split(",", 1)[1].strip()
            continue
        if ln.startswith("RES,") and current_sid:
            parts = [p.strip() for p in ln.split(",")]
            if len(parts) >= 4:
                code, value, unit = parts[1], parts[2], parts[3]
                keyword = TEST_MAP.get(code)
                if keyword:
                    out.append({
                        "SampleID": current_sid,
                        "keyword": keyword,
                        "result": value,
                        "unit": unit,
                        "flags": parts[4] if len(parts) > 4 else None,
                        "meta": {"raw": ln},
                    })
    return out

def parse_file(raw: bytes) -> List[Dict]:
    """
    Punto de entrada del parser: recibe bytes y retorna lista de determinaciones.
    """
    lines = decode_lines(raw)
    return parse_results(lines)
