"""Metricas e reamostragem por cluster; somente biblioteca padrao e resultados salvos."""
from collections import Counter
import math
import random
import statistics


def ratio(a, b):
    return a / b if b else None


def occurrence(tp, fp, fn):
    return dict(tp=tp, fp=fp, fn=fn, precision=ratio(tp,tp+fp), recall=ratio(tp,tp+fn),
        f1=ratio(2*tp,2*tp+fp+fn), f0_5=ratio(1.25*tp,1.25*tp+fp+.25*fn),
        f2=ratio(5*tp,5*tp+fp+4*fn), jaccard=ratio(tp,tp+fp+fn),
        false_discovery_rate=ratio(fp,tp+fp), miss_rate=ratio(fn,tp+fn),
        support=tp+fn, predictions=tp+fp)


def presence(tp, fp, fn, tn):
    total=tp+fp+fn+tn
    sensitivity=ratio(tp,tp+fn); specificity=ratio(tn,tn+fp)
    observed=ratio(tp+tn,total)
    expected=ratio((tp+fp)*(tp+fn)+(fn+tn)*(fp+tn),total*total)
    denom=(tp+fp)*(tp+fn)*(tn+fp)*(tn+fn)
    return dict(tp=tp,fp=fp,fn=fn,tn=tn,n=total,precision=ratio(tp,tp+fp),
        recall=sensitivity,specificity=specificity,npv=ratio(tn,tn+fn),
        accuracy=observed,error_rate=ratio(fp+fn,total),f1=ratio(2*tp,2*tp+fp+fn),
        balanced_accuracy=(sensitivity+specificity)/2 if sensitivity is not None and specificity is not None else None,
        fpr=ratio(fp,fp+tn),fnr=ratio(fn,fn+tp),
        mcc=(tp*tn-fp*fn)/math.sqrt(denom) if denom else None,
        kappa=(observed-expected)/(1-expected) if observed is not None and expected is not None and expected!=1 else None)


def distribution(values):
    values=sorted(float(v) for v in values if v is not None)
    if not values:return dict(n=0,total=None,mean=None,median=None,stddev=None,min=None,max=None,p90=None,p95=None)
    return dict(n=len(values),total=sum(values),mean=statistics.mean(values),median=statistics.median(values),
        stddev=statistics.stdev(values) if len(values)>1 else None,min=values[0],max=values[-1],
        p90=quantile(values,.90),p95=quantile(values,.95))


def quantile(values, q):
    values=sorted(values)
    if not values:return None
    position=(len(values)-1)*q
    lo=int(position);hi=min(lo+1,len(values)-1)
    return values[lo]+(values[hi]-values[lo])*(position-lo)


def interval(values, confidence=.95):
    values=[v for v in values if v is not None and math.isfinite(v)]
    tail=(1-confidence)/2
    return dict(confidence=confidence,low=quantile(values,tail),high=quantile(values,1-tail),
        bootstrap_stddev=statistics.stdev(values) if len(values)>1 else None,
        valid_resamples=len(values))


def paired_bootstrap(conditions, clusters, iterations=10000, seed=42):
    """Mesmos pesos de arquivos/projetos em todas as condicoes, sem nova inferencia."""
    names=list(conditions)
    samples={name:{metric:[] for metric in ('precision','recall','f1')} for name in names}
    rng=random.Random(seed)
    for _ in range(iterations):
        weights=Counter(rng.choices(clusters,k=len(clusters)))
        for name,counts in conditions.items():
            tp=sum(w*counts[c][0] for c,w in weights.items())
            fp=sum(w*counts[c][1] for c,w in weights.items())
            fn=sum(w*counts[c][2] for c,w in weights.items())
            result=occurrence(tp,fp,fn)
            for metric in samples[name]:samples[name][metric].append(result[metric])
    return samples


def bootstrap_difference(a,b):
    values=[x-y for x,y in zip(a,b) if x is not None and y is not None]
    n=len(values)
    return dict(**interval(values),fraction_positive=ratio(sum(v>0 for v in values),n),
        fraction_tied=ratio(sum(v==0 for v in values),n),
        win_score_with_half_ties=ratio(sum(v>0 for v in values)+.5*sum(v==0 for v in values),n),
        note='Fractions of paired bootstrap resamples, not a p-value or posterior probability.')


def mcnemar(b,c):
    """Binomial exato bilateral para acertos discordantes em celulas validas comuns."""
    n=b+c
    if not n:return 1.0
    # Recurrence normalized in log-space avoids overflow for larger manifests.
    terms=[math.lgamma(n+1)-math.lgamma(k+1)-math.lgamma(n-k+1)-n*math.log(2)
           for k in range(min(b,c)+1)]
    return min(1.0,2*sum(math.exp(t) for t in terms))


def holm(values):
    result={};maximum=0
    ordered=sorted(values.items(),key=lambda x:x[1])
    for i,(key,p) in enumerate(ordered):
        maximum=max(maximum,min(1.0,(len(ordered)-i)*p));result[key]=maximum
    return result
