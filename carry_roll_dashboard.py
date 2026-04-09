"""
╔══════════════════════════════════════════════════════════════╗
║     CARRY & ROLL DOWN MONITOR — IRS & XCCY                  ║
║     Dash/Plotly dashboard — run: python carry_roll_dashboard.py
╚══════════════════════════════════════════════════════════════╝

Install dependencies:
    pip install dash plotly pandas numpy dash-bootstrap-components
"""

import dash
from dash import dcc, html, dash_table, Input, Output, callback
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
import dash_bootstrap_components as dbc
from datetime import datetime

# ─────────────────────────────────────────────
# MOCK MARKET DATA  (replace with live feed)
# ─────────────────────────────────────────────

def get_irs_curve(ccy="EUR"):
    """Simulated par swap rates for a given currency."""
    tenors = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30]
    base = {
        "EUR": [3.45, 3.52, 3.60, 3.55, 3.48, 3.35, 3.28, 3.20, 3.15, 3.10, 3.05],
        "USD": [5.28, 5.30, 5.15, 4.80, 4.60, 4.35, 4.20, 4.10, 4.00, 3.92, 3.85],
        "GBP": [5.10, 5.12, 5.05, 4.85, 4.70, 4.50, 4.35, 4.20, 4.08, 4.00, 3.90],
        "JPY": [0.10, 0.12, 0.18, 0.35, 0.52, 0.80, 0.95, 1.05, 1.15, 1.20, 1.22],
        "CAD": [4.70, 4.65, 4.55, 4.25, 4.05, 3.80, 3.65, 3.52, 3.40, 3.32, 3.25],
    }
    rates = base.get(ccy, base["EUR"])
    noise = np.random.normal(0, 0.01, len(tenors))
    return dict(zip(tenors, [r + n for r, n in zip(rates, noise)]))


def get_xccy_basis(pair="EUR/USD"):
    """Simulated xccy basis (bps), per tenor."""
    tenors = [1, 2, 3, 5, 7, 10, 15, 20, 30]
    base = {
        "EUR/USD": [-15, -18, -20, -22, -24, -25, -24, -23, -21],
        "GBP/USD": [-10, -12, -14, -16, -17, -18, -17, -16, -15],
        "JPY/USD": [-40, -45, -48, -52, -55, -58, -56, -54, -50],
        "EUR/GBP": [-5,  -6,  -7,  -8,  -9, -10,  -9,  -9,  -8],
        "CAD/USD": [-8,  -9, -10, -11, -12, -13, -12, -11, -10],
    }
    rates = base.get(pair, base["EUR/USD"])
    noise = np.random.normal(0, 0.5, len(tenors))
    return dict(zip(tenors, [r + n for r, n in zip(rates, noise)]))


# ─────────────────────────────────────────────
# CARRY & ROLL CALCULATIONS
# ─────────────────────────────────────────────

def interpolate_rate(curve: dict, tenor: float) -> float:
    """Linear interpolation on the curve."""
    tenors = sorted(curve.keys())
    rates  = [curve[t] for t in tenors]
    return float(np.interp(tenor, tenors, rates))


def calc_carry_irs(curve: dict, tenor_y: float, horizon_m: float,
                   fixing_rate: float, dv01: float) -> float:
    """
    Carry (annualised bps) = (SR(0,T) - Fixing) / dv01 * coverage
    Eq. (1a) from Nordea note.
    """
    sr = interpolate_rate(curve, tenor_y)
    coverage = horizon_m / 12
    carry_fv = (sr - fixing_rate) / 100 * coverage
    carry_ann = carry_fv / (dv01 / 10000) * 100   # back to bps annualised
    return round(carry_ann * 100, 2)               # return in bps


def calc_roll_irs(curve: dict, tenor_y: float, horizon_m: float) -> float:
    """
    Roll (bps) for spot starting swap:
    Roll(H) = SR(0, T) - SR(0, T - H)   [Eq. 2a]
    """
    horizon_y = horizon_m / 12
    sr_start  = interpolate_rate(curve, tenor_y)
    sr_end    = interpolate_rate(curve, tenor_y - horizon_y)
    return round((sr_start - sr_end) * 100, 2)


def calc_roll_fwd(curve: dict, fwd_m: float, tenor_y: float, horizon_m: float) -> float:
    """
    Roll (bps) for forward-starting swap:
    Roll(H) = SR(F, T) - SR(0, T)       [Eq. 2b]
    """
    fwd_y     = fwd_m  / 12
    horizon_y = horizon_m / 12
    sr_fwd    = interpolate_rate(curve, tenor_y + fwd_y)
    sr_spot   = interpolate_rate(curve, tenor_y)
    return round((sr_fwd - sr_spot) * 100, 2)


def calc_xccy_carry_roll(basis_curve: dict, tenor_y: float, horizon_m: float,
                         irs_spread: float = 0.0) -> dict:
    """
    For xccy: carry ≈ basis at entry tenor (bps)
              roll  ≈ change in basis as tenor shortens
    """
    horizon_y = horizon_m / 12
    basis_now  = interpolate_rate(basis_curve, tenor_y)
    basis_fwd  = interpolate_rate(basis_curve, tenor_y - horizon_y)
    carry = round(basis_now + irs_spread, 2)
    roll  = round(basis_fwd - basis_now, 2)
    return {"carry": carry, "roll": roll, "total": round(carry + roll, 2)}


# ─────────────────────────────────────────────
# BUILD OPPORTUNITY TABLE
# ─────────────────────────────────────────────

HORIZONS = [3, 6, 12]
IRS_TENORS = [2, 3, 5, 7, 10, 15, 20, 30]
CCYS   = ["EUR", "USD", "GBP", "JPY", "CAD"]
XCCY_PAIRS = ["EUR/USD", "GBP/USD", "JPY/USD", "EUR/GBP", "CAD/USD"]

FIXINGS = {"EUR": 3.92, "USD": 5.33, "GBP": 5.20, "JPY": 0.09, "CAD": 4.45}

DV01_APPROX = {t: t * 92 for t in IRS_TENORS}   # rough: ~92 per year per 10m


def build_irs_table(horizon_m=6):
    rows = []
    for ccy in CCYS:
        curve   = get_irs_curve(ccy)
        fixing  = FIXINGS[ccy]
        for t in IRS_TENORS:
            dv01  = DV01_APPROX[t]
            carry = calc_carry_irs(curve, t, horizon_m, fixing, dv01)
            roll  = calc_roll_irs(curve, t, horizon_m)
            total = round(carry + roll, 2)
            rows.append({
                "Type":      "IRS",
                "Ccy":       ccy,
                "Tenor":     f"{t}Y",
                "Horizon":   f"{horizon_m}M",
                "Carry(bps)": carry,
                "Roll(bps)":  roll,
                "Total(bps)": total,
                "Fixing(%)":  fixing,
                "SR(%)":      round(interpolate_rate(curve, t), 3),
                "DV01":       dv01,
            })
    return pd.DataFrame(rows)


def build_xccy_table(horizon_m=6):
    rows = []
    for pair in XCCY_PAIRS:
        basis = get_xccy_basis(pair)
        for t in [2, 3, 5, 7, 10, 15, 20]:
            res = calc_xccy_carry_roll(basis, t, horizon_m)
            rows.append({
                "Type":       "XCCY",
                "Pair":       pair,
                "Tenor":      f"{t}Y",
                "Horizon":    f"{horizon_m}M",
                "Carry(bps)": res["carry"],
                "Roll(bps)":  res["roll"],
                "Total(bps)": res["total"],
                "Basis(bps)": round(interpolate_rate(basis, t), 2),
            })
    return pd.DataFrame(rows)


def build_heatmap_data(instrument="IRS", horizon_m=6):
    if instrument == "IRS":
        df = build_irs_table(horizon_m)
        pivot = df.pivot_table(index="Ccy", columns="Tenor", values="Total(bps)")
        tenor_order = [f"{t}Y" for t in IRS_TENORS if f"{t}Y" in pivot.columns]
        return pivot[tenor_order]
    else:
        df = build_xccy_table(horizon_m)
        pivot = df.pivot_table(index="Pair", columns="Tenor", values="Total(bps)")
        return pivot


# ─────────────────────────────────────────────
# APP LAYOUT
# ─────────────────────────────────────────────

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.CYBORG],
    title="Carry & Roll Monitor"
)

ACCENT   = "#00d4aa"
ACCENT2  = "#ff6b6b"
BG_CARD  = "#0d1117"
BG_PAGE  = "#060a0f"
TXT      = "#e0e6ef"
GRID_CLR = "#1c2a3a"

# ── Styles ──────────────────────────────────
card_style = {
    "background": BG_CARD,
    "border": f"1px solid {GRID_CLR}",
    "borderRadius": "8px",
    "padding": "16px",
}

kpi_style = {
    **card_style,
    "textAlign": "center",
    "borderTop": f"3px solid {ACCENT}",
}

header_style = {
    "background": "linear-gradient(135deg, #060a0f 0%, #0d1a2a 100%)",
    "borderBottom": f"1px solid {ACCENT}",
    "padding": "20px 32px",
    "marginBottom": "24px",
}

def kpi_card(title, value, sub="", color=ACCENT):
    return html.Div([
        html.P(title, style={"color": "#8899aa", "fontSize": "11px",
                             "letterSpacing": "1.5px", "textTransform": "uppercase",
                             "marginBottom": "6px"}),
        html.H3(value, style={"color": color, "fontSize": "28px",
                               "fontFamily": "monospace", "margin": "0"}),
        html.P(sub,   style={"color": "#8899aa", "fontSize": "11px", "margin": "4px 0 0"}),
    ], style={**kpi_style, "borderTopColor": color})


# ── Controls ─────────────────────────────────
controls = dbc.Row([
    dbc.Col([
        html.Label("Instrument", style={"color": "#8899aa", "fontSize": "11px",
                                        "letterSpacing": "1px", "textTransform": "uppercase"}),
        dcc.Dropdown(
            id="inst-select",
            options=[{"label": "IRS", "value": "IRS"},
                     {"label": "XCCY Basis Swap", "value": "XCCY"}],
            value="IRS",
            clearable=False,
            style={"background": BG_CARD, "color": TXT},
        )
    ], width=2),
    dbc.Col([
        html.Label("Horizon", style={"color": "#8899aa", "fontSize": "11px",
                                     "letterSpacing": "1px", "textTransform": "uppercase"}),
        dcc.Dropdown(
            id="horizon-select",
            options=[{"label": f"{h}M", "value": h} for h in [3, 6, 12]],
            value=6,
            clearable=False,
        )
    ], width=2),
    dbc.Col([
        html.Label("Filter Currency / Pair", style={"color": "#8899aa", "fontSize": "11px",
                                                     "letterSpacing": "1px", "textTransform": "uppercase"}),
        dcc.Dropdown(
            id="ccy-filter",
            options=[{"label": c, "value": c} for c in CCYS + XCCY_PAIRS],
            value=None,
            multi=True,
            placeholder="All",
        )
    ], width=3),
    dbc.Col([
        html.Label("Min Total Carry+Roll (bps)", style={"color": "#8899aa", "fontSize": "11px",
                                                         "letterSpacing": "1px", "textTransform": "uppercase"}),
        dcc.Slider(id="min-total", min=-30, max=50, step=1, value=0,
                   marks={i: str(i) for i in range(-30, 51, 10)},
                   tooltip={"placement": "bottom"}),
    ], width=4),
    dbc.Col([
        dbc.Button("↻ Refresh", id="refresh-btn", color="success",
                   style={"marginTop": "22px", "width": "100%",
                          "fontFamily": "monospace", "letterSpacing": "1px"}),
    ], width=1),
], className="g-3", style={"marginBottom": "20px"})


# ── Main Layout ──────────────────────────────
app.layout = html.Div([

    # ── Header ──
    html.Div([
        dbc.Row([
            dbc.Col([
                html.Div("CARRY & ROLL MONITOR", style={
                    "fontSize": "22px", "fontWeight": "700",
                    "color": ACCENT, "letterSpacing": "3px",
                    "fontFamily": "monospace",
                }),
                html.Div("IRS  ·  XCCY BASIS SWAPS  ·  REAL-TIME OPPORTUNITY SCANNER", style={
                    "fontSize": "11px", "color": "#556677",
                    "letterSpacing": "2px", "marginTop": "4px",
                }),
            ]),
            dbc.Col([
                html.Div(id="clock", style={
                    "textAlign": "right", "color": "#556677",
                    "fontFamily": "monospace", "fontSize": "12px",
                })
            ]),
        ])
    ], style=header_style),

    html.Div([

        # ── Auto-refresh interval ──
        dcc.Interval(id="interval", interval=30_000, n_intervals=0),

        # ── KPI Row ──
        html.Div(id="kpi-row", style={"marginBottom": "20px"}),

        # ── Controls ──
        controls,

        # ── Charts Row ──
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.P("CARRY + ROLL HEATMAP", style={
                        "color": "#8899aa", "fontSize": "11px",
                        "letterSpacing": "2px", "marginBottom": "12px"
                    }),
                    dcc.Graph(id="heatmap", style={"height": "320px"}),
                ], style=card_style)
            ], width=6),
            dbc.Col([
                html.Div([
                    html.P("YIELD CURVE  &  FORWARD RATES", style={
                        "color": "#8899aa", "fontSize": "11px",
                        "letterSpacing": "2px", "marginBottom": "12px"
                    }),
                    dcc.Graph(id="curve-chart", style={"height": "320px"}),
                ], style=card_style)
            ], width=6),
        ], className="g-3", style={"marginBottom": "20px"}),

        # ── Scatter + Xccy Basis ──
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.P("CARRY vs ROLL SCATTER", style={
                        "color": "#8899aa", "fontSize": "11px",
                        "letterSpacing": "2px", "marginBottom": "12px"
                    }),
                    dcc.Graph(id="scatter", style={"height": "300px"}),
                ], style=card_style)
            ], width=5),
            dbc.Col([
                html.Div([
                    html.P("XCCY BASIS TERM STRUCTURE", style={
                        "color": "#8899aa", "fontSize": "11px",
                        "letterSpacing": "2px", "marginBottom": "12px"
                    }),
                    dcc.Graph(id="basis-chart", style={"height": "300px"}),
                ], style=card_style)
            ], width=7),
        ], className="g-3", style={"marginBottom": "20px"}),

        # ── Table ──
        html.Div([
            html.P("OPPORTUNITY TABLE", style={
                "color": "#8899aa", "fontSize": "11px",
                "letterSpacing": "2px", "marginBottom": "12px"
            }),
            html.Div(id="opp-table"),
        ], style=card_style),

    ], style={"padding": "0 24px 24px"}),

], style={"background": BG_PAGE, "minHeight": "100vh", "color": TXT,
          "fontFamily": "'IBM Plex Mono', 'Courier New', monospace"})


# ─────────────────────────────────────────────
# CALLBACKS
# ─────────────────────────────────────────────

@app.callback(
    Output("clock", "children"),
    Input("interval", "n_intervals"),
)
def update_clock(n):
    return datetime.now().strftime("Last updated: %Y-%m-%d  %H:%M:%S UTC")


@app.callback(
    Output("kpi-row", "children"),
    Input("inst-select", "value"),
    Input("horizon-select", "value"),
    Input("interval", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
)
def update_kpis(inst, horizon, n, clicks):
    if inst == "IRS":
        df = build_irs_table(horizon)
    else:
        df = build_xccy_table(horizon)

    best   = df.nlargest(1, "Total(bps)").iloc[0]
    avg    = df["Total(bps)"].mean()
    pct_pos = (df["Total(bps)"] > 0).mean() * 100
    best_label = f"{best.get('Ccy', best.get('Pair',''))} {best['Tenor']}"

    return dbc.Row([
        dbc.Col(kpi_card("Best Opportunity", f"{best['Total(bps)']} bps",
                         best_label, ACCENT), width=3),
        dbc.Col(kpi_card("Average Total", f"{avg:.1f} bps",
                         f"{inst} universe", "#4fc3f7"), width=3),
        dbc.Col(kpi_card("% Positive C+R", f"{pct_pos:.0f}%",
                         "of screened instruments", "#a5d6a7"), width=3),
        dbc.Col(kpi_card("Horizon", f"{horizon}M",
                         "carry & roll window", ACCENT2), width=3),
    ], className="g-3")


@app.callback(
    Output("heatmap", "figure"),
    Input("inst-select", "value"),
    Input("horizon-select", "value"),
    Input("interval", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
)
def update_heatmap(inst, horizon, n, clicks):
    pivot = build_heatmap_data(inst, horizon)

    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=list(pivot.columns),
        y=list(pivot.index),
        colorscale=[
            [0.0,  "#c0392b"],
            [0.35, "#e74c3c"],
            [0.5,  "#1a2a3a"],
            [0.65, "#27ae60"],
            [1.0,  "#00d4aa"],
        ],
        zmid=0,
        text=[[f"{v:.1f}" for v in row] for row in pivot.values],
        texttemplate="%{text}",
        textfont={"size": 11, "color": "white"},
        hoverongaps=False,
        colorbar=dict(
            title=dict(text="bps", font=dict(color=TXT)),
            tickfont=dict(color=TXT),
        ),
    ))
    fig.update_layout(**_base_layout("Total Carry+Roll (bps)"))
    return fig


@app.callback(
    Output("curve-chart", "figure"),
    Input("inst-select", "value"),
    Input("ccy-filter", "value"),
    Input("interval", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
)
def update_curve(inst, ccy_filter, n, clicks):
    tenors = np.linspace(0.25, 30, 100)
    colors = [ACCENT, "#4fc3f7", ACCENT2, "#ffd54f", "#ce93d8"]

    fig = go.Figure()
    ccys_to_show = ccy_filter if ccy_filter else CCYS

    for i, ccy in enumerate([c for c in CCYS if c in ccys_to_show or not ccy_filter]):
        curve  = get_irs_curve(ccy)
        rates  = [interpolate_rate(curve, t) for t in tenors]
        col    = colors[i % len(colors)]
        fig.add_trace(go.Scatter(
            x=list(tenors), y=rates,
            mode="lines", name=ccy,
            line=dict(color=col, width=2),
            hovertemplate=f"{ccy} %{{x:.1f}}Y: %{{y:.3f}}%<extra></extra>",
        ))

    fig.update_layout(**_base_layout("Swap Rate (%)"))
    fig.update_xaxes(title_text="Tenor (years)")
    return fig


@app.callback(
    Output("scatter", "figure"),
    Input("inst-select", "value"),
    Input("horizon-select", "value"),
    Input("min-total", "value"),
    Input("interval", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
)
def update_scatter(inst, horizon, min_total, n, clicks):
    if inst == "IRS":
        df = build_irs_table(horizon)
        color_col, label_col = "Ccy", "Tenor"
    else:
        df = build_xccy_table(horizon)
        color_col, label_col = "Pair", "Tenor"

    df = df[df["Total(bps)"] >= min_total]

    fig = px.scatter(
        df, x="Carry(bps)", y="Roll(bps)",
        color=color_col, size=df["Total(bps)"].abs() + 1,
        text=label_col,
        color_discrete_sequence=[ACCENT, "#4fc3f7", ACCENT2, "#ffd54f",
                                  "#a5d6a7", "#ce93d8", "#ffcc02", "#80cbc4"],
    )
    fig.add_hline(y=0, line_dash="dot", line_color=GRID_CLR)
    fig.add_vline(x=0, line_dash="dot", line_color=GRID_CLR)
    fig.update_traces(textposition="top center",
                      textfont=dict(size=9, color=TXT))
    fig.update_layout(**_base_layout(""))
    fig.update_xaxes(title_text="Carry (bps)")
    fig.update_yaxes(title_text="Roll (bps)")
    return fig


@app.callback(
    Output("basis-chart", "figure"),
    Input("ccy-filter", "value"),
    Input("interval", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
)
def update_basis(ccy_filter, n, clicks):
    tenors = np.linspace(1, 30, 80)
    colors = [ACCENT, "#4fc3f7", ACCENT2, "#ffd54f", "#ce93d8"]
    fig    = go.Figure()

    for i, pair in enumerate(XCCY_PAIRS):
        basis = get_xccy_basis(pair)
        vals  = [interpolate_rate(basis, t) for t in tenors]
        col   = colors[i % len(colors)]
        fig.add_trace(go.Scatter(
            x=list(tenors), y=vals,
            mode="lines", name=pair,
            line=dict(color=col, width=2),
            fill="tozeroy",
            fillcolor=col.replace(")", ",0.08)").replace("rgb", "rgba"),
            hovertemplate=f"{pair} %{{x:.1f}}Y: %{{y:.1f}} bps<extra></extra>",
        ))

    fig.add_hline(y=0, line_color=GRID_CLR, line_dash="dash")
    fig.update_layout(**_base_layout("Basis (bps)"))
    fig.update_xaxes(title_text="Tenor (years)")
    return fig


@app.callback(
    Output("opp-table", "children"),
    Input("inst-select", "value"),
    Input("horizon-select", "value"),
    Input("min-total", "value"),
    Input("ccy-filter", "value"),
    Input("interval", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
)
def update_table(inst, horizon, min_total, ccy_filter, n, clicks):
    if inst == "IRS":
        df = build_irs_table(horizon)
        cols_show = ["Ccy", "Tenor", "Horizon", "SR(%)", "Fixing(%)",
                     "Carry(bps)", "Roll(bps)", "Total(bps)", "DV01"]
    else:
        df = build_xccy_table(horizon)
        cols_show = ["Pair", "Tenor", "Horizon", "Basis(bps)",
                     "Carry(bps)", "Roll(bps)", "Total(bps)"]

    df = df[df["Total(bps)"] >= min_total].sort_values("Total(bps)", ascending=False)
    df = df[cols_show].reset_index(drop=True)

    def style_row(col, val):
        if col == "Total(bps)":
            if val > 10:  return {"color": ACCENT,  "fontWeight": "700"}
            if val > 0:   return {"color": "#a5d6a7"}
            if val < 0:   return {"color": ACCENT2}
        if col == "Carry(bps)":
            return {"color": "#4fc3f7"}
        if col == "Roll(bps)":
            return {"color": "#ffd54f"}
        return {}

    return dash_table.DataTable(
        data=df.to_dict("records"),
        columns=[{"name": c, "id": c} for c in df.columns],
        sort_action="native",
        filter_action="native",
        page_size=20,
        style_table={"overflowX": "auto"},
        style_header={
            "background": "#0a1628",
            "color": "#8899aa",
            "fontSize": "10px",
            "letterSpacing": "1.5px",
            "textTransform": "uppercase",
            "border": f"1px solid {GRID_CLR}",
            "fontFamily": "monospace",
        },
        style_data={
            "background": BG_CARD,
            "color": TXT,
            "border": f"1px solid {GRID_CLR}",
            "fontFamily": "monospace",
            "fontSize": "12px",
        },
        style_data_conditional=[
            {"if": {"filter_query": "{Total(bps)} > 10"},
             "color": ACCENT, "fontWeight": "700"},
            {"if": {"filter_query": "{Total(bps)} > 0 && {Total(bps)} <= 10"},
             "color": "#a5d6a7"},
            {"if": {"filter_query": "{Total(bps)} < 0"},
             "color": ACCENT2},
            {"if": {"state": "selected"},
             "background": "#1a2a3a", "border": f"1px solid {ACCENT}"},
        ],
        style_filter={
            "background": "#0a1628",
            "color": TXT,
            "border": f"1px solid {GRID_CLR}",
        },
    )


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _base_layout(y_title=""):
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="'IBM Plex Mono', monospace", color=TXT, size=11),
        margin=dict(l=40, r=20, t=20, b=40),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=TXT, size=10)),
        xaxis=dict(
            gridcolor=GRID_CLR, gridwidth=1,
            zerolinecolor=GRID_CLR,
            tickfont=dict(color="#8899aa"),
        ),
        yaxis=dict(
            title=y_title,
            gridcolor=GRID_CLR, gridwidth=1,
            zerolinecolor=GRID_CLR,
            tickfont=dict(color="#8899aa"),
            title_font=dict(color="#8899aa"),
        ),
        hoverlabel=dict(bgcolor="#0d1a2a", font_color=TXT,
                        bordercolor=ACCENT, font_family="monospace"),
    )


# ─────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  CARRY & ROLL MONITOR")
    print("  http://127.0.0.1:8050")
    print("="*60 + "\n")
    app.run(debug=True, port=8050)