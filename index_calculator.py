"""
index_calculator.py - 合成景气指数计算
步骤：同比变换 → 5年滚动分位数 → PCA第一主成分 → 0-100映射
"""
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.decomposition import PCA
from functools import lru_cache

from data_loader import load_all
from chart_config import INDUSTRY_CONFIG


def _to_weekly(series: pd.Series) -> pd.Series:
    """重采样到周频（周末），最多向前填充2期"""
    if series is None or len(series) == 0:
        return pd.Series(dtype=float)
    return series.resample('W').last().ffill(limit=2)


def _yoy_transform(weekly: pd.Series, yoy_type: str) -> pd.Series:
    """
    计算同比变化量
    pct: 同比增速（%），适合价格/库存
    diff: 同差（绝对差值），适合开工率/利润/价差
    """
    if yoy_type == 'pct':
        return weekly.pct_change(periods=52) * 100
    elif yoy_type == 'diff':
        return weekly - weekly.shift(52)
    else:
        raise ValueError(f"Unknown yoy_type: {yoy_type}")


def _rolling_percentile(yoy_series: pd.Series, window: int = 260) -> pd.Series:
    """
    5年（260周）滚动历史分位数变换
    当前YoY值在过去window期中处于什么百分位（0-100）
    """
    def pct_score(x):
        if len(x) < 10:
            return np.nan
        return stats.percentileofscore(x[:-1], x[-1], kind='rank')

    return yoy_series.rolling(window, min_periods=52).apply(pct_score, raw=True)


def _compute_industry(industry: str, data: dict, window: int = 260) -> pd.Series:
    """
    计算单行业合成景气指数时序（0-100）
    返回pd.Series，index为周频日期
    """
    ind_data = data.get(industry, {})
    cfg = INDUSTRY_CONFIG.get(industry, {})
    indicators = cfg.get('prosperity_indicators', [])

    if not indicators:
        return pd.Series(dtype=float)

    percentile_cols = {}
    for ind in indicators:
        series_name = ind['series']
        raw = ind_data.get(series_name)
        if raw is None or len(raw) < 60:
            continue
        # 处理开工率（0-1小数形式→百分比）
        if raw.abs().max() <= 1.5:
            raw = raw * 100

        weekly = _to_weekly(raw)
        yoy = _yoy_transform(weekly, ind['yoy_type'])
        pct = _rolling_percentile(yoy, window)

        if ind['direction'] == 'negative':
            pct = 100 - pct

        percentile_cols[series_name] = pct

    if not percentile_cols:
        return pd.Series(dtype=float)

    # 对齐到共同时间轴
    df = pd.DataFrame(percentile_cols)
    df = df.dropna(how='all')

    # 只使用所有指标都有数据的行做PCA
    df_full = df.dropna()

    if len(df_full) < 20:
        # 数据不足，用简单平均
        return df.mean(axis=1)

    # PCA提取第一主成分
    try:
        pca = PCA(n_components=1, random_state=42)
        scores = pca.fit_transform(df_full.values).flatten()

        # 线性映射到0-100（用全历史极值）
        s_min, s_max = scores.min(), scores.max()
        if s_max == s_min:
            mapped = np.full_like(scores, 50.0)
        else:
            mapped = (scores - s_min) / (s_max - s_min) * 100

        result = pd.Series(mapped, index=df_full.index)

        # 对未参与PCA的行（部分NaN），用当时可用指标的加权平均近似
        missing_idx = df.index.difference(df_full.index)
        if len(missing_idx) > 0:
            sub = df.loc[missing_idx]
            # 计算每行可用指标数量和均值
            available_counts = sub.count(axis=1)
            sub_mean_values = sub.mean(axis=1)
            
            # 重新映射到0-100（用历史均值和方差近似）
            sub_mean = result.mean()
            sub_std = result.std()
            sub_raw_mean = df_full.mean().mean()
            sub_raw_std = df_full.std().mean()
            
            mapped_values = []
            for idx in missing_idx:
                count = available_counts.loc[idx]
                val = sub_mean_values.loc[idx]
                
                # 如果可用指标少于2个，使用更保守的估计
                if count < 2:
                    # 使用最近完整行的值，或者中性值50
                    if len(result) > 0:
                        # 向前寻找最近的有效值
                        prev_values = result[result.index < idx]
                        if len(prev_values) > 0:
                            mapped_values.append(prev_values.iloc[-1])
                        else:
                            mapped_values.append(50.0)
                    else:
                        mapped_values.append(50.0)
                elif sub_raw_std > 0:
                    mapped_val = (val - sub_raw_mean) / sub_raw_std * sub_std + sub_mean
                    mapped_val = max(0, min(100, mapped_val))
                    mapped_values.append(mapped_val)
                else:
                    mapped_values.append(50.0)
            
            sub_mapped = pd.Series(mapped_values, index=missing_idx)
            result = pd.concat([result, sub_mapped]).sort_index()

        return result.clip(0, 100)

    except Exception as e:
        print(f"PCA failed for {industry}: {e}, using mean")
        return df.mean(axis=1)


@lru_cache(maxsize=1)
def compute_all(window: int = 260) -> dict:
    """
    计算所有行业的景气指数（带缓存）
    返回 {行业: pd.Series(weekly scores 0-100)}
    """
    data = load_all()
    result = {}
    for industry in INDUSTRY_CONFIG:
        result[industry] = _compute_industry(industry, data, window)
    return result


def get_current_score(industry: str, window: int = 260) -> float:
    """获取最新景气指数得分"""
    scores = compute_all(window)
    s = scores.get(industry)
    if s is None or len(s) == 0:
        return None
    return float(s.dropna().iloc[-1])


def get_score_wow(industry: str, window: int = 260) -> float:
    """获取景气指数周环比变化"""
    scores = compute_all(window)
    s = scores.get(industry)
    if s is None or len(s) < 2:
        return None
    s = s.dropna()
    if len(s) < 2:
        return None
    return float(s.iloc[-1] - s.iloc[-2])


def get_score_history(industry: str, months: int = 12, window: int = 260) -> pd.Series:
    """获取近N个月的景气指数历史"""
    scores = compute_all(window)
    s = scores.get(industry)
    if s is None or len(s) == 0:
        return pd.Series(dtype=float)
    cutoff = pd.Timestamp.today() - pd.DateOffset(months=months)
    return s[s.index >= cutoff].dropna()


if __name__ == '__main__':
    print("Computing prosperity indices...")
    all_scores = compute_all()
    for industry, s in all_scores.items():
        if len(s) > 0:
            latest = s.dropna().iloc[-1]
            wow = get_score_wow(industry)
            print(f"{industry}: {latest:.1f} (WoW: {wow:+.1f})")
        else:
            print(f"{industry}: No data")
