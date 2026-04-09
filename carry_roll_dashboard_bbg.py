"""
╔══════════════════════════════════════════════════════════════════╗
║   CARRY & ROLL MONITOR — BLOOMBERG LIVE DATA                    ║
║   run: python carry_roll_dashboard_bbg.py                       ║
╠══════════════════════════════════════════════════════════════════╣
║   Requirements:                                                  ║
║     pip install dash plotly pandas numpy dash-bootstrap-components
║     Bloomberg Desktop API (blpapi) — must run on a BBG terminal ║
║     pip install --index-url=https://bcms.bloomberg.com/pip/simple blpapi
╚══════════════════════════════════════════════════════════════════╝

  Bloomberg tickers used
  ──────────────────────
  IRS par swap rates  :  USSW2 Curncy, EUSA2 Curncy, BPSW2 Curncy, etc.
  XCCY basis          :  EURUSD3M BGN Curncy  (or XCCY-specific tickers)
  Overnight fixings   :  USOSFR Curncy, EUSWE Curncy, etc.
  Forward swap rates  :  computed via BDP CURVE_OVERRIDE or derived
                         from spot + basis using blp BDH/BDP
"""

import dash
from dash import dcc, html, dash_table, Input, Output
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
import dash_bootstrap_components as dbc
from datetime import datetime
import logging

# ─────────────────────────────────────────────────────────────────
# BLOOMBERG CONNECTION
# ─────────────────────────────────────────────────────────────────

try:
    import blpapi
    BBG_AVAILABLE = True
except ImportError:
    BBG_AVAILABLE = False
    logging.warning("blpapi not found — running in FALLBACK mode with stub data.")


class BloombergSession:
    """
    Thin wrapper around blpapi.  Provides:
      - bdp()  : Bloomberg Data Point  (current snapshot)
      - bdh()  : Bloomberg Data History (not used here but useful)
    Handles session lifecycle; call .start() once at app init.
    """

    def __init__(self, host="localhost", port=8194):
        self.host    = host
        self.port    = port
        self.session = None

    def start(self):
        if not BBG_AVAILABLE:
            return False
        opts = blpapi.SessionOptions()
        opts.setServerHost(self.host)
        opts.setServerPort(self.port)
        self.session = blpapi.Session(opts)
        if not self.session.start():
            logging.error("Failed to start Bloomberg session.")
            return False
        if not self.session.openService("//blp/refdata"):
            logging.error("Failed to open //blp/refdata service.")
            return False
        logging.info("Bloomberg session started.")
        return True

    def bdp(self, tickers: list[str], fields: list[str],
            overrides: dict | None = None) -> pd.DataFrame:
        """
        Reference Data Request (snapshot).
        Returns a DataFrame indexed by ticker with one column per field.
        """
        if not self.session:
            raise RuntimeError("Bloomberg session not started.")

        svc     = self.session.getService("//blp/refdata")
        request = svc.createRequest("ReferenceDataRequest")

        for t in tickers:
            request.getElement("securities").appendValue(t)
        for f in fields:
            request.getElement("fields").appendValue(f)

        if overrides:
            ovr = request.getElement("overrides")
            for k, v in overrides.items():
                o = ovr.appendElement()
                o.setElement("fieldId", k)
                o.setElement("value", str(v))

        self.session.sendRequest(request)

        results: dict[str, dict] = {}
        while True:
            ev = self.session.nextEvent(500)
            for msg in ev:
                if msg.hasElement("securityData"):
                    sd = msg.getElement("securityData")
                    for i in range(sd.numValues()):
                        item   = sd.getValue(i)
                        ticker = item.getElementAsString("security")
                        fd     = item.getElement("fieldData")
                        row    = {}
                        for f in fields:
                            try:
                                row[f] = fd.getElementAsFloat(f)
                            except Exception:
                                row[f] = np.nan
                        results[ticker] = row
            if ev.eventType() == blpapi.Event.RESPONSE:
                break

        return pd.DataFrame(results).T

    def stop(self):
        if self.session:
            self.session.stop()


# Global session (started once at startup)
BBG = BloombergSession()


# ─────────────────────────────────────────────────────────────────
# BLOOMBERG TICKER MAPS
# ─────────────────────────────────────────────────────────────────

# Par swap rate tickers per currency and tenor
# Format: {ccy: {tenor_y: "BBG_TICKER"}}
IRS_TICKERS: dict[str, dict[float, str]] = {
    "USD": {
        0.25: "USSW3M Curncy",   0.5:  "USSW6M Curncy",
        1:    "USSW1 Curncy",    2:    "USSW2 Curncy",
        3:    "USSW3 Curncy",    5:    "USSW5 Curncy",
        7:    "USSW7 Curncy",    10:   "USSW10 Curncy",
        15:   "USSW15 Curncy",   20:   "USSW20 Curncy",
        30:   "USSW30 Curncy",
    },
    "EUR": {
        0.25: "EUSA3M Curncy",   0.5:  "EUSA6M Curncy",
        1:    "EUSA1 Curncy",    2:    "EUSA2 Curncy",
        3:    "EUSA3 Curncy",    5:    "EUSA5 Curncy",
        7:    "EUSA7 Curncy",    10:   "EUSA10 Curncy",
        15:   "EUSA15 Curncy",   20:   "EUSA20 Curncy",
        30:   "EUSA30 Curncy",
    },
    "GBP": {
        0.25: "BPSW3M Curncy",   0.5:  "BPSW6M Curncy",
        1:    "BPSW1 Curncy",    2:    "BPSW2 Curncy",
        3:    "BPSW3 Curncy",    5:    "BPSW5 Curncy",
        7:    "BPSW7 Curncy",    10:   "BPSW10 Curncy",
        15:   "BPSW15 Curncy",   20:   "BPSW20 Curncy",
        30:   "BPSW30 Curncy",
    },
    "JPY": {
        0.25: "JYSW3M Curncy",   0.5:  "JYSW6M Curncy",
        1:    "JYSW1 Curncy",    2:    "JYSW2 Curncy",
        3:    "JYSW3 Curncy",    5:    "JYSW5 Curncy",
        7:    "JYSW7 Curncy",    10:   "JYSW10 Curncy",
        15:   "JYSW15 Curncy",   20:   "JYSW20 Curncy",
        30:   "JYSW30 Curncy",
    },
    "CAD": {
        0.25: "CDSW3M Curncy",   0.5:  "CDSW6M Curncy",
        1:    "CDSW1 Curncy",    2:    "CDSW2 Curncy",
        3:    "CDSW3 Curncy",    5:    "CDSW5 Curncy",
        7:    "CDSW7 Curncy",    10:   "CDSW10 Curncy",
        15:   "CDSW15 Curncy",   20:   "CDSW20 Curncy",
        30:   "CDSW30 Curncy",
    },
}

# Overnight / short fixing tickers used as the floating leg proxy
FIXING_TICKERS: dict[str, str] = {
    "USD": "USOSFR Curncy",    # SOFR
    "EUR": "EUSWE Curncy",     # €STR
    "GBP": "BPSWSN Curncy",   # SONIA
    "JPY": "JYSWSN Curncy",   # TONAR
    "CAD": "CDSWSN Curncy",   # CORRA
}

# XCCY basis tickers (3M rolling basis vs USD, in bps)
# Tenor suffix: 1Y=1, 2Y=2, ... 30Y=30
XCCY_TICKERS: dict[str, dict[float, str]] = {
    "EUR/USD": {
        1: "EURUSD1Y BGN Curncy",  2: "EURUSD2Y BGN Curncy",
        3: "EURUSD3Y BGN Curncy",  5: "EURUSD5Y BGN Curncy",
        7: "EURUSD7Y BGN Curncy", 10: "EURUSD10Y BGN Curncy",
        15:"EURUSD15Y BGN Curncy", 20:"EURUSD20Y BGN Curncy",
        30:"EURUSD30Y BGN Curncy",
    },
    "GBP/USD": {
        1: "GBPUSD1Y BGN Curncy",  2: "GBPUSD2Y BGN Curncy",
        3: "GBPUSD3Y BGN Curncy",  5: "GBPUSD5Y BGN Curncy",
        7: "GBPUSD7Y BGN Curncy", 10: "GBPUSD10Y BGN Curncy",
        15:"GBPUSD15Y BGN Curncy", 20:"GBPUSD20Y BGN Curncy",
        30:"GBPUSD30Y BGN Curncy",
    },
    "JPY/USD": {
        1: "JPYUSD1Y BGN Curncy",  2: "JPYUSD2Y BGN Curncy",
        3: "JPYUSD3Y BGN Curncy",  5: "JPYUSD5Y BGN Curncy",
        7: "JPYUSD7Y BGN Curncy", 10: "JPYUSD10Y BGN Curncy",
        15:"JPYUSD15Y BGN Curncy", 20:"JPYUSD20Y BGN Curncy",
        30:"JPYUSD30Y BGN Curncy",
    },
    "EUR/GBP": {
        1: "EURGBP1Y BGN Curncy",  2: "EURGBP2Y BGN Curncy",
        3: "EURGBP3Y BGN Curncy",  5: "EURGBP5Y BGN Curncy",
        7: "EURGBP7Y BGN Curncy", 10: "EURGBP10Y BGN Curncy",
        15:"EURGBP15Y BGN Curncy", 20:"EURGBP20Y BGN Curncy",
    },
    "CAD/USD": {
        1: "CADUSD1Y BGN Curncy",  2: "CADUSD2Y BGN Curncy",
        3: "CADUSD3Y BGN Curncy",  5: "CADUSD5Y BGN Curncy",
        7: "CADUSD7Y BGN Curncy", 10: "CADUSD10Y BGN Curncy",
        15:"CADUSD15Y BGN Curncy", 20:"CADUSD20Y BGN Curncy",
    },
}


# ─────────────────────────────────────────────────────────────────
# DATA FETCHERS  (live BBG or stub fallback)
# ─────────────────────────────────────────────────────────────────

# In-process cache: {cache_key: (timestamp, data)}
_CACHE: dict = {}
CACHE_TTL_SECONDS = 60   # refresh at most once per minute


def _cache_get(key: str):
    if key in _CACHE:
        ts, val = _CACHE[key]
        if (datetime.now() - ts).total_seconds() < CACHE_TTL_SECONDS:
            return val
    return None


def _cache_set(key: str, val):
    _CACHE[key] = (datetime.now(), val)
    return val


def get_irs_curve_live(ccy: str) -> dict[float, float]:
    """
    Fetch live par swap rates from Bloomberg for `ccy`.
    Returns {tenor_y: rate_%}.
    Falls back to stub data if Bloomberg is unavailable.
    """
    key = f"irs_{ccy}"
    cached = _cache_get(key)
    if cached:
        return cached

    if BBG_AVAILABLE and BBG.session:
        ticker_map = IRS_TICKERS.get(ccy, {})
        tickers    = list(ticker_map.values())
        try:
            df = BBG.bdp(tickers, ["LAST_PRICE"])
            result = {}
            for tenor, ticker in ticker_map.items():
                if ticker in df.index and not np.isnan(df.loc[ticker, "LAST_PRICE"]):
                    result[tenor] = df.loc[ticker, "LAST_PRICE"]
            if result:
                return _cache_set(key, result)
        except Exception as e:
            logging.warning(f"BBG IRS fetch failed for {ccy}: {e}")

    # ── Fallback stub ──────────────────────────────────────────
    return _cache_set(key, _stub_irs_curve(ccy))


def get_fixing_live(ccy: str) -> float:
    """
    Fetch overnight/short-end fixing rate from Bloomberg.
    Falls back to stub value.
    """
    key = f"fixing_{ccy}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    if BBG_AVAILABLE and BBG.session:
        ticker = FIXING_TICKERS.get(ccy)
        if ticker:
            try:
                df = BBG.bdp([ticker], ["LAST_PRICE"])
                val = df.loc[ticker, "LAST_PRICE"]
                if not np.isnan(val):
                    return _cache_set(key, float(val))
            except Exception as e:
                logging.warning(f"BBG fixing fetch failed for {ccy}: {e}")

    return _cache_set(key, _STUB_FIXINGS.get(ccy, 3.0))


def get_xccy_basis_live(pair: str) -> dict[float, float]:
    """
    Fetch XCCY basis curve from Bloomberg.
    Returns {tenor_y: basis_bps}.
    """
    key = f"xccy_{pair}"
    cached = _cache_get(key)
    if cached:
        return cached

    if BBG_AVAILABLE and BBG.session:
        ticker_map = XCCY_TICKERS.get(pair, {})
        tickers    = list(ticker_map.values())
        try:
            df = BBG.bdp(tickers, ["LAST_PRICE"])
            result = {}
            for tenor, ticker in ticker_map.items():
                if ticker in df.index and not np.isnan(df.loc[ticker, "LAST_PRICE"]):
                    result[tenor] = df.loc[ticker, "LAST_PRICE"]
            if result:
                return _cache_set(key, result)
        except Exception as e:
            logging.warning(f"BBG XCCY fetch failed for {pair}: {e}")

    return _cache_set(key, _stub_xccy_basis(pair))


# ─────────────────────────────────────────────────────────────────
# STUB DATA  (used when BBG is unavailable)
# ─────────────────────────────────────────────────────────────────

_STUB_IRS: dict[str, list[float]] = {
    "EUR": [3.45, 3.52, 3.60, 3.55, 3.48, 3.35, 3.28, 3.20, 3.15, 3.10, 3.05],
    "USD": [5.28, 5.30, 5.15, 4.80, 4.60, 4.35, 4.20, 4.10, 4.00, 3.92, 3.85],
    "GBP": [5.10, 5.12, 5.05, 4.85, 4.70, 4.50, 4.35, 4.20, 4.08, 4.00, 3.90],
    "JPY": [0.10, 0.12, 0.18, 0.35, 0.52, 0.80, 0.95, 1.05, 1.15, 1.20, 1.22],
    "CAD": [4.70, 4.65, 4.55, 4.25, 4.05, 3.80, 3.65, 3.52, 3.40, 3.32, 3.25],
}
_STUB_TENORS_IRS = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30]

_STUB_FIXINGS: dict[str, float] = {
    "EUR": 3.92, "USD": 5.33, "GBP": 5.20, "JPY": 0.09, "CAD": 4.45,
}

_STUB_XCCY: dict[str, list[float]] = {
    "EUR/USD": [-15, -18, -20, -22, -24, -25, -24, -23, -21],
    "GBP/USD": [-10, -12, -14, -16, -17, -18, -17, -16, -15],
    "JPY/USD": [-40, -45, -48, -52, -55, -58, -56, -54, -50],
    "EUR/GBP": [-5,  -6,  -7,  -8,  -9, -10,  -9,  -9,  -8],
    "CAD/USD": [-8,  -9, -10, -11, -12, -13, -12, -11, -10],
}
_STUB_TENORS_XCCY = [1, 2, 3, 5, 7, 10, 15, 20, 30]


def _stub_irs_curve(ccy: str) -> dict[float, float]:
    rates  = _STUB_IRS.get(ccy, _STUB_IRS["EUR"])
    noise  = np.random.normal(0, 0.01, len(_STUB_TENORS_IRS))
    return dict(zip(_STUB_TENORS_IRS, [r + n for r, n in zip(rates, noise)]))


def _stub_xccy_basis(pair: str) -> dict[float, float]:
    rates = _STUB_XCCY.get(pair, _STUB_XCCY["EUR/USD"])
    noise = np.random.normal(0, 0.3, len(_STUB_TENORS_XCCY))
    return dict(zip(_STUB_TENORS_XCCY, [r + n for r, n in zip(rates, noise)]))


# ─────────────────────────────────────────────────────────────────
# CARRY & ROLL MATH  (unchanged from mock version)
# ─────────────────────────────────────────────────────────────────

def interpolate_rate(curve: dict, tenor: float) -> float:
    tenors = sorted(curve.keys())
    rates  = [curve[t] for t in tenors]
    return float(np.interp(tenor, tenors, rates))


def calc_carry_irs(curve, tenor_y, horizon_m, fixing_rate, dv01):
    sr        = interpolate_rate(curve, tenor_y)
    coverage  = horizon_m / 12
    carry_fv  = (sr - fixing_rate) / 100 * coverage
    carry_ann = carry_fv / (dv01 / 10000) * 100
    return round(carry_ann * 100, 2)


def calc_roll_irs(curve, tenor_y, horizon_m):
    horizon_y = horizon_m / 12
    return round((interpolate_rate(curve, tenor_y)
                  - interpolate_rate(curve, tenor_y - horizon_y)) * 100, 2)


def calc_xccy_carry_roll(basis_curve, tenor_y, horizon_m, irs_spread=0.0):
    horizon_y  = horizon_m / 12
    basis_now  = interpolate_rate(basis_curve, tenor_y)
    basis_fwd  = interpolate_rate(basis_curve, max(tenor_y - horizon_y, 0.25))
    carry = round(basis_now + irs_spread, 2)
    roll  = round(basis_fwd - basis_now, 2)
    return {"carry": carry, "roll": roll, "total": round(carry + roll, 2)}


# ─────────────────────────────────────────────────────────────────
# TABLE BUILDERS
# ─────────────────────────────────────────────────────────────────

CCYS       = ["EUR", "USD", "GBP", "JPY", "CAD"]
XCCY_PAIRS = ["EUR/USD", "GBP/USD", "JPY/USD", "EUR/GBP", "CAD/USD"]
IRS_TENORS = [2, 3, 5, 7, 10, 15, 20, 30]
DV01_APPROX = {t: t * 92 for t in IRS_TENORS}


def build_irs_table(horizon_m=6):
    rows = []
    for ccy in CCYS:
        curve  = get_irs_curve_live(ccy)
        fixing = get_fixing_live(ccy)
        for t in IRS_TENORS:
            dv01  = DV01_APPROX[t]
            carry = calc_carry_irs(curve, t, horizon_m, fixing, dv01)
            roll  = calc_roll_irs(curve, t, horizon_m)
            rows.append({
                "Ccy": ccy, "Tenor": f"{t}Y", "Horizon": f"{horizon_m}M",
                "SR(%)":      round(interpolate_rate(curve, t), 3),
                "Fixing(%)":  round(fixing, 3),
                "Carry(bps)": carry,
                "Roll(bps)":  roll,
                "Total(bps)": round(carry + roll, 2),
                "DV01":       dv01,
            })
    return pd.DataFrame(rows)


def build_xccy_table(horizon_m=6):
    rows = []
    for pair in XCCY_PAIRS:
        basis = get_xccy_basis_live(pair)
        for t in [2, 3, 5, 7, 10, 15, 20]:
            res = calc_xccy_carry_roll(basis, t, horizon_m)
            rows.append({
                "Pair": pair, "Tenor": f"{t}Y", "Horizon": f"{horizon_m}M",
                "Basis(bps)": round(interpolate_rate(basis, t), 2),
                "Carry(bps)": res["carry"],
                "Roll(bps)":  res["roll"],
                "Total(bps)": res["total"],
            })
    return pd.DataFrame(rows)


def build_heatmap_data(instrument="IRS", horizon_m=6):
    if instrument == "IRS":
        df    = build_irs_table(horizon_m)
        pivot = df.pivot_table(index="Ccy", columns="Tenor", values="Total(bps)")
        order = [f"{t}Y" for t in IRS_TENORS if f"{t}Y" in pivot.columns]
        return pivot[order]
    df    = build_xccy_table(horizon_m)
    pivot = df.pivot_table(index="Pair", columns="Tenor", values="Total(bps)")
    return pivot


# ─────────────────────────────────────────────────────────────────
# DASH APP
# ─────────────────────────────────────────────────────────────────

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.CYBORG],
    title="Carry & Roll Monitor [BBG]",
)

ACCENT   = "#00d4aa"
ACCENT2  = "#ff6b6b"
BG_CARD  = "#0d1117"
BG_PAGE  = "#060a0f"
TXT      = "#e0e6ef"
GRID_CLR = "#1c2a3a"
WARN_CLR = "#ffd54f"

card_style   = {"background": BG_CARD, "border": f"1px solid {GRID_CLR}",
                "borderRadius": "8px", "padding": "16px"}
kpi_style    = {**card_style, "textAlign": "center",
                "borderTop": f"3px solid {ACCENT}"}
header_style = {"background": "linear-gradient(135deg,#060a0f 0%,#0d1a2a 100%)",
                "borderBottom": f"1px solid {ACCENT}",
                "padding": "20px 32px", "marginBottom": "24px"}


def kpi_card(title, value, sub="", color=ACCENT):
    return html.Div([
        html.P(title, style={"color": "#8899aa", "fontSize": "11px",
                             "letterSpacing": "1.5px", "textTransform": "uppercase",
                             "marginBottom": "6px"}),
        html.H3(value, style={"color": color, "fontSize": "28px",
                               "fontFamily": "monospace", "margin": "0"}),
        html.P(sub,   style={"color": "#8899aa", "fontSize": "11px",
                             "margin": "4px 0 0"}),
    ], style={**kpi_style, "borderTopColor": color})


def bbg_status_badge():
    if BBG_AVAILABLE:
        color, label = ACCENT,   "● BBG LIVE"
    else:
        color, label = WARN_CLR, "⚠ STUB DATA"
    return html.Span(label, style={
        "color": color, "fontFamily": "monospace",
        "fontSize": "11px", "letterSpacing": "1.5px",
        "border": f"1px solid {color}", "borderRadius": "4px",
        "padding": "3px 8px",
    })


controls = dbc.Row([
    dbc.Col([
        html.Label("Instrument", style={"color": "#8899aa", "fontSize": "11px",
                                        "letterSpacing": "1px", "textTransform": "uppercase"}),
        dcc.Dropdown(
            id="inst-select",
            options=[{"label": "IRS", "value": "IRS"},
                     {"label": "XCCY Basis Swap", "value": "XCCY"}],
            value="IRS", clearable=False,
        )
    ], width=2),
    dbc.Col([
        html.Label("Horizon", style={"color": "#8899aa", "fontSize": "11px",
                                     "letterSpacing": "1px", "textTransform": "uppercase"}),
        dcc.Dropdown(
            id="horizon-select",
            options=[{"label": f"{h}M", "value": h} for h in [3, 6, 12]],
            value=6, clearable=False,
        )
    ], width=2),
    dbc.Col([
        html.Label("Filter Ccy / Pair", style={"color": "#8899aa", "fontSize": "11px",
                                                "letterSpacing": "1px", "textTransform": "uppercase"}),
        dcc.Dropdown(
            id="ccy-filter",
            options=[{"label": c, "value": c} for c in CCYS + XCCY_PAIRS],
            value=None, multi=True, placeholder="All",
        )
    ], width=3),
    dbc.Col([
        html.Label("Min Total C+R (bps)", style={"color": "#8899aa", "fontSize": "11px",
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


app.layout = html.Div([

    html.Div([
        dbc.Row([
            dbc.Col([
                html.Div("CARRY & ROLL MONITOR", style={
                    "fontSize": "22px", "fontWeight": "700",
                    "color": ACCENT, "letterSpacing": "3px", "fontFamily": "monospace",
                }),
                html.Div([
                    html.Span("IRS  ·  XCCY  ·  BLOOMBERG LIVE DATA  ", style={
                        "fontSize": "11px", "color": "#556677",
                        "letterSpacing": "2px",
                    }),
                    bbg_status_badge(),
                ], style={"marginTop": "6px"}),
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
        dcc.Interval(id="interval", interval=60_000, n_intervals=0),  # 60s auto-refresh

        html.Div(id="kpi-row", style={"marginBottom": "20px"}),

        controls,

        dbc.Row([
            dbc.Col([
                html.Div([
                    html.P("CARRY + ROLL HEATMAP", style={
                        "color": "#8899aa", "fontSize": "11px",
                        "letterSpacing": "2px", "marginBottom": "12px"}),
                    dcc.Graph(id="heatmap", style={"height": "320px"}),
                ], style=card_style)
            ], width=6),
            dbc.Col([
                html.Div([
                    html.P("YIELD CURVE  (live par swap rates)", style={
                        "color": "#8899aa", "fontSize": "11px",
                        "letterSpacing": "2px", "marginBottom": "12px"}),
                    dcc.Graph(id="curve-chart", style={"height": "320px"}),
                ], style=card_style)
            ], width=6),
        ], className="g-3", style={"marginBottom": "20px"}),

        dbc.Row([
            dbc.Col([
                html.Div([
                    html.P("CARRY vs ROLL SCATTER", style={
                        "color": "#8899aa", "fontSize": "11px",
                        "letterSpacing": "2px", "marginBottom": "12px"}),
                    dcc.Graph(id="scatter", style={"height": "300px"}),
                ], style=card_style)
            ], width=5),
            dbc.Col([
                html.Div([
                    html.P("XCCY BASIS TERM STRUCTURE (live)", style={
                        "color": "#8899aa", "fontSize": "11px",
                        "letterSpacing": "2px", "marginBottom": "12px"}),
                    dcc.Graph(id="basis-chart", style={"height": "300px"}),
                ], style=card_style)
            ], width=7),
        ], className="g-3", style={"marginBottom": "20px"}),

        html.Div([
            html.P("OPPORTUNITY TABLE", style={
                "color": "#8899aa", "fontSize": "11px",
                "letterSpacing": "2px", "marginBottom": "12px"}),
            html.Div(id="opp-table"),
        ], style=card_style),

    ], style={"padding": "0 24px 24px"}),

], style={"background": BG_PAGE, "minHeight": "100vh", "color": TXT,
          "fontFamily": "'IBM Plex Mono','Courier New',monospace"})


# ─────────────────────────────────────────────────────────────────
# CALLBACKS
# ─────────────────────────────────────────────────────────────────

@app.callback(Output("clock", "children"), Input("interval", "n_intervals"))
def update_clock(n):
    src = "BBG LIVE" if BBG_AVAILABLE else "STUB"
    return f"[{src}]  {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}"


@app.callback(
    Output("kpi-row", "children"),
    Input("inst-select", "value"), Input("horizon-select", "value"),
    Input("interval", "n_intervals"), Input("refresh-btn", "n_clicks"),
)
def update_kpis(inst, horizon, n, clicks):
    df = build_irs_table(horizon) if inst == "IRS" else build_xccy_table(horizon)
    best      = df.nlargest(1, "Total(bps)").iloc[0]
    avg       = df["Total(bps)"].mean()
    pct_pos   = (df["Total(bps)"] > 0).mean() * 100
    best_lbl  = f"{best.get('Ccy', best.get('Pair',''))} {best['Tenor']}"
    return dbc.Row([
        dbc.Col(kpi_card("Best Opportunity", f"{best['Total(bps)']} bps", best_lbl, ACCENT), width=3),
        dbc.Col(kpi_card("Avg Total C+R",    f"{avg:.1f} bps", f"{inst} universe", "#4fc3f7"), width=3),
        dbc.Col(kpi_card("% Positive",       f"{pct_pos:.0f}%", "of universe", "#a5d6a7"), width=3),
        dbc.Col(kpi_card("Horizon",          f"{horizon}M", "roll & carry window", ACCENT2), width=3),
    ], className="g-3")


@app.callback(
    Output("heatmap", "figure"),
    Input("inst-select", "value"), Input("horizon-select", "value"),
    Input("interval", "n_intervals"), Input("refresh-btn", "n_clicks"),
)
def update_heatmap(inst, horizon, n, clicks):
    pivot = build_heatmap_data(inst, horizon)
    fig   = go.Figure(go.Heatmap(
        z=pivot.values, x=list(pivot.columns), y=list(pivot.index),
        colorscale=[[0.0,"#c0392b"],[0.35,"#e74c3c"],
                    [0.5,"#1a2a3a"],[0.65,"#27ae60"],[1.0,"#00d4aa"]],
        zmid=0,
        text=[[f"{v:.1f}" for v in row] for row in pivot.values],
        texttemplate="%{text}", textfont={"size": 11, "color": "white"},
        colorbar=dict(title=dict(text="bps", font=dict(color=TXT)),
                      tickfont=dict(color=TXT)),
    ))
    fig.update_layout(**_base_layout("Total Carry+Roll (bps)"))
    return fig


@app.callback(
    Output("curve-chart", "figure"),
    Input("inst-select", "value"), Input("ccy-filter", "value"),
    Input("interval", "n_intervals"), Input("refresh-btn", "n_clicks"),
)
def update_curve(inst, ccy_filter, n, clicks):
    tenors = np.linspace(0.25, 30, 100)
    colors = [ACCENT, "#4fc3f7", ACCENT2, "#ffd54f", "#ce93d8"]
    fig    = go.Figure()
    for i, ccy in enumerate(CCYS):
        if ccy_filter and ccy not in ccy_filter:
            continue
        curve = get_irs_curve_live(ccy)
        rates = [interpolate_rate(curve, t) for t in tenors]
        col   = colors[i % len(colors)]
        fig.add_trace(go.Scatter(
            x=list(tenors), y=rates, mode="lines", name=ccy,
            line=dict(color=col, width=2),
            hovertemplate=f"{ccy} %{{x:.1f}}Y: %{{y:.3f}}%<extra></extra>",
        ))
    fig.update_layout(**_base_layout("Swap Rate (%)"))
    fig.update_xaxes(title_text="Tenor (years)")
    return fig


@app.callback(
    Output("scatter", "figure"),
    Input("inst-select", "value"), Input("horizon-select", "value"),
    Input("min-total", "value"),
    Input("interval", "n_intervals"), Input("refresh-btn", "n_clicks"),
)
def update_scatter(inst, horizon, min_total, n, clicks):
    if inst == "IRS":
        df = build_irs_table(horizon);  color_col, lbl = "Ccy",  "Tenor"
    else:
        df = build_xccy_table(horizon); color_col, lbl = "Pair", "Tenor"
    df  = df[df["Total(bps)"] >= min_total]
    fig = px.scatter(
        df, x="Carry(bps)", y="Roll(bps)",
        color=color_col, size=df["Total(bps)"].abs() + 1, text=lbl,
        color_discrete_sequence=[ACCENT, "#4fc3f7", ACCENT2, "#ffd54f",
                                  "#a5d6a7", "#ce93d8", "#ffcc02", "#80cbc4"],
    )
    fig.add_hline(y=0, line_dash="dot", line_color=GRID_CLR)
    fig.add_vline(x=0, line_dash="dot", line_color=GRID_CLR)
    fig.update_traces(textposition="top center", textfont=dict(size=9, color=TXT))
    fig.update_layout(**_base_layout(""))
    fig.update_xaxes(title_text="Carry (bps)")
    fig.update_yaxes(title_text="Roll (bps)")
    return fig


@app.callback(
    Output("basis-chart", "figure"),
    Input("ccy-filter", "value"),
    Input("interval", "n_intervals"), Input("refresh-btn", "n_clicks"),
)
def update_basis(ccy_filter, n, clicks):
    tenors = np.linspace(1, 30, 80)
    colors = [ACCENT, "#4fc3f7", ACCENT2, "#ffd54f", "#ce93d8"]
    fig    = go.Figure()
    for i, pair in enumerate(XCCY_PAIRS):
        basis = get_xccy_basis_live(pair)
        vals  = [interpolate_rate(basis, t) for t in tenors]
        col   = colors[i % len(colors)]
        fig.add_trace(go.Scatter(
            x=list(tenors), y=vals, mode="lines", name=pair,
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
    Input("inst-select", "value"), Input("horizon-select", "value"),
    Input("min-total", "value"), Input("ccy-filter", "value"),
    Input("interval", "n_intervals"), Input("refresh-btn", "n_clicks"),
)
def update_table(inst, horizon, min_total, ccy_filter, n, clicks):
    if inst == "IRS":
        df = build_irs_table(horizon)
        cols = ["Ccy","Tenor","Horizon","SR(%)","Fixing(%)","Carry(bps)","Roll(bps)","Total(bps)","DV01"]
    else:
        df = build_xccy_table(horizon)
        cols = ["Pair","Tenor","Horizon","Basis(bps)","Carry(bps)","Roll(bps)","Total(bps)"]
    df = df[df["Total(bps)"] >= min_total].sort_values("Total(bps)", ascending=False)
    df = df[cols].reset_index(drop=True)
    return dash_table.DataTable(
        data=df.to_dict("records"),
        columns=[{"name": c, "id": c} for c in df.columns],
        sort_action="native", filter_action="native", page_size=20,
        style_table={"overflowX": "auto"},
        style_header={"background": "#0a1628", "color": "#8899aa",
                      "fontSize": "10px", "letterSpacing": "1.5px",
                      "textTransform": "uppercase",
                      "border": f"1px solid {GRID_CLR}", "fontFamily": "monospace"},
        style_data={"background": BG_CARD, "color": TXT,
                    "border": f"1px solid {GRID_CLR}",
                    "fontFamily": "monospace", "fontSize": "12px"},
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
        style_filter={"background": "#0a1628", "color": TXT,
                      "border": f"1px solid {GRID_CLR}"},
    )


# ─────────────────────────────────────────────────────────────────
# LAYOUT HELPER
# ─────────────────────────────────────────────────────────────────

def _base_layout(y_title=""):
    return dict(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="'IBM Plex Mono',monospace", color=TXT, size=11),
        margin=dict(l=40, r=20, t=20, b=40),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=TXT, size=10)),
        xaxis=dict(gridcolor=GRID_CLR, zerolinecolor=GRID_CLR,
                   tickfont=dict(color="#8899aa")),
        yaxis=dict(title=y_title, gridcolor=GRID_CLR, zerolinecolor=GRID_CLR,
                   tickfont=dict(color="#8899aa"),
                   title_font=dict(color="#8899aa")),
        hoverlabel=dict(bgcolor="#0d1a2a", font_color=TXT,
                        bordercolor=ACCENT, font_family="monospace"),
    )


# ─────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    BBG.start()   # opens Bloomberg session (no-op if blpapi not installed)
    print("\n" + "=" * 60)
    print("  CARRY & ROLL MONITOR  [Bloomberg Edition]")
    print(f"  Data source : {'Bloomberg LIVE' if BBG_AVAILABLE else 'STUB (blpapi not found)'}")
    print("  http://127.0.0.1:8050")
    print("=" * 60 + "\n")
    try:
        app.run(debug=False, port=8050)
    finally:
        BBG.stop()   # clean shutdown
