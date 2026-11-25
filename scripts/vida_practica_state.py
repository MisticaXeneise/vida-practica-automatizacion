"""Estado transaccional local para publicaciones de Vida Practica.

El llamador debe guardar este JSON en almacenamiento Git persistente antes de
publicar. Una reserva pendiente bloquea reintentos para evitar duplicados.
"""
import json
from pathlib import Path

def initial_state():
    return {"schema_version":1,"last_index":{"reel":1,"story":-1,"carousel":-1},"reservations":{},"publications":[]}

def read_state(path):
    p=Path(path)
    if not p.exists(): return initial_state()
    data=json.loads(p.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("reservations"),dict):
        raise ValueError("Estado incompatible o corrupto; se detiene sin publicar.")
    return data

def write_state(path,state):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+".tmp")
    tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    tmp.replace(p)

def reserve(state, *, date, slot, kind, asset_index, asset):
    key=f"{date}:{slot}"
    existing=state["reservations"].get(key)
    if existing:
        raise ValueError(f"El slot {key} ya tiene una reserva ({existing.get('status')}); no se reintenta.")
    reservation={"key":key,"date":date,"slot":slot,"kind":kind,"asset_index":asset_index,"asset":asset,"status":"reserved","media_id":None}
    state["reservations"][key]=reservation
    state["last_index"][kind]=asset_index
    return reservation

def mark_published(state, key, media_id):
    if not media_id: raise ValueError("Instagram debe devolver un media_id para confirmar.")
    reservation=state["reservations"].get(key)
    if not reservation: raise ValueError(f"No existe reserva para {key}.")
    if reservation["status"]=="published":
        if str(reservation["media_id"])==str(media_id): return reservation
        raise ValueError("La reserva ya fue publicada con otro ID; requiere revisión.")
    if reservation["status"]!="reserved": raise ValueError("Estado de reserva inesperado.")
    reservation["status"]="published"
    reservation["media_id"]=str(media_id)
    state["publications"].append({"key":key,"kind":reservation["kind"],"asset":reservation["asset"],"media_id":str(media_id)})
    return reservation

def save_reservation(path, state, **kwargs):
    reservation=reserve(state,**kwargs)
    write_state(path,state)
    return reservation

def save_publication(path,state,key,media_id):
    mark_published(state,key,media_id)
    write_state(path,state)
