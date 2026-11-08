# Redirigir el panel (Vercel) al backend de Oracle Cloud

El panel es un SPA en Vercel que habla con el API por HTTPS. "Redirigir" = cambiar
el valor de `VITE_API_URL` del frontend para que apunte al nuevo servidor en
Oracle (Caddy) en vez de a Render.

## Qué es VITE_API_URL

`frontend/src/client.js`:

```js
const _rawApiUrl = (import.meta.env.VITE_API_URL || '/api').trim().replace(/\/+$/, '')
export const API_BASE = _rawApiUrl.endsWith('/api') ? _rawApiUrl : `${_rawApiUrl}/api`
```

Es decir: puede llevar o no el sufijo `/api` (se agrega solo), y en desarrollo
(sin la variable) cae a relativo `/api`, que Vite proxya localmente a
`http://localhost:8000` (ver `frontend/vite.config.js`).

## Pasos en Vercel

1. **Dashboard de Vercel** → proyecto del panel → **Settings → Environment
   Variables**.
2. Edita `VITE_API_URL` y cámbiala de
   `https://inventory-master-api.onrender.com` a
   `https://tu-dominio`  (ej. `https://api.tudominio.com` o
   `https://mi-api.duckdns.org`).
3. **Redeploy**: **Deployments → ver latest → ⋯ → Redeploy** (o push a main si el
   proyecto está conectado a Git). Las variables de entorno solo cambian al
   rebuild; un redeploy "Use existing Build Cache" basta para recompilar con el
   nuevo valor.
4. Verifica en el navegador (DevTools → Network) que las peticiones salen a
   `https://tu-dominio/api/...` y responden 200. Revisa también
   `https://tu-dominio/api/health`.

## CORS (imprescindible si sale error de CORS)

El API en Oracle rechazará llamadas de un origen no permitido. En el servidor:

```bash
cd inventory-master/deploy/oracle
nano .env
#   CORS_ORIGINS=https://tu-panel.vercel.app     <- origen EXACTO del panel
#   CORS_ORIGIN_REGEX=https://.*\.vercel\.app    <- ya permite cualquier subdominio de vercel.app
docker compose up -d        # recrea el contenedor api con el nuevo .env
docker compose logs -f api  # confirma que no hay errores de CORS
```

> Si tu panel usa un dominio personalizado (ej. `panel.midominio.com`), agrégalo
> también en `CORS_ORIGINS`, ya que la regex solo cubre `*.vercel.app`.

## OAuth de Google Drive (opcional)

Si el panel usa el botón "Conectar con Google Drive", agrega en
console.cloud.google.com → tu Cliente OAuth la URI de redirección:

```
https://tu-dominio/api/backup/drive/oauth/callback
```

Además, `PUBLIC_BASE_URL` en `deploy/oracle/.env` debe ser `https://tu-dominio`
(tu `.env.oracle.example` ya lo refleja).

## Checklist final

- [ ] `curl https://tu-dominio/api/health` responde ok desde tu PC.
- [ ] `VITE_API_URL` actualizada y panel redeployado en Vercel.
- [ ] Login contra el nuevo API OK (crear sesión).
- [ ] CORS sin errores en DevTools/consola.
- [ ] Backups diarios aparecen en Admin → Respaldo (carpeta montada en el volumen).
- [ ] Nota: no toques nada en Render hasta confirmar que todo lo crítico funciona
      en Oracle (licencias, backups, Google Drive, multi-proveedor).