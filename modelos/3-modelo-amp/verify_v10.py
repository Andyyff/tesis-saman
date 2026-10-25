from pathlib import Path
import numpy as np
import pandas as pd
from amp_v10 import AMPV10

HERE=Path(__file__).resolve().parent
expected=pd.read_csv(HERE/'examples'/'expected.csv')
model=AMPV10()
rows=[]
for p in sorted((HERE/'examples').glob('*.jpg')):
    for r in model.predict_image(p):
        rows.append({'filename':p.name,'phase':r['phase'],'value':r['value'],'status':r['status'],
                     'raw_digits':r['raw_digits'],'decimal_pos':r['decimal_pos'],
                     'n_digit_overrides_v10':r['n_digit_overrides_v10']})
actual=pd.DataFrame(rows)
m=expected.merge(actual,on=['filename','phase'],suffixes=('_expected','_actual'))
val=np.isclose(m.value_expected.fillna(-9999),m.value_actual.fillna(-9999),atol=1e-12)
status=m.status_expected.fillna('NA').eq(m.status_actual.fillna('NA'))
raw=pd.to_numeric(m.raw_digits_expected,errors='coerce').fillna(-1).astype(int).eq(pd.to_numeric(m.raw_digits_actual,errors='coerce').fillna(-1).astype(int))
dec=m.decimal_pos_expected.eq(m.decimal_pos_actual)
ov=m.n_digit_overrides_v10_expected.eq(m.n_digit_overrides_v10_actual)
ok=val & status & raw & dec & ov
print(f'Verificación: {int(ok.sum())}/{len(ok)} lecturas coinciden con la salida congelada esperada.')
if not ok.all():
    print(m.loc[~ok].to_string(index=False))
    raise SystemExit(1)
print('OK: AMP V10 reproducible en los ejemplos incluidos.')
