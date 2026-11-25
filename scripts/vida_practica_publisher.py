#!/usr/bin/env python3
"""Publicador transaccional de Vida Practica para Instagram."""
import argparse, hashlib, json, os, subprocess, sys, time
from datetime import datetime
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont

try:
    from .vida_practica_github_state import GitHubState
    from .vida_practica_state import reserve, mark_published
    from .vida_practica_scheduler import REELS, STORIES, CAROUSELS, SLOTS
except ImportError:
    from vida_practica_github_state import GitHubState
    from vida_practica_state import reserve, mark_published
    from vida_practica_scheduler import REELS, STORIES, CAROUSELS, SLOTS

DRIVE_FOLDER_URL = "https://drive.google.com/drive/folders/1MhixQwZ-4yvWv3jRH6wwS4A0JCI1Fo9J"
HOTLINK = "https://go.hotmart.com/S108572402G"
ACCOUNT_ID = "17841474316669794"
USERNAME = "vidapractica_hoy"

def require_env():
    required = ["GITHUB_TOKEN", "GITHUB_REPOSITORY", "CLOUDINARY_CLOUD_NAME",
                "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET", "INSTAGRAM_TOKEN"]
    missing = [x for x in required if not os.environ.get(x, "").strip()]
    if missing:
        raise RuntimeError("Faltan secretos/configuracion: " + ", ".join(missing))

def api_check(response, label):
    try:
        data = response.json()
    except ValueError:
        raise RuntimeError(f"{label}: respuesta no JSON (HTTP {response.status_code}).")
    if not response.ok or "error" in data:
        error = data.get("error", {})
        raise RuntimeError(f"{label}: {error.get('message', 'Meta/Cloudinary rechazo la solicitud.')}")
    return data

def download_inventory():
    subprocess.run(["gdown", DRIVE_FOLDER_URL, "--folder", "--json", "--quiet"], check=True, stdout=open("drive-index.json","w",encoding="utf-8"))
    entries = json.loads(Path("drive-index.json").read_text(encoding="utf-8"))
    if not isinstance(entries, list) or len(entries) < 70:
        raise RuntimeError(f"Inventario de Drive inesperado: {len(entries) if isinstance(entries,list) else 'formato invalido'} archivos.")
    return entries

def get_asset(state, date, slot):
    key = f"{date}:{slot}"
    if key in state.get("reservations", {}):
        raise RuntimeError(f"El horario {key} ya tiene una reserva ({state['reservations'][key].get('status')}); no se reintenta.")
    kind, local, utc = SLOTS[slot]
    pools = {"reel": REELS, "story": STORIES, "carousel": CAROUSELS}
    pool = pools[kind]
    idx = (int(state["last_index"].get(kind, -1)) + 1) % len(pool)
    return kind, local, utc, idx, pool[idx]

def locate(entries, path):
    matches = [x for x in entries if x.get("path") == path]
    if len(matches) != 1:
        raise RuntimeError(f"Drive: se esperaba exactamente un archivo {path}; encontrados {len(matches)}.")
    return matches[0]["url"]

def download_file(url, target):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["gdown", url, "--output", str(target), "--quiet"], check=True)
    if not target.is_file() or target.stat().st_size < 10000:
        raise RuntimeError(f"Archivo descargado inexistente o demasiado pequeño: {target.name}")
    return target

def add_story_cta(path):
    with Image.open(path) as src:
        if src.size != (1080, 1920):
            raise RuntimeError(f"Story debe ser 1080x1920; se obtuvo {src.size}.")
        image = src.convert("RGB")
    draw = ImageDraw.Draw(image)
    bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    f1, f2 = ImageFont.truetype(bold, 48), ImageFont.truetype(bold, 38)
    x0,y0,x1,y1 = 70,1430,1010,1690
    draw.rounded_rectangle((x0+8,y0+10,x1+8,y1+10),radius=42,fill=(0,0,0))
    draw.rounded_rectangle((x0,y0,x1,y1),radius=42,fill=(255,211,54),outline=(255,255,255),width=5)
    for text, font, y in [("VER LA HERRAMIENTA",f1,1480),("ENLACE EN LA BIO",f2,1565)]:
        box=draw.textbbox((0,0),text,font=font)
        draw.text(((1080-(box[2]-box[0]))/2,y),text,font=font,fill=(20,35,55))
    image.save(path,quality=95,optimize=True)

def cloudinary_upload(path, kind, date, slot, index):
    cloud,key,secret=(os.environ[x] for x in ["CLOUDINARY_CLOUD_NAME","CLOUDINARY_API_KEY","CLOUDINARY_API_SECRET"])
    folder={"reel":"reels","story":"stories","carousel":"carousels"}[kind]
    resource="video" if kind=="reel" else "image"
    params={"folder":f"vida-practica/{folder}","public_id":f"{date}_{slot}_{index+1}","overwrite":"true","timestamp":str(int(time.time()))}
    base="&".join(f"{k}={params[k]}" for k in sorted(params))+secret
    signature=hashlib.sha1(base.encode()).hexdigest()
    endpoint=f"https://api.cloudinary.com/v1_1/{cloud}/{resource}/upload"
    with Path(path).open("rb") as f:
        response=requests.post(endpoint,data={**params,"api_key":key,"signature":signature},
            files={"file":(Path(path).name,f,"video/mp4" if kind=="reel" else "image/jpeg")},timeout=(30,900))
    data=api_check(response,"Carga a Cloudinary")
    url=data.get("secure_url","")
    if data.get("resource_type")!=resource or not url.startswith("https://"):
        raise RuntimeError("Cloudinary no devolvio una URL HTTPS valida.")
    check=requests.get(url,stream=True,timeout=(20,60))
    ctype=check.headers.get("Content-Type","").lower()
    check.close()
    if not check.ok or (resource=="video" and not ctype.startswith("video/")) or (resource=="image" and not ctype.startswith("image/")):
        raise RuntimeError("La URL publica de Cloudinary no entrega el archivo esperado.")
    return url

def wait_container(graph, token, container_id, label, max_attempts=24):
    headers={"Authorization":f"Bearer {token}"}
    for _ in range(max_attempts):
        data=api_check(requests.get(f"{graph}/{container_id}",params={"fields":"status_code,status"},headers=headers,timeout=(20,90)),f"Procesamiento {label}")
        code=data.get("status_code","")
        if code=="FINISHED": return
        if code in ("ERROR","EXPIRED"): raise RuntimeError(f"Instagram no pudo procesar {label} (estado {code}).")
        time.sleep(10)
    raise RuntimeError(f"Instagram no termino de procesar {label}; no se envio a publicar.")

def publish_to_instagram(kind, urls, date, slot):
    token=os.environ["INSTAGRAM_TOKEN"]
    graph=f"https://graph.facebook.com/{os.environ.get('META_GRAPH_VERSION','v27.0')}"
    headers={"Authorization":f"Bearer {token}"}
    account=api_check(requests.get(f"{graph}/{ACCOUNT_ID}",params={"fields":"id,username"},headers=headers,timeout=(20,90)),"Verificacion de cuenta")
    if str(account.get("id"))!=ACCOUNT_ID or account.get("username","").lstrip("@").lower()!=USERNAME:
        raise RuntimeError("El token no corresponde a @vidapractica_hoy.")
    if kind=="story":
        params={"media_type":"STORIES","image_url":urls[0]}
    elif kind=="reel":
        caption=("Ideas prácticas para organizar las comidas y aprovechar mejor cada ingrediente. "
                 f"Conocé la herramienta desde el enlace de la bio: {HOTLINK}\n\n"
                 "#publicidad #afiliado #cocina #organizacion #ahorro")
        params={"media_type":"REELS","video_url":urls[0],"caption":caption,"share_to_feed":"true"}
    else:
        children=[]
        for i,url in enumerate(urls,1):
            child=api_check(requests.post(f"{graph}/{ACCOUNT_ID}/media",data={"image_url":url,"is_carousel_item":"true"},headers=headers,timeout=(20,90)),f"Crear lamina {i}")
            cid=child.get("id")
            if not cid: raise RuntimeError(f"Meta no devolvio ID de lamina {i}.")
            wait_container(graph,token,cid,f"lamina {i}",18)
            children.append(cid)
        caption=("¿Qué cocinamos hoy? Organizar el menú y la compra ayuda a aprovechar mejor cada ingrediente y cuidar el presupuesto. "
                 f"Conocé la herramienta desde el enlace de la bio: {HOTLINK}\n\n"
                 "#publicidad #afiliado #cocina #organizacion #ahorro")
        params={"media_type":"CAROUSEL","children":",".join(children),"caption":caption}
    created=api_check(requests.post(f"{graph}/{ACCOUNT_ID}/media",data=params,headers=headers,timeout=(20,120)),"Crear contenedor")
    container=created.get("id")
    if not container: raise RuntimeError("Meta no devolvio ID del contenedor.")
    wait_container(graph,token,container,"publicacion")
    # No se reintenta esta llamada: si el resultado de red es incierto, la reserva queda pendiente.
    published=api_check(requests.post(f"{graph}/{ACCOUNT_ID}/media_publish",data={"creation_id":container},headers=headers,timeout=(20,120)),"Publicar en Instagram")
    media_id=published.get("id")
    if not media_id: raise RuntimeError("Instagram no confirmo la publicacion con un ID.")
    return str(media_id)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--slot",required=True,choices=sorted(SLOTS))
    p.add_argument("--date",default=datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date().isoformat())
    p.add_argument("--dry-run",action="store_true")
    a=p.parse_args()
    require_env()
    store=GitHubState(os.environ["GITHUB_REPOSITORY"],os.environ["GITHUB_TOKEN"])
    state,sha=store.load()
    kind,local,utc,index,asset=get_asset(state,a.date,a.slot)
    entries=download_inventory()
    assets=asset if isinstance(asset,list) else [asset]
    local_paths=[]
    for i,path in enumerate(assets):
        url=locate(entries,path)
        target=Path("vida-practica")/Path(path).name
        file=download_file(url,target)
        if kind=="reel":
            with file.open("rb") as f: header=f.read(12)
            if header[4:8]!=b"ftyp": raise RuntimeError("El archivo seleccionado no es un MP4 valido.")
        else:
            with Image.open(file) as im:
                expected=(1080,1920) if kind=="story" else (1080,1350)
                if im.format!="JPEG" or im.size!=expected:
                    raise RuntimeError(f"{file.name}: se esperaba JPEG {expected}; se obtuvo {im.format} {im.size}.")
        local_paths.append(file)
    if kind=="story": add_story_cta(local_paths[0])
    urls=[cloudinary_upload(path,kind,a.date,a.slot,i) for i,path in enumerate(local_paths)]
    print(f"Cuenta: @{USERNAME} | Fecha: {a.date} | Slot: {a.slot} ({local} Argentina / {utc} UTC)")
    print(f"Material: {json.dumps(asset,ensure_ascii=False)}")
    if a.dry_run:
        print("DRY-RUN COMPLETO: Drive, archivos y Cloudinary verificados. No se reservó el horario ni se publicó.")
        return
    reservation=reserve(state,date=a.date,slot=a.slot,kind=kind,asset_index=index,asset=asset)
    store.save(state,sha)
    print("RESERVA PERSISTENTE GUARDADA ANTES DE PUBLICAR: "+reservation["key"])
    media_id=publish_to_instagram(kind,urls,a.date,a.slot)
    fresh,fresh_sha=store.load()
    mark_published(fresh,reservation["key"],media_id)
    store.save(fresh,fresh_sha)
    print("PUBLICACION CONFIRMADA Y REGISTRADA")
    print(f"Cuenta: @{USERNAME} | ID de Instagram: {media_id}")
    print("No se imprime ni se guarda ningun token.")

if __name__=="__main__":
    try: main()
    except Exception as exc:
        print(f"ERROR: {exc}",file=sys.stderr)
        sys.exit(1)
