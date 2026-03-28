"""
导出数据为JSON，供HTML版本使用
"""
import json
import os
from data_loader import load_all
from index_calculator import compute_all, get_current_score, get_score_wow, get_score_history
from chart_config import INDUSTRY_CONFIG, INDUSTRIES, TREND, SEASONAL, get_prosperity_level

def series_to_json(s):
    """将pandas Series转换为JSON列表"""
    if s is None or len(s) == 0:
        return []
    s = s.dropna()
    return [
        {'date': idx.strftime('%Y-%m-%d'), 'value': float(val)}
        for idx, val in s.items()
    ]

def main():
    print("Loading data...")
    data = load_all()
    scores = compute_all()
    
    # 构建导出数据结构
    export_data = {
        'industries': [],
        'industryData': {},
    }
    
    for industry in INDUSTRIES:
        cfg = INDUSTRY_CONFIG[industry]
        score_series = scores.get(industry, [])
        
        # 基础信息
        industry_info = {
            'name': industry,
            'color': cfg['color'],
            'summaryText': cfg.get('summary_text', ''),
            'currentScore': None,
            'scoreWow': None,
            'prosperityLevel': '无数据',
            'levelColor': '#666',
        }
        
        # 景气指数
        if len(score_series) > 0:
            current = score_series.dropna().iloc[-1] if len(score_series.dropna()) > 0 else None
            if current is not None:
                industry_info['currentScore'] = round(float(current), 1)
                level, level_color = get_prosperity_level(current)
                industry_info['prosperityLevel'] = level
                industry_info['levelColor'] = level_color
                
                if len(score_series.dropna()) >= 2:
                    wow = float(score_series.dropna().iloc[-1] - score_series.dropna().iloc[-2])
                    industry_info['scoreWow'] = round(wow, 1)
        
        # KPI卡片数据
        kpi_cards = []
        for kpi in cfg.get('kpi_cards', []):
            series_name = kpi['series']
            series_data = data.get(industry, {}).get(series_name)
            
            kpi_data = {
                'label': kpi['label'],
                'unit': kpi.get('unit', ''),
                'direction': kpi.get('direction', 1),
                'scale': kpi.get('scale', 1),
                'currentValue': None,
                'wow': None,
                'yoy': None,
            }
            
            if series_data is not None and len(series_data) > 0:
                s = series_data.dropna()
                if len(s) > 0:
                    kpi_data['currentValue'] = round(float(s.iloc[-1]) * kpi.get('scale', 1), 2)
                    
                    # WoW
                    if len(s) >= 2:
                        cutoff = s.index[-1] - __import__('pandas').Timedelta(days=10)
                        prev = s[s.index <= cutoff]
                        if len(prev) > 0 and prev.iloc[-1] != 0:
                            wow = (s.iloc[-1] - prev.iloc[-1]) / abs(prev.iloc[-1])
                            kpi_data['wow'] = round(float(wow), 4)
                    
                    # YoY
                    if len(s) >= 2:
                        latest_date = s.index[-1]
                        yoy_date = latest_date - __import__('pandas').Timedelta(days=365)
                        candidates = s[abs(s.index - yoy_date) < __import__('pandas').Timedelta(days=30)]
                        if len(candidates) > 0 and candidates.iloc[-1] != 0:
                            yoy = (s.iloc[-1] - candidates.iloc[-1]) / abs(candidates.iloc[-1])
                            kpi_data['yoy'] = round(float(yoy), 4)
            
            kpi_cards.append(kpi_data)
        
        industry_info['kpiCards'] = kpi_cards
        
        # 表格数据 - 所有PDF表格中的指标
        table_metrics = []
        for metric in cfg.get('table_metrics', []):
            series_name = metric['series']
            series_data = data.get(industry, {}).get(series_name)
            
            metric_data = {
                'category': metric.get('category', ''),  # 分类：价格/库存/需求/盈利/生产
                'label': metric['label'],
                'unit': metric.get('unit', ''),
                'direction': metric.get('direction', 1),
                'scale': metric.get('scale', 1),
                'currentValue': None,
                'wow': None,
                'yoy': None,
                'vs5YearAvg': None,  # 较五年同期平均变化
                'updateTime': None,
                'frequency': None,
            }
            
            if series_data is not None and len(series_data) > 0:
                s = series_data.dropna()
                if len(s) > 0:
                    metric_data['currentValue'] = round(float(s.iloc[-1]) * metric.get('scale', 1), 2)
                    metric_data['updateTime'] = s.index[-1].strftime('%Y-%m-%d')
                    
                    # WoW
                    if len(s) >= 2:
                        cutoff = s.index[-1] - __import__('pandas').Timedelta(days=10)
                        prev = s[s.index <= cutoff]
                        if len(prev) > 0 and prev.iloc[-1] != 0:
                            wow = (s.iloc[-1] - prev.iloc[-1]) / abs(prev.iloc[-1])
                            metric_data['wow'] = round(float(wow), 4)
                    
                    # YoY
                    if len(s) >= 2:
                        latest_date = s.index[-1]
                        yoy_date = latest_date - __import__('pandas').Timedelta(days=365)
                        candidates = s[abs(s.index - yoy_date) < __import__('pandas').Timedelta(days=30)]
                        if len(candidates) > 0 and candidates.iloc[-1] != 0:
                            yoy = (s.iloc[-1] - candidates.iloc[-1]) / abs(candidates.iloc[-1])
                            metric_data['yoy'] = round(float(yoy), 4)
                    
                    # Vs 5-Year Average (计算当前值与过去5年同期平均值的对比)
                    if len(s) >= 260:  # 至少5年数据
                        latest_date = s.index[-1]
                        latest_month = latest_date.month
                        latest_day = latest_date.day
                        
                        # 收集过去5年同期的数据（同一天或相近的日期）
                        five_year_values = []
                        for year_offset in range(1, 6):  # 前1-5年
                            try:
                                target_date = latest_date.replace(year=latest_date.year - year_offset)
                                # 找最近的数据点（前后7天内）
                                window_start = target_date - __import__('pandas').Timedelta(days=7)
                                window_end = target_date + __import__('pandas').Timedelta(days=7)
                                nearby_data = s[(s.index >= window_start) & (s.index <= window_end)]
                                if len(nearby_data) > 0:
                                    # 取最接近目标日期的值
                                    closest_idx = nearby_data.index.get_indexer([target_date], method='nearest')[0]
                                    five_year_values.append(nearby_data.iloc[closest_idx])
                            except:
                                continue
                        
                        if len(five_year_values) >= 3:  # 至少3年有数据
                            five_year_avg = sum(five_year_values) / len(five_year_values)
                            if five_year_avg != 0:
                                vs_5year_avg = (s.iloc[-1] - five_year_avg) / abs(five_year_avg)
                                metric_data['vs5YearAvg'] = round(float(vs_5year_avg), 4)
            
            table_metrics.append(metric_data)
        
        industry_info['tableMetrics'] = table_metrics
        
        # 图表数据
        charts = []
        for chart_cfg in cfg.get('charts', []):
            chart_data = {
                'id': chart_cfg['id'],
                'title': chart_cfg.get('title', ''),
                'defaultType': chart_cfg.get('default_type', TREND),
                'dualAxis': chart_cfg.get('dual_axis', False),
                'unitScale': chart_cfg.get('unit_scale', 1),
                'yaxis': chart_cfg.get('yaxis', {}),
                'yaxis2': chart_cfg.get('yaxis2', {}),
                'series': []
            }
            
            for s_cfg in chart_cfg.get('series', []):
                series_name = s_cfg['name']
                series_raw = data.get(industry, {}).get(series_name)
                
                s_data = {
                    'name': s_cfg['name'],
                    'label': s_cfg['label'],
                    'unit': s_cfg.get('unit', ''),
                    'color': s_cfg['color'],
                    'scale': s_cfg.get('scale', 1),
                    'axis': s_cfg.get('axis', 'y1'),
                    'data': series_to_json(series_raw)
                }
                chart_data['series'].append(s_data)
            
            charts.append(chart_data)
        
        industry_info['charts'] = charts
        
        # 景气指数历史（用于sparkline）
        history = get_score_history(industry, months=12)
        industry_info['scoreHistory'] = series_to_json(history)
        
        export_data['industries'].append(industry)
        export_data['industryData'][industry] = industry_info
    
    # 保存JSON
    output_path = os.path.join(os.path.dirname(__file__), 'assets', 'data.json')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    
    print(f"Data exported to: {output_path}")
    
    # 同时输出一个内联版本的JS文件
    js_output_path = os.path.join(os.path.dirname(__file__), 'data.js')
    with open(js_output_path, 'w', encoding='utf-8') as f:
        f.write(f"const INDUSTRY_DATA = {json.dumps(export_data, ensure_ascii=False, indent=2)};\n")
    
    print(f"JS data exported to: {js_output_path}")

if __name__ == '__main__':
    main()
