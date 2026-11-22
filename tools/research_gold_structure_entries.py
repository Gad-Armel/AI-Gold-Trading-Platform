"""Fixed structure-feature challenger using the original tick model/splits/gates."""
import json
import hashlib
from datetime import datetime,timezone
import os
os.environ.setdefault('OMP_NUM_THREADS','2')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
from pathlib import Path
import sys
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from config import gold_consensus_settings as settings
from services.research.gold_entry_structure_features import candle_structure
from research_gold_tick_entries import ROOT as OUTPUT,main


def augment(data):
    count=len(data)
    for name,seconds in [('M1',60),('M5',300),('M15',900)]:
        bars=pd.read_csv(OUTPUT/'broker_bars'/(name+'.csv'))
        features=candle_structure(bars,seconds=seconds,
            broker_offset_seconds=settings.MT5_SERVER_UTC_OFFSET_SECONDS)
        features=features.rename(columns={key:'structure_'+name.lower()+'_'+key
                                         for key in features if key!='feature_epoch'})
        data=pd.merge_asof(data,features,on='feature_epoch',direction='backward',tolerance=seconds+5)
    data=data.dropna().reset_index(drop=True)
    (OUTPUT/'structure_entry_hypothesis.json').write_text(json.dumps(dict(
        features_family='COMPLETED_STRUCTURE_V1',original_examples=count,complete_examples=len(data),
        frozen_before_fit=datetime.now(timezone.utc).isoformat(),
        feature_source_sha256=hashlib.sha256((ROOT/'services/research/gold_entry_structure_features.py').read_bytes()).hexdigest(),
        model_source_sha256=hashlib.sha256((ROOT/'tools/research_gold_tick_entries.py').read_bytes()).hexdigest(),
        validation_gate=dict(minimum_trades=100,minimum_base_pf=1.1,minimum_cost_stress_pf=1.05),
        live_approved=False,design=[
            'Only completed M1/M5/M15 bars, available after their close; no future candles.',
            'Twenty-bar prior extrema, fixed $5 price-distance budget, wicks, sweeps, three-bar gaps, local VWAP and two completed bodies.',
            'Same two models, training split, hyperparameters, threshold grid and validation acceptance gate as rejected tick challenger.',
            'Previously inspected validation dates; exploratory hypothesis, not a blind test.',
            'Actual quote labels unchanged; no new artifact cache or outcome rewriting.',
            'Final dates evaluated only if the existing validation gate passes; no execution promotion.']),indent=2))
    return data


if __name__=='__main__':
    main(augment=augment,filename='structure_tick_entry_assessment.json')
