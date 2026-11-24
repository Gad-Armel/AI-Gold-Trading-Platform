# Connecteur MT5 Aurum Quant AI — kit de démarrage VS Code (Windows)

## Limites et sécurité

Kit de développement local **lecture seule uniquement**. Il relie Python au terminal MT5 installé localement et expose une API locale pour vérifier le compte, les symboles, les cours et positions. Il ne transmet pas d'ordre, n'intègre pas d'IA décisionnelle, et n'établit pas de connexion depuis Blink/mobile. Ces étapes nécessitent un développement et une validation séparés. Utilisez exclusivement un compte démo. Ne transmettez jamais votre mot de passe dans un chat, un dépôt ou le frontend.

La librairie Python officielle nécessite Windows, Python 3.7–3.11 (vérifier la compatibilité courante sur la doc MetaQuotes), un terminal MT5 installé et l'architecture Python correspondante. Source: https://www.mql5.com/en/docs/python_metatrader5

## Arborescence à créer dans VS Code

```text
mt5-connector/
├── .gitignore
├── requirements.txt
├── .env.example
├── README.md
└── src/
    ├── __init__.py
    ├── settings.py
    ├── mt5_service.py
    └── api.py
```

Créez ces fichiers dans un nouveau dossier VS Code. Copiez `.env.example` vers `.env` localement si vous avez besoin des valeurs de configuration. `.env` est ignoré par Git. Ne fournissez pas les identifiants pour ce kit en lecture seule; laissez MT5 déjà ouvert et connecté manuellement au compte démo.

---

### `.gitignore`

```gitignore
.venv/
__pycache__/
*.py[cod]
.env
.vscode/
.pytest_cache/
```

### `requirements.txt`

```text
fastapi>=0.115,<1
uvicorn[standard]>=0.30,<1
MetaTrader5>=5.0.45
python-dotenv>=1.0,<2
```

### `.env.example`

```dotenv
# API strictement liée à localhost. Ne pas l'exposer sur le réseau.
API_HOST=127.0.0.1
API_PORT=8787
# Chemin facultatif vers terminal64.exe; vide = terminal déjà démarré.
MT5_TERMINAL_PATH=
# Laisser désactivé pour ce kit lecture seule.
ALLOW_TRADE_ORDERS=false
```

### `src/__init__.py`

```python
"""Connecteur local MT5 en lecture seule."""
```

### `src/settings.py`

```python
from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("API_HOST", "127.0.0.1")
    port: int = int(os.getenv("API_PORT", "8787"))
    terminal_path: str = os.getenv("MT5_TERMINAL_PATH", "")
    allow_trade_orders: bool = os.getenv("ALLOW_TRADE_ORDERS", "false").lower() == "true"

settings = Settings()

if settings.host not in {"127.0.0.1", "localhost", "::1"}:
    raise RuntimeError("Refusing to bind outside localhost; remote exposure is not supported.")
if settings.allow_trade_orders:
    raise RuntimeError("Order execution is deliberately disabled in this starter kit.")
```

### `src/mt5_service.py`

```python
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
import MetaTrader5 as mt5
from .settings import settings

class MT5Unavailable(RuntimeError):
    pass


def _connected() -> None:
    info = mt5.terminal_info()
    if info is None:
        raise MT5Unavailable(f"MT5 terminal unavailable: {mt5.last_error()}")
    if not info.connected:
        raise MT5Unavailable("MT5 terminal is open but disconnected from the broker.")


def connect() -> dict[str, Any]:
    kwargs: dict[str, Any] = {"timeout": 10_000}
    if settings.terminal_path:
        kwargs["path"] = settings.terminal_path
    if not mt5.initialize(**kwargs):
        raise MT5Unavailable(f"MT5 initialize failed: {mt5.last_error()}")
    _connected()
    return {"connected": True, "checked_at": datetime.now(timezone.utc).isoformat()}


def status() -> dict[str, Any]:
    _connected()
    terminal = mt5.terminal_info()
    version = mt5.version()
    return {
        "connected": True,
        "terminal_name": getattr(terminal, "name", None),
        "company": getattr(terminal, "company", None),
        "terminal_build": version[0] if version else None,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "trading_enabled_by_connector": False,
    }


def account_summary() -> dict[str, Any]:
    _connected()
    account = mt5.account_info()
    if account is None:
        raise MT5Unavailable(f"Could not read account: {mt5.last_error()}")
    # Do not return login, server, name, or credentials from this local demo API.
    return {
        "currency": account.currency,
        "balance": account.balance,
        "equity": account.equity,
        "margin": account.margin,
        "free_margin": account.margin_free,
        "profit": account.profit,
        "leverage": account.leverage,
        "trade_allowed": bool(account.trade_allowed),
        "trade_expert": bool(account.trade_expert),
    }


def allowed_symbols() -> list[dict[str, Any]]:
    _connected()
    result = []
    for symbol in ("XAUUSD", "EURUSD", "BTCUSD"):
        info = mt5.symbol_info(symbol)
        if info is None:
            result.append({"symbol": symbol, "available": False, "reason": "Symbol not found; broker may use a suffix."})
            continue
        selected = bool(info.visible) or bool(mt5.symbol_select(symbol, True))
        tick = mt5.symbol_info_tick(symbol) if selected else None
        result.append({
            "symbol": symbol,
            "available": bool(selected and tick),
            "digits": info.digits,
            "point": info.point,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "trade_mode": info.trade_mode,
            "bid": tick.bid if tick else None,
            "ask": tick.ask if tick else None,
            "time_msc": tick.time_msc if tick else None,
        })
    return result


def positions() -> list[dict[str, Any]]:
    _connected()
    items = mt5.positions_get()
    if items is None:
        raise MT5Unavailable(f"Could not read positions: {mt5.last_error()}")
    return [{
        "ticket": int(p.ticket),
        "symbol": p.symbol,
        "type": int(p.type),
        "volume": p.volume,
        "price_open": p.price_open,
        "price_current": p.price_current,
        "profit": p.profit,
        "sl": p.sl,
        "tp": p.tp,
        "time": int(p.time),
    } for p in items]


def disconnect() -> None:
    mt5.shutdown()
```

### `src/api.py`

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from . import mt5_service
from .settings import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        mt5_service.connect()
    except mt5_service.MT5Unavailable:
        # API starts even if terminal is offline; health explains the state.
        pass
    yield
    mt5_service.disconnect()

app = FastAPI(title="Aurum Quant local MT5 monitor", version="0.1.0", lifespan=lifespan)
# Local-only origins. This is not a remotely accessible API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000", "http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Accept", "Content-Type"],
)


def read_or_503(fn):
    try:
        return fn()
    except mt5_service.MT5Unavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

@app.get("/health")
def health():
    return {"service": "ok", "mode": "read-only"}

@app.get("/api/mt5/status")
def get_status():
    return read_or_503(mt5_service.status)

@app.get("/api/mt5/account")
def get_account():
    return read_or_503(mt5_service.account_summary)

@app.get("/api/mt5/symbols")
def get_symbols():
    return read_or_503(mt5_service.allowed_symbols)

@app.get("/api/mt5/positions")
def get_positions():
    return read_or_503(mt5_service.positions)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api:app", host=settings.host, port=settings.port, reload=False)
```

---

## Lancement dans VS Code / PowerShell

Dans le dossier `mt5-connector` :

```powershell
py -3 --version
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Ouvrez MT5 manuellement et connectez-vous au compte démo. Puis lancez :

```powershell
python -m src.api
```

Dans le navigateur du même PC, consultez :

- `http://127.0.0.1:8787/health`
- `http://127.0.0.1:8787/docs`
- `http://127.0.0.1:8787/api/mt5/status`
- `http://127.0.0.1:8787/api/mt5/account`
- `http://127.0.0.1:8787/api/mt5/symbols`
- `http://127.0.0.1:8787/api/mt5/positions`

Si PowerShell bloque l'activation, exécutez dans cette fenêtre uniquement `Set-ExecutionPolicy -Scope Process Bypass`, puis réactivez l'environnement virtuel. Cela ne change pas la politique système.

## Lecture rapide avec Python

```powershell
python -c "import MetaTrader5 as mt5; print('init', mt5.initialize()); print('terminal', mt5.terminal_info()); print('account', mt5.account_info()); mt5.shutdown()"
```

## État attendu

- `connected: true` signifie que la bibliothèque voit le terminal; vérifiez aussi que le compte affiché dans MT5 est bien le compte démo attendu.
- Si un symbole est absent, vérifiez son nom exact dans Market Watch chez le courtier; ce kit ne devine pas les suffixes.
- Une erreur `initialize failed` nécessite la vérification de l'installation Windows/Python 64-bit, du terminal MT5 ouvert et des prérequis officiels.
- La réponse `/account` contient des valeurs financières du compte; n'exposez jamais ce port sur Internet.

## Jusqu'à l'intégration complète

Ce petit service ne se connecte qu'au navigateur du même ordinateur. Pour que Blink PC/web ou l'app mobile consulte ces données à distance, il faut ajouter un relais distant authentifié/chiffré, autoriser uniquement une liaison sortante depuis l'ordinateur, faire signer/expirer les commandes et associer chaque commande à l'utilisateur. Le dépôt mobile actuel ne possède pas cette passerelle. Ne remplacez pas cela par une redirection de port, un tunnel public non authentifié, ou des identifiants dans le navigateur.

L'exécution d'ordres est volontairement exclue de ce kit. Avant de l'implémenter séparément, exiger tests démo avec limites de positions, allowlist, taille maximale, Stop Loss, perte maximale, cours récent, idempotence, expiration des propositions IA et confirmation/reconciliation MT5. L'IA ne doit jamais envoyer directement des ordres ni lever ces garde-fous.
