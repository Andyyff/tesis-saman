"""AMP V10 congelado — inferencia portable.

Entrada: fotografía ORIGINAL AMP (`input_img_path`).
Salida: una lectura por F1/F2/F3, o NO_VALIDO cuando la evidencia no alcanza.

Este módulo NO reentrena nada. Carga los modelos congelados desde
`model/amp_v10_bundle.joblib`.
"""
from __future__ import annotations

from pathlib import Path
import cv2
import joblib
import numpy as np
from skimage.feature import hog

# Geometría canónica de los tres displays derechos, después de alinear.
ROWS = [(342,401),(405,465),(468,526)]
COLS = [(631,676),(677,721),(721,764),(764,808)]

# Display de siete segmentos: a,b,c,d,e,f,g.
PATTERNS = {
    0:(1,1,1,1,1,1,0), 1:(0,1,1,0,0,0,0),
    2:(1,1,0,1,1,0,1), 3:(1,1,1,1,0,0,1),
    4:(0,1,1,0,0,1,1), 5:(1,0,1,1,0,1,1),
    6:(1,0,1,1,1,1,1), 7:(1,1,1,0,0,0,0),
    8:(1,1,1,1,1,1,1), 9:(1,1,1,1,0,1,1),
}
SEG_NAMES = ['a','b','c','d','e','f','g']
SEG_ROIS = {
    'a':(2,7,9,21), 'b':(9,17,24,27), 'c':(30,38,22,32),
    'd':(44,49,5,17), 'e':(32,40,0,3), 'f':(7,15,0,3),
    'g':(22,26,7,19),
}


def digit_feature(crop: np.ndarray) -> np.ndarray:
    """Característica visual HOG + mapas binarios usada por los SVM."""
    r = crop[:,:,2].astype(float)
    lo, hi = np.percentile(r,[10,99])
    z = np.clip((r-lo)/(hi-lo+1e-6),0,1)
    z = cv2.resize(z,(32,48))
    h = hog(z, orientations=9, pixels_per_cell=(8,8),
            cells_per_block=(2,2), feature_vector=True)
    extra=[]
    for q in (.55,.65,.75,.85):
        m=(z>q).astype(np.float32)
        extra.extend(cv2.resize(m,(8,12),interpolation=cv2.INTER_AREA).ravel())
    return np.r_[h,extra]


def red_map(crop: np.ndarray) -> np.ndarray:
    b,g,r = cv2.split(crop.astype(np.float32))
    rd = r - (g+b)/2.0
    rd = cv2.resize(rd,(40,60),interpolation=cv2.INTER_AREA)
    lo,hi=np.percentile(rd,[5,99.5])
    return np.clip((rd-lo)/(hi-lo+1e-6),0,1)


def segment_scores(crop: np.ndarray) -> np.ndarray:
    z=red_map(crop)
    return np.array([
        z[y0:y1,x0:x1].mean()
        for name in SEG_NAMES
        for (y0,y1,x0,x1) in [SEG_ROIS[name]]
    ],dtype=np.float32)


def segment_probabilities(models, scores: np.ndarray) -> np.ndarray:
    return np.array([
        m.predict_proba([[scores[j]]])[0,1]
        for j,m in enumerate(models)
    ],dtype=np.float32)


def canonical_loglik(pseg: np.ndarray) -> np.ndarray:
    p=np.clip(np.asarray(pseg,float),1e-5,1-1e-5)
    out=[]
    for d in range(10):
        pat=np.asarray(PATTERNS[d],float)
        out.append(float((pat*np.log(p)+(1-pat)*np.log(1-p)).sum()))
    return np.asarray(out,dtype=np.float32)


def decimal_feature(im: np.ndarray, row, col) -> np.ndarray:
    """Recorte visual local del posible punto decimal. No usa magnitud."""
    y0,y1=row; x0,x1=col
    crop=im[y0:y1,x0:x1+8]
    b,g,r=cv2.split(crop.astype(np.float32))
    rd=r-(g+b)/2.0
    lo,hi=np.percentile(rd,[5,99])
    z=np.clip((rd-lo)/(hi-lo+1e-6),0,1)
    z=cv2.resize(z,(40,48),interpolation=cv2.INTER_AREA)
    q=z[28:48,24:40]
    return cv2.resize(q,(12,15),interpolation=cv2.INTER_AREA).ravel().astype(np.float32)


class AMPV10:
    """Modelo AMP V10 congelado y listo para inferencia."""

    def __init__(self, bundle_path: str | Path | None = None):
        if bundle_path is None:
            bundle_path=Path(__file__).resolve().parent/'model'/'amp_v10_bundle.joblib'
        self.bundle_path=Path(bundle_path)
        b=joblib.load(self.bundle_path)
        self.version=b['version']
        self.base_model=b['base_model']
        self.seg_models=b['segment_models']
        self.meta=b['meta_model']
        self.global_model=b['global_model']
        self.pos_models=b['position_models']
        self.hog_model=b['hog_model']
        self.dec_model=b['decimal_model']
        self.specialist=b['specialist_5689']
        self.ref=b['reference_image']
        self.cfg_align=b['alignment']
        self.cfg_decision=b['decision']
        self._init_alignment()

    def _init_alignment(self):
        self.orb=cv2.ORB_create(int(self.cfg_align['orb_features']))
        gref=cv2.cvtColor(self.ref,cv2.COLOR_BGR2GRAY)
        self.kref,self.dref=self.orb.detectAndCompute(gref,None)
        self.matcher=cv2.BFMatcher(cv2.NORM_HAMMING)

    def _align(self, im):
        g=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)
        k,d=self.orb.detectAndCompute(g,None)
        if d is None or self.dref is None:
            return None,0,0
        pairs=self.matcher.knnMatch(d,self.dref,k=2)
        ratio=float(self.cfg_align['lowe_ratio'])
        good=[m for m,n in pairs if m.distance < ratio*n.distance]
        if len(good)<int(self.cfg_align['min_matches_pre_h']):
            return None,len(good),0
        src=np.float32([k[m.queryIdx].pt for m in good])
        dst=np.float32([self.kref[m.trainIdx].pt for m in good])
        H,mask=cv2.findHomography(src,dst,cv2.RANSAC,float(self.cfg_align['ransac_threshold']))
        if H is None:
            return None,len(good),0
        ni=int(mask.sum())
        warped=cv2.warpPerspective(im,H,(self.ref.shape[1],self.ref.shape[0]))
        return warped,len(good),ni

    @staticmethod
    def _classes(model):
        return (model[-1].classes_ if hasattr(model,'named_steps') else model.classes_).astype(int)

    def predict_image(self, image_path: str | Path):
        """Devuelve una lista de 3 diccionarios: F1, F2, F3."""
        image_path=Path(image_path)
        raw=cv2.imread(str(image_path))
        if raw is None:
            raise ValueError(f'No se pudo leer la imagen: {image_path}')

        # Las imágenes originales AMP vienen invertidas respecto de la lectura humana.
        im=cv2.rotate(raw,cv2.ROTATE_180)
        ali,ng,ni=self._align(im)
        inlier_ratio=ni/max(ng,1)
        align_ok=(
            ali is not None
            and ng>=int(self.cfg_align['accept_matches'])
            and ni>=int(self.cfg_align['accept_inliers'])
            and inlier_ratio>=float(self.cfg_align['accept_inlier_ratio'])
        )
        if ali is None:
            ali=np.zeros_like(self.ref)

        crops=[]; digit_positions=[]
        for y0,y1 in ROWS:
            for di,(x0,x1) in enumerate(COLS,1):
                crops.append(ali[y0:y1,x0:x1])
                digit_positions.append(di)

        # 12 recortes: F1..F3 x D1..D4.
        H=np.asarray([digit_feature(c) for c in crops])

        # Lector base.
        decision=self.base_model.decision_function(H)
        p0=self.base_model.predict_proba(H)
        base_prob=np.zeros((12,10)); base_dec=np.zeros((12,10))
        cls=self.base_model.classes_.astype(int)
        base_prob[:,cls]=p0; base_dec[:,cls]=decision

        # Evidencia física de siete segmentos.
        ss=np.asarray([segment_scores(c) for c in crops])
        ps=np.zeros((12,7),float)
        for j,m in enumerate(self.seg_models):
            ps[:,j]=m.predict_proba(ss[:,[j]])[:,1]
        lls=np.asarray([canonical_loglik(p) for p in ps])

        # Feature híbrida usada por lectores meta/global/posición.
        F=np.hstack([base_dec,base_prob,ss,ps,lls])

        pm0=self.meta.predict_proba(F)
        PM=np.zeros((12,10)); PM[:,self.meta.classes_.astype(int)]=pm0
        meta_digit=PM.argmax(1)
        meta_prob=PM[np.arange(12),meta_digit]
        meta_segment_ll=lls[np.arange(12),meta_digit]

        pg0=self.global_model.predict_proba(F)
        PG=np.zeros((12,10)); PG[:,self._classes(self.global_model)]=pg0
        global_digit=PG.argmax(1)

        pos_digit=np.zeros(12,int)
        digit_positions_np=np.asarray(digit_positions)
        for dpos in (1,2,3,4):
            ix=digit_positions_np==dpos
            model=self.pos_models[dpos]
            pp0=model.predict_proba(F[ix])
            PP=np.zeros((ix.sum(),10)); PP[:,self._classes(model)]=pp0
            pos_digit[ix]=PP.argmax(1)

        ph0=self.hog_model.predict_proba(H)
        PH=np.zeros((12,10)); PH[:,self.hog_model.classes_.astype(int)]=ph0
        hog_digit=PH.argmax(1)
        hog_prob=PH[np.arange(12),hog_digit]

        seg_digit=lls.argmax(1)

        # Especialista V10 {5,6,8,9}.
        sp0=self.specialist.predict_proba(H)
        sclasses=self.specialist.classes_.astype(int)
        order=np.argsort(sp0,axis=1)[:,::-1]
        specialist_digit=sclasses[order[:,0]]
        specialist_prob=sp0[np.arange(12),order[:,0]]
        specialist_margin=(
            specialist_prob-sp0[np.arange(12),order[:,1]]
        )

        # Decimal visual: cuatro candidatos por fase. No usa magnitud del valor.
        DF=[]
        for row in ROWS:
            for col in COLS:
                DF.append(decimal_feature(ali,row,col))
        decimal_scores=self.dec_model.predict_proba(np.asarray(DF))[:,1].reshape(3,4)

        results=[]
        for fi in range(3):
            sl=slice(fi*4,(fi+1)*4)
            meta_raw=''.join(map(str,meta_digit[sl]))
            global_raw=''.join(map(str,global_digit[sl]))
            pos_raw=''.join(map(str,pos_digit[sl]))
            hog_raw=''.join(map(str,hog_digit[sl]))
            seg_raw=''.join(map(str,seg_digit[sl]))
            min_meta=float(meta_prob[sl].min())
            min_seg=float(meta_segment_ll[sl].min())
            min_hog=float(hog_prob[sl].min())
            ds=decimal_scores[fi].tolist()
            decimal_pos=int(np.argmax(decimal_scores[fi])+1)

            if not align_ok:
                status='NO_VALIDO_ALINEACION'; rule=None; raw_v9=None
            elif min_meta>=float(self.cfg_decision['meta_min_prob']) and min_seg>=float(self.cfg_decision['segment_min_loglik']):
                status='OK'; rule='V5'; raw_v9=meta_raw
            elif min_meta>=float(self.cfg_decision['v6_meta_rescue']):
                status='OK_RESCATE_ALTA_CONFIANZA'; rule='V6_META>=0.925'; raw_v9=meta_raw
            elif meta_raw==global_raw==pos_raw:
                status='OK_RESCATE_CONSENSO_DIGITOS'; rule='V8_CONSENSO'; raw_v9=meta_raw
            elif min_hog>=float(self.cfg_decision['v9_hog_min_prob']):
                status='OK_RESCATE_V9_HOG'; rule='V9_HOG>=0.70'; raw_v9=hog_raw
            elif pos_raw==seg_raw:
                status='OK_RESCATE_V9_POS_SEG'; rule='V9_POS=SEG'; raw_v9=pos_raw
            else:
                status='NO_VALIDO_DIGITO'; rule=None; raw_v9=None

            value_v9=np.nan
            if raw_v9 is not None:
                value_v9=(float(raw_v9[:decimal_pos]+'.'+raw_v9[decimal_pos:])
                          if decimal_pos<4 else float(raw_v9))

            raw_v10=raw_v9
            value_v10=value_v9
            overrides=0
            if raw_v9 is not None:
                chars=list(raw_v9)
                for jj,v9_digit in enumerate(map(int,raw_v9)):
                    k=fi*4+jj
                    if (
                        v9_digit in set(self.cfg_decision['ambiguous_digits'])
                        and int(specialist_digit[k])!=v9_digit
                        and float(specialist_prob[k])>=float(self.cfg_decision['v10_specialist_min_prob'])
                        and float(specialist_margin[k])>=float(self.cfg_decision['v10_specialist_min_margin'])
                    ):
                        chars[jj]=str(int(specialist_digit[k]))
                        overrides+=1
                raw_v10=''.join(chars)
                value_v10=(float(raw_v10[:decimal_pos]+'.'+raw_v10[decimal_pos:])
                           if decimal_pos<4 else float(raw_v10))

            results.append({
                'phase':f'F{fi+1}',
                'value':value_v10,
                'status':status,
                'raw_digits':raw_v10,
                'decimal_pos':decimal_pos,
                'rule':rule,
                'n_digit_overrides_v10':overrides,
                'decimal_scores':ds,
                'matches':int(ng),
                'inliers':int(ni),
                'inlier_ratio':float(inlier_ratio),
                # Diagnóstico reproducible:
                'value_before_v10_specialist':value_v9,
                'raw_before_v10_specialist':raw_v9,
                'meta_raw':meta_raw,
                'global_raw':global_raw,
                'position_raw':pos_raw,
                'hog_raw':hog_raw,
                'segment_raw':seg_raw,
                'min_meta_probability':min_meta,
                'min_segment_loglik':min_seg,
                'min_hog_probability':min_hog,
            })
        return results
