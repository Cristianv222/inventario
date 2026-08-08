from thefuzz import fuzz
from inventario.models import Producto, Marca, CategoriaProducto

def match_pdf_items_with_db(extracted_items):
    """
    Compara la lista de ítems extraídos del PDF contra los productos registrados en la base de datos.
    Retorna los ítems enriquecidos con el estado de coincidencia ('EXACT', 'SIMILAR', 'NEW'),
    las opciones sugeridas y la razón en lenguaje humano.
    """
    all_products = list(Producto.objects.filter(activo=True).select_related('categoria', 'marca'))
    all_marcas = list(Marca.objects.filter(activa=True))
    all_categorias = list(CategoriaProducto.objects.filter(activa=True))
    
    matched_results = []
    
    for item in extracted_items:
        raw_code = item.get('codigo', '').strip()
        raw_name = item.get('nombre', '').strip().upper()
        
        matched_prod = None
        match_status = 'NEW'
        match_score = 0
        match_reason = 'No se encontraron coincidencias en el inventario actual.'
        candidates = []
        
        # 1. Búsqueda por código exacto
        if raw_code:
            exact_by_code = next((p for p in all_products if p.codigo_unico.upper() == raw_code.upper()), None)
            if exact_by_code:
                matched_prod = exact_by_code
                match_status = 'EXACT'
                match_score = 100
                match_reason = f"Coincidencia exacta por Código Único '{exact_by_code.codigo_unico}'"
        
        # 2. Si no hubo coincidencia por código, hacer fuzzy matching por nombre
        if not matched_prod and raw_name:
            scored_candidates = []
            for p in all_products:
                prod_name = p.nombre.upper()
                score = fuzz.token_set_ratio(raw_name, prod_name)
                
                # Bonificación si coinciden palabras clave numéricas (ej. 428, 120L, etc)
                pdf_numbers = set(part for part in raw_name.split() if any(c.isdigit() for c in part))
                prod_numbers = set(part for part in prod_name.split() if any(c.isdigit() for c in part))
                if pdf_numbers and pdf_numbers.issubset(prod_numbers):
                    score = min(100, score + 10)
                elif pdf_numbers and not pdf_numbers.intersection(prod_numbers):
                    score = max(0, score - 15)
                    
                if score >= 50:
                    scored_candidates.append({
                        'id': p.id,
                        'codigo_unico': p.codigo_unico,
                        'nombre': p.nombre,
                        'categoria': p.categoria.nombre if p.categoria else '',
                        'marca': p.marca.nombre if p.marca else '',
                        'precio_compra': float(p.precio_compra),
                        'precio_venta': float(p.precio_venta),
                        'stock_actual': float(p.stock_actual),
                        'score': score
                    })
            
            # Ordenar candidatos de mayor a menor puntuación
            scored_candidates.sort(key=lambda x: x['score'], reverse=True)
            candidates = scored_candidates[:5]
            
            if candidates:
                best = candidates[0]
                match_score = best['score']
                
                if match_score >= 88:
                    matched_prod = next(p for p in all_products if p.id == best['id'])
                    match_status = 'EXACT'
                    match_reason = f"Alta coincidencia ({match_score}%) con producto existente '{best['nombre']}'"
                elif match_score >= 55:
                    match_status = 'SIMILAR'
                    match_reason = f"Se encontraron {len(candidates)} sugerencias posibles. Principal candidato ({match_score}%): '{best['nombre']}'"
                else:
                    match_status = 'NEW'
                    match_reason = "Baja coincidencia. Se sugiere registrar como producto nuevo."
        
        # Detectar Marca / Categoría sugerida a partir del nombre
        sug_marca_id = None
        sug_cat_id = None
        for m in all_marcas:
            if m.nombre.upper() in raw_name:
                sug_marca_id = m.id
                break
        for c in all_categorias:
            if c.nombre.upper() in raw_name:
                sug_cat_id = c.id
                break

        matched_results.append({
            'index': item['index'],
            'pdf_codigo': raw_code or item.get('codigo', ''),
            'pdf_nombre': raw_name,
            'pdf_cantidad': item['cantidad'],
            'pdf_precio_compra': item['precio_compra'],
            'pdf_precio_venta': item['precio_venta'],
            'raw_text': item.get('raw_text', ''),
            
            'match_status': match_status, # 'EXACT', 'SIMILAR', 'NEW'
            'match_score': match_score,
            'match_reason': match_reason,
            'selected_product_id': matched_prod.id if matched_prod else (candidates[0]['id'] if candidates and match_status == 'SIMILAR' else None),
            'candidates': candidates,
            
            'sug_marca_id': sug_marca_id or (all_marcas[0].id if all_marcas else None),
            'sug_cat_id': sug_cat_id or (all_categorias[0].id if all_categorias else None),
        })
        
    return matched_results
