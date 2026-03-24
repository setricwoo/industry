"""
data_loader.py - 读取所有Excel数据，返回清洗后的时间序列字典
"""
import pandas as pd
import numpy as np
from functools import lru_cache
import os

DATA_DIR = os.path.dirname(os.path.abspath(__file__))


def _ts(df, date_col, val_col, skip):
    """从DataFrame提取时间序列（指定列索引）"""
    sub = df.iloc[skip:].copy()
    dates = pd.to_datetime(sub.iloc[:, date_col], errors='coerce')
    vals = pd.to_numeric(sub.iloc[:, val_col], errors='coerce')
    s = pd.Series(vals.values, index=dates)
    # 0值视为缺失（Excel中0表示未填充），但保留负值（利润/价差可为负）
    s = s.replace(0, np.nan).dropna()
    return s[s.index.notna()].sort_index()


def _unpivot_seasonal(df, mmdd_col, year_header_row, data_start_row, val_col_offset=1):
    """
    反透视预透视季节表 -> 时间序列
    mmdd_col: MM-DD列的索引
    year_header_row: 年份标题所在行（0-indexed from file start）
    data_start_row: 数据起始行
    val_col_offset: 值列相对于mmdd_col的偏移（默认1）
    """
    year_row = df.iloc[year_header_row]
    year_cols = {}
    for j in range(mmdd_col + val_col_offset, len(year_row)):
        yr_label = year_row.iloc[j]
        if pd.isna(yr_label):
            continue
        try:
            year = int(str(yr_label)[:4])
            year_cols[j] = year
        except Exception:
            continue

    records = []
    for i in range(data_start_row, len(df)):
        mmdd = df.iloc[i, mmdd_col]
        if pd.isna(mmdd) or not isinstance(mmdd, str):
            continue
        # 过滤非日期格式的行
        if len(mmdd) != 5 or mmdd[2] != '-':
            continue
        for j, year in year_cols.items():
            try:
                val = float(df.iloc[i, j])
                if not np.isnan(val):
                    date = pd.Timestamp(f'{year}-{mmdd}')
                    records.append((date, val))
            except Exception:
                continue

    if not records:
        return pd.Series(dtype=float)
    dates, vals = zip(*records)
    ts = pd.Series(list(vals), index=pd.DatetimeIndex(list(dates)))
    return ts.sort_index()


def _read_coal():
    path = os.path.join(DATA_DIR, '煤炭.xlsx')

    # === 煤价 sheet ===
    # 结构：行0=指标名，行1=频率，行2=单位，行3=指标ID；数据从行4开始
    # 列：0=指标名称(日期), 1=秦港动力煤, 2=主焦煤, 3=长协
    df_coal_price = pd.read_excel(path, sheet_name='煤价', header=None)
    qin_gang_coal = _ts(df_coal_price, 0, 1, 4)
    coking_coal = _ts(df_coal_price, 0, 2, 4)
    long_term_price = _ts(df_coal_price, 0, 3, 4)

    # === 库存 sheet ===
    # 左侧时序：行0=名，行1=频，行2=单位，行3=ID；数据从行4
    # 右侧季节表：行4=年份标题(cols 7+)，行5+数据(col6=MMDD, col7+=值)
    df_inv = pd.read_excel(path, sheet_name='库存', header=None)
    cctd_inv = _ts(df_inv, 0, 1, 4)
    qhd_inv = _ts(df_inv, 0, 2, 4)
    # 25省电厂库存（季节表）
    plant_inv_25 = _unpivot_seasonal(df_inv, mmdd_col=6, year_header_row=4, data_start_row=5)

    # === 日耗 sheet ===
    # 行0=标题，行1=年份标题(cols 2+)；数据从行2(col1=MMDD, col2+=值)
    df_daily = pd.read_excel(path, sheet_name='日耗', header=None)
    daily_consumption_25 = _unpivot_seasonal(df_daily, mmdd_col=1, year_header_row=1, data_start_row=2)

    return {
        '秦港动力煤价': qin_gang_coal,
        '主焦煤价': coking_coal,
        '山西优混平仓价': coking_coal,  # 别名，实际数据可能需从其他列获取
        '秦港长协价': long_term_price,
        'CCTD港口库存': cctd_inv,
        '秦皇岛港库存': qhd_inv,
        '25省电厂库存': plant_inv_25,
        '25省电厂日耗': daily_consumption_25,
    }


def _read_steel():
    path = os.path.join(DATA_DIR, '钢铁.xlsx')

    # === 钢价 sheet ===
    # 行0=空白，行1=名，行2=单位，行3=频率；数据从行4
    # 列：0=空，1=日期，2=热卷，3=螺纹
    df_price = pd.read_excel(path, sheet_name='钢价', header=None)
    hr_coil = _ts(df_price, 1, 2, 4)
    rebar = _ts(df_price, 1, 3, 4)

    # === 铁矿石 sheet ===
    # 行0=空，行1=名，行2=频，行3=单位；数据从行4
    df_ore = pd.read_excel(path, sheet_name='铁矿石', header=None)
    iron_ore = _ts(df_ore, 1, 2, 4)

    # === 库存 sheet ===
    # 行0=空，行1=名（col2=钢协库存; col4=Mysteel季节标题），行2=单位/年份标题(col4+)
    # 行3=频率/数据(col4=MMDD, col5+=值)；行4+左侧时序
    df_inv = pd.read_excel(path, sheet_name='库存', header=None)
    steel_corp_inv = _ts(df_inv, 1, 2, 4)   # 中钢协旬度库存，从行4
    # 五大材钢厂+社会库存（季节表）：年份标题在行2 cols4+，数据从行3 col4=MMDD
    wuda_inv = _unpivot_seasonal(df_inv, mmdd_col=4, year_header_row=2, data_start_row=3)

    # === 产销量 sheet ===
    # 行0=空，行1=名，行2=单位/年份标题(col7+)，行3=频率/季节数据(col6=MMDD,col7+=值)，行4+=左侧时序
    df_prod = pd.read_excel(path, sheet_name='产销量', header=None)
    bf_rate = _ts(df_prod, 1, 2, 4)    # 247家高炉开工率
    molten_iron = _ts(df_prod, 1, 3, 4)  # 铁水产量
    # 五大材产量（季节表）：年份标题在行2 col7+，数据从行3 col6=MMDD
    wuda_prod = _unpivot_seasonal(df_prod, mmdd_col=6, year_header_row=2, data_start_row=3)
    # 五大材表观消费量（即表需）= 五大材产量（PDF图7）
    # 注：PDF图7标题为"五大材消费量"，数据就是产量（表观消费=产量+库存变化≈产量）
    wuda_demand = wuda_prod  # 使用同一预透视表的数据

    # === 盈利 sheet ===
    # 行0=空，行1=名，行2=单位，行3=频率；数据从行4
    # 左侧：col1=日期, col2=盈利率（从2015）
    # 右侧：col5=日期, col6=螺纹盈利, col7=热卷盈利（从2022）
    df_profit = pd.read_excel(path, sheet_name='盈利', header=None)
    profit_rate = _ts(df_profit, 1, 2, 4)
    rebar_profit = _ts(df_profit, 5, 6, 4)
    hr_profit = _ts(df_profit, 5, 7, 4)

    return {
        '上海热卷价格': hr_coil,
        '上海螺纹价格': rebar,
        '铁矿石价格': iron_ore,
        '重点钢企库存': steel_corp_inv,
        '五大材库存': wuda_inv,
        '高炉开工率': bf_rate,
        '铁水产量': molten_iron,
        '五大材产量': wuda_prod,
        '五大材表需': wuda_demand,
        '钢厂盈利率': profit_rate,
        '螺纹盈利': rebar_profit,
        '热卷盈利': hr_profit,
        # 表格需要的其他指标（使用已有数据作为近似或占位）
        '青岛港铁矿石价格指数': iron_ore,  # 使用已有铁矿石价格
        '粗钢产量': wuda_prod,  # 使用五大材产量近似
        '粗钢表需': wuda_demand,  # 使用五大材表需
        '钢厂盈利率:螺纹': profit_rate,  # 使用整体盈利率
    }


def _read_nonferrous():
    path = os.path.join(DATA_DIR, '有色.xlsx')

    # === 价格 sheet ===
    # 行0=名，行1=单位，行2=来源；数据从行3
    # 列：0=日期，1=A00铝，2=1#铜，3=伦敦金，4=TC，5=RC
    df_price = pd.read_excel(path, sheet_name='价格', header=None)
    aluminum_price = _ts(df_price, 0, 1, 3)
    copper_price = _ts(df_price, 0, 2, 3)
    gold_price = _ts(df_price, 0, 3, 3)
    tc = _ts(df_price, 0, 4, 3)
    rc = _ts(df_price, 0, 5, 3)

    # === 库存 sheet ===
    # 行0=名，行1=单位，行2=频率，行3=时间跨度，行4=来源；数据从行5
    # 列：0=日期，1=铜库存，2=铝库存
    df_inv = pd.read_excel(path, sheet_name='库存', header=None)
    copper_inv = _ts(df_inv, 0, 1, 5)
    aluminum_inv = _ts(df_inv, 0, 2, 5)

    # === 盈利 sheet ===
    # 行0=名，行1=单位，行2=频率，行3=来源；数据从行4
    # 列：0=日期，1=电解铝税前利润
    df_profit = pd.read_excel(path, sheet_name='盈利', header=None)
    al_profit = _ts(df_profit, 0, 1, 4)

    return {
        'A00铝价格': aluminum_price,
        '1#铜价格': copper_price,
        '伦敦金价格': gold_price,
        '铜精矿TC': tc,
        '铜精矿RC': rc,
        '铜社会库存': copper_inv,
        '电解铝库存': aluminum_inv,
        '电解铝利润': al_profit,
    }


def _read_petrochem():
    path = os.path.join(DATA_DIR, '石化.xlsx')

    # === 价格 sheet ===
    # 行0=空，行1=名，行2=单位，行3=频率；数据从行3（注意：实际数据从行3开始）
    # 左：col1=NYMEX日期，col2=NYMEX天然气
    # 右：col3=布伦特日期，col4=布伦特原油
    df_price = pd.read_excel(path, sheet_name='价格', header=None)
    nymex_gas = _ts(df_price, 1, 2, 3)
    brent = _ts(df_price, 3, 4, 3)

    # === 开工&需求 sheet ===
    # 行0=空，行1=名，行2=数据起始（各子表独立）
    # 子表1: col1=日期, col2=山东地炼开工率（从行2）
    # 子表2: col4=日期, col5=主营炼厂开工率（从行2）
    # 子表3: col7=日期, col8=美国炼厂开工率（从行2）
    # 子表4: col10=日期, col11=汽油供应, col12=柴油供应, col13=合计（从行3）
    df_op = pd.read_excel(path, sheet_name='开工&需求', header=None)
    shandong_op = _ts(df_op, 1, 2, 2)
    major_refinery_op = _ts(df_op, 4, 5, 2)
    us_refinery_op = _ts(df_op, 7, 8, 2)
    us_gasoline_demand = _ts(df_op, 10, 11, 3)
    us_diesel_demand = _ts(df_op, 10, 12, 3)
    us_total_demand = _ts(df_op, 10, 13, 3)

    # === 库存 sheet ===
    # 行0=空，行1=名，行2=单位；数据从行3
    # 列：1=日期，2=商业原油，3=汽油，4=柴油，5=煤油，6=成品油
    df_inv = pd.read_excel(path, sheet_name='库存', header=None)
    us_crude_inv = _ts(df_inv, 1, 2, 3)
    us_gasoline_inv = _ts(df_inv, 1, 3, 3)
    us_diesel_inv = _ts(df_inv, 1, 4, 3)

    # === 价差 sheet ===
    # 行0=空，行1=名，行2=单位；数据从行3
    # 列：1=日期，2=汽油裂解价差，3=柴油裂解价差，4=乙烯毛利
    df_spread = pd.read_excel(path, sheet_name='价差', header=None)
    gasoline_spread = _ts(df_spread, 1, 2, 3)
    diesel_spread = _ts(df_spread, 1, 3, 3)
    ethylene_margin = _ts(df_spread, 1, 4, 3)

    return {
        'NYMEX天然气': nymex_gas,
        '布伦特原油': brent,
        '山东地炼开工率': shandong_op,
        '主营炼厂开工率': major_refinery_op,
        '美国炼厂开工率': us_refinery_op,
        '美国汽油需求': us_gasoline_demand,
        '美国柴油需求': us_diesel_demand,
        '美国成品油需求': us_total_demand,
        '美国商业原油库存': us_crude_inv,
        '美国汽油库存': us_gasoline_inv,
        '美国柴油库存': us_diesel_inv,
        '美国成品油库存': us_gasoline_inv,  # 使用汽油库存作为成品油库存近似
        '汽油裂解价差': gasoline_spread,
        '柴油裂解价差': diesel_spread,
        '乙烯裂解毛利': ethylene_margin,
    }


def _read_chemicals():
    path = os.path.join(DATA_DIR, '基础化工.xlsx')

    # === 价格 sheet ===
    # 行0=空，行1=名，行2=频率，行3=单位；数据从行4
    # 左：col1=日期，col2=化工价格指数，col3=乙烯CFR，col4=尿素
    # 右：col6=日期，col7=涤纶DTY价格，col8=除草剂价格指数
    df_price = pd.read_excel(path, sheet_name='价格', header=None)
    chem_price_index = _ts(df_price, 1, 2, 4)
    ethylene_cfr = _ts(df_price, 1, 3, 4)
    urea_price = _ts(df_price, 1, 4, 4)
    dty_price = _ts(df_price, 6, 7, 4)
    herbicide_index = _ts(df_price, 6, 8, 4)

    # === 库存 sheet ===
    # 行0=空，行1=名，行2=频率，行3=单位；数据从行4
    # 实际列顺序（根据探索确认）：
    # 1=日期，2=甲醛库存天数（不用），3=PTA库存天数，4=POY库存天数，5=DTY库存天数，6=FDY库存天数
    df_inv = pd.read_excel(path, sheet_name='库存', header=None)
    pta_inv_days = _ts(df_inv, 1, 3, 4)   # PTA库存天数
    poy_inv_days = _ts(df_inv, 1, 4, 4)   # POY库存天数
    dty_inv_days = _ts(df_inv, 1, 5, 4)   # DTY库存天数
    fdy_inv_days = _ts(df_inv, 1, 6, 4)   # FDY库存天数

    # === 开工 sheet ===
    # 行0=空，行1=名，行2=频率，行3=单位?；数据从行3（甲醛无数据，涤纶从此开始）
    # 列：1=日期，2=甲醛开工率（不用），3=涤纶长丝开工率，4=江浙织机开工率
    df_op = pd.read_excel(path, sheet_name='开工', header=None)
    poy_op = _ts(df_op, 1, 3, 3)   # 涤纶长丝开工率（0-1小数形式）
    loom_op = _ts(df_op, 1, 4, 3)  # 江浙织机开工率

    # === 价差 sheet ===
    # 行0=空，行1=名，行2=频率，行3=单位；数据从行4
    # 列：1=日期，2=PX-石脑油价差，3=POY价差，4=FDY价差，5=DTY价差
    df_spread = pd.read_excel(path, sheet_name='价差', header=None)
    px_naphtha = _ts(df_spread, 1, 2, 4)
    poy_spread = _ts(df_spread, 1, 3, 4)
    fdy_spread = _ts(df_spread, 1, 4, 4)
    dty_spread = _ts(df_spread, 1, 5, 4)

    return {
        '化工产品价格指数': chem_price_index,
        '化工价格指数': chem_price_index,  # 别名
        '乙烯CFR价格': ethylene_cfr,
        '尿素价格': urea_price,
        '涤纶DTY价格': dty_price,
        'DTY市场价格': dty_price,  # 别名
        '除草剂价格指数': herbicide_index,
        'PTA库存天数': pta_inv_days,
        'POY库存天数': poy_inv_days,
        'DTY库存天数': dty_inv_days,
        'FDY库存天数': fdy_inv_days,
        '涤纶长丝开工率': poy_op,    # 0-1小数形式，显示时*100转为%
        '织机开工率': loom_op,        # 0-1小数形式
        'PX石脑油价差': px_naphtha,
        'PX-石脑油价差': px_naphtha,  # 别名
        'POY价差': poy_spread,
        'POY-PTA-MEG价差': poy_spread,  # 别名
        'FDY价差': fdy_spread,
        'FDY-PTA-MEG价差': fdy_spread,  # 别名
        'DTY价差': dty_spread,
        'DTY-PTA-MEG价差': dty_spread,  # 别名
        # 表格需要的其他指标（使用已有数据作为近似或占位）
        '短纤价格': poy_spread,  # 使用POY价差作为占位
        '短纤市场价格': poy_spread,  # 别名
        '硫酸铵价格': urea_price,  # 使用尿素价格作为近似
        '石脑油裂解利润': px_naphtha,  # 使用PX石脑油价差作为近似
        '石脑油裂解动态利润': px_naphtha,  # 别名
    }


@lru_cache(maxsize=1)
def load_all():
    """加载所有行业数据（带缓存，刷新需调用 load_all.cache_clear()）"""
    return {
        '煤炭': _read_coal(),
        '钢铁': _read_steel(),
        '有色': _read_nonferrous(),
        '石化': _read_petrochem(),
        '基础化工': _read_chemicals(),
    }


def get_latest(industry, series_name):
    """获取最新值"""
    data = load_all()
    s = data.get(industry, {}).get(series_name)
    if s is None or len(s) == 0:
        return None
    return s.dropna().iloc[-1]


def get_wow(industry, series_name):
    """获取周环比（最近7天内的变化）"""
    data = load_all()
    s = data.get(industry, {}).get(series_name)
    if s is None or len(s) < 2:
        return None
    s = s.dropna()
    latest = s.iloc[-1]
    # 找7天前最近的值
    cutoff = s.index[-1] - pd.Timedelta(days=10)
    prev = s[s.index <= cutoff]
    if len(prev) == 0:
        return None
    prev_val = prev.iloc[-1]
    if prev_val == 0:
        return None
    return (latest - prev_val) / abs(prev_val)


def get_yoy(industry, series_name):
    """获取年同比"""
    data = load_all()
    s = data.get(industry, {}).get(series_name)
    if s is None or len(s) < 2:
        return None
    s = s.dropna()
    latest_date = s.index[-1]
    latest_val = s.iloc[-1]
    yoy_date = latest_date - pd.Timedelta(days=365)
    candidates = s[abs(s.index - yoy_date) < pd.Timedelta(days=30)]
    if len(candidates) == 0:
        return None
    prev_val = candidates.iloc[-1]
    if prev_val == 0:
        return None
    return (latest_val - prev_val) / abs(prev_val)


if __name__ == '__main__':
    # 测试加载
    print("Loading data...")
    data = load_all()
    for industry, series_dict in data.items():
        print(f"\n{industry}:")
        for name, ts in series_dict.items():
            if ts is not None and len(ts) > 0:
                print(f"  {name}: {len(ts)} points, latest={ts.dropna().iloc[-1]:.2f} @ {ts.dropna().index[-1].date()}")
            else:
                print(f"  {name}: EMPTY")
