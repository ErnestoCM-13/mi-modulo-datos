import pandas as pd

def q1(df: pd.DataFrame) -> pd.DataFrame:
    """Conteo total de transacciones por country_code, ordenado de mayor a menor."""
    return (
        df.groupby('country_code', as_index=False)
        .size()
        .rename(columns={'size': 'count'})
        .sort_values('count', ascending=False)
        .reset_index(drop=True)
    )

def q2(df: pd.DataFrame) -> pd.DataFrame:
    """Monto promedio, mínimo y máximo agrupado por category."""
    return(
        df.groupby('category', as_index=False)['amount']
        .agg(avg_amount='mean', min_amount='min', max_amount='max')
        .sort_values('category')
        .reset_index(drop=True)
    )

def q3(df: pd.DataFrame) -> pd.DataFrame:
    """Top 10 user_id por suma de amount, incluyendo su conteo de transacciones."""
    return(
        df.groupby('user_id', as_index=False)
        .agg(total_amount=('amount', 'sum'), transaction_count=('amount', 'count'))
        .nlargest(10, 'total_amount')
        .reset_index(drop=True)
    )

def q4(df: pd.DataFrame) -> pd.DataFrame:
    """Conteo de transacciones con status='failed' agrupado por hora del día (0-23)."""
    tmp = df[df['status'] == 'failed'].copy()
    tmp['hour'] = pd.to_datetime(tmp['timestamp']).dt.hour
    return(
        tmp.groupby('hour', as_index=False)
        .size()
        .rename(columns={'size': 'count'})
        .sort_values('hour')
        .reset_index(drop=True)
    )

def q5(df: pd.DataFrame) -> pd.DataFrame:
    """Transacciones con amount > 500 en MX o CO en los últimos 30 días del dataset."""
    tmp = df.copy()
    tmp['timestamp'] = pd.to_datetime(tmp['timestamp'])
    cutoff = tmp['timestamp'].max() - pd.Timedelta(days=30)
    return (
        tmp[
            (tmp['amount'] > 500) &
            (tmp['country_code'].isin(['MX', 'CO'])) &
            (tmp['timestamp'] >= cutoff)
        ]
        .sort_values('transaction_id')
        .reset_index(drop=True)
    )

def q6(df: pd.DataFrame) -> pd.DataFrame:
    """Por cada country_code, la category con más transacciones y su monto promedio."""
    agg = (
        df.groupby(['country_code', 'category'], as_index=False)
        .agg(count=('transaction_id', 'count'), avg_amount=('amount', 'mean'))
    )
    idx = agg.groupby('country_code')['count'].idxmax()
    return (
        agg.loc[idx]
        .sort_values('country_code')
        .reset_index(drop=True)
    )

def q7(df: pd.DataFrame) -> pd.DataFrame:
    """Usuarios con más de 5 transacciones fallidas: user_id y conteo."""
    return (
        df[df['status'] == 'failed']
        .groupby('user_id', as_index=False)
        .size()
        .rename(columns={'size': 'failed_count'})
        .query('failed_count > 5')
        .sort_values('failed_count', ascending=False)
        .reset_index(drop=True)
    )

def q8(df: pd.DataFrame) -> pd.DataFrame:
    """Monto promedio diario por category."""
    tmp = df.copy()
    tmp['date'] = pd.to_datetime(tmp['timestamp']).dt.date
    return (
        tmp.groupby(['date', 'category'], as_index=False)['amount']
        .mean()
        .rename(columns={'amount': 'avg_amount'})
        .sort_values(['date', 'category'])
        .reset_index(drop=True)
    )
