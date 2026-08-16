# rest

REST API модуль для Mia Framework. HTTP API на FastAPI поверх apiproxy.

## Features

- **Динамические маршруты** из MethodRegistry
- **POST /api/v1/{module}/{method}** — JSON body
- **GET /api/v1/{module}?method={method}&arg1=val1** — query params
- **Bootstrap endpoints** — GET /api/v1/auth/status, POST /api/v1/auth/bootstrap
- **Health check** — GET /api/v1/health
- **Браузерный редирект** — 401 + Accept: text/html → 302
- **Пагинация** — формат {items, total, offset, limit}

## Usage

```python
app.load_module("rest")

# Или запуск через CLI
from rest.server import run_server
run_server(app, host="0.0.0.0", port=8000)
```

## Configuration

| ENV Variable | Default | Description |
|---|---|---|
| `MIA_REST_HOST` | `0.0.0.0` | Хост |
| `MIA_REST_PORT` | `8000` | Порт |
| `MIA_REST_ENABLED` | `true` | Включён ли сервер |

## Routes

| Method | Path | Описание |
|---|---|---|
| GET | `/api/v1/health` | Health check |
| GET | `/api/v1` | Список модулей и методов |
| GET | `/api/v1/auth/status` | Нужен ли bootstrap (публичный) |
| POST | `/api/v1/auth/bootstrap` | Создание первого админа (публичный) |
| POST | `/api/v1/{module}/{method}` | Вызов метода (JSON body) |
| GET | `/api/v1/{module}?method={method}` | Вызов метода (query params) |
