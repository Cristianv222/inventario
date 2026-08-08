# 📘 DOCUMENTACIÓN TÉCNICA: INTEGRACIÓN API REST TIENDA WEB VPMOTOS

Este documento contiene las especificaciones técnicas para consumir el backend de **VPMOTOS** desde el frontend e-commerce (Svelte / React / Next.js / App Móvil).

---

## 🔒 1. ARQUITECTURA DE SEGURIDAD POR TOKEN DE API (SIN LOGIN DE USUARIO)

Para garantizar la seguridad de la comunicación sin exigir que los visitantes o talleres inicien sesión ni envíen usuarios o contraseñas:

- **Autenticación mediante Clave Secreta de Aplicación (`API Secret Key`)**:
  - Tu aplicación web almacena un Token Secreto en su archivo de configuración `.env`.
  - **Sin Formularios de Login**: Ni el cliente ni el taller tienen que escribir contraseñas.
  - **Protección de API**: Cualquier intento externo no autorizado de acceder a la API sin el Token de Seguridad será rechazado automáticamente con error `401 Unauthorized`.

---

## 🌐 2. URL Base y Configuración del Frontend

- **Desarrollo Local**: `http://localhost:8001`
- **Producción (Automático)**: `https://midominio.com` *(el backend detecta y genera automáticamente las URLs absolutas de imágenes `.webp`)*.

### Configuración de Variables de Entorno en el Frontend (`.env`):

En tu proyecto Svelte/Vite/React, configura en el archivo `.env`:

```env
PUBLIC_API_URL=http://localhost:8001
PUBLIC_API_SECRET_KEY=vpm_live_secret_key_984102983719827398127398
```

---

## 🛡️ 3. Cabecera de Seguridad Obligatoria en Peticiones (`HTTP Headers`)

Toda solicitud desde la tienda web a los endpoints del servidor debe incluir una de las siguientes cabeceras HTTP:

```http
X-API-Key: vpm_live_secret_key_984102983719827398127398
Content-Type: application/json
```

*(También se acepta el formato estándar `Authorization: Bearer vpm_live_secret_key_984102983719827398127398`)*.

---

## 📦 4. ENDPOINT 1: Catálogo de Productos y Promociones Web

Obtiene la lista completa de productos activos, sus imágenes optimizadas en `.webp`, precios originales, precios finales calculados, promociones globales, descuentos de remate y productos destacados.

- **Método**: `GET`
- **URL**: `http://localhost:8001/inventario/api/v1/productos/`
- **Headers Obligatorios**: `X-API-Key: vpm_live_secret_key_984102983719827398127398`

### 🔍 Parámetros Query Opcionales:
| Parámetro | Tipo | Descripción | Ejemplo |
| :--- | :--- | :--- | :--- |
| `solo_destacados` | `boolean` | Retorna únicamente los **Productos Estrellas** de la tienda. | `?solo_destacados=true` |
| `busqueda` | `string` | Filtra por nombre, código único o descripción. | `?busqueda=motul` |
| `categoria` | `string` / `int` | Filtra por ID o nombre de categoría. | `?categoria=lubricantes` |

---

### 📄 Respuesta JSON Estructurada (`200 OK`):

```json
{
    "success": true,
    "configuracion_tienda": {
        "descuento_global_activo": true,
        "porcentaje_descuento_global": 5.0,
        "precio_minimo_descuento": 2.0
    },
    "productos": [
        {
            "id": 1,
            "codigo": "PROD-MSJFDJ38-CRZQ",
            "nombre": "Aceite Motul 7100 10w40 1L",
            "descripcion": "Aceite 100% sintético con tecnología Ester para motos de 4 tiempos.",
            "precio_original": 15.40,
            "precio": 14.63,
            "aplica_descuento": true,
            "porcentaje_descuento": 5.0,
            "tipo_descuento": "GLOBAL",
            "es_destacado": true,
            "stock": "11.00",
            "categoria": "Lubricantes",
            "marca": "Motul",
            "imagen_url": "http://localhost:8001/media/productos/imagen_pegada_1786136717923.webp",
            "imagen_2_url": null,
            "imagen_3_url": null
        }
    ]
}
```

---

## 🎟️ 5. ENDPOINT 2: Validar Código Promocional / Cupón de Taller

Valida en tiempo real si un código promocional ingresado por un cliente o taller existe y está activo.

- **Método**: `GET`
- **URL**: `http://localhost:8001/inventario/api/v1/validar-cupon/?codigo=TALLER5`
- **Headers Obligatorios**: `X-API-Key: vpm_live_secret_key_984102983719827398127398`

### 📄 Respuesta si el Cupón es VÁLIDO (`200 OK`):

```json
{
    "success": true,
    "cupon": {
        "codigo": "TALLER5",
        "descripcion": "Descuento 5% especial para talleres mecánicos de Cayambe",
        "porcentaje_descuento": 5.0,
        "precio_minimo_aplicable": 2.0
    }
}
```

---

## 💻 6. Ejemplo de Código en JS / Svelte (`fetch`)

```javascript
// Configuración desde archivo .env
const API_BASE_URL = 'http://localhost:8001';
const API_SECRET_KEY = 'vpm_live_secret_key_984102983719827398127398';

// 1. Obtener Productos para la Tienda Web (Sin requerir login de usuario)
async function getProductosWeb() {
    try {
        const response = await fetch(`${API_BASE_URL}/inventario/api/v1/productos/`, {
            method: 'GET',
            headers: {
                'X-API-Key': API_SECRET_KEY,
                'Content-Type': 'application/json'
            }
        });
        const data = await response.json();
        if (data.success) {
            console.log("Catálogo de Productos:", data.productos);
            return data.productos;
        }
    } catch (error) {
        console.error("Error al conectar con la API de VPMOTOS:", error);
    }
}

// 2. Validar Cupón de Taller
async function validarCupon(codigoCupon) {
    try {
        const response = await fetch(`${API_BASE_URL}/inventario/api/v1/validar-cupon/?codigo=${encodeURIComponent(codigoCupon)}`, {
            method: 'GET',
            headers: {
                'X-API-Key': API_SECRET_KEY,
                'Content-Type': 'application/json'
            }
        });
        return await response.json();
    } catch (error) {
        console.error("Error al validar el cupón:", error);
    }
}
```
