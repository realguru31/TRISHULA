import numpy as np, pandas as pd
ET='America/New_York'
def frame(d):
    r = pd.DataFrame(d['rows'], columns=['m', 'g', 'sb', 'sr', 'ab', 'ar'])
    r = r[r.g == 0].groupby('m')[['sb', 'sr']].sum()
    s = pd.DataFrame(d['spx'], columns=['m', 'o', 'h', 'l', 'c']).drop_duplicates('m', keep='last').set_index('m')
    t = pd.to_datetime(s.index, unit='ms', utc=True).tz_convert(ET).tz_localize(None)
    s.index = t; r.index = pd.to_datetime(r.index, unit='ms', utc=True).tz_convert(ET).tz_localize(None)
    day = d['day']
    rth = pd.date_range(pd.Timestamp(day + ' 09:30'), min(s.index.max(), pd.Timestamp(day + ' 15:59')), freq='1min')
    s = s.reindex(rth).ffill(); r = r.reindex(rth).fillna(0.0)
    return s, r


