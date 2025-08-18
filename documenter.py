#!/usr/bin/env python3
"""
Documentador Completo para Proyectos Django
Genera documentación exhaustiva similar al formato VENDO_SRI
"""

import os
import ast
import sys
import re
import subprocess
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import platform

class CompleteDjangoDocumenter:
    def __init__(self, project_path="."):
        self.project_path = Path(project_path).resolve()
        self.timestamp = datetime.now()
        self.apps_django = []
        self.installed_packages = {}
        self.required_packages = {}
        self.file_stats = defaultdict(int)
        self.total_files = 0
        self.total_dirs = 0
        
    def get_system_info(self):
        """Obtiene información del sistema"""
        try:
            python_version = f"Python {sys.version.split()[0]}"
        except:
            python_version = "Desconocido"
            
        try:
            pip_version = subprocess.check_output([sys.executable, "-m", "pip", "--version"], 
                                                text=True).strip()
        except:
            pip_version = "pip no disponible"
            
        # Detectar entorno virtual
        venv_active = hasattr(sys, 'real_prefix') or (
            hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
        )
        
        return {
            'python_version': python_version,
            'pip_version': pip_version,
            'venv_active': "✅ ACTIVO" if venv_active else "❌ NO ACTIVO",
            'os': platform.system(),
            'user': os.getenv('USER', 'Desconocido')
        }
    
    def get_file_tree(self, directory=None, prefix="", max_depth=6, current_depth=0, show_all_files=False):
        """Genera árbol de archivos detallado con tamaños"""
        if directory is None:
            directory = self.project_path
            
        tree = []
        excluded_dirs = {'__pycache__', '.git', 'node_modules', '.pytest_cache'}
        # Solo excluir venv si está en la raíz
        if current_depth == 0:
            excluded_dirs.update({'venv', '.venv'})
        
        try:
            items = []
            for item in directory.iterdir():
                # Mostrar archivos importantes que empiezan con punto
                if item.name.startswith('.') and item.name not in {'.env', '.gitignore', '.dockerignore'}:
                    continue
                if item.name in excluded_dirs:
                    if item.is_dir():
                        tree.append(f"{prefix}├── {item.name}/ (excluido)")
                    continue
                items.append(item)
            
            items = sorted(items, key=lambda x: (x.is_file(), x.name.lower()))
            
            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                current_prefix = "└── " if is_last else "├── "
                
                if item.is_file():
                    size = self.format_size(item.stat().st_size)
                    tree.append(f"{prefix}{current_prefix}{item.name} ({size})")
                    self.total_files += 1
                    # Contar extensiones
                    ext = item.suffix.lower()
                    self.file_stats[ext or '(sin extensión)'] += 1
                else:
                    # Contar elementos en directorio
                    try:
                        dir_items = [x for x in item.iterdir() if not x.name.startswith('.') or x.name in {'.env', '.gitignore'}]
                        dir_count = len(dir_items)
                        tree.append(f"{prefix}{current_prefix}{item.name}/ ({dir_count} elementos)")
                        self.total_dirs += 1
                        
                        # Decidir si mostrar contenido del directorio
                        should_expand = True
                        
                        # Limitar profundidad solo para ciertos directorios
                        if current_depth >= max_depth:
                            # Permitir expandir directorios importantes incluso en profundidad alta
                            important_dirs = {'apps', 'templates', 'static', 'storage', 'migrations', 'management', 'commands'}
                            if not any(important in item.name.lower() for important in important_dirs):
                                should_expand = False
                        
                        # Siempre expandir directorios de apps Django y configuración
                        django_dirs = {'apps', 'templates', 'static', 'storage', 'locale', 'fixtures', 'scripts', 'utils'}
                        if item.name in django_dirs or current_depth < 3:
                            should_expand = True
                        
                        if should_expand:
                            # Recursión para subdirectorios
                            extension = "    " if is_last else "│   "
                            subtree = self.get_file_tree(
                                item, 
                                prefix + extension, 
                                max_depth, 
                                current_depth + 1,
                                show_all_files
                            )
                            tree.extend(subtree)
                        else:
                            # Mostrar solo algunos archivos importantes del directorio
                            important_files = []
                            try:
                                for subitem in item.iterdir():
                                    if (subitem.is_file() and 
                                        (subitem.suffix in {'.py', '.html', '.md', '.txt', '.yml', '.yaml'} or
                                         subitem.name in {'manage.py', 'requirements.txt', '.env', 'Dockerfile'})):
                                        important_files.append(subitem.name)
                                
                                if important_files and len(important_files) <= 5:
                                    extension = "    " if is_last else "│   "
                                    for j, filename in enumerate(sorted(important_files)):
                                        file_prefix = "└── " if j == len(important_files) - 1 else "├── "
                                        tree.append(f"{prefix}{extension}{file_prefix}{filename}")
                                elif len(important_files) > 5:
                                    extension = "    " if is_last else "│   "
                                    tree.append(f"{prefix}{extension}├── ... ({len(important_files)} archivos)")
                            except PermissionError:
                                pass
                                
                    except PermissionError:
                        tree.append(f"{prefix}{current_prefix}{item.name}/ (sin permisos)")
                        
        except PermissionError:
            tree.append(f"{prefix}(sin permisos para listar)")
            
        return tree
    
    def format_size(self, size_bytes):
        """Formatea tamaño de archivo"""
        if size_bytes == 0:
            return "0B"
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f}TB"
    
    def find_django_apps(self):
        """Encuentra y analiza apps de Django"""
        apps_dir = self.project_path / "apps"
        apps = []
        
        # Buscar en directorio apps/
        if apps_dir.exists():
            for item in apps_dir.iterdir():
                if item.is_dir() and not item.name.startswith('_'):
                    apps.append(self.analyze_app(item))
        
        # Buscar en directorio raíz
        for item in self.project_path.iterdir():
            if (item.is_dir() and 
                not item.name.startswith('.') and 
                item.name not in {'venv', 'static', 'media', 'templates', 'locale'} and
                (item / 'models.py').exists()):
                apps.append(self.analyze_app(item))
        
        return apps
    
    def analyze_app(self, app_path):
        """Analiza una app Django individual"""
        basic_files = ['models.py', 'views.py', 'urls.py', 'admin.py', 'apps.py']
        optional_files = ['forms.py', 'serializers.py', 'tests.py', 'signals.py']
        
        app_info = {
            'name': app_path.name,
            'path': app_path,
            'basic_files': 0,
            'total_files': 0,
            'existing_files': [],
            'missing_files': [],
            'status': 'Incompleta'
        }
        
        # Contar archivos básicos
        for file_name in basic_files:
            file_path = app_path / file_name
            if file_path.exists() and file_path.stat().st_size > 0:
                app_info['basic_files'] += 1
                app_info['existing_files'].append(file_name)
            else:
                app_info['missing_files'].append(file_name)
        
        # Contar archivos opcionales
        for file_name in optional_files:
            file_path = app_path / file_name
            if file_path.exists() and file_path.stat().st_size > 0:
                app_info['existing_files'].append(file_name)
        
        # Contar todos los archivos
        try:
            app_info['total_files'] = len([f for f in app_path.rglob('*.py') 
                                         if not f.name.startswith('_')])
        except:
            app_info['total_files'] = len(app_info['existing_files'])
        
        # Determinar estado
        if app_info['basic_files'] == len(basic_files):
            app_info['status'] = 'Completa'
        elif app_info['basic_files'] > 0:
            app_info['status'] = 'Parcial'
        else:
            app_info['status'] = 'Vacía'
            
        return app_info
    
    def analyze_requirements(self):
        """Analiza requirements.txt y paquetes instalados"""
        # Paquetes requeridos típicos para SRI
        self.required_packages = {
            'Django': '4.2.7',
            'djangorestframework': '3.14.0',
            'psycopg2-binary': '2.9.7',
            'python-decouple': '3.8',
            'celery': '5.3.4',
            'redis': '5.0.1',
            'cryptography': '41.0.7',
            'lxml': '4.9.3',
            'zeep': '4.2.1',
            'reportlab': '4.0.7',
            'Pillow': '10.1.0',
            'drf-spectacular': '0.26.5',
            'django-cors-headers': '4.3.1'
        }
        
    def get_installed_packages(self):
        """Obtiene lista de paquetes instalados usando pip list"""
        packages = {}
        
        # Método principal: usar pip list
        try:
            print("   📦 Obteniendo lista de paquetes instalados...")
            result = subprocess.run([sys.executable, '-m', 'pip', 'list', '--format=freeze'], 
                                  capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if '==' in line and not line.startswith('#'):
                        try:
                            name, version = line.split('==', 1)
                            packages[name.strip()] = version.strip()
                        except ValueError:
                            continue
                print(f"   ✅ {len(packages)} paquetes detectados")
                return packages
        except subprocess.TimeoutExpired:
            print("   ⚠️  Timeout al ejecutar pip list")
        except Exception as e:
            print(f"   ⚠️  Error con pip list: {e}")
        
        # Método de respaldo: detectar paquetes Django manualmente
        print("   🔍 Usando detección manual de paquetes clave...")
        django_packages = {
            'Django': self._get_django_version(),
            'djangorestframework': self._get_drf_version(),
            'psycopg2-binary': self._get_psycopg2_version(),
            'cryptography': self._get_package_version('cryptography'),
            'lxml': self._get_package_version('lxml'),
            'zeep': self._get_package_version('zeep'),
            'reportlab': self._get_package_version('reportlab'),
            'Pillow': self._get_pillow_version(),
            'requests': self._get_package_version('requests'),
        }
        
        # Filtrar None values
        packages = {k: v for k, v in django_packages.items() if v is not None}
        print(f"   ✅ {len(packages)} paquetes clave detectados")
        return packages
    
    def _get_django_version(self):
        """Obtiene versión de Django"""
        try:
            import django
            return django.get_version()
        except ImportError:
            return None
    
    def _get_drf_version(self):
        """Obtiene versión de Django REST Framework"""
        try:
            import rest_framework
            return getattr(rest_framework, '__version__', 'unknown')
        except ImportError:
            return None
    
    def _get_psycopg2_version(self):
        """Obtiene versión de psycopg2"""
        try:
            import psycopg2
            return getattr(psycopg2, '__version__', 'unknown').split()[0]
        except ImportError:
            return None
    
    def _get_pillow_version(self):
        """Obtiene versión de Pillow"""
        try:
            from PIL import Image
            return getattr(Image, '__version__', 'unknown')
        except ImportError:
            try:
                import PIL
                return getattr(PIL, '__version__', 'unknown')
            except ImportError:
                return None
    
    def _get_package_version(self, package_name):
        """Obtiene versión de un paquete genérico"""
        try:
            module = __import__(package_name)
            # Buscar atributos comunes de versión
            for attr in ['__version__', 'VERSION', 'version']:
                if hasattr(module, attr):
                    version = getattr(module, attr)
                    if isinstance(version, tuple):
                        return '.'.join(map(str, version))
                    return str(version)
            return 'unknown'
        except ImportError:
            return None
        except Exception:
            return 'error'
        
        # Leer requirements.txt si existe
        req_file = self.project_path / 'requirements.txt'
        if req_file.exists():
            try:
                with open(req_file, 'r') as f:
                    content = f.read()
                    # Actualizar versiones requeridas desde el archivo
                    for line in content.split('\n'):
                        if '==' in line:
                            pkg, version = line.strip().split('==')
                            self.required_packages[pkg] = version
            except:
                pass
    
    def analyze_settings(self):
        """Analiza el archivo settings.py"""
        settings_info = {
            'found': False,
            'installed_apps': [],
            'middleware': [],
            'databases': False,
            'rest_framework': False,
            'static_url': False,
            'debug': False,
            'secret_key': False
        }
        
        # Buscar settings.py
        settings_paths = [
            self.project_path / 'settings.py',
            self.project_path / f'{self.project_path.name}' / 'settings.py'
        ]
        
        for settings_dir in self.project_path.iterdir():
            if settings_dir.is_dir():
                settings_paths.append(settings_dir / 'settings.py')
        
        for settings_path in settings_paths:
            if settings_path.exists():
                settings_info['found'] = True
                try:
                    with open(settings_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Buscar configuraciones específicas
                    if 'INSTALLED_APPS' in content:
                        # Extraer INSTALLED_APPS
                        apps_match = re.search(r'INSTALLED_APPS\s*=\s*\[(.*?)\]', 
                                             content, re.DOTALL)
                        if apps_match:
                            apps_content = apps_match.group(1)
                            apps = re.findall(r'[\'\"](.*?)[\'\"]', apps_content)
                            settings_info['installed_apps'] = apps
                    
                    # Buscar otras configuraciones
                    settings_info['databases'] = 'DATABASES' in content
                    settings_info['rest_framework'] = 'REST_FRAMEWORK' in content
                    settings_info['static_url'] = 'STATIC_URL' in content
                    settings_info['debug'] = 'DEBUG' in content
                    settings_info['secret_key'] = 'SECRET_KEY' in content
                    
                    break
                except:
                    pass
        
        return settings_info
    
    def check_important_files(self):
        """Verifica archivos importantes del proyecto"""
        important_files = {
            'manage.py': 'Comando principal de Django',
            'requirements.txt': 'Dependencias del proyecto',
            '.env': 'Variables de entorno',
            '.env.example': 'Ejemplo de variables de entorno',
            '.gitignore': 'Archivos ignorados por Git',
            'README.md': 'Documentación del proyecto',
            'docker-compose.yml': 'Configuración Docker',
            'Dockerfile': 'Imagen Docker',
            'pytest.ini': 'Configuración de tests',
            'setup.cfg': 'Configuración del proyecto'
        }
        
        file_status = {}
        for filename, description in important_files.items():
            file_path = self.project_path / filename
            file_status[filename] = {
                'exists': file_path.exists(),
                'description': description,
                'size': self.format_size(file_path.stat().st_size) if file_path.exists() else None
            }
        
        return file_status
    
    def analyze_storage_structure(self):
        """Analiza estructura de almacenamiento"""
        storage_dirs = [
            'storage/certificates/encrypted/',
            'storage/certificates/temp/',
            'storage/invoices/xml/',
            'storage/invoices/pdf/',
            'storage/invoices/sent/',
            'storage/logs/',
            'storage/backups/',
            'media/',
            'static/',
            'uploads/'
        ]
        
        storage_status = {}
        for dir_path in storage_dirs:
            full_path = self.project_path / dir_path
            storage_status[dir_path] = {
                'exists': full_path.exists(),
                'files': 0
            }
            
            if full_path.exists():
                try:
                    storage_status[dir_path]['files'] = len(list(full_path.rglob('*')))
                except:
                    storage_status[dir_path]['files'] = 0
        
        return storage_status
    
    def generate_complete_documentation(self):
        """Genera documentación completa"""
        print("📝 Generando documentación completa del proyecto...")
        
        # Recopilar información
        system_info = self.get_system_info()
        print("✅ Información del sistema obtenida")
        
        self.apps_django = self.find_django_apps()
        print(f"✅ {len(self.apps_django)} apps Django analizadas")
        
        self.analyze_requirements()
        print("✅ Dependencias analizadas")
        
        settings_info = self.analyze_settings()
        print("✅ Configuración Django analizada")
        
        important_files = self.check_important_files()
        print("✅ Archivos importantes verificados")
        
        storage_structure = self.analyze_storage_structure()
        print("✅ Estructura de almacenamiento analizada")
        
        print("📁 Generando árbol de archivos completo...")
        file_tree = self.get_file_tree()
        print("✅ Árbol de archivos generado")
        
        # Comenzar a escribir documentación
        doc = []
        
        # ENCABEZADO
        doc.append("=" * 80)
        doc.append(f"                    DOCUMENTACIÓN COMPLETA - PROYECTO {self.project_path.name.upper()}")
        doc.append("=" * 80)
        doc.append("")
        doc.append("INFORMACIÓN GENERAL")
        doc.append("-" * 19)
        doc.append(f"Fecha de generación: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        doc.append(f"Ubicación: {self.project_path}")
        doc.append(f"Python Version: {system_info['python_version']}")
        doc.append(f"Pip Version: {system_info['pip_version']}")
        doc.append(f"Entorno Virtual: {system_info['venv_active']}")
        doc.append(f"Sistema Operativo: {system_info['os']}")
        doc.append(f"Usuario: {system_info['user']}")
        doc.append("")
        
        # ESTRUCTURA DEL PROYECTO
        doc.append("=" * 80)
        doc.append("                            ESTRUCTURA DEL PROYECTO")
        doc.append("=" * 80)
        doc.append("")
        # Mostrar toda la estructura sin límites
        doc.extend(file_tree)
        doc.append("")
        
        # ANÁLISIS DE ARCHIVOS
        doc.append("=" * 80)
        doc.append("                            ANÁLISIS DE ARCHIVOS")
        doc.append("=" * 80)
        doc.append("")
        doc.append("ARCHIVOS IMPORTANTES")
        doc.append("-" * 20)
        for filename, info in important_files.items():
            status = "✅ Existe" if info['exists'] else "❌ Faltante"
            size_info = f" ({info['size']})" if info['exists'] and info['size'] else ""
            doc.append(f"{filename:<25} {status}{size_info}")
        doc.append("")
        
        doc.append("ESTADÍSTICAS POR EXTENSIÓN")
        doc.append("-" * 26)
        total_counted = sum(self.file_stats.values())
        for ext, count in sorted(self.file_stats.items(), key=lambda x: x[1], reverse=True)[:10]:
            percentage = (count / total_counted * 100) if total_counted > 0 else 0
            doc.append(f"{ext:<20} {count:>4} archivos ({percentage:>5.1f}%)")
        doc.append("")
        
        doc.append("TOTALES")
        doc.append("-" * 7)
        doc.append(f"Total de archivos: {self.total_files}")
        doc.append(f"Total de directorios: {self.total_dirs}")
        doc.append("")
        
        # APLICACIONES DJANGO
        doc.append("=" * 80)
        doc.append("                           APLICACIONES DJANGO")
        doc.append("=" * 80)
        doc.append("")
        doc.append("ESTADO DE LAS APPS")
        doc.append("-" * 80)
        doc.append(f"{'App':<20} {'Estado':<10} {'Básicos':<10} {'Total':<10} {'Archivos Existentes':<25}")
        doc.append("-" * 80)
        
        for app in self.apps_django:
            existing_files = ", ".join(app['existing_files'][:3])
            if len(app['existing_files']) > 3:
                existing_files += "..."
            doc.append(f"{app['name']:<20} {app['status']:<10} {app['basic_files']}/5{'':<5} "
                      f"{app['total_files']:<10} {existing_files:<25}")
        
        doc.append("")
        doc.append("DETALLE POR APP")
        doc.append("=" * 50)
        doc.append("")
        
        for app in self.apps_django:
            doc.append(f"📦 App: {app['name']}")
            doc.append(f"   Ubicación: {app['path'].relative_to(self.project_path)}/")
            doc.append(f"   Estado: {app['status']}")
            doc.append(f"   Archivos básicos: {app['basic_files']}/5")
            
            if app['existing_files']:
                doc.append(f"   Archivos encontrados: {', '.join(app['existing_files'])}")
            
            if app['missing_files']:
                doc.append(f"   ❌ Archivos faltantes: {', '.join(app['missing_files'])}")
            else:
                doc.append("   ✅ Todos los archivos básicos presentes")
            doc.append("")
        
        # CONFIGURACIÓN DJANGO
        doc.append("=" * 80)
        doc.append("                         CONFIGURACIÓN DJANGO")
        doc.append("=" * 80)
        doc.append("")
        
        if settings_info['found']:
            doc.append("✅ ARCHIVO settings.py ENCONTRADO")
            doc.append("-" * 40)
            
            configs = {
                'INSTALLED_APPS': len(settings_info['installed_apps']) > 0,
                'DATABASES': settings_info['databases'],
                'REST_FRAMEWORK': settings_info['rest_framework'],
                'STATIC_URL': settings_info['static_url'],
                'DEBUG': settings_info['debug'],
                'SECRET_KEY': settings_info['secret_key']
            }
            
            for config, exists in configs.items():
                status = "✅ Configurado" if exists else "❌ Faltante"
                description = {
                    'INSTALLED_APPS': 'Apps instaladas',
                    'DATABASES': 'Configuración de BD',
                    'REST_FRAMEWORK': 'API REST Framework',
                    'STATIC_URL': 'Archivos estáticos',
                    'DEBUG': 'Modo debug',
                    'SECRET_KEY': 'Clave secreta'
                }.get(config, '')
                doc.append(f"{config:<20} {status:<15} {description}")
            
            if settings_info['installed_apps']:
                doc.append("")
                doc.append("CONTENIDO DE INSTALLED_APPS:")
                doc.append("-" * 40)
                for app in settings_info['installed_apps'][:20]:  # Mostrar primeras 20
                    doc.append(f"- {app}")
                if len(settings_info['installed_apps']) > 20:
                    doc.append(f"... y {len(settings_info['installed_apps']) - 20} más")
        else:
            doc.append("❌ ARCHIVO settings.py NO ENCONTRADO")
        
        doc.append("")
        
        # PAQUETES PYTHON
        doc.append("=" * 80)
        doc.append("                         PAQUETES PYTHON")
        doc.append("=" * 80)
        doc.append("")
        doc.append("PAQUETES REQUERIDOS PARA SRI")
        doc.append("-" * 28)
        
        for pkg, required_version in self.required_packages.items():
            installed_version = self.installed_packages.get(pkg, 'No instalado')
            if installed_version != 'No instalado':
                status = "✅ Instalado"
                version_info = f"{installed_version:<15} (Req: {required_version})"
            else:
                status = "❌ Faltante"
                version_info = f"{'No instalado':<15} (Req: {required_version})"
            
            doc.append(f"{pkg:<25} {status:<15} {version_info}")
        
        doc.append("")
        doc.append("")
        doc.append("TODOS LOS PAQUETES INSTALADOS")
        doc.append("-" * 29)
        
        for pkg, version in sorted(self.installed_packages.items())[:30]:
            doc.append(f"{pkg}=={version}")
        
        if len(self.installed_packages) > 30:
            doc.append(f"... y {len(self.installed_packages) - 30} paquetes más")
        
        doc.append("")
        
        # ESTRUCTURA DE ALMACENAMIENTO
        doc.append("=" * 80)
        doc.append("                    ESTRUCTURA DE ALMACENAMIENTO SEGURO")
        doc.append("=" * 80)
        doc.append("")
        doc.append("DIRECTORIOS DE STORAGE")
        doc.append("-" * 22)
        
        for dir_path, info in storage_structure.items():
            status = "✅" if info['exists'] else "❌"
            file_count = f"({info['files']} archivos)" if info['exists'] else ""
            description = {
                'storage/certificates/encrypted/': 'Certificados .p12 encriptados',
                'storage/certificates/temp/': 'Temporal para procesamiento',
                'storage/invoices/xml/': 'Facturas XML firmadas',
                'storage/invoices/pdf/': 'Facturas PDF generadas',
                'storage/invoices/sent/': 'Facturas enviadas al SRI',
                'storage/logs/': 'Logs del sistema',
                'storage/backups/': 'Respaldos de BD',
                'media/': 'Archivos de media',
                'static/': 'Archivos estáticos',
                'uploads/': 'Archivos subidos'
            }.get(dir_path, dir_path)
            
            doc.append(f"{dir_path:<35} {status} {description} {file_count}")
        
        doc.append("")
        
        # ANÁLISIS Y PRÓXIMOS PASOS
        doc.append("=" * 80)
        doc.append("                         ANÁLISIS Y PRÓXIMOS PASOS")
        doc.append("=" * 80)
        doc.append("")
        
        # Archivos faltantes críticos
        missing_critical = [f for f, info in important_files.items() 
                          if not info['exists'] and f in ['README.md', 'requirements.txt', '.env']]
        
        if missing_critical:
            doc.append("ARCHIVOS FALTANTES CRÍTICOS")
            doc.append("-" * 27)
            for file in missing_critical:
                doc.append(f"❌ {file}")
            doc.append("")
        
        # Apps sin configurar
        incomplete_apps = [app for app in self.apps_django if app['status'] != 'Completa']
        if incomplete_apps:
            doc.append("APPS DJANGO SIN CONFIGURAR")
            doc.append("-" * 30)
            for app in incomplete_apps:
                doc.append(f"❌ {app['name']} - {app['status']}")
            doc.append("")
        
        # Tareas prioritarias
        doc.append("TAREAS PRIORITARIAS")
        doc.append("=" * 19)
        doc.append("")
        
        task_counter = 1
        
        if not important_files['requirements.txt']['exists']:
            doc.append(f"{task_counter}. CREAR requirements.txt")
            doc.append("   Con los paquetes necesarios para SRI")
            doc.append("")
            task_counter += 1
        
        if not settings_info['found']:
            doc.append(f"{task_counter}. CONFIGURAR DJANGO")
            doc.append("   - Crear/verificar settings.py")
            doc.append("   - Configurar INSTALLED_APPS")
            doc.append("   - Configurar base de datos")
            doc.append("")
            task_counter += 1
        
        if incomplete_apps:
            doc.append(f"{task_counter}. COMPLETAR APPS DJANGO")
            doc.append("   Crear archivos faltantes en:")
            for app in incomplete_apps[:5]:
                doc.append(f"   - {app['name']}: {', '.join(app['missing_files'])}")
            doc.append("")
            task_counter += 1
        
        if not important_files['README.md']['exists']:
            doc.append(f"{task_counter}. CREAR DOCUMENTACIÓN")
            doc.append("   - README.md con instrucciones de instalación")
            doc.append("   - Documentación de API")
            doc.append("")
            task_counter += 1
        
        # Comandos útiles
        doc.append("COMANDOS ÚTILES")
        doc.append("=" * 15)
        doc.append("# Instalar dependencias")
        doc.append("pip install -r requirements.txt")
        doc.append("")
        doc.append("# Aplicar migraciones")
        doc.append("python manage.py makemigrations")
        doc.append("python manage.py migrate")
        doc.append("")
        doc.append("# Crear superusuario")
        doc.append("python manage.py createsuperuser")
        doc.append("")
        doc.append("# Ejecutar servidor")
        doc.append("python manage.py runserver")
        doc.append("")
        
        # MÉTRICAS FINALES
        doc.append("=" * 80)
        doc.append("                                MÉTRICAS FINALES")
        doc.append("=" * 80)
        doc.append("")
        
        # Calcular progreso
        complete_apps = len([app for app in self.apps_django if app['status'] == 'Completa'])
        total_apps = len(self.apps_django) if self.apps_django else 1
        
        critical_files_exists = sum(1 for f in ['manage.py', 'requirements.txt'] 
                                  if important_files[f]['exists'])
        
        structure_progress = 100 if important_files['manage.py']['exists'] else 50
        config_progress = 80 if settings_info['found'] else 20
        apps_progress = (complete_apps / total_apps) * 100
        docs_progress = 60 if important_files['README.md']['exists'] else 20
        
        doc.append("PROGRESO DEL PROYECTO")
        doc.append("-" * 21)
        doc.append(f"Estructura básica:       {'✅ Completada' if structure_progress > 80 else '⚠️  Parcial'} ({structure_progress:.0f}%)")
        doc.append(f"Configuración Django:    {'✅ Completada' if config_progress > 80 else '⚠️  Parcial'} ({config_progress:.0f}%)")
        doc.append(f"Apps implementadas:      {'✅ Completadas' if apps_progress > 80 else '❌ Pendiente'} ({apps_progress:.0f}%)")
        doc.append(f"Documentación:           {'✅ Completada' if docs_progress > 80 else '⚠️  Iniciada'} ({docs_progress:.0f}%)")
        doc.append("")
        
        doc.append("ESTADÍSTICAS GENERALES")
        doc.append("-" * 21)
        doc.append(f"Total directorios:       {self.total_dirs}")
        doc.append(f"Total archivos:          {self.total_files}")
        doc.append(f"Apps Django:             {len(self.apps_django)}")
        doc.append(f"Archivos Python:         {self.file_stats.get('.py', 0)}")
        doc.append(f"Paquetes instalados:     {len(self.installed_packages)}")
        doc.append("")
        
        doc.append("=" * 80)
        doc.append(f"Reporte generado automáticamente el {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        doc.append(f"Para actualizar, ejecuta: python {sys.argv[0] if sys.argv else 'documentar.py'}")
        doc.append("=" * 80)
        
        return "\n".join(doc)
    
    def save_documentation(self, output_file="ESTRUCTURA_PROYECTO.md"):
        """Guarda la documentación en un archivo"""
        documentation = self.generate_complete_documentation()
        output_path = self.project_path / output_file
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(documentation)
        
        return output_path

def main():
    """Función principal"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Documentador Completo para Proyectos Django")
    parser.add_argument("--path", "-p", default=".", 
                       help="Ruta del proyecto Django (por defecto: directorio actual)")
    parser.add_argument("--output", "-o", default="DOCUMENTACION_COMPLETA.md",
                       help="Archivo de salida (por defecto: DOCUMENTACION_COMPLETA.md)")
    
    args = parser.parse_args()
    
    documenter = CompleteDjangoDocumenter(args.path)
    
    print(f"🚀 Analizando proyecto Django en: {os.path.abspath(args.path)}")
    print("=" * 60)
    
    try:
        output_path = documenter.save_documentation(args.output)
        print("=" * 60)
        print(f"✅ Documentación completa generada en: {output_path}")
        print(f"📊 Estadísticas:")
        print(f"   - Apps Django: {len(documenter.apps_django)}")
        print(f"   - Total archivos: {documenter.total_files}")
        print(f"   - Paquetes instalados: {len(documenter.installed_packages)}")
        print("🎉 ¡Proceso completado exitosamente!")
        
    except Exception as e:
        print(f"❌ Error al generar la documentación: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()