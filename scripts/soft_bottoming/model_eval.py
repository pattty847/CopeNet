"""Expanding quarterly evaluation. Labels must mature before each test quarter."""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .model_features import GROUPS

HORIZONS=(12,26,52)


def split_indices(rows, horizon, start, end):
    key=str(horizon)
    complete=[i for i,r in enumerate(rows) if r['outcomes'][key]['status']=='complete']
    train=[i for i in complete if pd.Timestamp(rows[i]['outcomes'][key]['exit_date']) < start
           and pd.Timestamp(rows[i]['signal_week'])+pd.Timedelta(days=4) < start]
    test=[i for i in complete if start <= pd.Timestamp(rows[i]['signal_week'])+pd.Timedelta(days=4) < end]
    return train,test


def evaluate(rows):
    predictions=[]; folds=[]
    dates=pd.to_datetime([r['signal_week'] for r in rows])
    first=(dates.min()+pd.DateOffset(years=2)).to_period('Q')
    for h in HORIZONS:
        for quarter in pd.period_range(first,dates.max().to_period('Q'),freq='Q'):
            start=quarter.start_time; end=(quarter+1).start_time
            train,test=split_indices(rows,h,start,end)
            y=np.array([int(rows[i]['outcomes'][str(h)]['excess_pct']>0) for i in train])
            weeks={rows[i]['signal_week'] for i in train}
            valid=len(train)>=40 and len(weeks)>=20 and len(np.unique(y))==2 and min(np.bincount(y))>=10
            folds.append({'horizon':h,'quarter':str(quarter),'train':len(train),'test':len(test),
                          'train_signal_weeks':len(weeks),'status':'evaluated' if valid and test else 'insufficient_data'})
            if not valid or not test: continue
            # Equal total training weight per signal week; this does not remove serial dependence.
            counts=pd.Series([rows[i]['signal_week'] for i in train]).value_counts()
            weights=np.array([1/counts[rows[i]['signal_week']] for i in train]); weights*=len(weights)/weights.sum()
            prior=float(np.average(y,weights=weights))
            for group,columns in GROUPS.items():
                x=np.array([[rows[i]['engineered'][c] if rows[i]['engineered'][c] is not None else np.nan for c in columns] for i in train])
                xt=np.array([[rows[i]['engineered'][c] if rows[i]['engineered'][c] is not None else np.nan for c in columns] for i in test])
                for name,estimator in [('logistic',LogisticRegression(C=0.1,max_iter=2000,random_state=17)),
                                       ('forest',RandomForestClassifier(n_estimators=200,max_depth=3,min_samples_leaf=10,max_features=0.7,random_state=17,n_jobs=1))]:
                    pipeline=make_pipeline(SimpleImputer(strategy='median',keep_empty_features=True),StandardScaler(),estimator)
                    step=list(pipeline.named_steps)[-1]
                    pipeline.fit(x,y,**{step+'__sample_weight':weights})
                    # Threshold chosen from training scores only, never from future test ranks.
                    threshold=float(np.quantile(pipeline.predict_proba(x)[:,1],2/3))
                    scores=pipeline.predict_proba(xt)[:,1]
                    for i,score in zip(test,scores):
                        predictions.append({'horizon':h,'quarter':str(quarter),'group':group,'model':name,
                                            'symbol':rows[i]['symbol'],'signal_week':rows[i]['signal_week'],
                                            'score':float(score),'threshold':threshold,'selected':bool(score>=threshold),
                                            'prior':prior,**rows[i]['outcomes'][str(h)]})
    return predictions,folds


def metrics(records):
    if not records: return {'n':0}
    f=pd.DataFrame(records); y=(f.excess_pct>0).astype(int)
    return {'n':len(f),'beat_voo_pct':float(y.mean()*100),'median_excess_pct':float(f.excess_pct.median()),
            'mean_excess_pct':float(f.excess_pct.mean()),'median_return_pct':float(f.return_pct.median()),
            'median_mae_pct':float(f.mae_pct.median()),'median_drawdown_pct':float(f.max_drawdown_pct.median()),
            'median_vol_pct':float(f.annualized_vol_pct.median()),
            'auc':float(roc_auc_score(y,f.score)) if y.nunique()==2 else None,
            'brier':float(brier_score_loss(y,f.score)), 'prior_brier':float(brier_score_loss(y,f.prior))}


def summarize_predictions(predictions):
    results=[]
    for h in HORIZONS:
        for group in GROUPS:
            for model in ('logistic','forest'):
                r=[x for x in predictions if x['horizon']==h and x['group']==group and x['model']==model]
                selected=[x for x in r if x['selected']]
                nonoverlap=[]; exits={}
                for x in sorted(selected,key=lambda x:(x['entry_date'],x['symbol'])):
                    if x['entry_date']>exits.get(x['symbol'],''):
                        nonoverlap.append(x);exits[x['symbol']]=x['exit_date']
                results.append({'horizon':h,'group':group,'model':model,'all':metrics(r),'selected':metrics(selected),
                                'selected_nonoverlap':metrics(nonoverlap),
                                'quarters':{q:{'all':metrics([x for x in r if x['quarter']==q]),
                                               'selected':metrics([x for x in selected if x['quarter']==q])} for q in sorted({x['quarter'] for x in r})}})
    return results
