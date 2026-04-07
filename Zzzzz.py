import random
import numpy as np
import pandas as pd
from datetime import datetime

import dash
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# ─────────────────────────────────────────────────────────────
#  MARKET DATA
# ─────────────────────────────────────────────────────────────
CURRENCIES  = ["USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD"]
TENORS      = ["1Y", "2Y", "3Y", "5Y", "7Y", "10Y"]
TENOR_YEARS = [1, 2, 3, 5, 7, 10]

BASE_CURVES = {
    "USD": [5.30, 4.90, 4.70, 4.50, 4.45, 4.40],
    "EUR": [3.80, 3.50, 3.30, 3.10, 3.05, 3.00],
    "GBP": [5.10, 4.75, 4.55, 4.35, 4.30, 4.25],
    "JPY": [0.10, 0.25, 0.40, 0.65, 0.80, 1.00],
    "CHF": [1.20, 1.10, 1.05, 1.00, 0.98, 0.95],
    "AUD": [4.50, 4.30, 4.20, 4.10, 4.05, 4.00],
    "CAD": [5.00, 4.70, 4.55, 4.35, 4.30, 4.25],
}

FUNDING_SPREAD = {
    "USD": 0.05, "EUR": 0.03, "GBP": 0.04,
    "JPY": 0.02, "CHF": 0.02, "AUD": 0.05, "CAD": 0.04,
}

CCY_COLORS = {
    "USD": "#00d4ff", "EUR": "#a78bfa", "GBP": "#f59e0b",
    "JPY": "#f43f5e", "CHF": "#10b981", "AUD": "#fb923c", "CAD": "#e879f9",
}

FLAGS = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧",
    "JPY": "🇯🇵", "CHF": "🇨🇭", "AUD": "🇦🇺", "CAD": "🇨🇦",
}

# ─────────────────────────────────────────────────────────────
#  THEME
# ─────────────────────────────────────────────────────────────
BG       = "#080c12"
PANEL    = "#0d1520"
BORDER   = "#1a2a3a"
TXT_DIM  = "#3a5060"
TXT_MID  = "#6080a0"
TXT_MAIN = "#c8d0e0"
GREEN    = "#00ff88"
CYAN     = "#00d4ff"
YELLOW   = "#f0c040"
RED      = "#ff4466"
PURPLE   = "#a080ff"

PLOTLY_LAYOUT = dict(
    paper_bgcolor=PANEL,
    plot_bgcolor=PANEL,
    font=dict(family="IBM Plex Mono, Courier New, monospace", color=TXT_MAIN, size=11),
    margin=dict(l=10, r=10, t=28, b=10),
    xaxis=dict(gridcolor=BORDER, zerolinecolor=BORDER, tickcolor=TXT_DIM, linecolor=BORDER),
    yaxis=dict(gridcolor=BORDER, zerolinecolor=BORDER, tickcolor=TXT_DIM, linecolor=BORDER),
)

# ─────────────────────────────────────────────────────────────
#  ENGINE
# ─────────────────────────────────────────────────────────────
def live_curves():
    return {
        ccy: [max(0.001, r + random.gauss(0, 0.025)) for r in BASE_CURVES[ccy]]
        for ccy in CURRENCIES
    }

def compute_metrics(curves, horizon=0.5):
    rows = []
    for ccy in CURRENCIES:
        c    = curves[ccy]
        fund = c[0] + FUNDING_SPREAD[ccy]
        for i in range(1, len(TENORS)):
            carry    = (c[i] - fund) * horizon
            rolldown = (c[i] - c[i-1]) * horizon
            total    = carry + rolldown
            dv01     = TENOR_YEARS[i] * 0.0001 * 1_000_000
            be       = total / (TENOR_YEARS[i] * 100) if TENOR_YEARS[i] else 0
            signal   = ("STRONG BUY" if total > 0.004 else
                        "BUY"        if total > 0.002 else
                        "NEUTRAL"    if total > 0     else "AVOID")
            rows.append(dict(
                ccy=ccy, flag=FLAGS[ccy], tenor=TENORS[i],
                rate=round(c[i]*100, 3), funding=round(fund*100, 3),
                carry=round(carry*100, 2), rolldown=round(rolldown*100, 2),
                total=round(total*100, 2), dv01=int(dv01),
                breakeven=round(be*100, 2), signal=signal,
            ))
    return pd.DataFrame(rows).sort_values("total", ascending=False).reset_index(drop=True)

# ─────────────────────────────────────────────────────────────
#  APP LAYOUT
# ─────────────────────────────────────────────────────────────
app = dash.Dash(
    __name__,
    title="Carry · Roll-Down Monitor",
    update_title=None,
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)

MONO = "IBM Plex Mono, Courier New, monospace"

def kpi_card(label, value, sub, color, idx):
    return html.Div([
        html.Div(style={"height": "3px", "background": color, "borderRadius": "2px 2px 0 0"}),
        html.Div([
            html.Div(label, style={"fontSize": "10px", "color": TXT_DIM,
                                   "letterSpacing": "0.12em", "marginBottom": "8px"}),
            html.Div(value, id=f"kpi-val-{idx}",
                     style={"fontSize": "26px", "fontWeight": "700",
                            "color": color, "letterSpacing": "-0.02em"}),
            html.Div(sub, id=f"kpi-sub-{idx}",
                     style={"fontSize": "11px", "color": TXT_MID, "marginTop": "4px"}),
        ], style={"padding": "14px 16px 14px"}),
    ], style={
        "background": PANEL, "border": f"1px solid {BORDER}",
        "borderRadius": "8px", "flex": "1", "minWidth": "0",
        "fontFamily": MONO,
    })

app.layout = html.Div([
    # live store
    dcc.Store(id="store-curves"),
    dcc.Store(id="store-history", data={ccy: [BASE_CURVES[ccy][3]] for ccy in CURRENCIES}),
    dcc.Interval(id="interval", interval=2500, n_intervals=0),

    # ── HEADER ──────────────────────────────────────
    html.Div([
        html.Div([
            html.Span("● ", style={"color": GREEN, "fontSize": "10px"}),
            html.Span("CARRY · ROLL-DOWN MONITOR",
                      style={"color": CYAN, "fontSize": "14px",
                             "fontWeight": "700", "letterSpacing": "0.15em"}),
            html.Span("  |  IRS · XCCY · FX SWAP",
                      style={"color": TXT_DIM, "fontSize": "11px"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "6px"}),
        html.Div([
            html.Span(id="clock", style={"color": CYAN, "fontSize": "11px"}),
            html.Span("  LIVE",
                      style={"background": "#0f2030", "border": f"1px solid {BORDER}",
                             "borderRadius": "4px", "padding": "3px 10px",
                             "color": GREEN, "fontSize": "10px", "marginLeft": "12px"}),
        ], style={"display": "flex", "alignItems": "center"}),
    ], style={
        "background": "#0d1117", "borderBottom": f"1px solid {BORDER}",
        "padding": "12px 28px", "display": "flex",
        "justifyContent": "space-between", "alignItems": "center",
        "fontFamily": MONO,
    }),

    # ── BODY ────────────────────────────────────────
    html.Div([

        # KPI row
        html.Div([
            kpi_card("AVG CARRY",     "—", "6M horizon",       GREEN,  0),
            kpi_card("AVG ROLL-DOWN", "—", "6M horizon",       CYAN,   1),
            kpi_card("BEST PAIR",     "—", "—",                YELLOW, 2),
            kpi_card("POSITIVE OPP.", "—", "pairs with C+R>0", PURPLE, 3),
        ], style={"display": "flex", "gap": "12px", "marginBottom": "20px"}),

        # Controls
        html.Div([
            html.Span("HORIZON", style={"color": TXT_DIM, "fontSize": "11px", "marginRight": "8px"}),
            dcc.RadioItems(
                id="horizon",
                options=[{"label": "3M", "value": 0.25},
                         {"label": "6M", "value": 0.5},
                         {"label": "1Y", "value": 1.0}],
                value=0.5,
                inline=True,
                inputStyle={"marginRight": "4px"},
                labelStyle={"marginRight": "16px", "cursor": "pointer",
                            "fontSize": "12px", "color": TXT_MID, "fontFamily": MONO},
            ),
            html.Span("  |  ", style={"color": BORDER}),
            html.Span("CURRENCY", style={"color": TXT_DIM, "fontSize": "11px",
                                          "marginLeft": "8px", "marginRight": "8px"}),
            dcc.Dropdown(
                id="ccy-filter",
                options=[{"label": f"{FLAGS[c]} {c}", "value": c} for c in CURRENCIES],
                multi=True, placeholder="All currencies",
                style={"background": PANEL, "border": f"1px solid {BORDER}",
                       "borderRadius": "4px", "minWidth": "260px",
                       "fontSize": "12px", "fontFamily": MONO},
                className="dark-dropdown",
            ),
            html.Span("  |  ", style={"color": BORDER}),
            html.Span("TENOR", style={"color": TXT_DIM, "fontSize": "11px",
                                       "marginLeft": "8px", "marginRight": "8px"}),
            dcc.Dropdown(
                id="tenor-filter",
                options=[{"label": t, "value": t} for t in TENORS[1:]],
                multi=True, placeholder="All tenors",
                style={"background": PANEL, "border": f"1px solid {BORDER}",
                       "borderRadius": "4px", "minWidth": "200px",
                       "fontSize": "12px", "fontFamily": MONO},
            ),
            html.Span("  |  ", style={"color": BORDER}),
            html.Span("SORT", style={"color": TXT_DIM, "fontSize": "11px",
                                      "marginLeft": "8px", "marginRight": "8px"}),
            dcc.Dropdown(
                id="sort-col",
                options=[
                    {"label": "Total C+R", "value": "total"},
                    {"label": "Carry",     "value": "carry"},
                    {"label": "Roll-Down", "value": "rolldown"},
                    {"label": "Breakeven", "value": "breakeven"},
                ],
                value="total", clearable=False,
                style={"background": PANEL, "border": f"1px solid {BORDER}",
                       "borderRadius": "4px", "minWidth": "140px",
                       "fontSize": "12px", "fontFamily": MONO},
            ),
        ], style={
            "display": "flex", "alignItems": "center", "flexWrap": "wrap",
            "gap": "6px", "marginBottom": "16px",
            "background": PANEL, "border": f"1px solid {BORDER}",
            "borderRadius": "8px", "padding": "12px 16px",
            "fontFamily": MONO,
        }),

        # Main table + heatmap row
        html.Div([
            # Table
            html.Div([
                html.Div("▶ OPPORTUNITY TABLE",
                         style={"fontSize": "10px", "color": TXT_DIM,
                                "letterSpacing": "0.12em", "marginBottom": "8px",
                                "fontFamily": MONO}),
                html.Div(id="table-container"),
            ], style={"flex": "1.6", "minWidth": "0"}),

            # Heatmap
            html.Div([
                html.Div("▶ TOTAL C+R HEATMAP (bp)",
                         style={"fontSize": "10px", "color": TXT_DIM,
                                "letterSpacing": "0.12em", "marginBottom": "8px",
                                "fontFamily": MONO}),
                dcc.Graph(id="heatmap", config={"displayModeBar": False},
                          style={"height": "320px"}),
            ], style={"flex": "1", "minWidth": "0"}),
        ], style={"display": "flex", "gap": "16px", "marginBottom": "16px", "alignItems": "flex-start"}),

        # Curves + bar chart row
        html.Div([
            html.Div([
                html.Div("▶ YIELD CURVES",
                         style={"fontSize": "10px", "color": TXT_DIM,
                                "letterSpacing": "0.12em", "marginBottom": "8px",
                                "fontFamily": MONO}),
                dcc.Graph(id="curves", config={"displayModeBar": False},
                          style={"height": "260px"}),
            ], style={"flex": "1.4", "minWidth": "0"}),

            html.Div([
                html.Div("▶ CARRY vs ROLL-DOWN (top 10)",
                         style={"fontSize": "10px", "color": TXT_DIM,
                                "letterSpacing": "0.12em", "marginBottom": "8px",
                                "fontFamily": MONO}),
                dcc.Graph(id="bar-chart", config={"displayModeBar": False},
                          style={"height": "260px"}),
            ], style={"flex": "1", "minWidth": "0"}),
        ], style={"display": "flex", "gap": "16px", "marginBottom": "12px"}),

        # Footer
        html.Div(
            "CARRY = (SwapRate − FundingRate) × Horizon   ·   "
            "ROLL-DOWN = (Rate[T] − Rate[T−1]) × Horizon   ·   "
            "SIGNAL: >40bp STRONG BUY  |  >20bp BUY  |  >0 NEUTRAL  |  <0 AVOID   ·   Data simulated",
            style={"fontSize": "10px", "color": TXT_DIM, "textAlign": "center",
                   "fontFamily": MONO, "paddingTop": "4px"},
        ),

    ], style={"padding": "20px 28px", "background": BG, "minHeight": "calc(100vh - 50px)"}),

], style={"background": BG, "minHeight": "100vh"})

# ─────────────────────────────────────────────────────────────
#  CALLBACKS
# ─────────────────────────────────────────────────────────────
@app.callback(
    Output("store-curves",  "data"),
    Output("store-history", "data"),
    Output("clock",         "children"),
    Input("interval",       "n_intervals"),
    State("store-history",  "data"),
)
def tick(n, history):
    curves = live_curves()
    for ccy in CURRENCIES:
        history[ccy] = history.get(ccy, []) + [curves[ccy][3]]
        if len(history[ccy]) > 30:
            history[ccy] = history[ccy][-30:]
    ts = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    return curves, history, ts


@app.callback(
    Output("kpi-val-0", "children"), Output("kpi-sub-0", "children"),
    Output("kpi-val-1", "children"), Output("kpi-sub-1", "children"),
    Output("kpi-val-2", "children"), Output("kpi-sub-2", "children"),
    Output("kpi-val-3", "children"), Output("kpi-sub-3", "children"),
    Output("table-container", "children"),
    Output("heatmap",    "figure"),
    Output("curves",     "figure"),
    Output("bar-chart",  "figure"),
    Input("store-curves", "data"),
    State("horizon",      "value"),
    State("ccy-filter",   "value"),
    State("tenor-filter", "value"),
    State("sort-col",     "value"),
    State("store-history","data"),
)
def update_all(curves_data, horizon, ccy_filter, tenor_filter, sort_col, history):
    if not curves_data:
        raise dash.exceptions.PreventUpdate

    horizon   = horizon or 0.5
    sort_col  = sort_col or "total"
    df        = compute_metrics(curves_data, horizon)

    # apply filters
    df_f = df.copy()
    if ccy_filter:
        df_f = df_f[df_f["ccy"].isin(ccy_filter)]
    if tenor_filter:
        df_f = df_f[df_f["tenor"].isin(tenor_filter)]
    df_f = df_f.sort_values(sort_col, ascending=False).reset_index(drop=True)

    horizon_lbl = {0.25: "3M", 0.5: "6M", 1.0: "1Y"}.get(horizon, f"{int(horizon*12)}M")
    pos = int((df_f["total"] > 0).sum())

    # KPIs
    avg_carry = df_f["carry"].mean() if len(df_f) else 0
    avg_roll  = df_f["rolldown"].mean() if len(df_f) else 0
    best      = df_f.iloc[0] if len(df_f) else None
    kv0 = f"{avg_carry:+.1f}bp";  ks0 = f"horizon {horizon_lbl}"
    kv1 = f"{avg_roll:+.1f}bp";   ks1 = f"horizon {horizon_lbl}"
    kv2 = f"{best['ccy']} {best['tenor']}" if best is not None else "—"
    ks2 = f"total {best['total']:+.1f}bp"  if best is not None else "—"
    kv3 = f"{pos}/{len(df_f)}"; ks3 = "pairs with C+R > 0"

    # ── TABLE ──────────────────────────────────────
    sig_bg = {"STRONG BUY": "#003320", "BUY": "#002818",
              "NEUTRAL": "#2a2400",    "AVOID": "#2a0010"}
    sig_col= {"STRONG BUY": GREEN, "BUY": "#80d090",
              "NEUTRAL": YELLOW,   "AVOID": RED}

    hdr_style = {"background": "#0a1018", "color": TXT_DIM,
                 "fontSize": "10px", "padding": "8px 10px",
                 "fontFamily": MONO, "letterSpacing": "0.08em",
                 "borderBottom": f"2px solid {CYAN}", "whiteSpace": "nowrap"}

    def cell(txt, color=TXT_MAIN, bold=False, bg=None, align="left"):
        s = {"padding": "7px 10px", "fontSize": "11px", "fontFamily": MONO,
             "color": color, "textAlign": align, "whiteSpace": "nowrap",
             "borderBottom": f"1px solid {BORDER}"}
        if bold: s["fontWeight"] = "700"
        if bg:   s["background"] = bg
        return html.Td(txt, style=s)

    rows = []
    for _, r in df_f.iterrows():
        c_col = GREEN  if r["carry"]    > 0 else RED
        rd_col= CYAN   if r["rolldown"] > 0 else RED
        tot_c = (GREEN if r["total"] > 0.3 else
                 "#80d090" if r["total"] > 0 else RED)
        bg = "#0d1a26" if _ % 2 == 0 else "#0b1219"
        rows.append(html.Tr([
            cell(f"{r['flag']} {r['ccy']}", CCY_COLORS.get(r["ccy"], TXT_MAIN), bold=True, bg=bg),
            cell(r["tenor"],           TXT_MID,  bg=bg),
            cell(f"{r['rate']:.2f}%",  TXT_MAIN, bg=bg),
            cell(f"{r['funding']:.2f}%",TXT_DIM, bg=bg),
            cell(f"{r['carry']:+.1f}bp",  c_col,  bold=True, bg=bg),
            cell(f"{r['rolldown']:+.1f}bp",rd_col, bold=True, bg=bg),
            cell(f"{r['total']:+.1f}bp",  tot_c,  bold=True, bg=bg),
            cell(f"${r['dv01']:,}",    TXT_DIM,  bg=bg, align="right"),
            cell(f"{r['breakeven']:.1f}bp/m", TXT_MID, bg=bg),
            cell(r["signal"],
                 sig_col.get(r["signal"], TXT_MID),
                 bold=True,
                 bg=sig_bg.get(r["signal"], bg)),
        ]))

    table = html.Div(html.Table([
        html.Thead(html.Tr([
            html.Th(h, style=hdr_style)
            for h in ["CCY","TENOR","RATE","FUNDING","CARRY","ROLL-DOWN","TOTAL","DV01 1MM","BE","SIGNAL"]
        ])),
        html.Tbody(rows),
    ], style={"width": "100%", "borderCollapse": "collapse"}),
    style={"overflowX": "auto", "border": f"1px solid {BORDER}",
           "borderRadius": "8px", "background": PANEL})

    # ── HEATMAP ───────────────────────────────────
    pivot = df.pivot(index="ccy", columns="tenor", values="total")
    pivot = pivot[TENORS[1:]]

    hm = go.Figure(go.Heatmap(
        z=pivot.values * 100,
        x=pivot.columns.tolist(),
        y=[f"{FLAGS[c]} {c}" for c in pivot.index],
        colorscale=[[0, "#3a0015"], [0.35, "#1a1a00"],
                    [0.5, PANEL],   [0.65, "#002a15"], [1, "#005530"]],
        zmid=0,
        text=[[f"{v*100:.1f}bp" for v in row] for row in pivot.values],
        texttemplate="%{text}",
        textfont={"size": 10, "family": MONO, "color": TXT_MAIN},
        hovertemplate="<b>%{y}  %{x}</b><br>Total C+R: %{z:.1f}bp<extra></extra>",
        showscale=True,
        colorbar=dict(
            tickfont=dict(family=MONO, size=9, color=TXT_MID),
            ticksuffix="bp", thickness=12,
            bgcolor=PANEL, bordercolor=BORDER,
        ),
    ))
    hm.update_layout(**PLOTLY_LAYOUT,
        yaxis=dict(autorange="reversed", gridcolor=BORDER,
                   tickfont=dict(family=MONO, size=10)),
        xaxis=dict(gridcolor=BORDER, tickfont=dict(family=MONO, size=10)),
    )

    # ── CURVES ────────────────────────────────────
    curves_fig = go.Figure()
    for ccy in CURRENCIES:
        c = [v * 100 for v in curves_data[ccy]]
        curves_fig.add_trace(go.Scatter(
            x=TENOR_YEARS, y=c, name=f"{FLAGS[ccy]} {ccy}",
            mode="lines+markers",
            line=dict(color=CCY_COLORS[ccy], width=2),
            marker=dict(size=5),
            hovertemplate=f"<b>{ccy}</b> %{{x}}Y: %{{y:.2f}}%<extra></extra>",
        ))
    curves_fig.update_layout(**PLOTLY_LAYOUT,
        xaxis=dict(tickvals=TENOR_YEARS, ticktext=TENORS,
                   gridcolor=BORDER, tickfont=dict(family=MONO, size=9)),
        yaxis=dict(ticksuffix="%", gridcolor=BORDER,
                   tickfont=dict(family=MONO, size=9)),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(family=MONO, size=9),
                    orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified",
    )

    # ── BAR CHART ─────────────────────────────────
    top10 = df_f.head(10).copy()
    labels = [f"{r['flag']}{r['ccy']} {r['tenor']}" for _, r in top10.iterrows()]

    bar_fig = go.Figure()
    bar_fig.add_trace(go.Bar(
        name="Carry",
        x=labels, y=top10["carry"],
        marker_color=GREEN, marker_opacity=0.8,
        hovertemplate="%{x}<br>Carry: %{y:.1f}bp<extra></extra>",
    ))
    bar_fig.add_trace(go.Bar(
        name="Roll-Down",
        x=labels, y=top10["rolldown"],
        marker_color=CYAN, marker_opacity=0.8,
        hovertemplate="%{x}<br>Roll-Down: %{y:.1f}bp<extra></extra>",
    ))
    bar_fig.update_layout(**PLOTLY_LAYOUT,
        barmode="stack",
        xaxis=dict(tickfont=dict(family=MONO, size=8), gridcolor=BORDER),
        yaxis=dict(ticksuffix="bp", gridcolor=BORDER,
                   tickfont=dict(family=MONO, size=9)),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(family=MONO, size=9),
                    orientation="h", yanchor="bottom", y=1.02),
    )

    return (kv0, ks0, kv1, ks1, kv2, ks2, kv3, ks3,
            table, hm, curves_fig, bar_fig)


@app.callback(
    Output("heatmap",   "figure", allow_duplicate=True),
    Output("bar-chart", "figure", allow_duplicate=True),
    Input("horizon",      "value"),
    Input("ccy-filter",   "value"),
    Input("tenor-filter", "value"),
    Input("sort-col",     "value"),
    State("store-curves", "data"),
    State("store-history","data"),
    prevent_initial_call=True,
)
def update_on_filter(horizon, ccy_filter, tenor_filter, sort_col, curves_data, history):
    if not curves_data:
        raise dash.exceptions.PreventUpdate
    return dash.no_update, dash.no_update


# ─────────────────────────────────────────────────────────────
#  CUSTOM CSS (dark dropdowns etc.)
# ─────────────────────────────────────────────────────────────
app.index_string = """<!DOCTYPE html>
<html>
<head>
{%metas%}
<title>{%title%}</title>
{%favicon%}
{%css%}
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  * { box-sizing: border-box; }
  body { margin: 0; background: #080c12; }
  .Select-control, .Select-menu-outer { background: #0d1520 !important; border-color: #1a2a3a !important; color: #c8d0e0 !important; }
  .Select-value-label, .Select-placeholder, .Select-option { color: #c8d0e0 !important; font-family: 'IBM Plex Mono', monospace !important; }
  .Select-menu-outer { background: #0d1520 !important; }
  .Select-option:hover, .Select-option.is-focused { background: #1a2a3a !important; }
  .Select-multi-value-wrapper { background: #0d1520 !important; }
  ::-webkit-scrollbar { width: 5px; height: 5px; }
  ::-webkit-scrollbar-track { background: #080c12; }
  ::-webkit-scrollbar-thumb { background: #1a2a3a; border-radius: 3px; }
  input[type=radio] { accent-color: #00d4ff; }
</style>
</head>
<body>
{%app_entry%}
<footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>"""


if __name__ == "__main__":
    print("\n" + "═"*60)
    print("  CARRY · ROLL-DOWN MONITOR")
    print("  http://127.0.0.1:8050")
    print("═"*60 + "\n")
    app.run(debug=False, host="127.0.0.1", port=8050)
