"""
app.py - 周期行业景气度跟踪数据可视化网页
"""
import dash
from dash import dcc, html, Input, Output, State, callback_context, ALL, MATCH
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from datetime import datetime, date

from data_loader import load_all, get_latest, get_wow, get_yoy
from chart_config import INDUSTRY_CONFIG, INDUSTRIES, TREND, SEASONAL, get_prosperity_level
from index_calculator import compute_all, get_current_score, get_score_wow, get_score_history

# ============================================================
# 初始化
# ============================================================
app = dash.Dash(
    __name__,
    suppress_callback_exceptions=True,
    title='周期行业景气度跟踪',
    meta_tags=[{'name': 'viewport', 'content': 'width=device-width, initial-scale=1'}],
)
server = app.server  # 用于 gunicorn 部署

# 季节图颜色方案（越近年份越深）
YEAR_COLORS = [
    '#2d3a4a', '#3a4f6e', '#4c6a8f', '#5a85b0',
    '#6fa3d0', '#85bde3', '#f0a500', '#ff7733',
]
CURRENT_YEAR_COLOR = '#ff6b35'  # 当年高亮

# ============================================================
# 辅助函数：构建图表
# ============================================================
def _make_trend_fig(industry: str, chart_cfg: dict) -> go.Figure:
    """构建趋势图"""
    data = load_all()
    ind_data = data.get(industry, {})
    series_list = chart_cfg.get('series', [])
    dual = chart_cfg.get('dual_axis', False)

    if dual:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
    else:
        fig = go.Figure()

    for s in series_list:
        ts = ind_data.get(s['name'])
        if ts is None or len(ts) == 0:
            continue

        # 单位缩放
        scale = s.get('scale', 1)
        unit_scale = chart_cfg.get('unit_scale', 1)
        vals = ts.values * scale * unit_scale

        is_y2 = dual and s.get('axis') == 'y2'
        trace = go.Scatter(
            x=ts.index,
            y=vals,
            name=s['label'],
            line={'color': s['color'], 'width': 1.5},
            hovertemplate=f"{s['label']}: %{{y:.2f}} {s.get('unit', '')}<br>%{{x|%Y-%m-%d}}<extra></extra>",
        )
        if dual:
            fig.add_trace(trace, secondary_y=is_y2)
        else:
            fig.add_trace(trace)

    yax = chart_cfg.get('yaxis', {})
    yax2 = chart_cfg.get('yaxis2', {})

    layout_updates = dict(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font={'color': '#abb2bf', 'size': 11},
        margin={'t': 30, 'b': 60, 'l': 55, 'r': 15 if not dual else 55},
        legend={'orientation': 'h', 'y': -0.15, 'x': 0, 'font': {'size': 10}},
        hovermode='x unified',
        xaxis={
            'gridcolor': '#2d3748', 'showgrid': True,
            'rangeslider': {'visible': True, 'thickness': 0.06},
            'type': 'date',
        },
        yaxis={
            'gridcolor': '#2d3748', 'showgrid': True,
            'title': yax.get('title', ''),
            'zeroline': yax.get('zeroline', False),
            'zerolinecolor': '#666',
        },
    )
    if dual:
        layout_updates['yaxis2'] = {
            'gridcolor': '#2d3748', 'showgrid': False,
            'title': yax2.get('title', ''),
            'overlaying': 'y', 'side': 'right',
        }
    # 零轴参考线
    if yax.get('zeroline'):
        layout_updates['shapes'] = [{
            'type': 'line', 'x0': 0, 'x1': 1, 'xref': 'paper',
            'y0': 0, 'y1': 0, 'yref': 'y',
            'line': {'color': '#666', 'width': 1, 'dash': 'dot'},
        }]

    fig.update_layout(**layout_updates)
    return fig


def _make_seasonal_fig(industry: str, chart_cfg: dict) -> go.Figure:
    """构建季节图（X轴=MM-DD，每年一条线）"""
    data = load_all()
    ind_data = data.get(industry, {})
    series_list = chart_cfg.get('series', [])

    fig = go.Figure()
    current_year = datetime.now().year

    for s in series_list:
        ts = ind_data.get(s['name'])
        if ts is None or len(ts) == 0:
            continue

        scale = s.get('scale', 1)
        unit_scale = chart_cfg.get('unit_scale', 1)

        # 按年分组
        df = ts.to_frame('val')
        df['year'] = df.index.year
        df['mmdd'] = df.index.strftime('%m-%d')
        df['val'] = df['val'] * scale * unit_scale

        years = sorted(df['year'].unique())
        n_years = len(years)

        for i, yr in enumerate(years):
            yr_df = df[df['year'] == yr].sort_values('mmdd')
            if len(yr_df) == 0:
                continue

            is_current = (yr == current_year)
            color_idx = min(i, len(YEAR_COLORS) - 1)
            color = CURRENT_YEAR_COLOR if is_current else YEAR_COLORS[color_idx]
            width = 2.5 if is_current else 1.2
            opacity = 1.0 if is_current or i >= n_years - 3 else 0.6

            # 生成假日期用于统一X轴（固定为2000年）
            x_dates = []
            for mmdd in yr_df['mmdd']:
                try:
                    x_dates.append(pd.Timestamp(f'2000-{mmdd}'))
                except Exception:
                    x_dates.append(None)

            fig.add_trace(go.Scatter(
                x=x_dates,
                y=yr_df['val'].values,
                name=str(yr),
                line={'color': color, 'width': width},
                opacity=opacity,
                hovertemplate=f"{yr}: %{{y:.1f}} {s.get('unit', '')}<extra></extra>",
            ))

    yax = chart_cfg.get('yaxis', {})
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font={'color': '#abb2bf', 'size': 11},
        margin={'t': 30, 'b': 60, 'l': 55, 'r': 15},
        legend={'orientation': 'h', 'y': -0.15, 'x': 0, 'font': {'size': 10}},
        hovermode='x',
        xaxis={
            'gridcolor': '#2d3748', 'showgrid': True,
            'type': 'date',
            'tickformat': '%m月',
            'dtick': 'M1',
        },
        yaxis={
            'gridcolor': '#2d3748', 'showgrid': True,
            'title': yax.get('title', ''),
        },
    )
    return fig


def _make_sparkline(industry: str) -> go.Figure:
    """制作总览页景气指数sparkline"""
    s = get_score_history(industry, months=12)
    fig = go.Figure()
    if len(s) > 0:
        color = INDUSTRY_CONFIG[industry]['color']
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values,
            fill='tozeroy',
            fillcolor=f'rgba({_hex_to_rgb(color)},0.15)',
            line={'color': color, 'width': 1.5},
            hoverinfo='skip',
        ))
    fig.update_layout(
        margin={'t': 0, 'b': 0, 'l': 0, 'r': 0},
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        showlegend=False,
        xaxis={'visible': False},
        yaxis={'visible': False, 'range': [0, 100]},
        height=60,
    )
    return fig


def _hex_to_rgb(hex_color: str) -> str:
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f'{r},{g},{b}'


# ============================================================
# 布局组件
# ============================================================
def make_overview_card(industry: str) -> html.Div:
    """总览页行业景气卡片"""
    score = get_current_score(industry)
    wow = get_score_wow(industry)
    cfg = INDUSTRY_CONFIG[industry]
    color = cfg['color']

    if score is not None:
        score_disp = f'{score:.1f}'
        level_label, level_color = get_prosperity_level(score)
    else:
        score_disp = '--'
        level_label, level_color = '无数据', '#666'

    if wow is not None:
        wow_sign = '+' if wow >= 0 else ''
        wow_disp = f'{wow_sign}{wow:.1f}'
        wow_color = '#98c379' if wow >= 0 else '#e06c75'
    else:
        wow_disp = '--'
        wow_color = '#666'

    sparkline = _make_sparkline(industry)

    return html.Div(
        id={'type': 'overview-card', 'industry': industry},
        className='overview-card',
        style={'borderLeft': f'4px solid {color}', 'cursor': 'pointer'},
        children=[
            html.Div(className='card-header', children=[
                html.Span(industry, className='card-industry-name'),
                html.Span(level_label, className='card-level-badge',
                          style={'backgroundColor': level_color}),
            ]),
            html.Div(className='card-body', children=[
                html.Div(className='card-score', children=[
                    html.Span(score_disp, className='score-number', style={'color': color}),
                    html.Span('景气指数', className='score-label'),
                ]),
                html.Div(className='card-wow', children=[
                    html.Span('周环比: ', style={'color': '#666'}),
                    html.Span(wow_disp, style={'color': wow_color, 'fontWeight': 'bold'}),
                ]),
            ]),
            dcc.Graph(
                figure=sparkline,
                config={'displayModeBar': False},
                style={'height': '60px'},
            ),
        ],
    )


def make_kpi_card(industry: str, kpi: dict) -> html.Div:
    """行业详情页指标卡片"""
    val = get_latest(industry, kpi['series'])
    wow = get_wow(industry, kpi['series'])
    yoy = get_yoy(industry, kpi['series'])
    scale = kpi.get('scale', 1)

    if val is not None:
        val_disp = f'{val * scale:,.1f}' if val * scale >= 100 else f'{val * scale:.2f}'
    else:
        val_disp = '--'

    wow_str, yoy_str = '--', '--'
    wow_color, yoy_color = '#666', '#666'
    if wow is not None:
        direction = kpi.get('direction', 1)
        wow_pct = wow * 100
        wow_str = f'{"+"}' if wow >= 0 else ''
        wow_str = f'{wow_str}{wow_pct:.1f}%'
        # 涨跌与景气同向→绿色
        wow_color = '#98c379' if (wow >= 0) == (direction > 0) else '#e06c75'
    if yoy is not None:
        yoy_pct = yoy * 100
        yoy_str = f'{"+"}' if yoy >= 0 else ''
        yoy_str = f'{yoy_str}{yoy_pct:.1f}%'
        direction = kpi.get('direction', 1)
        yoy_color = '#98c379' if (yoy >= 0) == (direction > 0) else '#e06c75'

    return html.Div(className='kpi-card', children=[
        html.Div(kpi['label'], className='kpi-label'),
        html.Div([
            html.Span(val_disp, className='kpi-value'),
            html.Span(f" {kpi.get('unit', '')}", className='kpi-unit'),
        ]),
        html.Div(className='kpi-changes', children=[
            html.Span('WoW: ', style={'color': '#555'}),
            html.Span(wow_str, style={'color': wow_color}),
            html.Span('  YoY: ', style={'color': '#555'}),
            html.Span(yoy_str, style={'color': yoy_color}),
        ]),
    ])


def make_chart_panel(industry: str, chart_cfg: dict) -> html.Div:
    """图表面板（含趋势/季节切换按钮）"""
    chart_id = chart_cfg['id']
    default_type = chart_cfg.get('default_type', TREND)
    title = chart_cfg.get('title', '')

    return html.Div(className='chart-panel', children=[
        html.Div(className='chart-header', children=[
            html.Span(title, className='chart-title'),
            html.Div(className='chart-type-switch', children=[
                dcc.RadioItems(
                    id={'type': 'chart-type', 'industry': industry, 'chart': chart_id},
                    options=[
                        {'label': '趋势图', 'value': TREND},
                        {'label': '季节图', 'value': SEASONAL},
                    ],
                    value=default_type,
                    inline=True,
                    className='chart-radio',
                    inputClassName='chart-radio-input',
                    labelClassName='chart-radio-label',
                ),
            ]),
        ]),
        dcc.Graph(
            id={'type': 'chart-graph', 'industry': industry, 'chart': chart_id},
            config={'displayModeBar': True, 'modeBarButtonsToRemove': ['lasso2d', 'select2d']},
            style={'height': '300px'},
        ),
    ])


def make_industry_tab(industry: str) -> html.Div:
    """行业详情页内容"""
    cfg = INDUSTRY_CONFIG[industry]
    color = cfg['color']

    kpi_cards = [make_kpi_card(industry, kpi) for kpi in cfg.get('kpi_cards', [])]
    chart_panels = [make_chart_panel(industry, c) for c in cfg.get('charts', [])]

    # 分成2×2网格
    charts_grid = html.Div(className='charts-grid', children=[
        html.Div(className='chart-cell', children=[cp]) for cp in chart_panels
    ])

    return html.Div(className='industry-tab-content', children=[
        # 正文摘要
        html.Div(
            className='summary-box',
            style={'borderLeft': f'3px solid {color}'},
            children=[
                html.Div('本周观点', className='summary-title'),
                html.P(cfg.get('summary_text', ''), className='summary-text'),
            ],
        ),
        # KPI指标卡片
        html.Div(className='kpi-row', children=kpi_cards),
        # 图表网格
        charts_grid,
    ])


# ============================================================
# 主布局
# ============================================================
update_time = datetime.now().strftime('%Y-%m-%d')

app.layout = html.Div(className='app-container', children=[
    # 顶部标题栏
    html.Div(className='header', children=[
        html.H1('周期行业景气度跟踪', className='header-title'),
        html.Div([
            html.Span(f'更新时间: {update_time}', className='header-date'),
            html.Button('🔄 刷新数据', id='refresh-btn', className='refresh-btn', n_clicks=0),
        ], className='header-right'),
    ]),

    # 刷新通知
    html.Div(id='refresh-status', style={'display': 'none'}),

    # Tab 导航
    dcc.Tabs(
        id='main-tabs',
        value='总览',
        className='main-tabs',
        children=[
            dcc.Tab(label='总览', value='总览', className='tab', selected_className='tab-selected'),
        ] + [
            dcc.Tab(label=ind, value=ind, className='tab', selected_className='tab-selected')
            for ind in INDUSTRIES
        ],
    ),

    # Tab 内容区
    html.Div(id='tab-content', className='tab-content'),
])


# ============================================================
# 回调
# ============================================================

@app.callback(
    Output('tab-content', 'children'),
    Input('main-tabs', 'value'),
)
def render_tab(tab_value):
    if tab_value == '总览':
        cards = [make_overview_card(ind) for ind in INDUSTRIES]
        return html.Div([
            html.Div(className='overview-grid', children=cards),
        ])
    elif tab_value in INDUSTRIES:
        return make_industry_tab(tab_value)
    return html.Div('未知页面')


@app.callback(
    Output({'type': 'chart-graph', 'industry': MATCH, 'chart': MATCH}, 'figure'),
    Input({'type': 'chart-type', 'industry': MATCH, 'chart': MATCH}, 'value'),
    State({'type': 'chart-type', 'industry': MATCH, 'chart': MATCH}, 'id'),
)
def update_chart(chart_type, component_id):
    industry = component_id['industry']
    chart_id = component_id['chart']
    cfg = INDUSTRY_CONFIG.get(industry, {})
    charts = cfg.get('charts', [])
    chart_cfg = next((c for c in charts if c['id'] == chart_id), None)

    if chart_cfg is None:
        return go.Figure()

    if chart_type == SEASONAL:
        return _make_seasonal_fig(industry, chart_cfg)
    else:
        return _make_trend_fig(industry, chart_cfg)


@app.callback(
    Output('refresh-status', 'children'),
    Output('refresh-status', 'style'),
    Input('refresh-btn', 'n_clicks'),
    prevent_initial_call=True,
)
def refresh_data(n_clicks):
    if n_clicks > 0:
        from data_loader import load_all as _load
        from index_calculator import compute_all as _calc
        _load.cache_clear()
        _calc.cache_clear()
        _load()  # 重新加载
        _calc()
        return '数据已刷新', {'display': 'block', 'color': '#98c379', 'padding': '4px 12px', 'textAlign': 'right', 'fontSize': '12px'}
    return '', {'display': 'none'}


# ============================================================
# 运行
# ============================================================
if __name__ == '__main__':
    app.run(debug=True, port=8050, host='0.0.0.0')
