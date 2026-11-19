# 🧾 ERP Finanzas — Estado del proyecto y traspaso

> Documento de continuidad. Si abres este proyecto en una sesión local de
> Claude Code, lee esto primero: resume qué se decidió, qué ya está hecho y
> qué falta. Rama de trabajo: **`claude/sharp-knuth-t1ms2d`**.

---

## 1. Qué estamos construyendo

Un **ERP Financiero con IA** dentro del sistema VP Motos (Django 5.2 + Postgres
+ Docker). Nueva app **`finanzas/`** que concentra toda el área financiera.

**Reglas de oro (no negociables):**
- La **IA solo clasifica correos, extrae facturas y redacta resúmenes**. NUNCA
  calcula ni verifica números.
- Toda cifra (balances, estados, conciliaciones) se calcula con **lógica
  determinista** desde la base de datos. La contabilidad es **partida doble**.
- Todo lo nuevo es **aditivo**: no rompe lo que ya está en producción.

## 2. Decisiones ya tomadas

- **App única `finanzas`** como ERP paraguas; `reportes` y demás se manejan
  desde ahí (sin mover datos todavía).
- **Contabilidad formal de partida doble** con **plan de cuentas de Ecuador**
  (Superintendencia de Compañías / NIIF).
- Estados financieros descargables en **PDF + Excel + pantalla**.
- **Capa de IA agnóstica por entorno**: `claude` en producción;
  `groq`/`gemini`/`ollama` en desarrollo (por decidir). Se elige con la
  variable `AI_PROVIDER`.
- La verificación de **facturas SRI emitidas** también entra al ERP
  (lógica + API SRI, no IA).

## 3. ✅ Lo que YA está hecho y validado

Commits en la rama (de más antiguo a más nuevo):
- `feat(pos)`: búsqueda con escáner/teclado + atajos en el POS (mejora aparte).
- `feat(finanzas): motor contable de partida doble (base del ERP)`
- `feat(finanzas): migración inicial del motor contable (generada y validada)`
- `feat(finanzas): reportes contables y estados financieros en pantalla`

Archivos de la app `finanzas/`:
- `models.py` — `CuentaContable`, `AsientoContable`, `LineaAsiento`, `PeriodoContable`.
- `services/contabilidad.py` — `crear_asiento()` (valida Debe=Haber),
  `generar_asiento_venta()`, `generar_asiento_gasto()` (idempotentes).
- `services/reportes_contables.py` — Libro Mayor, Balance de Comprobación,
  Estado de Resultados, Balance General, Flujo de Caja.
- `views.py` + `urls.py` — pantallas en `/finanzas/` con filtro de fechas.
- `management/commands/sembrar_plan_cuentas.py` — siembra 67 cuentas (Ecuador).
- `signals.py` — auto-generación de asientos desde ventas/gastos, **APAGADA
  por defecto** y resiliente (un fallo contable nunca rompe la venta).
- `migrations/0001_initial.py` — generada con Django 5.2.1 y probada.

**Validado end-to-end contra SQLite** (banco de pruebas desechable, NO en el
repo): migrate limpio, plan sembrado, asientos de venta/gasto cuadran,
balance de comprobación y balance general cuadran, flujo correcto, y las 5
vistas responden 200.

Cambios en el core del proyecto:
- `vpmotos/settings.py`: `finanzas` en `INSTALLED_APPS`; flags
  `FINANZAS_CONTABILIDAD_AUTO` (default False) y `AI_PROVIDER` (default 'groq').
- `vpmotos/urls.py`: ruta `/finanzas/`.

## 4. ▶️ Cómo correrlo en local (Docker)

```bash
git pull origin claude/sharp-knuth-t1ms2d
docker compose -f docker-compose.dev.yml exec web python manage.py migrate
docker compose -f docker-compose.dev.yml exec web python manage.py sembrar_plan_cuentas
```
Luego entra a **`/finanzas/`** y navega los estados (saldrán en cero hasta que
haya asientos). El admin de Django muestra "Finanzas (ERP)" con el plan y los
asientos.

> La auto-generación de asientos sigue **apagada**. Para activarla tras probar:
> variable de entorno `FINANZAS_CONTABILIDAD_AUTO=true` en el contenedor web.

## 5. ⏳ Lo que FALTA (roadmap)

Progreso del backend estimado: **~35-40%**. El núcleo contable ya está de pie.

**Cerrar bloque contable**
- [ ] Descarga **PDF** de los estados (ya hay WeasyPrint/ReportLab en el proyecto).
- [ ] Descarga **Excel** (falta `openpyxl`).
- [ ] **Asiento de apertura** (saldos iniciales: capital, inventario, caja, deudas).
- [ ] Mayorización/cierre de período y asiento de cierre anual.

**Compras y cuentas por pagar/cobrar**
- [ ] Modelos `Proveedor`, `FacturaCompra`, `CuentaPorPagar` (app `compras` está vacía).
- [ ] Generadores de asiento de compra y de pago/cobro.
- [ ] Cuentas por cobrar + detección de deudores.

**Tributario**
- [ ] Recepción de **XML de compra** (parseo determinista) + conciliación SRI.
- [ ] Verificación de **facturas SRI emitidas** integrada al ERP.
- [ ] Borradores IVA / ATS.

**Nómina**
- [ ] Roles de pago, aportes IESS, décimos → asiento de nómina.

**Capa de IA** (`finanzas/services/ai/`)
- [ ] Interfaz `base.py` + adaptadores `claude.py`, `groq.py` (reusa
      `inventario/services/pdf_parser.py`), stubs `gemini.py`, `ollama.py`,
      `factory.py` que lee `AI_PROVIDER`.
- [ ] Clasificación de correos y extracción de facturas vía esa capa.

**Integraciones externas (dependen de credenciales/decisiones del dueño)**
- [ ] Lector de correo **Zoho** (IMAP/API) — confirmar plan Mail Lite y scopes.
- [ ] **WhatsApp** (sistema "Arranque") para reportes gerenciales.
- [ ] Tareas programadas (**Celery Beat**) para polling de correo y alertas.

**Transversal**
- [ ] Dashboard del ERP con diseño del sistema (base.html).
- [ ] Endpoints/API y tests automatizados.

## 6. Decisiones abiertas pendientes

1. **Modelo de IA para desarrollo**: Groq / Gemini / Ollama (producción = Claude).
2. **Plan de cuentas**: se sembró uno estándar; falta que el contador lo ajuste.
3. **Facturas de compra**: ¿llegan con XML adjunto o solo PDF? Define si la
   conciliación es 100% automática.
4. **Saldos iniciales de apertura**: quién provee los montos de partida.
5. **Zoho Mail Lite**: confirmar scopes de lectura de la API antes de contratar.

## 7. Notas técnicas

- `AsientoContable` usa **referencia blanda** (`referencia_tipo`+`referencia_id`),
  sin FK dura a `ventas`/`reportes`, para mantener el motor desacoplado y
  reutilizable en otras empresas.
- Cuentas clave mapeadas por código en `services/contabilidad.py` (dict `CUENTAS`).
- El ingreso de una venta se calcula como `total + descuento - IVA` para que el
  asiento cuadre siempre, sin depender del campo `subtotal`.
