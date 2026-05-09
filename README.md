# CINAX BTC v2 — Paper Trading Horario

Bot de paper trading para BTC/USD usando un modelo LightGBM entrenado (`.pkl`).  
Corre en Railway con un volumen persistente en `/data`.

---

## Estructura del repositorio

```
cinax_btc/
├── cinax_btc_v2.py     # Bot principal (worker)
├── dashboard.py        # Dashboard Flask (web)
├── modelo.pkl          # Tu modelo entrenado  ← subir manualmente
├── meta.pkl            # Metadatos del modelo ← subir manualmente
├── requirements.txt
├── Procfile
├── Dockerfile
└── README.md
```

---

## Parámetros leídos desde `meta.pkl`

El archivo `meta.pkl` debe ser un dict con:

| Clave                | Tipo    | Descripción                                      |
|----------------------|---------|--------------------------------------------------|
| `sma_period`         | int     | Período de la SMA para gate de régimen (ej. 200) |
| `tp_pct`             | float   | Take profit (ej. 0.025 = 2.5%)                  |
| `sl_pct`             | float   | Stop loss (ej. 0.015 = 1.5%)                    |
| `max_horas_trade`    | int     | Cierre por tiempo (ej. 48)                       |
| `umbral_produccion`  | float   | Umbral de probabilidad (ej. 0.52)               |
| `gate_bull`          | bool    | Filtrar entradas en régimen bajista              |
| `features`           | list    | Lista de columnas usadas por el modelo           |

---

## Variables de entorno en Railway

| Variable         | Descripción                                              |
|------------------|----------------------------------------------------------|
| `DISCORD_WEBHOOK`| URL del webhook de Discord para alertas                  |
| `RUTA_PKL`       | Ruta al modelo (default: `modelo.pkl`)                   |
| `RUTA_META`      | Ruta al meta (default: `meta.pkl`)                       |

---

## Despliegue en Railway

### 1. Crear repositorio en GitHub

```bash
git init
git add .
git commit -m "CINAX BTC v2 inicial"
git remote add origin https://github.com/TU_USUARIO/cinax-btc.git
git push -u origin main
```

### 2. Subir los archivos .pkl

Opciones:
- **Opción A**: Incluirlos directamente en el repositorio (si son pequeños, < 100MB)
- **Opción B**: Subirlos al volumen persistente de Railway via Railway CLI:
  ```bash
  railway run -- python -c "import shutil; shutil.copy('modelo.pkl', '/data/modelo.pkl')"
  ```
  Y luego configurar `RUTA_PKL=/data/modelo.pkl`

### 3. Crear proyecto en Railway

1. En [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**
2. Selecciona el repositorio
3. Railway detecta el `Dockerfile` automáticamente

### 4. Agregar volumen persistente

1. En el proyecto Railway → **Add Service** → **Volume**
2. Montarlo en `/data`

### 5. Configurar variables de entorno

En Railway → **Variables**:
```
DISCORD_WEBHOOK=https://discord.com/api/webhooks/...
```

### 6. Configurar los dos servicios (Procfile)

Railway desplegará el `Procfile`:
- `worker` → `cinax_btc_v2.py` (bot principal)
- `web`    → `dashboard.py` (dashboard)

---

## Anti-racha

El bot bloquea nuevas entradas si detecta **≥ 2 SL en las últimas 12 horas**.  
Ajustable con las constantes `SL_RACHA_MAX` y `VENTANA_RACHA` en `cinax_btc_v2.py`.

---

## Dashboard

Disponible en la URL pública de Railway (servicio `web`).  
Se actualiza automáticamente cada 60 segundos.

Endpoints:
- `/`             → Dashboard visual
- `/api/data`     → JSON con KPIs, posiciones y log
- `/api/señales`  → JSON con historial de señales
- `/health`       → Health check

---

## Ciclo del bot

```
Cada hora (minuto :05)
  ↓
Descargar BTC-USD 1h
  ↓
Calcular features (SMA, MACD, vol, etc.)
  ↓
Verificar posiciones abiertas → TP / SL / Time
  ↓
Predecir con modelo
  ↓
Gate de régimen (precio > SMAn?)
  ↓
Anti-racha (≥ 2 SL en 12h?)
  ↓
¿Ya hay posición abierta?
  ↓
ABRIR o ignorar
  ↓
Guardar señal + notificar Discord
```

---

## Archivos de datos generados en `/data`

| Archivo                    | Descripción                      |
|----------------------------|----------------------------------|
| `cinax_btc.log`            | Log completo del sistema         |
| `cinax_btc_señales.csv`    | Historial de todas las señales   |
| `cinax_btc_posiciones.csv` | Registro de trades (paper)       |
| `cinax_btc_intra.csv`      | OHLC intra de posiciones abiertas|
