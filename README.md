# Inventory Master OS Web v2026

Sistema de inventario con **préstamos y licencias**, evolucionado de la aplicación de escritorio (CustomTkinter + SQLite) a una **aplicación web moderna, multiusuario y desplegable en red local**.

## 🚀 Características

- **Login seguro**: contraseñas con hash bcrypt + salt, sesiones con **JWT**.
- **Recuperación de contraseña** mediante pregunta de seguridad.
- **Inventario**: alta, edición, borrado, stock, precios de compra/venta y hasta 3 ubicaciones por producto.
- **Carga masiva** de productos desde CSV o Excel.
- **Préstamos**: registro con ticket PDF, devolución parcial/total, prórrogas, bloqueo automático de vendedores con mercancía vencida y recordatorio por WhatsApp.
- **Dashboard interactivo** con métricas en tiempo real (total productos, préstamos activos, vencidos, stock bajo, capital invertido, ingreso potencial), gráficas de top productos y de actividad de los últimos 7 días, y accesos directos.
- **Licencias mensuales** `MC26-XXXX-XXXX` (30 días) con generación de claves por admin y bloqueo del sistema al vencer.
- **Backups**: automáticos diarios (pg_dump o respaldo Excel) con retención configurable, **restaurar base de datos anterior** y **borrar todos menos el último** desde la interfaz.
- **Usuarios con contraseña genérica** (`Cambiar123!`) y **cambio forzado de contraseña en el primer inicio de sesión**. Solo el admin puede crearlos.
- **Historial de movimientos solo para administradores** (exportable a Excel).
- **Generador de contraseñas** como programa aparte (doble clic).
- **Logo de empresa** para los comprobantes PDF.
- **Roles**: `admin` y `operador` (máx. 2 operadores recomendado según tu esquema de negocio).
- **Responsive**: funciona en computadoras, tablets y celulares de la red local.

## 🧱 Stack tecnológico

| Capa        | Tecnología                                        |
|-------------|---------------------------------------------------|
| Backend     | Python 3.13 · FastAPI · SQLAlchemy 2 · JWT        |
| Base datos  | PostgreSQL 16                                     |
| Frontend    | React 18 · Vite 6 · Tailwind CSS 4 · Recharts 3   |
| Extra       | APScheduler (backups) · ReportLab (PDF) · Pandas (Excel) |

## 📁 Estructura del proyecto

```
inventory-master-web/
├── backend/                  # API FastAPI
│   ├── app/
│   │   ├── main.py           # App, CORS, seed, scheduler
│   │   ├── config.py         # Configuración (.env)
│   │   ├── database.py       # Motor y sesiones SQLAlchemy
│   │   ├── models.py         # Modelos ORM (users, products, loans, ...)
│   │   ├── schemas.py        # Validación Pydantic
│   │   ├── deps.py           # Auth, roles, licencia
│   │   ├── routers/          # auth, users, products, loans, dashboard,
│   │   │                     # license, settings, backup, audit, reports
│   │   ├── services/         # backup.py (pg_dump/Excel), pdf.py
│   │   └── utils/            # security.py, licenses.py, audit.py
│   ├── uploads/logos/        # Logos subidos
│   ├── backups/              # Backups generados
│   └── requirements.txt
├── frontend/                 # Aplicación React
│   ├── src/
│   │   ├── api/              # Cliente axios + llamadas REST
│   │   ├── components/       # layout/ y ui/ (StatCard, Modal, Table, ...)
│   │   ├── pages/            # Login, ChangePassword, Dashboard, Products,
│   │   │                     # Loans, History, Admin, License
│   │   └── context/          # AuthContext (sesión)
│   └── package.json
├── tools/
│   ├── generador_contrasenas.py   # Generador de contraseñas (programa aparte)
│   └── generador_contrasenas.bat  # Lanzador de doble clic
├── database/
│   └── init.sql              # Esquema SQL manual (opcional)
├── docs/
│   └── deployment.md         # Guía de instalación y despliegue
├── docker-compose.yml        # PostgreSQL listo para usar
└── README.md
```

## ⚙️ Instalación rápida (Windows)

> Requisitos: **Python 3.12+**, **Node.js 18+**, **PostgreSQL 16**.

### 1. Base de datos PostgreSQL

Opción A — con Docker (recomendada):

```bash
docker compose up -d db
```

Opción B — manual: crea una base llamada `inventario_db`, usuario `inventario` y contraseña `inventario_secreto`.

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env     # ajusta DATABASE_URL y SECRET_KEY
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

> **¿Sin PostgreSQL instalado?** No hay problema para probar en local: si no existe el archivo `.env` y PostgreSQL no responde en `localhost:5432`, la aplicación **cae automáticamente a SQLite** (crea `backend/inventario_dev.db`) y funciona igual. Para el despliegue en red local instala PostgreSQL, crea el `.env` con `DATABASE_URL` y listo.

Las tablas y el usuario `admin` se crean automáticamente. Credenciales iniciales: **admin / admin1234** (cámbialas al primer ingreso).

La documentación interactiva de la API queda en: <http://localhost:8000/docs>

### 3. Frontend (desarrollo)

```bash
cd frontend
npm install
npm run dev
```

Abre <http://localhost:5173>

### 4. Producción (modo servidor para la red local)

```bash
cd frontend
npm run build          # genera frontend/dist
cd ..\backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

El backend sirve automáticamente el frontend compilado. Entra desde cualquier computadora de la red con: `http://IP_DEL_SERVIDOR:8000`

> Para que otras computadoras accedan, abre el puerto 8000 en el Firewall de Windows y agrega su IP en `CORS_ORIGINS` del `.env` (o usa `*` en una red de confianza).

## 🔑 Primeros pasos en la app

1. Inicia sesión con `admin / admin1234`.
2. Ve a **Panel Admin → Licencia** y activa una clave `MC26-XXXX-XXXX` (el admin puede generarlas en la sección Licencia).
3. Configura el logo y nombre de la empresa en **Panel Admin → Empresa**.
4. Carga tus productos con el botón **Carga masiva** desde el Dashboard/Inventario o uno a uno.
5. Crea usuarios en **Panel Admin → Usuarios**: se les asigna la contraseña genérica **`Cambiar123!`** y el sistema les pedirá cambiarla en su primer inicio de sesión.

## 🔑 Generador de contraseñas (programa aparte)

Doble clic en `tools\generador_contrasenas.bat` (o `python tools\generador_contrasenas.py`) para abrir una pequeña aplicación de escritorio que genera contraseñas seguras (longitud, mayúsculas, minúsculas, números, símbolos y exclusión de caracteres ambiguos) y las copia al portapapeles. No requiere instalar nada: usa solo la librería estándar de Python.

## 🌐 Despliegue en red local

Consulta la guía completa en [docs/deployment.md](docs/deployment.md).

## 🔐 Seguridad

- Contraseñas con **bcrypt** (cost 12) + JWT con expiración configurable.
- Endpoints protegidos por token; operaciones administrativas requieren rol `admin`.
- El sistema se **bloquea** si la licencia vence (todas las rutas de negocio devuelven `403 LICENSE_BLOCKED`).
- Cambia `SECRET_KEY` y las credenciales por defecto antes de usar en producción.

## 🤝 Contribuir / Subir a GitHub

```bash
git init
git add .
git commit -m "Inventory Master OS Web v2.0"
git remote add origin https://github.com/TU_USUARIO/inventory-master-web.git
git push -u origin main
```

El proyecto ya incluye `.gitignore`, `.env.example` y `docker-compose.yml` listos para el repositorio. **Nunca subas el archivo `.env`** (contiene secretos).
