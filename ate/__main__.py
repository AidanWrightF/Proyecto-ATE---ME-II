import logging

from ate.interfaz import iniciar

# Los mensajes y errores van a la consola; el operario solo ve la ventana.
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
iniciar()
