import re

# Códigos oficiales del SRI para tipos de identificación
SRI_TIPO_IDENTIFICACION = {
    'RUC': '04',
    'CEDULA': '05',
    'PASAPORTE': '06',
    'CONSUMIDOR_FINAL': '07',
    'EXTERIOR': '08',
}

def obtener_codigo_sri_identificacion(tipo_documento, numero_documento):
    """
    Retorna el código de identificación estándar del SRI
    """
    if numero_documento == '9999999999999':
        return SRI_TIPO_IDENTIFICACION['CONSUMIDOR_FINAL']
    
    return SRI_TIPO_IDENTIFICACION.get(tipo_documento, '07')

def validar_ruc(ruc):
    """Validación básica de RUC ecuatoriano"""
    if not ruc or len(ruc) != 13:
        return False
    # Podríamos añadir validación de módulo 11 aquí más adelante
    return ruc.isdigit()

def validar_cedula(cedula):
    """Validación básica de cédula ecuatoriana"""
    if not cedula or len(cedula) != 10:
        return False
    return cedula.isdigit()

def generar_clave_acceso(fecha, tipo_comprobante, ruc, ambiente, serie, secuencial, codigo_numerico, tipo_emision):
    """
    Genera la clave de acceso de 49 dígitos requerida por el SRI
    Formato: fecha(8) + tipo(2) + ruc(13) + ambiente(1) + serie(6) + secuencial(9) + codigo(8) + emision(1) + verificador(1)
    """
    fecha_fmt = fecha.strftime('%d%m%Y')
    clave = f"{fecha_fmt}{tipo_comprobante}{ruc}{ambiente}{serie}{secuencial}{codigo_numerico}{tipo_emision}"
    
    # Cálculo del dígito verificador (Módulo 11)
    verificador = calcular_modulo11(clave)
    return f"{clave}{verificador}"

def calcular_modulo11(clave):
    """Cálculo del dígito verificador mediante algoritmo de módulo 11"""
    factores = [2, 3, 4, 5, 6, 7]
    suma = 0
    for i, digito in enumerate(reversed(clave)):
        suma += int(digito) * factores[i % 6]
    
    verificador = 11 - (suma % 11)
    if verificador == 11:
        return 0
    if verificador == 10:
        return 1
    return verificador
