#!/usr/bin/env python3
"""Compara dos corridas SOBRE LAS MISMAS LECTURAS. Sin esto, una version que
mide mas casos parece peor solo porque los casos nuevos son los dificiles."""
import json, sys, collections, statistics, datetime as dt
import numpy as np

def cargar(p):
    return {(x["archivo"],k):(x,k,v) for x in json.load(open(p)) for k,v in x["varillas"].items()}

A=cargar(sys.argv[1]); B=cargar(sys.argv[2])
nomA, nomB = sys.argv[1], sys.argv[2]

def saltos(d, claves, campo):
    ser=collections.defaultdict(list)
    for c in claves:
        x,k,v=d[c]
        if v[campo] is None: continue
        t=dt.datetime.strptime(x["_hora"],"%Y-%m-%d %H:%M:%S")
        ser[(x["_fecha_dia"],k)].append((t,v[campo]))
    s=[]
    for _,xs in ser.items():
        xs.sort()
        s+=[abs(b[1]-a[1]) for a,b in zip(xs,xs[1:]) if (b[0]-a[0]).total_seconds()<=900]
    return s

for campo,u in (("inclinacion_grados","°"),("distancia_px","px")):
    # solo lecturas presentes en AMBAS versiones
    com=[c for c in A if c in B and A[c][2][campo] is not None and B[c][2][campo] is not None]
    print(f"\n{campo}  (lecturas comunes a ambas versiones: {len(com)})")
    for k in ("a","b"):
        cl=[c for c in com if c[1]==k]
        sa,sb=saltos(A,cl,campo), saltos(B,cl,campo)
        if len(sa)>10:
            print(f"   varilla {k}: n={len(sa):>4}   {nomA}: med {statistics.median(sa):.2f}{u} p90 {np.percentile(sa,90):.2f}"
                  f"   |   {nomB}: med {statistics.median(sb):.2f}{u} p90 {np.percentile(sb,90):.2f}")
    # cuanto cambia el valor mismo entre versiones
    dif=[abs(A[c][2][campo]-B[c][2][campo]) for c in com]
    print(f"   diferencia entre versiones sobre la misma foto: mediana {statistics.median(dif):.2f}{u}, p90 {np.percentile(dif,90):.2f}{u}")

for nom,d in ((nomA,A),(nomB,B)):
    n=sum(1 for c in d if d[c][2]["distancia_px"] is not None)
    print(f"\n{nom}: {n} lecturas de distancia de {len(d)} varillas")
