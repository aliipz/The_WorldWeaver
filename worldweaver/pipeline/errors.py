"""
Excepciones del pipeline WorldWeaver.
"""


class AgentError(ValueError):
    """
    Error recuperable de un agente LLM (JSON inválido o schema Pydantic fallido).
    Lleva el historial de mensajes incluyendo la respuesta errónea del LLM,
    para que el grafo pueda añadir feedback y reintentar con contexto completo.
    """
    def __init__(self, message: str, messages: list):
        super().__init__(message)
        self.messages = messages


class SinNarrativa(RuntimeError):
    """
    El texto de entrada no contiene una historia que extraer (0 escenas).
    No es recuperable con reintentos —el texto es el problema—, así que el grafo
    la deja propagar para fallar rápido con un mensaje amigable hacia el usuario.
    """
    pass


class ServicioModelosCaido(RuntimeError):
    """
    El servicio externo de búsqueda de modelos 3D (poly.pizza) está caído: su API
    no responde (timeouts repetidos confirmados por un sondeo de diagnóstico con
    keywords garantizadas). NO es un problema de WorldWeaver ni del texto, y reintentar
    la generación ahora no ayuda. El grafo la deja propagar para abortar; el server
    borra el mundo a medio construir y la landing muestra una pantalla de error
    dedicada ("servicio externo caído, reinténtalo en un rato").
    """
    pass
