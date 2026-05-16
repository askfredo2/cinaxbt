# CINAX BTC v2 — Paper Trading Horario
# Guarda datos en /data (volumen Railway persistente)
# Envía alertas a Discord via webhook
# Modelo: LightGBM horario con TP/SL y cierre por tiempo

import numpy as np
import pandas as pd
import yfinance as yf
import pickle
import os
import time
import warnings
import requests
from datetime import datetime
import pytz

warnings.filterwarnings("ignore")

# ══════════════════════════════════════════════════════════════
# CONFIGURACIÓN — ajusta estas variables de entorno en Railway
# ══════════════════════════════════════════════════════════════

RUTA_PKL        = os.environ.get("RUTA_PKL", "modelo.pkl")
RUTA_META       = os.environ.get("RUTA_META", "meta.pkl")
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")

# ══════════════════════════════════════════════════════════════
# CONFIG FIJA
# ══════════════════════════════════════════════════════════════

ACTIVO          = "BTC-USD"
WINDOW_PCT      = 168          # ventana percentil en horas (debe coincidir con entrenamiento)
CHECK_MINS      = 60           # revisar cada 60 minutos
SL_RACHA_MAX    = 1            # SLs consecutivos para activar bloqueo
VENTANA_RACHA   = 12           # ventana anti-racha en horas

DATA_DIR        = "/data"
LOG_FILE        = f"{DATA_DIR}/cinax_btc.log"
SEÑALES_CSV     = f"{DATA_DIR}/cinax_btc_señales.csv"
POSICIONES_CSV  = f"{DATA_DIR}/cinax_btc_posiciones.csv"
INTRA_CSV       = f"{DATA_DIR}/cinax_btc_intra.csv"

# dtypes explícitos para leer POSICIONES_CSV sin problemas de inferencia
POSICIONES_DTYPE = {
    "entry_price":    float,
    "tp_price":       float,
    "sl_price":       float,
    "exit_price":     str,
    "retorno":        str,
    "motivo_salida":  str,
    "prob":           float,
    "umbral":         float,
    "estado":         str,
}

os.makedirs(DATA_DIR, exist_ok=True)

# ══════════════════════════════════════════════════════════════
# LOG
# ══════════════════════════════════════════════════════════════

def log(msg, nivel="INFO"):
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sym = {"INFO": "·", "SEÑAL": "★", "WARN": "!", "ERR": "✗", "OK": "✓"}.get(nivel, "·")
    txt = f"[{ts}] {sym} {msg}"
    print(txt, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(txt + "\n")
    except Exception:
        pass

# ══════════════════════════════════════════════════════════════
# DISCORD
# ══════════════════════════════════════════════════════════════

def discord(mensaje):
    if not DISCORD_WEBHOOK:
        return
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": mensaje}, timeout=10)
    except Exception as e:
        log(f"Discord error: {e}", "WARN")


def discord_señal_nueva(fecha_barra, precio, prob, umbral, tp_pct, sl_pct, max_horas, sma_period):
    hoy     = fecha_barra.strftime("%Y-%m-%d %H:%M")
    header  = f"🟢 **CINAX BTC — SEÑAL LARGA** | {hoy} UTC"
    exit_tp = precio * (1 + tp_pct)
    exit_sl = precio * (1 - sl_pct)
    detalle = (
        f"```\n"
        f"BTC/USD Entry  : {precio:,.2f}\n"
        f"Probabilidad   : {prob:.4f}  (umbral {umbral:.4f})\n"
        f"Take Profit    : {exit_tp:,.2f} (+{tp_pct*100:.1f}%)\n"
        f"Stop Loss      : {exit_sl:,.2f} (-{sl_pct*100:.1f}%)\n"
        f"Cierre máx     : {max_horas}h si no toca TP/SL\n"
        f"Régimen        : precio > SMA{sma_period}h ✓\n"
        f"```"
    )
    resumen_txt = _bloque_acumulado()
    discord(f"{header}\n{detalle}{resumen_txt}")


def discord_cierre_posicion(pos, precio_cierre, retorno, motivo):
    emoji  = "✅" if retorno > 0 else "❌"
    header = f"{emoji} **CINAX BTC — Posición Cerrada**"
    detalle = (
        f"```\n"
        f"Entry    : {pos['entry_date']}  @  {float(pos['entry_price']):,.2f}\n"
        f"Exit     : {datetime.now().strftime('%Y-%m-%d %H:%M')}  @  {precio_cierre:,.2f}\n"
        f"Retorno  : {retorno*100:+.2f}%\n"
        f"Motivo   : {motivo}\n"
        f"```"
    )
    resumen_txt = _bloque_acumulado()
    discord(f"{header}\n{detalle}{resumen_txt}")


def discord_seguimiento(fecha_barra, precio_actual):
    if not os.path.exists(POSICIONES_CSV):
        return
    df_pos   = _leer_posiciones()
    abiertas = df_pos[df_pos["estado"] == "ABIERTA"]
    if abiertas.empty:
        return

    hoy    = fecha_barra.strftime("%Y-%m-%d %H:%M")
    header = f"📊 **CINAX BTC — Seguimiento** | {hoy} UTC"
    lineas = []
    for _, p in abiertas.iterrows():
        entry_price = float(p["entry_price"])
        ret_actual  = precio_actual / entry_price - 1
        emoji       = "🟢" if ret_actual >= 0 else "🔴"
        horas_abier = p.get("horas_abiertas", "?")
        lineas.append(
            f"{emoji}  entry {p['entry_date']} @ {entry_price:,.2f}"
            f"  →  ahora {precio_actual:,.2f}"
            f"  ret {ret_actual*100:+.2f}%"
            f"  | TP {float(p['tp_price']):,.2f} | SL {float(p['sl_price']):,.2f}"
        )
    pos_txt     = "\n**Posiciones abiertas:**\n```\n" + "\n".join(lineas) + "\n```"
    resumen_txt = _bloque_acumulado()
    discord(f"{header}{pos_txt}{resumen_txt}")


def discord_bloqueado_racha(fecha_barra, n_sl, ventana_h):
    msg = (f"🚫 **CINAX BTC — Entrada BLOQUEADA** | {fecha_barra.strftime('%Y-%m-%d %H:%M')} UTC\n"
           f"```Anti-racha: {n_sl} SL en últimas {ventana_h}h → señal ignorada```")
    discord(msg)


def _bloque_acumulado():
    if not os.path.exists(POSICIONES_CSV):
        return ""
    df_all   = _leer_posiciones()
    cerradas = df_all[df_all["estado"] == "CERRADA"]
    abiertas = df_all[df_all["estado"] == "ABIERTA"]
    if len(cerradas) == 0:
        return ""
    rets = pd.to_numeric(cerradas["retorno"], errors="coerce").dropna()
    wr   = (rets > 0).mean()
    pf   = rets[rets > 0].sum() / (abs(rets[rets < 0].sum()) + 1e-8)
    return (
        f"\n**Acumulado ({len(cerradas)} trades cerrados):**\n"
        f"```\n"
        f"Win Rate      : {wr:.1%}\n"
        f"Profit Factor : {pf:.2f}\n"
        f"Retorno acum  : {rets.sum()*100:+.1f}%\n"
        f"Abiertas ahora: {len(abiertas)}\n"
        f"```"
    )

# ══════════════════════════════════════════════════════════════
# HELPERS CSV
# ══════════════════════════════════════════════════════════════

def _leer_posiciones():
    """Lee POSICIONES_CSV con dtypes seguros para evitar errores de tipo."""
    return pd.read_csv(
        POSICIONES_CSV,
        parse_dates=["entry_date", "exit_max_date"],
        dtype=POSICIONES_DTYPE,
    )

# ══════════════════════════════════════════════════════════════
# DATOS
# ══════════════════════════════════════════════════════════════

def descargar_datos(sma_period=200):
    """Descarga suficiente historia para calcular todas las features."""
    warmup_dias = max(60, sma_period // 24 + 30)
    inicio      = (pd.Timestamp.now() - pd.Timedelta(days=warmup_dias)).strftime("%Y-%m-%d")
    log(f"Descargando {ACTIVO} 1h desde {inicio}...")
    df = yf.download(
        ACTIVO, start=inicio, interval="1h",
        auto_adjust=False, progress=False
    )
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    df.columns = [c.lower() for c in df.columns]
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df = df.ffill().fillna(0).dropna(subset=["close", "high", "low"])
    log(f"✓ {len(df)} velas cargadas")
    return df

# ══════════════════════════════════════════════════════════════
# FEATURES  ← Deben coincidir con el entrenamiento
# ══════════════════════════════════════════════════════════════

def pctil_roll(series, w=WINDOW_PCT):
    def _rank_last(x):
        if len(x) < 2:
            return 0.5
        return float((x[:-1] < x[-1]).sum() / (len(x) - 1))
    return series.rolling(window=w, min_periods=w // 3).apply(_rank_last, raw=True)


def build_features(d, meta):
    d          = d.copy()
    ret1       = d["close"].pct_change(1)
    pr         = pctil_roll
    sma_period = meta.get("sma_period", 200)
    sma        = d["close"].rolling(sma_period).mean()

    d["vol_pct_24h"]                 = pr(ret1.rolling(24).std())
    d["vol_pct_72h"]                 = pr(ret1.rolling(72).std())
    d["btc_bull_regime"]             = (d["close"] > sma).astype(float)
    d[f"dist_sma{sma_period}_pct"]  = pr((d["close"] - sma) / (sma + 1e-8))

    ema12    = d["close"].ewm(span=12).mean()
    ema26    = d["close"].ewm(span=26).mean()
    macd_h   = (ema12 - ema26) - (ema12 - ema26).ewm(span=9).mean()
    d["macd_hist_pct"]       = pr(macd_h)
    d["hour_sin"]            = np.sin(2 * np.pi * d.index.hour / 24.0)

    rango_24h                = d["high"].rolling(24).max() - d["low"].rolling(24).min()
    d["rango_expansion_pct"] = pr(rango_24h / (d["close"] + 1e-8))

    return d.dropna()

# ══════════════════════════════════════════════════════════════
# PREDICCIÓN
# ══════════════════════════════════════════════════════════════

def predecir(modelo, meta, df_feat):
    features = meta.get("features", [])
    fila     = df_feat.iloc[-1]
    fecha    = df_feat.index[-1]
    precio   = float(fila["close"])
    cols     = [c for c in features if c in df_feat.columns]
    X        = fila[cols].fillna(0.5).values.reshape(1, -1)
    prob     = float(modelo.predict_proba(X)[:, 1][0])
    return prob, fecha, precio

# ══════════════════════════════════════════════════════════════
# REGISTROS
# ══════════════════════════════════════════════════════════════

def guardar_señal(fecha_barra, precio, prob, umbral, señal):
    nuevo = not os.path.exists(SEÑALES_CSV)
    with open(SEÑALES_CSV, "a", encoding="utf-8") as f:
        if nuevo:
            f.write("timestamp,fecha_barra,precio,prob,umbral,señal\n")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"{ts},{fecha_barra},{precio:.2f},{prob:.4f},{umbral:.4f},{int(señal)}\n")


def abrir_posicion(fecha_barra, precio_entrada, prob, umbral, meta):
    tp_pct    = meta.get("tp_pct", 0.025)
    sl_pct    = meta.get("sl_pct", 0.015)
    max_horas = meta.get("max_horas_trade", 48)
    tp_price  = precio_entrada * (1 + tp_pct)
    sl_price  = precio_entrada * (1 - sl_pct)
    exit_max  = fecha_barra + pd.Timedelta(hours=max_horas)

    nuevo = not os.path.exists(POSICIONES_CSV)
    with open(POSICIONES_CSV, "a", encoding="utf-8") as f:
        if nuevo:
            f.write("entry_date,entry_price,tp_price,sl_price,exit_max_date,"
                    "exit_price,retorno,motivo_salida,prob,umbral,estado\n")
        # FIX: usar "PENDIENTE" como placeholder en campos de salida
        # para que pandas infiera la columna motivo_salida como string (object)
        # y no como float64 (lo que ocurría cuando los campos quedaban vacíos)
        f.write(
            f"{fecha_barra},{precio_entrada:.2f},{tp_price:.2f},{sl_price:.2f},"
            f"{exit_max},,,PENDIENTE,{prob:.4f},{umbral:.4f},ABIERTA\n"
        )
    log(
        f"Posición abierta | entry={fecha_barra} | precio={precio_entrada:.2f} | "
        f"TP={tp_price:.2f} | SL={sl_price:.2f} | exit_max={exit_max} | prob={prob:.4f}",
        "SEÑAL"
    )


def _normalizar_ts(ts):
    """Convierte cualquier timestamp a naive (sin timezone)."""
    t = pd.Timestamp(ts)
    if t.tzinfo is not None:
        t = t.tz_localize(None)
    return t


def verificar_posiciones_abiertas(df_raw, meta):
    """
    Revisa si alguna posición abierta tocó TP, SL o venció por tiempo.
    Usa las velas recientes de df_raw.
    Devuelve lista de posiciones cerradas en esta ronda.
    """
    if not os.path.exists(POSICIONES_CSV):
        return []

    # FIX: leer con dtypes explícitos para que motivo_salida/exit_price/retorno
    # sean siempre string (object) y no float64, evitando TypeError al asignarles
    # valores como "TP 🎯" o "SL 🛑"
    df_pos   = _leer_posiciones()
    abiertas = df_pos[df_pos["estado"] == "ABIERTA"]
    if abiertas.empty:
        return []

    # Normalizar índice de df_raw a naive (sin timezone)
    df_raw = df_raw.copy()
    if hasattr(df_raw.index, 'tz') and df_raw.index.tz is not None:
        df_raw.index = df_raw.index.tz_localize(None)

    cerradas_ahora = []

    for idx_pos, pos in abiertas.iterrows():
        tp_price    = float(pos["tp_price"])
        sl_price    = float(pos["sl_price"])
        entry_price = float(pos["entry_price"])

        # Normalizar fechas del CSV a naive
        entry_date = _normalizar_ts(pos["entry_date"])
        exit_max   = _normalizar_ts(pos["exit_max_date"])

        velas_post = df_raw[df_raw.index > entry_date].copy()

        if velas_post.empty:
            log(
                f"⚠ Sin velas post entry {entry_date} | "
                f"df_raw va de {df_raw.index[0]} a {df_raw.index[-1]}",
                "WARN"
            )
            continue

        motivo      = None
        precio_exit = None
        fecha_exit  = None

        for ts, vela in velas_post.iterrows():
            h = float(vela["high"])
            l = float(vela["low"])
            c = float(vela["close"])

            if l <= sl_price:
                motivo      = "SL 🛑"
                precio_exit = sl_price
                fecha_exit  = ts
                break
            if h >= tp_price:
                motivo      = "TP 🎯"
                precio_exit = tp_price
                fecha_exit  = ts
                break
            if ts >= exit_max:
                motivo      = "Time ⏳"
                precio_exit = c
                fecha_exit  = ts
                break

        if motivo is None:
            log(
                f"Posición {entry_date} aún viva | "
                f"exit_max={exit_max} | última vela={df_raw.index[-1]}"
            )
            continue

        retorno = precio_exit / entry_price - 1

        # FIX: asignar directamente sobre el DataFrame ya tipado como object
        df_pos.at[idx_pos, "exit_price"]    = str(round(precio_exit, 2))
        df_pos.at[idx_pos, "retorno"]       = str(round(retorno, 6))
        df_pos.at[idx_pos, "motivo_salida"] = motivo
        df_pos.at[idx_pos, "estado"]        = "CERRADA"
        cerradas_ahora.append(df_pos.loc[idx_pos].to_dict())

        log(
            f"Posición cerrada | entry={entry_date} → exit={fecha_exit} | "
            f"ret={retorno:+.2%} | {motivo}",
            "OK"
        )
        discord_cierre_posicion(pos, precio_exit, retorno, motivo)

    df_pos.to_csv(POSICIONES_CSV, index=False)
    return cerradas_ahora


def contar_sl_recientes(ventana_horas=VENTANA_RACHA):
    """Cuenta SL en la ventana de anti-racha.
    Usa UTC en ambos lados para evitar desfase si Railway no corre en UTC."""
    if not os.path.exists(POSICIONES_CSV):
        return 0
    df_pos   = _leer_posiciones()
    cerradas = df_pos[df_pos["estado"] == "CERRADA"].copy()
    if cerradas.empty:
        return 0
    # entry_date guardado como naive UTC — normalizamos a UTC para comparar
    cerradas["entry_date"] = pd.to_datetime(cerradas["entry_date"], utc=False)
    limite = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(hours=ventana_horas)
    recientes = cerradas[cerradas["entry_date"] >= limite]
    return int((recientes["motivo_salida"] == "SL 🛑").sum())


def resumen_log():
    if not os.path.exists(POSICIONES_CSV):
        return
    df_pos   = _leer_posiciones()
    cerradas = df_pos[df_pos["estado"] == "CERRADA"]
    abiertas = df_pos[df_pos["estado"] == "ABIERTA"]
    if cerradas.empty:
        log(f"Sin posiciones cerradas aún | Abiertas: {len(abiertas)}")
        return
    rets = pd.to_numeric(cerradas["retorno"], errors="coerce").dropna()
    wr   = (rets > 0).mean()
    pf   = rets[rets > 0].sum() / (abs(rets[rets < 0].sum()) + 1e-8)
    log(
        f"RESUMEN | Cerradas: {len(cerradas)} | Abiertas: {len(abiertas)} | "
        f"WR: {wr:.1%} | PF: {pf:.2f} | Acum: {rets.sum()*100:+.1f}%"
    )

# ══════════════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════════════

def main():
    log("=" * 60)
    log("CINAX BTC v2 — Paper Trading Horario")
    log(f"Anti-racha: bloqueo si >={SL_RACHA_MAX} SL en últimas {VENTANA_RACHA}h")
    log(f"Datos en  : {DATA_DIR}")
    log(f"Discord   : {'configurado ✓' if DISCORD_WEBHOOK else 'NO configurado'}")
    log("=" * 60)

    # Cargar modelo y meta
    for path, label in [(RUTA_PKL, "modelo"), (RUTA_META, "meta")]:
        if not os.path.exists(path):
            log(f"ERROR: No se encontró {label} en: {path}", "ERR")
            return

    with open(RUTA_PKL, "rb") as f:
        modelo = pickle.load(f)
    with open(RUTA_META, "rb") as f:
        meta   = pickle.load(f)

    sma_period = meta.get("sma_period", 200)
    tp_pct     = meta.get("tp_pct", 0.025)
    sl_pct     = meta.get("sl_pct", 0.015)
    max_horas  = meta.get("max_horas_trade", 48)
    gate_bull  = meta.get("gate_bull", True)

    log(
        f"Modelo cargado | SMA: {sma_period}h | TP: {tp_pct*100:.1f}% | "
        f"SL: {sl_pct*100:.1f}% | Max: {max_horas}h | gate_bull: {gate_bull}",
        "OK"
    )

    ultima_hora_evaluada = None

    while True:
        try:
            ahora = datetime.now()

            # BTC es 24/7 — evaluar en el minuto 5 de cada hora
            minuto_actual = ahora.minute
            if minuto_actual < 5:
                espera = (5 - minuto_actual) * 60
                log(f"Esperando minuto :05 ... {espera}s")
                time.sleep(espera)
                continue

            hora_actual = ahora.replace(minute=0, second=0, microsecond=0)

            if hora_actual == ultima_hora_evaluada:
                log(f"Hora {hora_actual} ya evaluada. Esperando próxima hora...")
                time.sleep(CHECK_MINS * 60 - ahora.minute * 60 - ahora.second + 360)
                continue

            log(f"─── Evaluando hora {hora_actual} ───")

            # Descargar datos y calcular features
            df_raw  = descargar_datos(sma_period)
            df_feat = build_features(df_raw, meta)

            if df_feat.empty:
                log("DataFrame vacío — reintentando en 5 min.", "WARN")
                time.sleep(300)
                continue

            # Verificar posiciones abiertas
            cerradas = verificar_posiciones_abiertas(df_raw, meta)
            if cerradas:
                log(f"{len(cerradas)} posición(es) cerrada(s) esta ronda")

            # Obtener predicción de la última vela
            prob, fecha_barra, precio = predecir(modelo, meta, df_feat)
            umbral = float(meta.get("umbral_produccion", 0.5))

            log(f"BTC: {precio:,.2f} | prob: {prob:.4f} | umbral: {umbral:.4f}")

            # Gate de régimen
            en_bull = bool(df_feat["btc_bull_regime"].iloc[-1] == 1.0)
            if gate_bull and not en_bull:
                log(f"Régimen bajista (precio < SMA{sma_period}) — señal omitida")
                ultima_hora_evaluada = hora_actual
                time.sleep(CHECK_MINS * 60)
                continue

            señal = prob >= umbral

            if señal:
                # Único filtro: anti-racha (fiel al backtest)
                n_sl_recientes = contar_sl_recientes(VENTANA_RACHA)
                if n_sl_recientes >= SL_RACHA_MAX:
                    log(
                        f"🚫 Anti-racha: {n_sl_recientes} SL en últimas {VENTANA_RACHA}h — entrada bloqueada",
                        "WARN"
                    )
                    discord_bloqueado_racha(fecha_barra, n_sl_recientes, VENTANA_RACHA)
                    señal = False

            if señal:
                log(f"★ SEÑAL LARGA ★ — BTC: {precio:,.2f} | prob: {prob:.4f}", "SEÑAL")
                abrir_posicion(fecha_barra, precio, prob, umbral, meta)
                discord_señal_nueva(
                    fecha_barra, precio, prob, umbral,
                    tp_pct, sl_pct, max_horas, sma_period
                )
            else:
                log(f"Sin señal | prob={prob:.4f} < umbral={umbral:.4f}" if prob < umbral
                    else f"Señal bloqueada (ver log)")

            guardar_señal(fecha_barra, precio, prob, umbral, señal)
            resumen_log()

            # Seguimiento cada 8 horas si hay posición abierta
            if os.path.exists(POSICIONES_CSV):
                df_pos = _leer_posiciones()
                if len(df_pos[df_pos["estado"] == "ABIERTA"]) > 0:
                    if ahora.hour % 8 == 0:
                        discord_seguimiento(fecha_barra, precio)

            ultima_hora_evaluada = hora_actual

            # Esperar hasta el siguiente minuto :05
            prox_hora = hora_actual + pd.Timedelta(hours=1)
            prox_eval = prox_hora.replace(minute=5)
            espera    = max(60, (prox_eval - datetime.now()).total_seconds())
            log(f"Próxima evaluación en {espera/60:.0f} min")
            time.sleep(espera)

        except KeyboardInterrupt:
            log("Detenido por usuario.", "WARN")
            resumen_log()
            break
        except Exception as e:
            import traceback
            log(f"Error: {e}", "ERR")
            log(traceback.format_exc(), "ERR")
            time.sleep(60)


if __name__ == "__main__":
    main()
