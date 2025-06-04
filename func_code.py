import os
import shutil
import time
import subprocess
from datetime import datetime
from gpiozero import Button

# ---------------------- CONFIGURACIÓN ----------------------
CARPETA = "final_cam"
SEGMENT_TIME = 6            # segundos por segmento
BUFFER_SEGMENTS = 10        # cubrir ~60 s con segmentos de ~3–4 s cada uno
PIN_BOTON = 27              # GPIO del botón

# ---------------------- INICIALIZACIÓN DE CARPETA ----------------------
if os.path.exists(CARPETA):
    try:
        shutil.rmtree(CARPETA)
    except OSError as e:
        print(f"⚠️  No se pudo borrar {CARPETA}: {e}")
os.makedirs(CARPETA, exist_ok=True)

# ---------------------- VARIABLES GLOBALES ----------------------
boton_presionado = False

# ---------------------- FUNCIONES ----------------------
def manejador_de_pulsacion():
    """
    Cuando se presiona el botón, activa la bandera.
    """
    global boton_presionado
    boton_presionado = True
    print("🔴 Botón presionado")


def generar_clip_final_segmentos():
    """
    Toma los últimos BUFFER_SEGMENTS archivos segment_XXX.mp4, concatena
    exactamente esos BUFFER_SEGMENTS (~60 s) y borra los demás segmentos.
    """
    global boton_presionado

    # 1) Listar todos los segmentos
    todos = sorted(os.listdir(CARPETA))
    segmentos = [f for f in todos if f.startswith("segment_") and f.endswith(".mp4")]

    # 2) Verificar que haya al menos BUFFER_SEGMENTS archivos
    if len(segmentos) < BUFFER_SEGMENTS:
        print(f"⏳ Esperando segmentos: hay {len(segmentos)}, se necesitan {BUFFER_SEGMENTS}.")
        boton_presionado = False
        return

    # 3) Tomar los más recientes
    ultimos = segmentos[-BUFFER_SEGMENTS:]

    # 4) Construir concat.txt con rutas absolutas
    concat_path = os.path.join(CARPETA, "concat.txt")
    with open(concat_path, "w") as f:
        for seg in ultimos:
            ruta_seg = os.path.abspath(os.path.join(CARPETA, seg))
            f.write(f"file '{ruta_seg}'\n")

    # 5) Nombre del video final
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = os.path.join(CARPETA, f"video_final_{timestamp}.mp4")

    # 6) Concatenar sin recodificar
    cmd_concat = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", os.path.abspath(concat_path),
        "-c", "copy", destino
    ]
    print(f"🔗 Concatenando {BUFFER_SEGMENTS} segmentos en {destino} ...")
    resultado = subprocess.run(cmd_concat)
    if resultado.returncode == 0:
        print(f"✅ Video final generado: {destino}")
    else:
        print("❌ Error al concatenar segmentos.")

    # 7) Borrar concat.txt
    try:
        os.remove(concat_path)
    except OSError:
        pass

    # 8) Eliminar los segmentos previos
    set_a_conservar = set(ultimos)
    for seg in segmentos:
        if seg not in set_a_conservar:
            try:
                os.remove(os.path.join(CARPETA, seg))
            except OSError:
                pass

    # 9) Reiniciar bandera
    boton_presionado = False

# ---------------------- INICIALIZACIÓN DEL BOTÓN ----------------------
boton = Button(PIN_BOTON, pull_up=True)
boton.when_pressed = manejador_de_pulsacion
print("🔌 Botón configurado en GPIO", PIN_BOTON)

# ---------------------- LANZAR FFMPEG EN SEGMENTACIÓN CONTINUA ----------------------
comando_ffmpeg = [
    "ffmpeg", "-hide_banner", "-loglevel", "error",
    "-f", "v4l2",
    "-framerate", "15",             # bajar a 12 fps para más suavidad
    "-video_size", "1080x608",      # resolución 854×480 (16:9 intermedio)
    "-i", "/dev/video0",
    "-vcodec", "h264_v4l2m2m",      # codificador por hardware
    "-b:v", "8M",                   # bitrate 8 Mbps (buena nitidez)
    "-f", "segment", "-segment_time", str(SEGMENT_TIME), "-reset_timestamps", "1",
    os.path.join(CARPETA, "segment_%03d.mp4")
]

print(f"🔄 Iniciando ffmpeg: 854×480, 12 fps, h264_v4l2m2m, 8 Mbps, segment={SEGMENT_TIME}s ...")
procesoff = subprocess.Popen(comando_ffmpeg)

# ---------------------- BUCLE PRINCIPAL ----------------------
try:
    print("⏳ Esperando pulsación del botón para generar clips de ~60 s...")
    while True:
        time.sleep(0.5)
        if boton_presionado:
            generar_clip_final_segmentos()

except KeyboardInterrupt:
    print("🛑 Interrupción por teclado. Finalizando ffmpeg...")
    procesoff.terminate()
    procesoff.wait()
    print("✅ ffmpeg detenido.")

