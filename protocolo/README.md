# Simulación de potencia del protocolo

`potencia.py` estima por simulación de Monte Carlo la potencia del modelo mixto principal del estudio propuesto en el artículo (resultado P1):

    y ~ modo + periodo + secuencia + pretest + (1 | estudiante)

Supuestos: 36 estudiantes reclutados (18 por secuencia), abandono aleatorio del 15 % antes del segundo periodo, efecto de periodo de 0,30 desviaciones estándar y pretest que explica la cuarta parte de la varianza entre estudiantes. Se varían el efecto del modo (0,3 a 0,6 DE), la correlación intraestudiante (0,3, 0,5 y 0,7) y un arrastre de 0,15 DE. Para cada escenario informa la potencia del modelo mixto, el sesgo del estimador y la potencia del análisis del periodo 1.

Se ejecutó con Python 3.12 y las versiones de `requirements-estadistica.txt`:

    python -m pip install -r requirements-estadistica.txt
    python potencia.py 1000        # 1000 réplicas por escenario; escribe potencia_resultados.csv

Los resultados del artículo están en `potencia_resultados.csv`.
