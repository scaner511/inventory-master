# Migración de Render (free) a Oracle Cloud Always Free

Guía paso a paso para mover el backend FastAPI + PostgreSQL desde Render (que
vence a los 90 días) a una VM **Oracle Cloud Always Free** (no caduca nunca si
usas solo los recursos Always Free).

Servicios que se levantan:

| Servicio | Imagen | Función |
|---|---|---|
| `db` | `postgres:16-alpine` | PostgreSQL (volumen `pgdata`) |
| `api` | `backend/Dockerfile` | FastAPI/uvicorn (1 worker) con APScheduler |
| `caddy` | `caddy:2-alpine` | Proxy inverso + HTTPS automático (Let's Encrypt) |

---

## 0. Requisitos

- Cuenta en [cloud.oracle.com](https://cloud.oracle.com) (pide tarjeta solo como
  verificación de identidad; **no te cobra** si permaneces dentro de los límites
  Always Free).
- Un dominio apuntando al servidor (o uno gratis con [DuckDNS](https://duckdns.org)).
- Acceso al panel actual en Render (para descargar backups) o exportar la BD antes
  de que venza.

---

## 1. Crear la VM en Oracle Cloud

1. Consola → **Compute → Instances → Create instance**.
2. **Shape**: la familia **Ampere A1 (ARM)** con los recursos Always Free
   (4 OCPU / 24 GB RAM recomendado).
3. **Image**: Oracle Linux 8 / Ubuntu 22.04 (o 24.04). Cualquiera sirve.
4. **SSH keys**: sube tu clave pública (o deja que Oracle cree una y descárgala).
   Guarda la clave privada en `~/.ssh/id_rsa_oracle` (o la ruta que uses).
5. Espera a que el estado sea **RUNNING** y anota la **IP pública**.

### Abrir el firewall (Security List)

En **Networking → Virtual Cloud Networks → <tu VCN> → Security Lists →
Default Security List → Add Ingress Rules**, abre:

| Protocolo | Puerto | Origen | Uso |
|---|---|---|---|
| TCP | 22 | 0.0.0.0/0 | SSH |
| TCP | 80 | 0.0.0.0/0 | HTTP (redirección a HTTPS por Caddy) |
| TCP | 443 | 0.0.0.0/0 | HTTPS |

> En Oracle Linux la regla entra en `iptables/firewalld`; normalmente ya queda
> abierto al crearla en la consola. Verifica con `sudo firewall-cmd --list-all`.

### Prueba de SSH

```bash
ssh -i ~/.ssh/id_rsa_oracle ubuntu@IP_PUBLICA
# o si la imagen es Oracle Linux:
ssh -i ~/.ssh/id_rsa_oracle opc@IP_PUBLICA
```

---

## 2. Instalar Docker y Docker Compose

```bash
# Ubuntu / Oracle Linux 8
sudo dnf update -y                          # (apt si es Ubuntu)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
docker compose version   # debe responder "Docker Compose version v2.x"
```

Cierra y vuelve a abrir SSH para que el grupo `docker` aplique.

---

## 3. Subir el proyecto y configurar

```bash
git clone https://github.com/scaner511/inventory-master.git
cd inventory-master/deploy/oracle
cp .env.oracle.example .env
nano .env            # cambia POSTGRES_PASSWORD, SECRET_KEY, API_DOMAIN, etc.
```

Ajustes obligatorios en `.env`:

- `POSTGRES_PASSWORD` → contraseña fuerte nueva.
- `SECRET_KEY` → `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`
- `ADMIN_PASSWORD` y `SUPERADMIN_PASSWORD` → contraseñas nuevas.
- `API_DOMAIN` → tu dominio (ej. `api.tudominio.com` o `mi-api.duckdns.org`).
- `PUBLIC_BASE_URL` → `https://` + `API_DOMAIN` (lo usa OAuth de Google Drive).
- `CORS_ORIGINS` → URL de tu panel (Vercel).

**Muy importante (licencias offline):** el código de activación del servidor está
almacenado en la BD (`licenses.machine_code`), no en el hardware. Como la BD se
migra completa, **las claves de licencia existentes siguen funcionando sin
regenerar nada**. `LICENSE_SECRET_KEY` debe quedar igual que en Render; si usas un
`.env` sin esa variable, el valor por defecto (`6c5ab6f0...`) es el mismo que
usa `offline_license.py`, así que las claves emitidas no se invalidan.

---

## 4. Migrar los DATOS (no olvides esto)

La app crea las tablas automáticamente al arrancar, pero **la base está vacía**.
Mueve los datos de Render antes de subir el compose completo (o descarga un backup
Excel desde el panel).

### Opción A: la BD de Render sigue viva (pg_dump → psql)

En tu máquina local (con `psql`/`pg_dump` instalados o desde WSL):

```bash
# Toma la URL de conexión de Render (Settings → Database → Internal Database URL,
# convirtiendo postgres:// en postgresql:// no hace falta: pg_dump lo acepta)
pg_dump "postgresql://USUARIO:PASSWORD@HOST:5432/BASEDATOS" \
  --no-owner --no-acl -f backup_render.sql
```

Sube y restaura. Primero levanta solo la BD:

```bash
cd inventory-master/deploy/oracle
docker compose up -d db
scp backup_render.sql ubuntu@IP_PUBLICA:~
ssh ubuntu@IP_PUBLICA
cd inventory-master/deploy/oracle
docker compose exec -T db \
  sh -c 'psql -U inventario -d inventario_db' < ~/backup_render.sql
```

### Opción B: la BD de Render ya venció

Descarga el último **backup del panel** (Admin → Respaldo → descargar) o usa el
botón "Cargar base de datos anterior" (`/api/backup/restore`) después de levantar
la app.

---

## 5. Levantar todo

```bash
cd inventory-master/deploy/oracle
docker compose up -d --build
docker compose ps            # db, api, caddy deben estar "Up" y caddy "healthy"
```

El primer arranque de la API puede tardar algunos segundos (migraciones + creación
del admin/superadmin). Verifica:

```bash
curl -s https://tu-dominio/api/health
# → {"status":"ok",...}   (o el payload que devuelva /api/health)
curl -s http://localhost:8000/api/health   # dentro del servidor, prueba directa
```

Revisa los logs si algo falla:

```bash
docker compose logs -f api
docker compose logs -f caddy
```

---

## 6. DNS y HTTPS

- **Dominio propio**: crea un registro `A`/`AAAA` que apunte `api.tudominio.com`
  → IP_PUBLICA del servidor. Caddy emitirá el certificado Let's Encrypt solo.
- **DuckDNS (gratis)**: crea un subdominio `mi-api.duckdns.org`, pon la IP pública
  y **programa la actualización de IP** (DuckDNS da un cron/script). Usa ese
  nombre en `API_DOMAIN`.

Caddy auto-HTTPS funciona si los puertos 80 y 443 están abiertos hacia el dominio
desde Internet (paso 1). Si prefieres probar sin dominio, comenta el primer bloque
del `Caddyfile` y usa el bloque `:80` (HTTP simple con la IP).

---

## 7. Actualizar las integraciones externas

Una vez el API responde en el dominio nuevo:

1. **Panel (Vercel)**: en el proyecto, variable de entorno
   `VITE_API_URL=http://localhost:5173/api` → `https://tu-dominio/api` y redeploy.
   (Según cómo consumes el API; ajusta la variable real usada por el frontend).
2. **CORS**: `CORS_ORIGINS` en `deploy/oracle/.env` debe incluir el origen exacto
   del panel (`https://tu-panel.vercel.app`).
3. **Google Drive OAuth** (si usas "Conectar con Google Drive"): en
   console.cloud.google.com → Credenciales → tu Cliente OAuth, agrega la URI
   `https://tu-dominio/api/backup/drive/oauth/callback`.
4. Si usas cuenta de servicio en vez de OAuth, el JSON va en
   `GOOGLE_SERVICE_ACCOUNT_JSON` y el nombre de la carpeta en
   `GOOGLE_DRIVE_FOLDER_ID`; no cambia nada más.

---

## 8. Poner la IP fija y verificación final

- **Reserved public IP** en Oracle: la IP cambia si detienes/arrancas la
  instancia. Para fijarla usa **Reserved public IP** unida a la instancia
  (incluido en el tier gratuito).
- Scheduler: el backup automático corre a las `BACKUP_HOUR` (03:00) hora
  `TZ` configurada. El primer backup real valida ese flujo.
- Revisa que `docker compose ps` se mantenga estable tras un reinicio
  (`restart: unless-stopped` ya está en el compose).

---

## Costos

Oracle Cloud **Always Free** incluye: 4 OCPU ARM Ampere (24 GB), 200 GB de bloque,
y 10 TB de salida al mes. Mientras no uses instancias, shapes o volúmenes de pago,
no debería llegar ningún cargo. Conviene activar *Usage reports* para monitorearlo.