# Simulaciones de la prueba técnica del artículo

Cada carpeta contiene un `simulate.py` autocontenido. Se ejecuta con `python simulate.py` y escribe sus resultados en `results/`. El entorno usado en el artículo está en [`../ENTORNO.md`](../ENTORNO.md).

## Casos de referencia (tabla 6)

Los valores publicados están en [`resultados_referencia.csv`](resultados_referencia.csv). `reproducir_tabla2.py` conserva el nombre de la primera versión del artículo, en la que estos casos formaban la tabla 2.

| Carpeta | Caso | Configuración | Tiempo aprox. |
|---|---|---|---|
| `dipolo_915` | Dipolo de media onda de hilo delgado, 915 MHz, L = 150,7 mm | PML, malla λ/80 | 1,5 min |
| `monopolo_450` | Monopolo λ/4 sobre tierra infinita, 450 MHz | PML + PEC en zmin, λ/80 | 3 min |
| `parche_fr4_2450_libro` | Parche FR-4 con dimensiones del modelo de línea de transmisión | MUR, λ/20 | 2 min |
| `parche_fr4_2450_ajustado` | Parche FR-4 ajustado (L = 28,0 mm, sonda a 6,8 mm) | PML, λ/20 | 2 min |
| `parche_ro4003c_5600`, `_5800`, `_6000` | Parche en RO4003C a 5,6, 5,8 y 6,0 GHz, L ≈ 76,9/f(GHz) mm | PML, λ/20 | 2 a 5 min c/u |

```bat
python reproducir_tabla2.py                  &REM todos los casos
python reproducir_tabla2.py dipolo_915       &REM solo algunos
python reproducir_tabla2.py --solo-comparar  &REM compara resultados ya calculados
```

## Estudios de control (tablas 7 y 8)

`estudios_control.py` copia el script de referencia, cambia una sola cosa y registra frecuencia de resonancia, S11, impedancia, ancho de banda, directividad, eficiencia, celdas, pasos de tiempo, criterio de parada, duración y memoria máxima en [`estudios_control.csv`](estudios_control.csv). Las corridas se guardan en `_estudios/`, que no se versiona.

| Grupo | Qué cambia | Casos |
|---|---|---|
| `convergencia` | Malla λ/20, 40, 80, 120 y 160 (dipolo de hilo) y λ/20, 30 y 40 (parche ajustado) | 8 |
| `hilo_finito` | Dipolo con conductor de sección cuadrada de 1 × 1 mm, malla λ/20, 40 y 80 | 3 |
| `repeticion` | Tres corridas idénticas del dipolo (λ/80) y del parche ajustado (λ/20) | 6 |
| `contornos` | MUR frente a PML con la misma geometría (parche del libro y parche ajustado) | 4 |
| `perdidas` | Parche ajustado con tan δ = 0,02 y con tan δ = 0,0027, resto idéntico | 2 |

```bat
python estudios_control.py                 &REM todos (unos 40 min en el equipo de ENTORNO.md)
python estudios_control.py contornos       &REM solo un grupo
```

## Contraste con CST Studio Suite

El parche ajustado se simuló también en CST Studio Suite 2025 (solver temporal, malla hexaédrica, contornos abiertos con 30 mm de aire, puerto discreto de 50 Ω entre plano de tierra y parche, FR-4 con εr = 4,3 y tan δ = 0,02 a 2,45 GHz, conductores PEC de 35 µm). El modelo no se distribuye porque CST requiere una licencia comercial; sus resultados están en [`contraste_cst.csv`](contraste_cst.csv) y la curva de S11 en `contraste_cst_s11.txt`. La directividad de CST no se evaluó porque falló la exportación del campo lejano.

## Resolución y tolerancias

- La frecuencia de resonancia se toma del mínimo de S11 sobre 1001 puntos de frecuencia. La resolución es de 0,73 MHz en el dipolo y de 1,96 MHz en el parche, es decir, 0,08 % en ambos casos.
- El criterio de parada de openEMS (energía −40 dB) se evalúa a intervalos, así que dos corridas idénticas pueden detenerse en pasos distintos. Eso no cambia la frecuencia, pero sí el valor de un mínimo de S11 muy profundo, en hasta unos 2 dB.
- Por eso `reproducir_tabla2.py` acepta como coincidencia ±0,2 % en la frecuencia, ±3 dB en el S11 mínimo y ±0,1 dBi en la directividad.
- En el monopolo no se compara la directividad: openEMS calcula el campo lejano del dipolo equivalente (antena más imagen), unos 2,2 dBi, mientras que el monopolo real sobre tierra infinita tiene unos 5,2 dBi.
