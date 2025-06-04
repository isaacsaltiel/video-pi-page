#!/usr/bin/env python3
import json
import os
from urllib.parse import urlparse, parse_qs, urlencode

# --------------- CONFIGURACIÓN ---------------
VIDEOS_JSON = "/home/isaac/codigo_funcional/videos_recientes.json"
OUTPUT_HTML = "/home/isaac/codigo_funcional/index.html"

HTML_HEAD = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Galería de Videos - Raspberry Pi</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      background: #f8f9fa;
      color: #222;
      margin: 0;
      padding: 20px;
    }
    h1 {
      text-align: center;
      margin-bottom: 20px;
    }
    .video-container {
      max-width: 720px;
      margin: 20px auto;
      background: #fff;
      padding: 10px;
      border-radius: 6px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.1);
    }
    video {
      width: 100%;
      height: auto;
      border-radius: 4px;
      margin-bottom: 5px;
    }
    .download-btn {
      display: inline-block;
      margin-bottom: 10px;
      text-decoration: none;
      background: #007bff;
      color: #fff;
      padding: 8px 16px;
      border-radius: 4px;
    }
    .download-btn:hover {
      background: #0056b3;
    }
  </style>
</head>
<body>
  <h1>Galería de Videos Recientes</h1>
"""

HTML_FOOT = """
</body>
</html>
"""

def convertir_a_raw(url_dropbox):
    """
    Convierte una URL de compartir de Dropbox (www.dropbox.com/scl/fi/ID/archivo?…)
    en un enlace de descarga directa:
    https://dl.dropboxusercontent.com/s/ID/archivo?todos_los_parametros_excepto_dl=1
    """
    parsed = urlparse(url_dropbox)
    # parsed.path es "/scl/fi/ID/archivo"
    partes = parsed.path.split("/")
    # partes = ["", "scl", "fi", "ID", "archivo"]
    if len(partes) < 5:
        return None

    id_archivo = partes[3]
    nombre_archivo = partes[4]

    # Parsear los parametros de consulta a un dict
    qs = parse_qs(parsed.query)
    # parse_qs devuelve valores en lista, así: {"rlkey":["..."], "dl":["0"], "st":["..."]}
    # Cambiamos dl["0"] a dl["1"]:
    qs["dl"] = ["1"]

    # Reconstruir la query string
    nueva_query = urlencode(qs, doseq=True)

    # Construir el URL raw final
    raw = f"https://dl.dropboxusercontent.com/s/{id_archivo}/{nombre_archivo}?{nueva_query}"
    return raw

def main():
    # 1. Verificar existencia de JSON
    if not os.path.exists(VIDEOS_JSON):
        print(f"[ERROR] No existe '{VIDEOS_JSON}'. Ejecuta antes upload_video.py.")
        return

    # 2. Cargar JSON
    try:
        with open(VIDEOS_JSON, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        print(f"[ERROR] '{VIDEOS_JSON}' no es un JSON válido.")
        return

    # 3. Verificar clave 'videos'
    if "videos" not in data or not isinstance(data["videos"], list):
        print(f"[ERROR] El JSON no contiene la clave 'videos' con una lista.")
        return

    videos = data["videos"]

    # 4. Abrir index.html para escritura
    with open(OUTPUT_HTML, "w") as out:
        out.write(HTML_HEAD)

        # 5. Para cada objeto en data["videos"], generar bloque HTML
        for entry in videos:
            nombre = entry.get("nombre")
            url_original = entry.get("url")

            if not nombre or not url_original:
                continue

            # 6. Convertir a URL raw (dl.dropboxusercontent.com)
            url_raw = convertir_a_raw(url_original)
            if url_raw is None:
                # Si la conversión falló, saltar ese video
                print(f"[WARN] No pude convertir URL de '{nombre}'.")
                continue

            # 7. Escribir el contenedor HTML
            out.write('  <div class="video-container">\n')
            out.write(f'    <video controls src="{url_raw}"></video>\n')
            out.write(f'    <a class="download-btn" href="{url_raw}" download="{nombre}">Descargar</a>\n')
            out.write('  </div>\n\n')

        out.write(HTML_FOOT)

    print(f"[OK] '{OUTPUT_HTML}' generado correctamente.")

if __name__ == "__main__":
    main()
