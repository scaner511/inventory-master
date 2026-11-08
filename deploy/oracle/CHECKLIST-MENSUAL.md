# Checklist mensual — Oracle Cloud Always Free ($0)

Revisar el **primer día de cada mes** para confirmar que sigues dentro del tier
gratuito y que **total = $0.00**. Tiempo: 5 minutos.

## 1. Usage (consola OCI)

1. Inicia sesión en **cloud.oracle.com**.
2. Icono de perfil (arriba a la derecha) → **Tenancy → Limits, Quotas and Usage**.
3. Verifica (compartimento de la VM):

| Recurso | Debe estar en | Nota |
|---|---|---|
| `VM.Standard.A1.Flex` | 1–4 OCPU / 6–24 GB | 1 OCPU / 6 GB actual |
| Block Volume `ocivolume-root` + boot | ≤ 200 GB total | 46.6 GB actual |

4. **Billing & Cost Management → Cost analysis** → filtra *Granularity: monthly*,
   tu compartimento → **Total cost = $0.00**.
   - Si quieres respaldo por escrito: **Billing → Usage Report** → crea el reporte
     de uso (si no existe) y descarga el CSV mensual: columna `Billed Quantity`
     debe ser 0 y `Cost` 0.

## 2. Qué NO hacer (evita cargos)

- ❌ Cambiar la **shape** de la VM por otra de pago.
- ❌ Crear **backups / snapshots de volumen** en la consola (se cobran aunque el
  volumen sea gratis).
- ❌ Crear más **VMs**, **volúmenes extra**, **Load Balancer**, **Object Storage**
  fuera del tier, o cualquier recurso de pago.
- ❌ Convertir la cuenta a **Pay As You Go** sin necesidad.
- ⚠️ Si detienes y vuelves a arrancar la VM: la **IP reservada** no cambia (bien);
  si la desligas y la instancia se pierde, la IP sigue existiendo (gratis) — no te
  preocupes por ella.

## 3. Estado del servicio (desde tu PC)

```bash
curl -s https://inventorymasteros.duckdns.org/api/health
# esperado: {"status":"ok","version":"2.0.0"}

# puertos desde internet (deben responder OK)
Test-NetConnection 137.131.14.164 -Port 443 -InformationLevel Quiet
```

> Realiza también una de estas tareas mensuales: **descargar un respaldo** desde
> Admin → Respaldo (o revisar que el de las 03:00 se generó) y guardarlo fuera de
> la VM (en tu PC/nube). Ese archivo es tu seguro ante cualquier imprevisto.

## 4. Alerta (opcional, plan de cuenta personal)

- Activar el **email de alertas presupuestarias** de OCI es engorroso sin
  presupuesto configurado. Alternativa simple: en **Notifications → Topics**,
  crea un tema con tu email y asócialo a una **Alarm de monitoreo** del
  `inventorymasteros` / health — te avisará si la API deja de responder.
- La revisión manual del mes 1 de cada mes (este checklist) es suficiente para el
  tier gratuito.

---

**Recordatorio en el teléfono/calendario**: `1º de cada mes → revisar Billing OCI
= $0 (cloud.oracle.com → Cost analysis) + descargar backup del panel.`