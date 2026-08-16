# Despliegue en producción

Este documento explica cómo publicar el proyecto:

- **Backend (FastAPI)** → [Render](https://render.com)
- **Frontend (React + Vite)** → [Vercel](https://vercel.com)
- **Base de datos** → PostgreSQL administrado por Render

> Repositorio de referencia: `https://github.com/scaner511/inventory-master`

---

## Arquitectura

```
Navegador (usuario)
   │
   ├── https://TU-FRONTEND.vercel.app        (React/Vite, SPA)
   │        └── llama a la API vía VITE_API_URL
   │
   └── https://TU-API.onrender.com/api/...   (FastAPI)
                └── PostgreSQL (Render)
```

El frontend en producción **no usa el proxy de `vite.config.js`** (ese proxy solo
existe para desarrollo). Todas las llamadas van al backend por la variable
`VITE_API_URL`, definida en el build de Vercel.

---

## 1. Crear la base de datos PostgreSQL en Render

1. Entra a [https://dashboard.render.com](https://dashboard.render.com) → **New** → **PostgreSQL**.
2. Nombra el servicio, por ejemplo `inventory-master-db`.
3. Plan: **Free** (para pruebas) o **Starter** (para producción).
4. Región: usa la misma que el Web Service (recomendado: `Oregon (us-west)`).
5. Clic en **Create Database**.

Al crearse, Render entrega la **Internal Connection String**, algo así:

```
postgres://inventory_user:PASSWORD@dpg-xxxxxx-a.oregon-postgres.render.com/inventory
```

Guárdala; la usarás en el paso siguiente. **No necesita `psycopg2` ni cambios de
esquema**: la app crea las tablas automáticamente al arrancar.

> Si usas el **Blueprint** (archivo `render.yaml` del repo), la base de datos se
> crea automáticamente y Render inyecta `DATABASE_URL` en el Web Service. Puedes
> saltarte los pasos manuales del punto 2.

---

## 2. Crear el Web Service en Render (Backend)

### Opción A — Blueprint (recomendado, reproducible)

1. En Render Dashboard → **New** → **Blueprint**.
2. Conecta el repositorio `scaner511/inventory-master`.
3. Render detecta `render.yaml` y crea: la base de datos `inventory-master-db`
   y el servicio `inventory-master-api`.
4. El primer despliegue fallará hasta definir dos variables que quedaron
   pendientes (`sync: false`): **ADMIN_PASSWORD** y **CORS_ORIGINS**. Ve a
   **Environment** del servicio y defínelas (ver punto 3).
5. Clic en **Manual Deploy** → **Deploy latest commit**.

### Opción B — Manual (Web Service)

1. **New** → **Web Service** → conecta el repositorio.
2. **Root Directory**: `backend`
3. **Runtime**: `Python 3`
4. **Build Command**:
   ```
   pip install -r requirements.txt
   ```
5. **Start Command**:
   ```
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
6. Plan **Free** (se apaga tras inactividad; el primer acceso tarda ~1 min) o **Starter**.
7. Añade la base de datos: **Dashboard** del servicio → **Connect** → selecciona
   `inventory-master-db`. Esto crea automáticamente la variable `DATABASE_URL`.

---

## 3. Variables de entorno necesarias en Render

En el servicio → **Environment**, define:

| Variable | Ejemplo | Obligatoria |
| --- | --- | --- |
| `DATABASE_URL` | `postgres://...` (la entrega Render) | Sí (auto, si conectas la BD) |
| `SECRET_KEY` | cadena aleatoria de 50+ caracteres | Sí (Blueprint la genera sola) |
| `ADMIN_PASSWORD` | contraseña fuerte del admin inicial | Sí |
| `CORS_ORIGINS` | `https://TU-FRONTEND.vercel.app` | Sí (dominios exactos) |
| `ADMIN_USERNAME` | `admin` | No |
| `ADMIN_EMAIL` | `admin@tudominio.com` | No |
| `SUPERADMIN_USERNAME` | `superadmin` | No (default `superadmin`) |
| `SUPERADMIN_PASSWORD` | contraseña fuerte del Super Admin | Sí (default solo dev) |
| `SUPERADMIN_EMAIL` | `superadmin@tudominio.com` | No |

> **CRÍTICO — Sin `DATABASE_URL` la app NO arranca en Render.** Si la base
> PostgreSQL no está conectada al Web Service, la app **falla con un error
> visible** en vez de usar SQLite en disco efímero. Render Free usa un disco
> EFÍMERO: si la app usara SQLite ahí, la licencia, los usuarios y los datos se
> borrarían en cada reinicio/redeploy. Para conectar la base: **Dashboard →
> Web Service → Connect → selecciona `inventory-master-db`**. Esto crea
> automáticamente la variable `DATABASE_URL`.

Otras opcionales (`ACCESS_TOKEN_EXPIRE_MINUTES`, `BACKUP_HOUR`, `BACKUP_RETENTION_DAYS`,
`LICENSE_PREFIX`, `LICENSE_DURATION_DAYS`, `LOW_STOCK_THRESHOLD`) están documentadas
en `.env.example`. El frontend de Vercel (`*.vercel.app`) está permitido por CORS
automáticamente mediante `CORS_ORIGIN_REGEX`; los **dominios personalizados** se
agregan como orígenes exactos en `CORS_ORIGINS` (separados por comas).

> **Generar `SECRET_KEY` seguro:**
> ```
> python -c "import secrets; print(secrets.token_urlsafe(50))"
> ```

### NOTA IMPORTANTE — Filesystem efímero en Render (plan Free)

Render Free usa un disco **efímero**: se borra con cada redeploy o reinicio.

- El **logo** subido desde el Panel de Administración (`/uploads`) se perderá.
- Los **backups automáticos** (APScheduler) y el reporte diario se guardan en disco
  y también se perderán.

Para producción real:

- Guarda el logo/archivos en **Cloudinary**, **Amazon S3** o **Cloudflare R2**.
- Usa la descarga manual de backups antes de cada redeploy, o apunta los backups a
  un bucket externo.

---

## 4. Desplegar el frontend en Vercel

1. Entra a [https://vercel.com](https://vercel.com) → **Add New** → **Project**.
2. Importa el repositorio `scaner511/inventory-master`.
3. **Root Directory**: `frontend`
4. Vercel detecta Vite automáticamente:
   - **Framework Preset**: `Vite`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
5. En **Environment Variables** agrega:
   ```
   VITE_API_URL=https://TU-API.onrender.com
   ```
   (La app agrega `/api` sola si no está en la URL.)
6. Clic en **Deploy**.

El archivo `vercel.json` del repo agrega *rewrites* para que las rutas de React
Router (`/products`, `/loans`, `/history`, etc.) funcionen al recargar la página
(SPA fallback).

---

## 5. Conectar frontend ↔ backend

- El frontend usa `import.meta.env.VITE_API_URL` como base de Axios (ver
  `frontend/src/api/client.js`). Con `VITE_API_URL=https://TU-API.onrender.com`,
  las llamadas van a `https://TU-API.onrender.com/api/...`.
- CORS: el backend permite `http://localhost:5173` (desarrollo), cualquier
  `https://*.vercel.app` (regex) y los dominios exactos de `CORS_ORIGINS`.
- Autenticación: el token JWT viaja en la cabecera `Authorization: Bearer ...`;
  los reportes PDF/Excel usan descarga autenticada (blob) — no requieren CORS extra.

### Desarrollo local sin cambios

Si no defines `VITE_API_URL`, la app usa `/api` en el mismo origen y el proxy de
`vite.config.js` apunta a `localhost:8000`. Nada de lo anterior interfiere con
`npm run dev`.

---

## 6. Checklist final de verificación

- [ ] El Web Service de Render arranca y el log muestra `Application startup complete`.
- [ ] `https://TU-API.onrender.com/api/health` responde `{"status":"ok",...}`.
- [ ] Se crearon las tablas en PostgreSQL (Render → tu base → Tables: users, products, loans...).
- [ ] La primera compra/creación de usuario no se hace con la contraseña por defecto
      (`ADMIN_PASSWORD` definida en Render).
- [ ] `https://TU-FRONTEND.vercel.app` carga el login.
- [ ] Login con el admin funciona (JWT + CORS correctos).
- [ ] Una ruta directa de React Router (ej. `https://TU-FRONTEND.vercel.app/products`)
      carga la app (verifica el rewrite del `vercel.json`).
- [ ] Generar el comprobante PDF de un préstamo funciona desde el frontend remoto.
- [ ] Subir un logo y descargar un backup funcionan (recuerda: el disco es efímero).
- [ ] `CORS_ORIGINS` incluye tu dominio real si no es `*.vercel.app`.

---

## Troubleshooting rápido

| Problema | Solución |
| --- | --- |
| `ModuleNotFoundError: No module named 'app'` | El **Root Directory** debe ser `backend`. |
| `Invalid URI scheme: 'postgres'` | La app ya normaliza `postgres://` → `postgresql+psycopg2://`; si ves esto, revisa que el código del repo esté actualizado. |
| CORS: `No 'Access-Control-Allow-Origin'` | Revisa `CORS_ORIGINS` (dominio exacto del frontend) y `CORS_ORIGIN_REGEX`. |
| La API cae en plan Free tras inactividad | Es normal; el primer request tarda ~1 min en "despertar" el servicio. |
| El logo/backup desaparece tras un redeploy | Disco efímero; usa Cloudinary/S3/R2 (ver nota del punto 3). |
| `port must be int` al iniciar | Usa `--port $PORT` (Render define `$PORT` automáticamente). |
