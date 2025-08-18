from django import template
from datetime import datetime, timedelta, date
from decimal import Decimal

register = template.Library()

@register.filter
def add_days(date_value, days):
    """
    Agrega el número especificado de días a una fecha
    Uso: {{ fecha|add_days:5 }}
    """
    try:
        days = int(days)
        if isinstance(date_value, datetime):
            return date_value + timedelta(days=days)
        elif isinstance(date_value, date):
            return date_value + timedelta(days=days)
        else:
            # Si es string, intentar parsear
            if isinstance(date_value, str):
                try:
                    parsed_date = datetime.strptime(date_value, '%Y-%m-%d').date()
                    return parsed_date + timedelta(days=days)
                except ValueError:
                    return date_value
            return date_value
    except (ValueError, TypeError):
        return date_value

@register.filter
def subtract_days(date_value, days):
    """
    Resta el número especificado de días a una fecha
    Uso: {{ fecha|subtract_days:5 }}
    """
    try:
        days = int(days)
        if isinstance(date_value, datetime):
            return date_value - timedelta(days=days)
        elif isinstance(date_value, date):
            return date_value - timedelta(days=days)
        else:
            if isinstance(date_value, str):
                try:
                    parsed_date = datetime.strptime(date_value, '%Y-%m-%d').date()
                    return parsed_date - timedelta(days=days)
                except ValueError:
                    return date_value
            return date_value
    except (ValueError, TypeError):
        return date_value

@register.filter
def currency(value):
    """
    Formatea un número como moneda
    Uso: {{ monto|currency }}
    """
    try:
        if value is None:
            return '$0.00'
        
        if isinstance(value, str):
            value = float(value)
        
        return f'${value:,.2f}'
    except (ValueError, TypeError):
        return '$0.00'

@register.filter
def percentage(value, total):
    """
    Calcula el porcentaje de un valor respecto al total
    Uso: {{ valor|percentage:total }}
    """
    try:
        if not total or total == 0:
            return '0%'
        
        value = float(value) if value else 0
        total = float(total)
        percentage = (value / total) * 100
        
        return f'{percentage:.1f}%'
    except (ValueError, TypeError, ZeroDivisionError):
        return '0%'

@register.filter
def abs_value(value):
    """
    Devuelve el valor absoluto
    Uso: {{ numero|abs_value }}
    """
    try:
        return abs(float(value))
    except (ValueError, TypeError):
        return 0

@register.filter
def multiply(value, multiplier):
    """
    Multiplica un valor por un multiplicador
    Uso: {{ valor|multiply:2 }}
    """
    try:
        return float(value) * float(multiplier)
    except (ValueError, TypeError):
        return 0

@register.filter
def format_date_range(start_date, end_date):
    """
    Formatea un rango de fechas
    Uso: {{ fecha_inicio|format_date_range:fecha_fin }}
    """
    try:
        if start_date == end_date:
            return start_date.strftime('%d/%m/%Y')
        else:
            return f"{start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}"
    except (AttributeError, ValueError):
        return ''

@register.simple_tag
def calculate_growth(current, previous):
    """
    Calcula el crecimiento porcentual entre dos valores
    Uso: {% calculate_growth valor_actual valor_anterior %}
    """
    try:
        current = float(current) if current else 0
        previous = float(previous) if previous else 0
        
        if previous == 0:
            return 0 if current == 0 else 100
        
        growth = ((current - previous) / previous) * 100
        return round(growth, 1)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

@register.simple_tag
def get_month_name(month_number):
    """
    Obtiene el nombre del mes en español
    Uso: {% get_month_name 5 %}
    """
    months = {
        1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
        5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
        9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
    }
    return months.get(int(month_number), '')

@register.simple_tag
def format_currency_difference(value):
    """
    Formatea una diferencia monetaria con signo
    Uso: {% format_currency_difference diferencia %}
    """
    try:
        value = float(value) if value else 0
        sign = '+' if value >= 0 else ''
        return f'{sign}${value:,.2f}'
    except (ValueError, TypeError):
        return '$0.00'