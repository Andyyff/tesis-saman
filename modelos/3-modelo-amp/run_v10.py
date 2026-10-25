from pathlib import Path
import argparse, json
import pandas as pd
from amp_v10 import AMPV10

EXT={'.jpg','.jpeg','.png','.bmp','.webp'}

def collect(path: Path):
    if path.is_file():
        return [path]
    return sorted(p for p in path.rglob('*') if p.is_file() and p.suffix.lower() in EXT)

def main():
    ap=argparse.ArgumentParser(description='AMP V10: lee F1/F2/F3 desde fotos originales AMP.')
    ap.add_argument('input',help='JPG/PNG individual o carpeta con imágenes')
    ap.add_argument('--out',default='predicciones_amp_v10.csv',help='CSV de salida')
    ap.add_argument('--details',action='store_true',help='Conservar columnas técnicas de diagnóstico')
    args=ap.parse_args()

    paths=collect(Path(args.input))
    if not paths:
        raise SystemExit('No se encontraron imágenes.')

    model=AMPV10()
    rows=[]
    for p in paths:
        for r in model.predict_image(p):
            r={'filename':p.name,'path':str(p),**r}
            r['decimal_scores']=json.dumps(r['decimal_scores'])
            rows.append(r)

    df=pd.DataFrame(rows)
    if not args.details:
        keep=['filename','phase','value','status','raw_digits','decimal_pos','rule','n_digit_overrides_v10']
        df=df[keep]
    df.to_csv(args.out,index=False)

    ok=df['value'].notna()
    print(f'AMP V10 | imágenes: {len(paths)} | lecturas: {len(df)} | respondió: {int(ok.sum())} | rechazó: {int((~ok).sum())}')
    print(df[['filename','phase','value','status']].to_string(index=False))
    print(f'CSV: {args.out}')

if __name__=='__main__':
    main()
