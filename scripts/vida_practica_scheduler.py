#!/usr/bin/env python3
"""Selector seguro y determinista para el scheduler de Vida Practica. No publica."""
import argparse, json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

REELS = [
"01_Videos_profesionales/B1_v3_Que_cocino_hoy_127_recetas_1080x1920.mp4",
"01_Videos_profesionales/V02_almuerzo_completo_en_40_minutos_v4_1080x1920.mp4",
"01_Videos_profesionales/V03_cinco_ingredientes_cero_excusas_v4_1080x1920.mp4",
"01_Videos_profesionales/V04_pizza_sin_masa_v4_1080x1920.mp4",
"01_Videos_profesionales/V05_la_tortilla_que_rinde_v4_1080x1920.mp4",
"01_Videos_profesionales/V06_el_tomate_que_ibas_a_botar_v4_1080x1920.mp4",
"01_Videos_profesionales/V07_tres_reglas_que_alargan_tu_comida_v4_1080x1920.mp4",
"01_Videos_profesionales/V08_el_domingo_que_ordena_tu_semana_v4_1080x1920.mp4",
"01_Videos_profesionales/V09_del_menu_al_carrito_v4_1080x1920.mp4",
"01_Videos_profesionales/V10_127_recetas_en_el_bolsillo_v4_1080x1920.mp4"]
STORIES = [
"04_Carruseles_e_historias/H01_que_cocino_hoy_1080x1920.jpg",
"04_Carruseles_e_historias/H02_menu_de_la_semana_1080x1920.jpg",
"04_Carruseles_e_historias/H03_encuesta_1080x1920.jpg",
"04_Carruseles_e_historias/H05_lista_automatica_1080x1920.jpg",
"04_Carruseles_e_historias/H06_para_tu_casa_1080x1920.jpg",
"04_Carruseles_e_historias/ig_historia_1_problema_1080x1920.jpg",
"04_Carruseles_e_historias/ig_historia_2_semana_1080x1920.jpg",
"04_Carruseles_e_historias/ig_historia_4_lista_1080x1920.jpg",
"04_Carruseles_e_historias/ig_historia_5_despensa_1080x1920.jpg",
"04_Carruseles_e_historias/ig_historia_6_presupuesto_1080x1920.jpg"]
CAROUSELS = [[f"04_Carruseles_e_historias/C{n}_{label}_{i:02d}.jpg" for i in range(1,6)] for n,label in [(1,"que_cocino_hoy"),(2,"como_funciona_4_pasos"),(4,"compra_solo_lo_que_falta")]]
SLOTS = {
"reel_1230":("reel","12:30","15:30"), "reel_2030":("reel","20:30","23:30"),
"story_0900":("story","09:00","12:00"), "story_1130":("story","11:30","14:30"),
"story_1430":("story","14:30","17:30"), "story_1730":("story","17:30","20:30"),
"story_2000":("story","20:00","23:00"), "carousel_1900":("carousel","19:00","22:00")}

def load_state(path):
    if not path.exists():
        # V02 ya fue publicado el 19-11-2026; el próximo Reel debe ser V03.
        return {"schema_version":1,"last_index":{"reel":1,"story":-1,"carousel":-1},"reservations":{},"publications":[]}
    state=json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema_version") != 1: raise SystemExit("Versión de estado desconocida; se detiene por seguridad.")
    return state

def next_asset_index(state, date, slot, simulate_day_order=False):
    kind, local, _ = SLOTS[slot]
    base = int(state["last_index"].get(kind, -1)) + 1
    if simulate_day_order:
        # En las pruebas aisladas no se persiste una reserva. Simulamos los slots
        # anteriores del mismo día que todavía no figuran en el historial remoto.
        reservations = state.get("reservations", {})
        prior_unreserved = sum(
            1 for other_slot, (other_kind, other_local, _) in SLOTS.items()
            if other_kind == kind and other_local < local
            and f"{date}:{other_slot}" not in reservations
        )
        base += prior_unreserved
    return base

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--slot",required=True,choices=sorted(SLOTS))
    p.add_argument("--date",default=datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date().isoformat())
    p.add_argument("--state",default="vida-practica-state.json")
    p.add_argument("--inventory",default="drive-index.json")
    p.add_argument("--output",default="selection.json")
    p.add_argument("--simulate-day-order",action="store_true",help="Simula los slots anteriores del día en validaciones sin persistencia.")
    a=p.parse_args()
    kind,local,utc=SLOTS[a.slot]; state=load_state(Path(a.state)); key=f"{a.date}:{a.slot}"
    if key in state["reservations"]: raise SystemExit(f"Slot ya reservado ({key}); no se vuelve a seleccionar.")
    pools={"reel":REELS,"story":STORIES,"carousel":CAROUSELS}
    pool=pools[kind]
    idx=next_asset_index(state,a.date,a.slot,a.simulate_day_order)%len(pool)
    asset=pool[idx]
    entries=json.loads(Path(a.inventory).read_text(encoding="utf-8"))
    available={str(x.get("path","")) for x in entries}
    required=asset if isinstance(asset,list) else [asset]
    missing=[x for x in required if x not in available]
    if missing: raise SystemExit("Faltan archivos en Drive: "+", ".join(missing))
    result={"date":a.date,"slot":a.slot,"kind":kind,"local_time":local,"utc_time":utc,"asset_index":idx,"asset":asset,"idempotency_key":key,"mode":"dry_run"}
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
