#!/usr/bin/env python3
import os
import subprocess
import time
import json
from datetime import datetime, timezone, timedelta

# -------------------------------------------------
# 1. CONFIGURACIÓN DE RUTAS Y REMOTO
# -------------------------------------------------
VIDEO_DIR   = "/home/isaac/codigo_funcional/final_cam"       # Carpeta local de videos
VIDEO_FIJO  = "ultimo.mp4"                                   # Nombre fijo para el último video
REMOTE_PATH = "dropbox:VideosPi"                             # Remote rclone + carpeta en Dropbox
REGISTRO    = os.path.join(VIDEO_DIR, "subidos.txt")         # Registro de videos subidos
RETENTION_HOURS = 8                                          # Horas a conservar en Dropbox

# -------------------------------------------------
# 2. FUNCIONES AUXILIARES
# -------------------------------------------------

def run_command(cmd_list):
    """
    Ejecuta un comando en subprocess y devuelve (exit_code, stdout, stderr).
    """
    try:
        completed = subprocess.run(cmd_list,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    check=True)
        return (0, completed.stdout.decode(), completed.stderr.decode())
    except subprocess.CalledProcessError as e:
        return (e.returncode, e.stdout.decode(), e.stderr.decode())

def obtener_ultimo_video():
    """
    Busca en VIDEO_DIR los archivos 'video_final_*.mp4',
    los ordena por fecha de modificación (descendente) y retorna la ruta
    del más nuevo, o None si no hay ninguno.
    """
    archivos = [f for f in os.listdir(VIDEO_DIR)
                if f.startswith("video_final_") and f.endswith(".mp4")]
    if not archivos:
        return None

    rutas = [os.path.join(VIDEO_DIR, f) for f in archivos]
    rutas.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return rutas[0]

def rclone_copy(origen, destino):
    """
    Ejecuta 'rclone copy origen destino'. Retorna True si tuvo éxito, o False.
    """
    ret, out, err = run_command(["rclone", "copy", origen, destino])
    if ret != 0:
        print(f"[ERROR] rclone falló copiando:\n  Origen: {origen}\n  Destino: {destino}")
        print("  stderr:", err.strip())
        return False
    return True

def rclone_delete(remote_file):
    """
    Ejecuta 'rclone delete remote_file'. Retorna True si OK, o False si hay error.
    """
    ret, out, err = run_command(["rclone", "delete", remote_file])
    if ret != 0:
        print(f"[ERROR] rclone falló borrando:\n  {remote_file}")
        print("  stderr:", err.strip())
        return False
    return True

def listar_archivos_json():
    """
    Ejecuta 'rclone lsjson REMOTE_PATH' y devuelve lista de diccionarios.
    """
    ret, out, err = run_command(["rclone", "lsjson", REMOTE_PATH])
    if ret != 0:
        print("[ERROR] rclone lsjson falló al listar archivos remotos:")
        print("  stderr:", err.strip())
        return None
    try:
        items = json.loads(out)
    except json.JSONDecodeError as e:
        print("[ERROR] No se pudo parsear JSON de lsjson:", e)
        return None
    return items

def limpiar_antiguos(retention_hours):
    """
    Revisa archivos en REMOTE_PATH; elimina los que superen retention_hours.
    Retorna lista de nombres vigentes.
    """
    items = listar_archivos_json()
    if items is None:
        return []

    ahora = datetime.now(timezone.utc)
    limite = ahora - timedelta(hours=retention_hours)
    vigentes = []

    for entry in items:
        nombre = entry.get("Name")
        modtime_str = entry.get("ModTime")
        if not nombre or not modtime_str:
            continue

        try:
            modtime = datetime.fromisoformat(modtime_str.replace("Z", "+00:00"))
        except Exception as e:
            print(f"[WARN] No se pudo parsear ModTime para {nombre}: {modtime_str}  ({e})")
            continue

        if modtime < limite:
            remoto_completo = f"{REMOTE_PATH}/{nombre}"
            print(f"[INFO] '{nombre}' tiene más de {retention_hours}h (ModTime={modtime_str}). Borrando...")
            exitoso = rclone_delete(remoto_completo)
            if exitoso:
                print(f"[OK] '{nombre}' eliminado.")
            else:
                print(f"[ERROR] No se pudo eliminar '{nombre}'.")
        else:
            vigentes.append(nombre)

    return vigentes

# -------------------------------------------------
# 3. PROGRAMA PRINCIPAL
# -------------------------------------------------

def main():
    # 3.1. Crear (si no existe) el registro de subidos
    if not os.path.exists(REGISTRO):
        open(REGISTRO, "w").close()

    with open(REGISTRO, "r+") as reg:
        subidos = set(line.strip() for line in reg if line.strip())

        # 3.3. Determinar el último video local
        ultimo_video = obtener_ultimo_video()
        if ultimo_video is None:
            print("[INFO] No hay ningún video 'video_final_*.mp4' en la carpeta local.")
            # No retornamos aquí. Solo limpiamos y seguimos al final para regenerar la página.
            archivos_vigentes = limpiar_antiguos(RETENTION_HOURS)
            print(f"[INFO] Después de limpieza, archivos vigentes en Dropbox: {archivos_vigentes}")
        else:
            nombre_uv = os.path.basename(ultimo_video)
            if nombre_uv in subidos:
                # Ya subimos este video; solo limpiamos y seguimos al final
                print(f"[INFO] '{nombre_uv}' ya fue subido anteriormente. Solo limpio antiguos remotos.")
                archivos_vigentes = limpiar_antiguos(RETENTION_HOURS)
                print(f"[INFO] Después de limpieza, archivos vigentes en Dropbox: {archivos_vigentes}")
            else:
                # Hay un video nuevo que debemos subir
                print(f"[INFO] Nuevo video detectado: '{nombre_uv}'. Preparando subida...")

                # 3.4. Copiar localmente como VIDEO_FIJO ("ultimo.mp4")
                ruta_fijo_local = os.path.join(VIDEO_DIR, VIDEO_FIJO)
                try:
                    if os.path.exists(ruta_fijo_local):
                        os.remove(ruta_fijo_local)
                    subprocess.run(["cp", ultimo_video, ruta_fijo_local], check=True)
                    print(f"[OK] Copiado localmente como '{VIDEO_FIJO}'.")
                except Exception as e:
                    print(f"[ERROR] No se pudo copiar '{nombre_uv}' a '{VIDEO_FIJO}': {e}")
                    # Aquí podrías retornar, pero mejor seguimos para limpiar antiguos y regenerar la página
                    archivos_vigentes = limpiar_antiguos(RETENTION_HOURS)
                    print(f"[INFO] Después de limpieza, archivos vigentes en Dropbox: {archivos_vigentes}")
                else:
                    # 3.5. Subir en bucle hasta que tenga éxito
                    while True:
                        print(f"[INFO] Subiendo a Dropbox:\n   1) '{nombre_uv}'\n   2) '{VIDEO_FIJO}'")
                        exito1 = rclone_copy(ultimo_video, REMOTE_PATH)
                        exito2 = rclone_copy(ruta_fijo_local, REMOTE_PATH)

                        if exito1 and exito2:
                            print(f"[OK] Subidos '{nombre_uv}' y '{VIDEO_FIJO}'.")
                            reg.write(nombre_uv + "\n")
                            reg.flush()
                            break
                        else:
                            print("[WARN] Falló subida. Reintentando en 60s...")
                            time.sleep(60)

                    # 3.6. Limpiar antiguos en Dropbox
                    archivos_vigentes = limpiar_antiguos(RETENTION_HOURS)
                    print(f"[INFO] Después de limpieza, archivos vigentes en Dropbox: {archivos_vigentes}")

        # 3.7. Guardar lista local (opcional)
        #    Esto se ejecuta tanto si había video nuevo, como si no
        lista_vigentes_path = os.path.join(VIDEO_DIR, "videos_vigentes.txt")
        try:
            with open(lista_vigentes_path, "w") as lv:
                for nombre in archivos_vigentes:
                    lv.write(nombre + "\n")
            print(f"[OK] Lista vigentes guardada en '{lista_vigentes_path}'.")
        except Exception as e:
            print(f"[ERROR] No se pudo escribir lista de vigentes: {e}")

        # -------------------------------------------------------
        # 3.8. Generar el index.html con build_index.py
        # -------------------------------------------------------
        print("[INFO] Regenerando 'index.html'...")
        ret_code = os.system("/usr/bin/python3 /home/isaac/codigo_funcional/build_index.py")
        if ret_code != 0:
            print("[ERROR] Falló build_index.py.")
            return
        print("[OK] 'index.html' regenerado.")

        # -------------------------------------------------------
        # 3.9. --- BLOQUE GIT PARA ACTUALIZAR PÁGINA EN GITHUB ---
        # -------------------------------------------------------
        print("[INFO] Haciendo commit y push de index.html a GitHub Pages...")

        # Directorio local del repositorio clonado
        repo_dir = "/home/isaac/codigo_funcional"
        os.chdir(repo_dir)

        # Rutas de origen y destino de index.html
        src_index = "/home/isaac/codigo_funcional/index.html"
        dst_index = os.path.join(repo_dir, "index.html")

        try:
            # Copiar el nuevo index.html al repo local
            os.system(f"cp {src_index} {dst_index}")
        except Exception as e:
            print(f"[ERROR] No se pudo copiar index.html al repositorio: {e}")

        # Agregar, commit y push
        os.system('git add index.html')
        # Usamos '|| true' para que no falle si no hay cambios
        os.system('git commit -m "Actualiza galería: videos recientes" || true')
        os.system("git push origin main")
        print("[OK] index.html enviado a GitHub Pages.")
        # -------------------------------------------------------

if __name__ == "__main__":
    main()
