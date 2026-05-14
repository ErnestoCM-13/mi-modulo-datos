import polars as pl

def q1(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.group_by('country_code')
        .agg(pl.len().alias('count'))
        .sort('count', descending=True)
    )

def q2(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.group_by('category')
        .agg([
            pl.col('amount').mean().alias('avg_amount'),
            pl.col('amount').min().alias('min_amount'),
            pl.col('amount').max().alias('max_amount'),
        ])
        .sort('category')
    )

def q3(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.group_by('user_id')
        .agg([
            pl.col('amount').sum().alias('total_amount'),
            pl.len().alias('transaction_count'),
        ])
        .sort('total_amount', descending=True)
        .head(10)
    )

def q4(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.filter(pl.col('status') == 'failed')
        .with_columns(pl.col('timestamp').dt.hour().alias('hour'))
        .group_by('hour')
        .agg(pl.len().alias('count'))
        .sort('hour')
    )

def q5(df: pl.DataFrame) -> pl.DataFrame:
    cutoff = df['timestamp'].max() - pl.duration(days=30)
    return (
        df.filter(
            (pl.col('amount') > 500) &
            (pl.col('country_code').is_in(['MX', 'CO'])) &
            (pl.col('timestamp') >= cutoff)
        )
        .sort('transaction_id')
    )

def q6(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.group_by(['country_code', 'category'])
        .agg([
            pl.len().alias('count'),
            pl.col('amount').mean().alias('avg_amount'),
        ])
        .filter(
            pl.col('count') == pl.col('count').max().over('country_code')
        )
        .sort('country_code')
    )

def q7(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.filter(pl.col('status') == 'failed')
        .group_by('user_id')
        .agg(pl.len().alias('failed_count'))
        .filter(pl.col('failed_count') > 5)
        .sort('failed_count', descending=True)
    )

def q8(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.with_columns(pl.col('timestamp').dt.date().alias('date'))
        .group_by(['date', 'category'])
        .agg(pl.col('amount').mean().alias('avg_amount'))
        .sort(['date', 'category'])
    )
