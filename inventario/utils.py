import os
import io
from pathlib import Path
from PIL import Image, ImageOps
from django.core.files.base import ContentFile

def convertir_a_webp(imagen_field, max_size=(1200, 1200), quality=82):
    """
    Recibe un campo de imagen de Django (UploadedFile o FieldFile),
    abre la imagen con Pillow, corrige la orientación EXIF, redimensiona
    si excede max_size y la convierte al formato WebP ultra-liviano.
    
    Retorna un nuevo ContentFile listo para asignarse al modelo.
    """
    if not imagen_field or not hasattr(imagen_field, 'file'):
        return imagen_field

    try:
        # Abrir la imagen con Pillow
        img = Image.open(imagen_field)
        
        # Corregir orientación basada en EXIF (ej: fotos tomadas con celulares)
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        # Manejar transparencia si es RGBA o P
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            img = img.convert('RGBA')
        else:
            img = img.convert('RGB')

        # Redimensionar proporcionalmente si supera las dimensiones máximas
        img.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Guardar en buffer en memoria como WEBP
        buffer = io.BytesIO()
        img.save(buffer, format='WEBP', quality=quality, method=6)
        buffer.seek(0)

        # Generar nuevo nombre con extensión .webp
        name = getattr(imagen_field, 'name', 'imagen.jpg')
        base_name = Path(name).stem
        new_filename = f"{base_name}.webp"

        return ContentFile(buffer.getvalue(), name=new_filename)
    except Exception as e:
        # Si ocurre un error al procesar, retornar el archivo original
        print(f"Error procesando imagen a WebP: {e}")
        return imagen_field
