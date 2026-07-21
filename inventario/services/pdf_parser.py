"""
Parser de facturas PDF basado en COORDENADAS (no en extract_tables).

Motivo: pdfplumber colapsa toda la zona de ítems en UNA sola fila con celdas
multilínea. Al hacer split('\n') se pierde la correspondencia física entre
columnas (la columna DESCRIPCION trae 10 líneas y las demás 8), lo que obliga a
heurísticas frágiles. Trabajando con extract_words() + posición 'top' cada línea
física se reconstruye intacta y las continuaciones de descripción se detectan de
forma determinista: son líneas con texto en DESCRIPCION pero sin REFERENCIA ni
VR. UNITARIO.
"""

import re
import os
import json
import requests
import pdfplumber
from decimal import Decimal, InvalidOperation

try:
    from django.conf import settings
except Exception:  # uso fuera de Django
    settings = None


# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #

HEADER_PATTERNS = {
    'codigo':   ['REFERENCIA', 'CODIGO', 'CÓDIGO', 'COD.', 'SKU', 'ITEM', 'CLAVE', 'REF'],
    'nombre':   ['DESCRIPCION', 'DESCRIPCIÓN', 'DETALLE', 'CONCEPTO', 'PRODUCTO', 'ARTICULO', 'ARTÍCULO'],
    'cantidad': ['CANTIDAD', 'CANT', 'QTY'],
    'precio':   ['VR. UNITARIO', 'VR UNITARIO', 'V.UNITARIO', 'VR.UNIT', 'PRECIO UNIT',
                 'P.UNIT', 'P. COMPRA', 'UNITARIO', 'PRECIO', 'COSTO'],
    'total':    ['VALOR TOTAL', 'TOTAL'],
}

STOP_WORDS = [
    'SUBTOTAL', 'CUFE', 'FIRMA', 'OBSERVAC', 'PEDIDO NO', 'REMISION',
    'FORMAS DE PAGO', 'GRACIAS POR SU COMPRA', 'VALOR NETO', 'NETO A PAGAR',
    'RETE.', 'DESCUENTO', 'SON:', 'INFORMACION ADICIONAL', 'INFORMACIÓN ADICIONAL',
    'EMAIL:', 'TELEFONO:', 'TELÉFONO:', 'VENDEDOR', 'VALOR TOTAL', 'IVA 15%',
    'SIN IMPUESTOS', 'NO OBJETO IVA',
]

MARGEN_VENTA = Decimal('1.30')
LINE_TOLERANCE = 6.0  # puntos; separación típica entre filas ≈ 11 pt


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #

def parse_pdf_productos(pdf_file_path_or_buffer, use_ai=True, ai_api_key=None,
                        ai_provider='groq', decimal_sep=None, debug=False):
    """
    Devuelve una lista de dicts con codigo, nombre, cantidad, precio_compra,
    precio_venta.

    decimal_sep: None = autodetectar por documento ('.' o ',').
    """
    items, full_text, ruta = [], '', 'ninguna'

    try:
        with pdfplumber.open(pdf_file_path_or_buffer) as pdf:
            full_text = "\n".join((p.extract_text() or '') for p in pdf.pages)

            if decimal_sep is None:
                decimal_sep = _detect_decimal_sep(full_text)

            for page in pdf.pages:
                page_items = _extract_from_page(page)
                if page_items:
                    items.extend(page_items)

            if items:
                ruta = 'coordenadas'
            else:
                items = _fallback_por_lineas(full_text)
                if items:
                    ruta = 'lineas'
    except Exception as e:
        print(f"[parser] extracción local falló: {e}")

    if items:
        items = _finalizar(items, decimal_sep or ',')
        if debug:
            print(f"[parser] ruta={ruta} items={len(items)} sep_decimal={decimal_sep}")
        if _es_valido(items):
            return items

    if use_ai and full_text:
        key = (ai_api_key
               or (getattr(settings, 'GROQ_API_KEY', None) if settings else None)
               or os.environ.get('GROQ_API_KEY'))
        if key:
            ai_items = _parse_with_groq(full_text, key)
            if ai_items:
                if debug:
                    print(f"[parser] ruta=groq items={len(ai_items)}")
                return ai_items

    return items


# --------------------------------------------------------------------------- #
# Extracción por coordenadas
# --------------------------------------------------------------------------- #

def _extract_from_page(page):
    resultados = []
    try:
        words_page = page.extract_words()
    except Exception:
        return resultados

    for tbl in page.find_tables():
        try:
            cells = tbl.rows[0].cells
            x_edges = [c[0] for c in cells if c] + [cells[-1][2]]
        except Exception:
            continue
        if len(x_edges) < 3:
            continue

        # El cuerpo de la tabla puede quedar FUERA del bbox detectado (p. ej. los
        # RIDE del SRI solo dibujan la barra del encabezado). Se escanea desde el
        # inicio de la tabla hasta el pie de página y se corta con STOP_WORDS.
        top = tbl.bbox[1]
        bottom = float(page.height)
        words = [w for w in words_page if top <= w['top'] < bottom]
        if not words:
            continue

        lines = [_words_to_cols(lw, x_edges) for lw in _cluster_lines(words)]

        header_idx, col = -1, {}
        for i, ln in enumerate(lines[:6]):
            c = _map_header(ln)
            if 'nombre' in c and ('precio' in c or 'codigo' in c):
                header_idx, col = i, c
                break
        if header_idx == -1:
            continue

        ci = col.get('codigo')
        ni = col['nombre']
        qi = col.get('cantidad')
        pi = col.get('precio', col.get('total'))

        items = []
        for ln in lines[header_idx + 1:]:
            cod = ln[ci].strip() if ci is not None and ci < len(ln) else ''
            nom = ln[ni].strip() if ni < len(ln) else ''
            qty = ln[qi].strip() if qi is not None and qi < len(ln) else ''
            pre = ln[pi].strip() if pi is not None and pi < len(ln) else ''

            joined = ' '.join(ln).upper()
            if any(s in joined for s in STOP_WORDS):
                break                      # fin del cuerpo: totales / pie
            if not any([cod, nom, qty, pre]):
                continue

            tiene_precio = _looks_numeric(pre)

            # Fila de ítem: código propio, o descripción con importe numérico.
            if cod or (nom and tiene_precio):
                items.append({'codigo': cod, 'nombre': nom,
                              '_cant': qty or '1', '_precio': pre or '0'})
                continue

            # Continuación: solo descripción, sin código ni importe.
            if nom and not cod and not tiene_precio and items:
                items[-1]['nombre'] += ' ' + nom

        resultados.extend(items)

    return resultados


def _cluster_lines(words, tol=LINE_TOLERANCE):
    """Agrupa palabras en líneas físicas por su coordenada 'top'."""
    grupos, actual, ref = [], [], None
    for w in sorted(words, key=lambda w: (w['top'], w['x0'])):
        if ref is None or abs(w['top'] - ref) <= tol:
            if ref is None:
                ref = w['top']
            actual.append(w)
        else:
            grupos.append(actual)
            actual, ref = [w], w['top']
    if actual:
        grupos.append(actual)
    return grupos


def _words_to_cols(line_words, x_edges):
    cols = [''] * (len(x_edges) - 1)
    for w in sorted(line_words, key=lambda w: w['x0']):
        cx = (w['x0'] + w['x1']) / 2
        for i in range(len(x_edges) - 1):
            if x_edges[i] <= cx < x_edges[i + 1]:
                cols[i] = (cols[i] + ' ' + w['text']).strip()
                break
    return cols


def _looks_numeric(val):
    return bool(re.search(r'\d', str(val or ''))) and \
        bool(re.fullmatch(r'[\s$€\d.,\-]+', str(val or '').strip()))


def _map_header(row_texts):
    col = {}
    for i, txt in enumerate(row_texts):
        t = re.sub(r'\s+', ' ', (txt or '').upper()).strip()
        if not t:
            continue
        for key, pats in HEADER_PATTERNS.items():
            if key in col:
                continue
            if any(p in t for p in pats):
                if key == 'precio' and 'TOTAL' in t:
                    continue
                col[key] = i
                break
    return col


# --------------------------------------------------------------------------- #
# Normalización numérica
# --------------------------------------------------------------------------- #

def _detect_decimal_sep(text):
    """
    Decide el separador decimal UNA vez por documento.
    Devuelve ',' (formato es-CO/es-ES) o '.' (formato en-US).
    """
    # 1) Ambos separadores presentes en el mismo número: evidencia más fuerte.
    es = len(re.findall(r'\d{1,3}(?:\.\d{3})+,\d{1,2}(?!\d)', text))
    en = len(re.findall(r'\d{1,3}(?:,\d{3})+\.\d{1,2}(?!\d)', text))
    if es != en:
        return ',' if es > en else '.'

    # 2) Separador de miles en grupos de 3 (21,500 / 21.500).
    miles_coma = len(re.findall(r'(?<!\d)\d{1,3}(?:,\d{3})+(?!\d)', text))
    miles_punto = len(re.findall(r'(?<!\d)\d{1,3}(?:\.\d{3})+(?!\d)', text))
    if miles_coma != miles_punto:
        return '.' if miles_coma > miles_punto else ','

    # 3) Solo parte decimal de 1-2 dígitos (21,50 vs 21.50).
    dec_coma = len(re.findall(r'\d,\d{1,2}(?!\d)', text))
    dec_punto = len(re.findall(r'\d\.\d{1,2}(?!\d)', text))
    if dec_coma != dec_punto:
        return ',' if dec_coma > dec_punto else '.'

    # 4) Sin evidencia: asumir formato en-US.
    return '.'


def _clean_decimal(val, decimal_sep=',', default=0.0):
    if val is None or str(val).strip() == '':
        return Decimal(str(default))
    s = re.sub(r'[^\d.,\-]', '', str(val))
    if not s:
        return Decimal(str(default))

    if decimal_sep == ',':
        s = s.replace('.', '').replace(',', '.')
    else:
        s = s.replace(',', '')

    if s.count('.') > 1:                       # residuo de separadores de miles
        head, _, tail = s.rpartition('.')
        s = head.replace('.', '') + '.' + tail
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal(str(default))


def _clean_name(val):
    return re.sub(r'\s+', ' ', str(val)).strip().upper()


def _clean_code_from_string(val):
    for w in re.findall(r'[A-Z0-9-]{3,}', str(val).upper()):
        if any(c.isdigit() for c in w):
            return w[:20]
    return f"PDF-{re.sub(r'[^A-Z0-9]', '', str(val).upper())[:10]}"


def _finalizar(items, decimal_sep):
    salida = []
    for idx, it in enumerate(items, 1):
        cant = _clean_decimal(it.get('_cant', '1'), decimal_sep, 1.0)
        prec = _clean_decimal(it.get('_precio', '0'), decimal_sep, 0.0)
        nombre = _clean_name(it['nombre'])
        codigo = (it.get('codigo') or '').strip() or _clean_code_from_string(nombre)
        salida.append({
            'index': idx,
            'codigo': codigo,
            'nombre': nombre,
            'cantidad': float(cant or 1),
            'precio_compra': float(prec),
            'precio_venta': float(round(prec * MARGEN_VENTA, 2)),
            'raw_text': f"{codigo} {nombre}",
        })
    return salida


def _es_valido(items):
    return (len(items) > 0
            and any(i['precio_compra'] > 0 for i in items)
            and all(0 < i['cantidad'] < 10000 for i in items))


# --------------------------------------------------------------------------- #
# Fallback por líneas de texto plano
# --------------------------------------------------------------------------- #

def _fallback_por_lineas(full_text):
    items = []
    num_re = re.compile(r'\$?\s?\d[\d.,]*')
    for line in full_text.split('\n'):
        l = line.strip()
        if len(l) < 6:
            continue
        U = l.upper()
        if any(s in U for s in STOP_WORDS + ['FACTURA', 'NIT', 'RUC', 'DIRECCION', 'TELEFONO', 'FECHA']):
            continue

        matches = list(num_re.finditer(l))
        if len(matches) < 2:
            continue

        # Recortar la parte textual usando posiciones reales, no comparación de tokens
        primer_num = matches[0].start()
        texto = l[:primer_num].strip()
        tokens = texto.split()
        codigo = ''
        if tokens and re.fullmatch(r'[A-Z0-9_-]{2,20}', tokens[0], re.IGNORECASE) \
                and not tokens[0].isdigit():
            codigo, tokens = tokens[0], tokens[1:]
        nombre = ' '.join(tokens).strip()
        if len(nombre) < 3:
            continue

        vals = [m.group().strip() for m in matches]
        cant_raw = vals[-3] if len(vals) >= 3 else vals[0]
        prec_raw = vals[-2] if len(vals) >= 2 else vals[-1]

        items.append({'codigo': codigo, 'nombre': nombre,
                      '_cant': cant_raw, '_precio': prec_raw})
    return items


# --------------------------------------------------------------------------- #
# Fallback IA
# --------------------------------------------------------------------------- #

def _parse_with_groq(full_text, api_key):
    lineas = [l.strip() for l in full_text.split('\n')
              if len(l.strip()) > 5 and any(c.isdigit() for c in l)
              and not any(k in l.upper() for k in ['NIT', 'RUC', 'CUFE', 'TEL'])]
    compressed = "\n".join(lineas[:120])

    prompt = (
        "Extrae SOLO un objeto JSON con la clave \"productos\", un arreglo de "
        "{\"codigo\":\"\",\"nombre\":\"\",\"cantidad\":1,\"precio_compra\":0.0}.\n"
        "Reglas: une las descripciones partidas en varias líneas al producto anterior. "
        "precio_compra es el valor unitario tal cual aparece, sin reescalar. "
        "Ignora CUFE, totales y pies de página.\n"
        f"Texto:\n{compressed}"
    )
    try:
        r = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={'Authorization': f'Bearer {api_key}',
                     'Content-Type': 'application/json'},
            json={'model': 'llama-3.3-70b-versatile',
                  'messages': [{'role': 'user', 'content': prompt}],
                  'temperature': 0,
                  'max_tokens': 4000,
                  'response_format': {'type': 'json_object'}},
            timeout=30)
        if r.status_code != 200:
            print(f"[parser] Groq HTTP {r.status_code}: {r.text[:200]}")
            return []
        data = json.loads(r.json()['choices'][0]['message']['content'])
        productos = data.get('productos', data if isinstance(data, list) else [])
        return _finalizar([{'codigo': str(p.get('codigo', '')),
                            'nombre': str(p.get('nombre', '')),
                            '_cant': str(p.get('cantidad', 1)),
                            '_precio': str(p.get('precio_compra', 0))}
                           for p in productos], '.')
    except Exception as e:
        print(f"[parser] Groq falló: {e}")
        return []


if __name__ == '__main__':
    import sys
    for it in parse_pdf_productos(sys.argv[1], use_ai=False, debug=True):
        print(it)
