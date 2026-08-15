# Guía de instalación y despliegue en red local

Esta guía cubre la instalación completa del sistema en una computadora que actuará como **servidor**, y el acceso desde otras computadoras de la misma red.

---

## 1. Requisitos del servidor

- **Windows 10/11** (esta guía) o Linux.
- **Python 3.12+** → https://www.python.org/downloads/ (marca "Add Python to PATH").
- **Node.js 18+** → https://nodejs.org (solo necesario para recompilar el frontend).
- **PostgreSQL 16** → https://www.postgresql.org/download/windows/

---

## 2. Instalar y configurar PostgreSQL (manual)

1. Instala PostgreSQL con el instalador oficial (asistente de configuración). Anota la contraseña del superusuario `postgres`.
2. Abre *SQL Shell (psql)* y ejecuta:

```sql
CREATE USER inventario WITH PASSWORD 'inventario_secreto';
CREATE DATABASE inventario_db OWNER inventario;
GRANT ALL PRIVILEGES ON DATABASE inventario_db TO inventario;
\q
```

> Alternativa con Docker: `docker compose up -d db`

### pg_dump (para backups en formato SQL)

Asegúrate de que `pg_dump` esté en el PATH o agrega `C:\Program Files\PostgreSQL\16\bin` a las variables de entorno. Si no está disponible, el sistema genera igualmente un **respaldo Excel** automáticamente.

---

## 3. Instalar el backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edita `.env`:

```ini
DATABASE_URL=postgresql+psycopg2://inventario:inventario_secreto@localhost:5432/inventario_db
SECRET_KEY=cambia-esto-por-una-frase-larga-y-aleatoria
ADMIN_PASSWORD=tu-contrasena-admin-segura
```

## 4. Compilar el frontend

```powershell
cd frontend
npm install
npm run build
```

> Esto genera `frontend/dist`, que el backend sirve automáticamente. Solo se necesita hacer una vez (o cuando cambie el frontend).

## 5. Arrancar el servidor

```powershell
cd backend
.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Verás los logs de inicio. La app queda disponible en:

- Local: <http://localhost:8000>
- Documentación API: <http://localhost:8000/docs>

### Arranque automático con Windows (opcional)

Crea `iniciar_servidor.bat`:

```bat
@echo off
cd /d C:\ruta\al\proyecto\backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Coloca un acceso directo en `shell:startup` para que el sistema arranque solo al encender el servidor.

---

## 6. Acceso desde otras computadoras de la red

1. Averigua la IP del servidor: en PowerShell ejecuta `ipconfig` (busca *IPv4*, ej: `192.168.1.50`).
2. En el Firewall de Windows abre el puerto **8000**:

```powershell
netsh advfirewall firewall add rule name="Inventory Master" dir=in action=allow protocol=TCP localport=8000
```

3. Desde cualquier computadora/tablet/celular de la misma red abre:

```
http://192.168.1.50:8000
```

> No se necesita instalar nada en los clientes: todo funciona con el navegador.

### Configurar CORS (si usas frontend de desarrollo)

Si otra computadora ejecuta `npm run dev` (puerto 5173) apuntando al backend, agrega su IP a `CORS_ORIGINS` en el `.env`:

```ini
CORS_ORIGINS=http://localhost:5173,http://192.168.1.50:5173
```

Para una red de confianza también puedes usar `CORS_ORIGINS=*`.

---

## 7. Backups

- Se generan **automáticamente cada día a las 03:00** (`BACKUP_HOUR`).
- Se conservan **30 días** (`BACKUP_RETENTION_DAYS`).
- Puedes hacer un backup manual y descargarlo desde **Panel Admin → Backups**.
- **Recomendación**: sincroniza la carpeta `backend/backups` con Google Drive/OneDrive para tener respaldo en la nube.

---

## 8. Licencias

- Cada clave `MC26-XXXX-XXXX` activa el sistema por **30 días**.
- El admin genera claves nuevas en **Licencia** (sección exclusiva).
- Al vencer la licencia, el sistema bloquea el acceso a los datos hasta activar una clave nueva (las cuentas y la configuración se conservan).

---

## 9. Solución de problemas

| Problema | Solución |
|---|---|
| `connection refused` a PostgreSQL | Verifica que el servicio `postgresql-x64-16` esté en ejecución y que el usuario/contraseña de `DATABASE_URL` sean correctos. |
| No se ven tablas al reiniciar | Normal: la app crea el esquema automáticamente con `Base.metadata.create_all`. |
| Los backups son `.xlsx` y no `.sql` | `pg_dump` no está en el PATH; agrega `C:\Program Files\PostgreSQL\16\bin`. |
| Otras PC no acceden | Abre el puerto 8000 en el firewall y verifica que estén en la misma red/IP correcta. |
| El frontend muestra "error 404" | Ejecuta `npm run build` en `frontend/` (falta `dist`). |
| Quiero cambiar la contraseña admin | En **Panel Admin → Mi cuenta → Cambiar contraseña** o reinicia la base. |

---

## 10. Actualizar la aplicación

```powershell
git pull
cd backend
.venv\Scripts\pip install -r requirements.txt
cd ..\frontend
npm install
npm run build
cd ..\backend
# reinicia uvicorn
```
