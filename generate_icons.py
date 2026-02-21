"""
Genera todos los tamaños de ícono PWA desde favicon.png
Ejecutar: python generate_icons.py

Requiere: pip install Pillow
"""

from PIL import Image
import os

# Ruta de tu favicon original
SOURCE = 'static/img/favicon.png'
OUTPUT_DIR = 'static/img/'

SIZES = [72, 96, 128, 192, 512]

def generate_icons():
    if not os.path.exists(SOURCE):
        print(f"❌ No se encontró: {SOURCE}")
        print("   Ajusta la variable SOURCE con la ruta correcta a tu favicon.png")
        return

    img = Image.open(SOURCE).convert('RGBA')
    print(f"✅ Leyendo: {SOURCE} ({img.width}x{img.height})")

    for size in SIZES:
        resized = img.resize((size, size), Image.LANCZOS)
        out_path = os.path.join(OUTPUT_DIR, f'icon-{size}.png')
        resized.save(out_path, 'PNG', optimize=True)
        print(f"   ✔ Generado: {out_path}")

    print("\n✅ Todos los íconos generados correctamente.")
    print("   Ahora corre: python manage.py collectstatic")

if __name__ == '__main__':
    generate_icons()