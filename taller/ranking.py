"""Ranking de rendimiento de técnicos (semana / día).

Lo usan el panel del técnico, la pantalla del administrador y la pantalla
pública (monitor del taller) que se actualiza en tiempo real por WebSocket.
"""
import hashlib
import hmac
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import Tecnico, OrdenTrabajo


def _trabajos_basicos_tecnico(tecnico, inicio, fin):
    """Servicios del técnico en [inicio, fin] (órdenes de taller + POS), con las
    mismas reglas del panel: devuelve [{'fecha_date', 'valor', 'tipo'}]."""
    from ventas.models import DetalleVenta
    out = []
    ordenes = OrdenTrabajo.objects.filter(
        Q(tecnico_principal=tecnico) | Q(servicios__tecnico_asignado=tecnico)
    ).filter(
        Q(estado__in=['COMPLETADO', 'ENTREGADO']) | Q(facturado=True) | Q(venta__isnull=False)
    ).filter(
        Q(fecha_completado__date__gte=inicio, fecha_completado__date__lte=fin) |
        Q(fecha_completado__isnull=True, venta__fecha_hora__date__gte=inicio, venta__fecha_hora__date__lte=fin) |
        Q(fecha_completado__isnull=True, venta__isnull=True, fecha_entrega__date__gte=inicio, fecha_entrega__date__lte=fin) |
        Q(fecha_completado__isnull=True, venta__isnull=True, fecha_entrega__isnull=True, fecha_ingreso__date__gte=inicio, fecha_ingreso__date__lte=fin)
    ).distinct().select_related('venta').prefetch_related('servicios')
    venta_ids = set()
    for orden in ordenes:
        if orden.venta_id:
            venta_ids.add(orden.venta_id)
        f = orden.fecha_completado or (orden.venta.fecha_hora if orden.venta else None) or orden.fecha_entrega or orden.fecha_ingreso
        fd = timezone.localtime(f).date() if f else inicio
        servs = [x for x in orden.servicios.all()
                 if (x.tecnico_asignado_id == tecnico.id) or (x.tecnico_asignado_id is None and orden.tecnico_principal_id == tecnico.id)]
        if servs:
            for x in servs:
                out.append({'fecha_date': fd, 'valor': x.precio_servicio or Decimal('0'), 'tipo': 'ORDEN'})
        elif orden.tecnico_principal_id == tecnico.id and orden.precio_mano_obra and orden.precio_mano_obra > 0:
            out.append({'fecha_date': fd, 'valor': orden.precio_mano_obra, 'tipo': 'ORDEN'})

    pos = DetalleVenta.objects.filter(
        tecnico=tecnico, es_servicio=True, venta__estado='COMPLETADA',
        venta__fecha_hora__date__gte=inicio, venta__fecha_hora__date__lte=fin,
    ).select_related('venta')
    if venta_ids:
        pos = pos.exclude(venta_id__in=venta_ids)
    for d in pos:
        fd = timezone.localtime(d.venta.fecha_hora).date() if d.venta.fecha_hora else inicio
        out.append({'fecha_date': fd, 'valor': d.total or d.subtotal or Decimal('0'), 'tipo': 'POS'})
    return out


def _armar_ranking(inicio, fin, dia=None, yo=None, campeones_dia=True):
    """Ranking de técnicos activos por servicios realizados (desempate: mano de obra).
    Cubre la semana [inicio, fin] o, si se indica, solo el día `dia`."""
    activos = list(Tecnico.objects.filter(estado='ACTIVO', activo=True))
    if yo is not None and all(t.pk != yo.pk for t in activos):
        activos.append(yo)
    nombres_dia = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado']
    dias = [inicio + timedelta(days=i) for i in range(6)]
    filas = []
    por_dia = {d: [] for d in dias}
    for t in activos:
        trabajos = _trabajos_basicos_tecnico(t, inicio, fin)
        sel = [x for x in trabajos if (dia is None or x['fecha_date'] == dia)]
        if campeones_dia:
            for d in dias:
                n = sum(1 for x in trabajos if x['fecha_date'] == d)
                por_dia[d].append((n, t))
        filas.append({
            'tecnico': t,
            'nombre': f"{t.nombres.split()[0].title()} {t.apellidos.split()[0][:1].upper()}." if t.apellidos else t.nombres.title(),
            'servicios': len(sel),
            'ordenes': sum(1 for x in sel if x['tipo'] == 'ORDEN'),
            'pos': sum(1 for x in sel if x['tipo'] == 'POS'),
            'valor': sum((x['valor'] for x in sel), Decimal('0')),
            'es_yo': yo is not None and t.pk == yo.pk,
        })
    filas.sort(key=lambda r: (-r['servicios'], -r['valor'], r['nombre']))
    pos_actual = 0
    prev = None
    maximo = filas[0]['servicios'] if filas else 0
    for i, r in enumerate(filas, start=1):
        clave = (r['servicios'], r['valor'])
        if clave != prev:
            pos_actual = i
            prev = clave
        r['posicion'] = pos_actual
        r['pct'] = int(r['servicios'] * 100 / maximo) if maximo else 0

    lider = filas[0] if filas and filas[0]['servicios'] > 0 else None
    mi = next((r for r in filas if r['es_yo']), None)
    mensaje = None
    if mi is not None:
        if mi['servicios'] == 0:
            mensaje = 'Aún no tienes servicios en este periodo. ¡A darle!'
        elif lider and mi['posicion'] == 1:
            otros = [r for r in filas if not r['es_yo']]
            seg = otros[0]['servicios'] if otros else 0
            mensaje = '¡Vas en primer lugar!' + (f' Le sacas {mi["servicios"] - seg} servicio(s) al siguiente.' if seg < mi['servicios'] else ' Estás empatado en el primer lugar.')
        elif lider:
            mensaje = f'Te faltan {lider["servicios"] - mi["servicios"]} servicio(s) para alcanzar a {lider["nombre"]}.'

    campeones = []
    for i, d in enumerate(dias if campeones_dia else []):
        lista = sorted(por_dia[d], key=lambda x: -x[0])
        mejor = lista[0][0] if lista else 0
        ganadores = [f"{t.nombres.split()[0].title()}" for n, t in lista if n == mejor and mejor > 0]
        campeones.append({'fecha': d, 'nombre': nombres_dia[i], 'ganadores': ganadores, 'servicios': mejor,
                          'yo_gano': bool(yo is not None and any(n == mejor and mejor > 0 and t.pk == yo.pk for n, t in lista))})
    return {
        'filas': filas, 'lider': lider, 'mi': mi, 'mensaje': mensaje, 'campeones': campeones,
        'total_equipo': sum(r['servicios'] for r in filas),
        'dia': dia,
    }


def _ranking_tecnicos(inicio, fin, dia=None, yo=None):
    """Ranking de la semana [inicio, fin] (lun–sáb) o, si se indica, de un solo día."""
    return _armar_ranking(inicio, fin, dia=dia, yo=yo, campeones_dia=True)


DIAS_ES = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
MESES_ES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto',
            'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
PERIODOS = ('dia', 'semana', 'mes')


def rango_periodo(periodo, ref):
    """(inicio, fin, etiqueta) del periodo que contiene `ref`.
    La semana va de lunes a sábado (los domingos no se trabaja)."""
    import calendar
    if periodo == 'dia':
        return ref, ref, f'{DIAS_ES[ref.weekday()]} {ref:%d/%m/%Y}'
    if periodo == 'mes':
        ini = ref.replace(day=1)
        fin = ref.replace(day=calendar.monthrange(ref.year, ref.month)[1])
        return ini, fin, f'{MESES_ES[ref.month - 1]} {ref.year}'
    ini = ref - timedelta(days=ref.weekday())
    fin = ini + timedelta(days=5)
    return ini, fin, f'Semana {ini:%d/%m} al {fin:%d/%m/%Y} (lun a sáb)'


def vecino_periodo(periodo, ref, delta):
    """Fecha de referencia del periodo anterior (delta=-1) o siguiente (delta=1)."""
    if periodo == 'dia':
        r = ref + timedelta(days=delta)
        if r.weekday() == 6:          # sin domingos
            r += timedelta(days=delta)
        return r
    if periodo == 'mes':
        m = ref.month - 1 + delta
        return ref.replace(day=1, year=ref.year + m // 12, month=m % 12 + 1)
    return ref + timedelta(days=7 * delta)


def ranking_rango(periodo, ref, yo=None):
    """Ranking para un periodo (dia | semana | mes) con su etiqueta y navegación."""
    if periodo not in PERIODOS:
        periodo = 'semana'
    ini, fin, etiqueta = rango_periodo(periodo, ref)
    r = _armar_ranking(ini, fin, dia=None, yo=yo, campeones_dia=(periodo == 'semana'))
    hoy = timezone.localdate()
    r.update({
        'periodo': periodo, 'etiqueta': etiqueta, 'inicio': ini, 'fin': fin,
        'anterior': vecino_periodo(periodo, ref, -1), 'siguiente': vecino_periodo(periodo, ref, 1),
        'es_actual': rango_periodo(periodo, hoy)[0] == ini,
    })
    return r


# ---------------------------------------------------------------------------
# Pantalla pública (monitor): sin datos de dinero, solo servicios realizados
# ---------------------------------------------------------------------------

def token_pantalla():
    """Token fijo derivado de SECRET_KEY: identifica la URL privada del monitor
    sin necesidad de iniciar sesión (el monitor no se desloguea a medianoche)."""
    return hmac.new(settings.SECRET_KEY.encode(), b'pantalla-ranking-v1', hashlib.sha256).hexdigest()[:32]


def token_valido(token):
    return bool(token) and hmac.compare_digest(str(token), token_pantalla())


def _fila_publica(r):
    t = r['tecnico']
    return {
        'nombre': r['nombre'],
        'iniciales': ''.join(p[:1] for p in (t.nombres.split()[:1] + t.apellidos.split()[:1])).upper(),
        'foto': t.foto.url if getattr(t, 'foto', None) else '',
        'servicios': r['servicios'],
        'ordenes': r['ordenes'],
        'pos': r['pos'],
        'posicion': r['posicion'],
        'pct': r['pct'],
    }


def _bloque_publico(r):
    return {
        'filas': [_fila_publica(x) for x in r['filas']],
        'total': r['total_equipo'],
    }


def payload_publico(periodo=None, fecha=None):
    """Datos para el monitor / widget.

    - Sin `periodo`: devuelve Hoy, Semana (lun–sáb) y Mes (monitor).
    - Con `periodo` (dia|semana|mes) y `fecha`: devuelve solo esa vista, con su
      etiqueta y las fechas para navegar al periodo anterior / siguiente (widget).
    """
    hoy = timezone.localdate()
    generado = timezone.localtime().strftime('%H:%M:%S')
    if periodo in PERIODOS:
        ref = fecha or hoy
        r = ranking_rango(periodo, ref)
        out = {
            'generado': generado, 'modo': 'filtro', 'periodo': periodo,
            'etiqueta': r['etiqueta'], 'fecha': ref.strftime('%Y-%m-%d'),
            'anterior': r['anterior'].strftime('%Y-%m-%d'),
            'siguiente': r['siguiente'].strftime('%Y-%m-%d'),
            'es_actual': r['es_actual'],
        }
        out.update(_bloque_publico(r))
        return out

    secciones = {}
    for clave, per in (('hoy', 'dia'), ('semana', 'semana'), ('mes', 'mes')):
        r = ranking_rango(per, hoy)
        secciones[clave] = dict(_bloque_publico(r), etiqueta=r['etiqueta'])
    return dict(secciones, generado=generado, modo='todo')
