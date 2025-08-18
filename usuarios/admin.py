from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario, Rol

@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ('usuario', 'nombre', 'apellido', 'email', 'rol', 'is_staff', 'activo')
    list_filter = ('rol', 'activo', 'is_staff')
    search_fields = ('usuario', 'nombre', 'apellido', 'email')
    fieldsets = (
        (None, {'fields': ('usuario', 'password')}),
        ('Información Personal', {'fields': ('nombre', 'apellido', 'email', 'telefono')}),
        ('Permisos', {'fields': ('rol', 'activo', 'is_staff', 'is_superuser', 'user_permissions')}),
        ('Fechas Importantes', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('usuario', 'email', 'nombre', 'apellido', 'password1', 'password2', 'rol', 'activo', 'is_staff'),
        }),
    )
    ordering = ('usuario',)
    filter_horizontal = ('groups', 'user_permissions',)

@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descripcion', 'activo')
    list_filter = ('activo',)
    search_fields = ('nombre', 'descripcion')
    filter_horizontal = ('permisos',)