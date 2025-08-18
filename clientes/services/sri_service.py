import requests
import json
import logging
from django.conf import settings
from django.core.cache import cache
from typing import Dict, Optional
import time

logger = logging.getLogger(__name__)

class SRIService:
    """
    Servicio para consultar información de contribuyentes en el SRI
    Integra con APIs públicas del SRI Ecuador
    """
    
    def __init__(self):
        # URLs de las APIs del SRI
        self.base_url = "https://srienlinea.sri.gob.ec"
        self.api_contribuyente = f"{self.base_url}/sri-en-linea/SriRucService"
        
        # APIs alternativas para consulta de cédulas/RUC
        self.apis_alternativas = [
            "https://api.ecuadorapi.com/persons/",  # API alternativa
            "https://cedula.top/api/",              # Otra API
        ]
        
        # Configuración de timeouts y reintentos
        self.timeout = 10
        self.max_reintentos = 3
        self.cache_duration = 3600  # 1 hora en segundos
    
    def consultar_contribuyente(self, identificacion: str) -> Optional[Dict]:
        """
        Consulta información de un contribuyente por cédula o RUC
        
        Args:
            identificacion (str): Número de cédula o RUC
            
        Returns:
            Dict: Información del contribuyente o None si no se encuentra
        """
        if not identificacion or len(identificacion.strip()) < 10:
            return None
        
        identificacion = identificacion.strip()
        
        # Verificar cache primero
        cache_key = f"sri_consulta_{identificacion}"
        resultado_cache = cache.get(cache_key)
        if resultado_cache:
            logger.info(f"Datos obtenidos del cache para: {identificacion}")
            return resultado_cache
        
        # Intentar consulta en APIs
        resultado = None
        
        # 1. Intentar con API oficial del SRI
        resultado = self._consultar_sri_oficial(identificacion)
        
        # 2. Si no funciona, intentar con APIs alternativas
        if not resultado:
            resultado = self._consultar_apis_alternativas(identificacion)
        
        # 3. Si aún no hay resultado, intentar con datos básicos
        if not resultado:
            resultado = self._generar_datos_basicos(identificacion)
        
        # Guardar en cache si se obtuvo resultado
        if resultado:
            cache.set(cache_key, resultado, self.cache_duration)
            logger.info(f"Datos consultados y guardados en cache para: {identificacion}")
        
        return resultado
    
    def _consultar_sri_oficial(self, identificacion: str) -> Optional[Dict]:
        """Consulta en la API oficial del SRI"""
        try:
            # Headers necesarios para la consulta
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            }
            
            # Datos para la consulta
            payload = {
                'ruc': identificacion,
                'naturaleza': 'TODOS'
            }
            
            response = requests.post(
                self.api_contribuyente,
                json=payload,
                headers=headers,
                timeout=self.timeout,
                verify=False  # Para evitar problemas con SSL en APIs gov
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if data and isinstance(data, dict):
                    return self._procesar_respuesta_sri(data, identificacion)
            
        except Exception as e:
            logger.warning(f"Error consultando SRI oficial para {identificacion}: {str(e)}")
        
        return None
    
    def _consultar_apis_alternativas(self, identificacion: str) -> Optional[Dict]:
        """Consulta en APIs alternativas"""
        for api_url in self.apis_alternativas:
            try:
                resultado = self._consultar_api_alternativa(api_url, identificacion)
                if resultado:
                    return resultado
                    
            except Exception as e:
                logger.warning(f"Error en API alternativa {api_url}: {str(e)}")
                continue
        
        return None
    
    def _consultar_api_alternativa(self, api_url: str, identificacion: str) -> Optional[Dict]:
        """Consulta una API alternativa específica"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; VPMotos/1.0)',
                'Accept': 'application/json'
            }
            
            # Construir URL según la API
            if "ecuadorapi.com" in api_url:
                url = f"{api_url}{identificacion}"
            elif "cedula.top" in api_url:
                url = f"{api_url}?cedula={identificacion}"
            else:
                url = f"{api_url}/{identificacion}"
            
            response = requests.get(
                url,
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Procesar según el formato de cada API
                return self._procesar_respuesta_alternativa(data, identificacion)
                
        except Exception as e:
            logger.warning(f"Error consultando API alternativa: {str(e)}")
        
        return None
    
    def _procesar_respuesta_sri(self, data: Dict, identificacion: str) -> Dict:
        """Procesa la respuesta de la API oficial del SRI"""
        try:
            # Estructura típica de respuesta del SRI
            if 'razonSocial' in data or 'nombres' in data:
                resultado = {
                    'identificacion': identificacion,
                    'razon_social': data.get('razonSocial', ''),
                    'nombres': data.get('nombres', ''),
                    'apellidos': data.get('apellidos', ''),
                    'direccion': data.get('direccion', ''),
                    'telefono': data.get('telefono', ''),
                    'email': data.get('email', ''),
                    'estado_contribuyente': data.get('estadoContribuyente', 'ACTIVO'),
                    'tipo_contribuyente': data.get('tipoContribuyente', ''),
                    'actividad_economica': data.get('actividadEconomica', ''),
                    'fuente': 'SRI_OFICIAL'
                }
                
                return self._limpiar_datos(resultado)
                
        except Exception as e:
            logger.error(f"Error procesando respuesta SRI: {str(e)}")
        
        return None
    
    def _procesar_respuesta_alternativa(self, data: Dict, identificacion: str) -> Dict:
        """Procesa respuestas de APIs alternativas"""
        try:
            resultado = {
                'identificacion': identificacion,
                'fuente': 'API_ALTERNATIVA'
            }
            
            # Mapear campos según estructura de la API
            if 'nombres' in data:
                resultado['nombres'] = data.get('nombres', '')
            elif 'first_name' in data:
                resultado['nombres'] = data.get('first_name', '')
            elif 'name' in data:
                # Si viene nombre completo, tratar de separar
                nombre_completo = data.get('name', '')
                partes = nombre_completo.split()
                if len(partes) >= 2:
                    resultado['nombres'] = ' '.join(partes[:2])
                    resultado['apellidos'] = ' '.join(partes[2:])
                else:
                    resultado['nombres'] = nombre_completo
            
            if 'apellidos' in data:
                resultado['apellidos'] = data.get('apellidos', '')
            elif 'last_name' in data:
                resultado['apellidos'] = data.get('last_name', '')
            
            # Otros campos
            resultado['direccion'] = data.get('direccion', data.get('address', ''))
            resultado['telefono'] = data.get('telefono', data.get('phone', ''))
            resultado['email'] = data.get('email', data.get('correo', ''))
            resultado['estado_contribuyente'] = data.get('estado', 'ACTIVO')
            
            return self._limpiar_datos(resultado)
            
        except Exception as e:
            logger.error(f"Error procesando respuesta alternativa: {str(e)}")
        
        return None
    
    def _generar_datos_basicos(self, identificacion: str) -> Dict:
        """Genera datos básicos cuando no se puede consultar en APIs externas"""
        try:
            # Validar si es cédula o RUC válido
            if self._es_identificacion_valida(identificacion):
                return {
                    'identificacion': identificacion,
                    'nombres': '',
                    'apellidos': '',
                    'direccion': '',
                    'telefono': '',
                    'email': '',
                    'estado_contribuyente': 'CONSULTA_NO_DISPONIBLE',
                    'tipo_contribuyente': self._determinar_tipo_identificacion(identificacion),
                    'fuente': 'DATOS_BASICOS',
                    'mensaje': 'Los servicios de consulta no están disponibles. Complete los datos manualmente.'
                }
        except Exception as e:
            logger.error(f"Error generando datos básicos: {str(e)}")
        
        return None
    
    def _limpiar_datos(self, datos: Dict) -> Dict:
        """Limpia y formatea los datos obtenidos"""
        try:
            # Limpiar espacios y caracteres especiales
            for key, value in datos.items():
                if isinstance(value, str):
                    datos[key] = value.strip().title() if key in ['nombres', 'apellidos'] else value.strip()
            
            # Validar email
            if datos.get('email') and '@' not in datos['email']:
                datos['email'] = ''
            
            # Formatear teléfono
            telefono = datos.get('telefono', '')
            if telefono:
                # Remover caracteres no numéricos
                telefono_limpio = ''.join(filter(str.isdigit, telefono))
                if len(telefono_limpio) >= 7:
                    datos['telefono'] = telefono_limpio
                else:
                    datos['telefono'] = ''
            
            return datos
            
        except Exception as e:
            logger.error(f"Error limpiando datos: {str(e)}")
            return datos
    
    def _es_identificacion_valida(self, identificacion: str) -> bool:
        """Valida si la identificación tiene formato correcto"""
        try:
            if len(identificacion) == 10:
                # Cédula ecuatoriana
                return self._validar_cedula(identificacion)
            elif len(identificacion) == 13:
                # RUC ecuatoriano
                return self._validar_ruc(identificacion)
            return False
        except:
            return False
    
    def _validar_cedula(self, cedula: str) -> bool:
        """Valida cédula ecuatoriana"""
        try:
            if not cedula.isdigit() or len(cedula) != 10:
                return False
            
            # Validar provincia
            provincia = int(cedula[:2])
            if provincia < 1 or provincia > 24:
                return False
            
            # Algoritmo de validación
            coeficientes = [2, 1, 2, 1, 2, 1, 2, 1, 2]
            suma = 0
            
            for i in range(9):
                valor = int(cedula[i]) * coeficientes[i]
                if valor >= 10:
                    valor = valor - 9
                suma += valor
            
            digito_verificador = 10 - (suma % 10)
            if digito_verificador == 10:
                digito_verificador = 0
            
            return digito_verificador == int(cedula[9])
            
        except:
            return False
    
    def _validar_ruc(self, ruc: str) -> bool:
        """Valida RUC ecuatoriano"""
        try:
            if not ruc.isdigit() or len(ruc) != 13:
                return False
            
            # Si termina en 001, es RUC de persona natural
            if ruc.endswith('001'):
                return self._validar_cedula(ruc[:10])
            
            # Validación para RUC de empresa
            tercero = int(ruc[2])
            return tercero >= 6 and tercero <= 9
            
        except:
            return False
    
    def _determinar_tipo_identificacion(self, identificacion: str) -> str:
        """Determina el tipo de identificación"""
        if len(identificacion) == 10:
            return 'CEDULA'
        elif len(identificacion) == 13:
            return 'RUC'
        else:
            return 'PASAPORTE'
    
    def verificar_disponibilidad_apis(self) -> Dict:
        """Verifica el estado de las APIs disponibles"""
        estado = {
            'sri_oficial': False,
            'apis_alternativas': [],
            'timestamp': time.time()
        }
        
        # Verificar API oficial
        try:
            response = requests.get(
                self.base_url,
                timeout=5
            )
            estado['sri_oficial'] = response.status_code == 200
        except:
            estado['sri_oficial'] = False
        
        # Verificar APIs alternativas
        for api_url in self.apis_alternativas:
            try:
                response = requests.get(api_url, timeout=5)
                estado['apis_alternativas'].append({
                    'url': api_url,
                    'disponible': response.status_code == 200
                })
            except:
                estado['apis_alternativas'].append({
                    'url': api_url,
                    'disponible': False
                })
        
        return estado
    
    @staticmethod
    def obtener_provincias_ecuador() -> Dict:
        """Retorna el mapeo de códigos de provincia en Ecuador"""
        return {
            '01': 'Azuay', '02': 'Bolívar', '03': 'Cañar', '04': 'Carchi',
            '05': 'Cotopaxi', '06': 'Chimborazo', '07': 'El Oro', '08': 'Esmeraldas',
            '09': 'Guayas', '10': 'Imbabura', '11': 'Loja', '12': 'Los Ríos',
            '13': 'Manabí', '14': 'Morona Santiago', '15': 'Napo', '16': 'Pastaza',
            '17': 'Pichincha', '18': 'Tungurahua', '19': 'Zamora Chinchipe',
            '20': 'Galápagos', '21': 'Sucumbíos', '22': 'Orellana',
            '23': 'Santo Domingo de los Tsáchilas', '24': 'Santa Elena'
        }
    
    def obtener_provincia_por_cedula(self, cedula: str) -> str:
        """Obtiene la provincia de origen según la cédula"""
        try:
            if len(cedula) >= 2:
                codigo_provincia = cedula[:2]
                provincias = self.obtener_provincias_ecuador()
                return provincias.get(codigo_provincia, 'Provincia no identificada')
        except:
            pass
        
        return 'No determinada'