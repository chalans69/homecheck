import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from .config import ROOT
from .database import get_analysis, init_db, list_analyses, save_analysis
from .models import AnalysisRequest
from .scoring import calculate, mobility_score, risk_score, urbanism_score, noise_score, market_score
from .services.geocoding import GeocodingError, geocode, reverse_geocode
from .services.routing import route
from .services.georisques import risks
from .services import urbanisme, noise, dvf, environment

@asynccontextmanager
async def lifespan(app): init_db(); yield
app=FastAPI(title="HomeCheck",version="1.0",lifespan=lifespan)
app.mount("/static",StaticFiles(directory=ROOT/"app"/"static"),name="static")
templates=Jinja2Templates(directory=ROOT/"app"/"templates")

def refresh_noise_report(result, priority):
    noise.refresh_levels(result.get("noise", {}))
    result["scores"]["noise"] = noise_score(result.get("noise", {}))
    computed = calculate(result["scores"], priority)
    result.update(score=computed["total"], weights=computed["weights"])
    road = result.get("noise", {}).get("road", {})
    if isinstance(road, dict) and road.get("level") in {"high", "very_high"}:
        text = f'{road.get("nearest_source", "Axe routier")} à {road.get("distance_m")} m — vigilance routière élevée (estimation par proximité).'
        if not any(w.get("text") == text for w in result["warnings"]):
            result["warnings"].append({"level":"IMPORTANT", "text":text})
        result["label"] = "Vigilance routière élevée"
    return result

@app.get("/",response_class=HTMLResponse)
def home(request:Request): return templates.TemplateResponse(request,"index.html",{})

@app.post("/analyze",response_class=HTMLResponse)
async def analyze(request:Request,property_address:str=Form(...),work_address:str=Form(...),arrival_time:str=Form("09:00"),departure_time:str=Form("18:00"),property_type:str=Form("maison"),priority:str=Form("trajet")):
    try: payload=AnalysisRequest(property_address=property_address,work_address=work_address,arrival_time=arrival_time,departure_time=departure_time,property_type=property_type,priority=priority)
    except Exception as exc: return templates.TemplateResponse(request,"index.html",{"error":"Veuillez vérifier les champs du formulaire."},status_code=422)
    try: home_point,work_point=await asyncio.gather(geocode(payload.property_address),geocode(payload.work_address))
    except GeocodingError as exc: return templates.TemplateResponse(request,"index.html",{"error":str(exc)},status_code=400)
    routing,risk_data,urb,noise_data,market,env=await asyncio.gather(route(home_point,work_point),risks(home_point),urbanisme.inspect(home_point),noise.inspect(home_point),dvf.inspect(home_point,payload.property_type),environment.inspect(home_point))
    computed=calculate({"mobility":mobility_score(routing),"risks":risk_score(risk_data),"urbanism":urbanism_score(urb),"noise":noise_score(noise_data),"environment":env.get("score") if env.get("available") else None,"market":market_score(market)},payload.priority)
    total=computed["total"]; warnings=[]
    if routing.get("duration_min") and routing["duration_min"]>50: warnings.append({"level":"IMPORTANT","text":f'Trajet nominal de {routing["duration_min"]} minutes, hors trafic.'})
    for item in risk_data.get("items",[])[:5]: warnings.append({"level":"À VÉRIFIER","text":item["name"]})
    if not risk_data.get("available"): warnings.append({"level":"À VÉRIFIER","text":"Données Géorisques indisponibles lors de l’analyse."})
    road=noise_data.get("road",{})
    if road.get("level") in {"very_high","high"}: warnings.append({"level":"IMPORTANT","text":f'{road.get("nearest_source","Route importante")} à {road.get("distance_m")} m — estimation de nuisance routière par proximité.'})
    result={"home":home_point,"work":work_point,"route":routing,"risks":risk_data,"urbanism":urb,"noise":noise_data,"market":market,"environment":env,"score":total,"scores":computed["scores"],"weights":computed["weights"],"explanation":computed["explanation"],"warnings":warnings,"label":"Bon potentiel" if total and total>=75 else "Potentiel à confirmer" if total else "Score indisponible"}
    refresh_noise_report(result, payload.priority)
    analysis_id=save_analysis(payload.model_dump(),result)
    return templates.TemplateResponse(request,"result.html",{"analysis":result,"payload":payload,"analysis_id":analysis_id})

@app.get("/analyses",response_class=HTMLResponse)
def history(request:Request): return templates.TemplateResponse(request,"history.html",{"rows":list_analyses()})

@app.get("/analyses/{analysis_id}",response_class=HTMLResponse)
def reopen(request:Request,analysis_id:int):
    row=get_analysis(analysis_id)
    if not row: raise HTTPException(404,"Analyse introuvable")
    refresh_noise_report(row["result"], row["request"].get("priority", "trajet"))
    return templates.TemplateResponse(request,"result.html",{"analysis":row["result"],"payload":row["request"],"analysis_id":analysis_id})

@app.get("/health")
def health(): return {"status":"ok"}

@app.get("/api/debug/urbanisme")
async def debug_urbanisme(lat:float,lon:float):
    if not (-90<=lat<=90 and -180<=lon<=180): raise HTTPException(422,"Coordonnées invalides")
    point={"lat":lat,"lon":lon,"source":"coordonnées fournies"}; result=await urbanisme.analyze(point)
    return {"geocoding":point,"parcel":result.get("parcel"),"zoning":result.get("zoning"),"prescriptions":result.get("prescriptions",[])+result.get("servitudes",[]),"oap":result.get("oap"),"errors":result.get("errors",[])}

@app.get("/api/debug/noise")
async def debug_noise(lat:float,lon:float):
    if not (-90<=lat<=90 and -180<=lon<=180): raise HTTPException(422,"Coordonnées invalides")
    result=await noise.analyze({"lat":lat,"lon":lon})
    return {"road":result["road"],"railway":result["railway"],"aircraft":result["aircraft"],"industry":result["industry"],"official_noise_sources_found":result["official_noise_sources_found"],"provider":result["provider"],"errors":result["errors"]}

@app.get("/api/debug/dvf")
async def debug_dvf(lat:float,lon:float,radius:int=1000,property_type:str="maison",insee:str|None=None):
    if not (-90<=lat<=90 and -180<=lon<=180) or not (100<=radius<=5000):raise HTTPException(422,"Paramètres invalides")
    if not insee:
        try: point=await reverse_geocode(lat,lon)
        except GeocodingError: point={"lat":lat,"lon":lon,"insee":""}
    else:point={"lat":lat,"lon":lon,"insee":insee}
    result=await dvf.analyze(point,property_type,radius)
    return result

@app.get("/api/debug/services")
async def debug_services(lat:float,lon:float,insee:str|None=None):
    if not (-90<=lat<=90 and -180<=lon<=180):raise HTTPException(422,"Coordonnées invalides")
    if insee:point={"lat":lat,"lon":lon,"insee":insee}
    else:
        try:point=await reverse_geocode(lat,lon)
        except GeocodingError:point={"lat":lat,"lon":lon,"insee":""}
    return await environment.inspect(point)
