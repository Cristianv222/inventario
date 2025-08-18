# Usar Python 3.11 como imagen base
FROM python:3.11-slim

# Establecer variables de entorno
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    postgresql-client \
    gettext \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Crear directorio de trabajo
WORKDIR /app

# Copiar requirements y instalar dependencias de Python
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del proyecto
COPY . /app/

# Crear directorio para archivos estáticos y media
RUN mkdir -p /app/staticfiles /app/media

# Hacer el script de entrada ejecutable
COPY entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh

# Exponer el puerto
EXPOSE 8000

# Comando de entrada
ENTRYPOINT ["/app/entrypoint.sh"]