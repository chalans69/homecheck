BASE={"mobility":25,"urbanism":20,"risks":20,"noise":15,"environment":10,"market":10}
PRIORITY={"trajet":"mobility","calme":"noise","risques":"risks","urbanisme":"urbanism","environnement":"environment","prix":"market"}

def mobility_score(route):
    if not route.get("duration_min"): return None
    return max(20,min(100,round(110-route["duration_min"]*1.5)))

def risk_score(risks):
    if not risks.get("available"): return None
    return max(25,100-len(risks.get("items",[]))*6)

def urbanism_score(urbanism):
    if not urbanism.get("available"): return None
    score=55
    if urbanism.get("parcel"): score+=10
    if urbanism.get("zone")!="Non disponible": score+=15
    if urbanism.get("document")!="Non disponible": score+=10
    if urbanism.get("oap",{}).get("on_parcel")=="oui": score-=10
    return max(20,min(100,score))

def noise_score(noise):
    if not noise.get("available"): return None
    penalties={"very_high":80,"high":65,"medium":40,"low":15,"very_low":3}
    available=[noise.get(k,{}) for k in ("road","railway","aircraft","industry") if noise.get(k,{}).get("status")=="available"]
    known=[penalties[x["level"]] for x in available if x.get("level") in penalties]
    return 100-max(known) if known else None

def market_score(market):
    if market.get("transactions_retained",0)<3:return None
    confidence={"faible":60,"moyenne":78,"haute":90}
    return confidence.get(market.get("reliability"),60)

def calculate(values,priority):
    weights=BASE.copy(); focus=PRIORITY.get(priority)
    if focus:
        for key in weights: weights[key]=weights[key]*1.5 if key==focus else weights[key]
    available={k:v for k,v in values.items() if v is not None}
    if not available: return {"total":None,"scores":values,"weights":{},"explanation":"Aucune donnée fiable disponible pour calculer le score."}
    denom=sum(weights[k] for k in available); used={k:round(weights[k]/denom*100,1) for k in available}
    total=round(sum(available[k]*weights[k] for k in available)/denom)
    return {"total":total,"scores":values,"weights":used,"explanation":"Le score est calculé uniquement à partir des données disponibles."}
