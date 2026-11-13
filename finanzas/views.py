from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

from .models import AsientoContable, CuentaContable


@login_required
def estado_motor(request):
    """Vista mínima de estado del motor contable (placeholder del dashboard).

    El dashboard real del ERP se construye en una fase posterior; por ahora
    solo confirma que la app está instalada y muestra conteos básicos.
    """
    cuentas = CuentaContable.objects.count()
    asientos = AsientoContable.objects.count()
    html = f"""
    <html><head><meta charset="utf-8"><title>Finanzas · Motor contable</title></head>
    <body style="font-family: system-ui, sans-serif; max-width: 640px; margin: 3rem auto;">
      <h1>Finanzas — Motor contable</h1>
      <p>App instalada correctamente.</p>
      <ul>
        <li>Cuentas en el plan: <strong>{cuentas}</strong></li>
        <li>Asientos registrados: <strong>{asientos}</strong></li>
      </ul>
      <p style="color:#666">El dashboard del ERP y los estados financieros se
      construyen en las siguientes fases.</p>
    </body></html>
    """
    return HttpResponse(html)
