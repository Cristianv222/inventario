from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Permission
from .models import Usuario

@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    """Administración personalizada del modelo Usuario"""
    
    # Campos a mostrar en la lista
    list_display = ('usuario', 'nombre', 'apellido', 'email', 'activo', 'is_staff', 'is_superuser', 'fecha_creacion')
    
    # Filtros laterales
    list_filter = ('activo', 'is_staff', 'is_superuser', 'fecha_creacion')
    
    # Campos de búsqueda
    search_fields = ('usuario', 'nombre', 'apellido', 'email', 'telefono')
    
    # Orden por defecto
    ordering = ('-fecha_creacion',)
    
    # Campos de solo lectura
    readonly_fields = ('fecha_creacion', 'fecha_modificacion', 'last_login', 'date_joined')
    
    # Configuración de los fieldsets (para editar usuarios existentes)
    fieldsets = (
        ('Credenciales', {
            'fields': ('usuario', 'password')
        }),
        ('Información Personal', {
            'fields': ('nombre', 'apellido', 'email', 'telefono')
        }),
        ('Permisos y Privilegios', {
            'fields': ('activo', 'is_staff', 'is_superuser', 'groups', 'user_permissions')
        }),
        ('Información del Sistema', {
            'fields': ('fecha_creacion', 'fecha_modificacion', 'last_login', 'date_joined'),
            'classes': ('collapse',)
        }),
    )
    
    # Configuración para agregar nuevos usuarios
    add_fieldsets = (
        ('Credenciales', {
            'classes': ('wide',),
            'fields': ('usuario', 'email', 'password1', 'password2'),
        }),
        ('Información Personal', {
            'classes': ('wide',),
            'fields': ('nombre', 'apellido', 'telefono'),
        }),
        ('Permisos Iniciales', {
            'classes': ('wide',),
            'fields': ('activo', 'is_staff', 'is_superuser'),
        }),
    )
    
    # Filtro horizontal para permisos (más fácil de usar)
    filter_horizontal = ('groups', 'user_permissions')
    
    # Acciones personalizadas
    actions = ['activar_usuarios', 'desactivar_usuarios', 'hacer_staff', 'quitar_staff']
    
    def activar_usuarios(self, request, queryset):
        """Activar usuarios seleccionados"""
        updated = queryset.update(activo=True, is_active=True)
        self.message_user(request, f'{updated} usuario(s) activado(s) correctamente.')
    activar_usuarios.short_description = "✅ Activar usuarios seleccionados"
    
    def desactivar_usuarios(self, request, queryset):
        """Desactivar usuarios seleccionados"""
        updated = queryset.update(activo=False, is_active=False)
        self.message_user(request, f'{updated} usuario(s) desactivado(s) correctamente.')
    desactivar_usuarios.short_description = "❌ Desactivar usuarios seleccionados"
    
    def hacer_staff(self, request, queryset):
        """Convertir usuarios en staff"""
        updated = queryset.update(is_staff=True)
        self.message_user(request, f'{updated} usuario(s) convertido(s) en administradores.')
    hacer_staff.short_description = "🛡️ Hacer administradores"
    
    def quitar_staff(self, request, queryset):
        """Quitar privilegios de staff"""
        # Prevenir quitar staff del usuario actual
        queryset = queryset.exclude(id=request.user.id)
        updated = queryset.update(is_staff=False)
        self.message_user(request, f'{updated} usuario(s) ya no son administradores.')
    quitar_staff.short_description = "👤 Quitar privilegios de administrador"


@admin.register(Permission)
class PermisoAdmin(admin.ModelAdmin):
    """Administración de permisos (opcional, para ver y editar permisos desde el admin)"""
    
    list_display = ('name', 'codename', 'content_type', 'app_label_display')
    list_filter = ('content_type__app_label',)
    search_fields = ('name', 'codename', 'content_type__model', 'content_type__app_label')
    ordering = ('content_type__app_label', 'content_type__model', 'codename')
    
    # Campos de solo lectura (no permitir editar el codename ya que puede romper cosas)
    readonly_fields = ('codename', 'content_type')
    
    # Solo permitir editar el nombre descriptivo
    fields = ('name', 'codename', 'content_type')
    
    # Paginación
    list_per_page = 50
    
    def app_label_display(self, obj):
        """Mostrar la aplicación de forma más legible"""
        return obj.content_type.app_label.replace('_', ' ').title()
    app_label_display.short_description = 'Aplicación'
    
    def has_add_permission(self, request):
        """Desactivar la creación desde aquí (mejor usar la vista personalizada)"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Solo superusuarios pueden eliminar permisos"""
        return request.user.is_superuser