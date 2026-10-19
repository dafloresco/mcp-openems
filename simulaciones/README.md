# Simulaciones de la tabla 2

Cada carpeta contiene un `simulate.py` autocontenido. Se ejecuta con `python simulate.py` y escribe sus resultados en `results/`. Los valores publicados están en [`resultados_referencia.csv`](resultados_referencia.csv).

| Carpeta | Fila de la tabla 2 | Configuración | Tiempo aprox. |
|---|---|---|---|
| `dipolo_915` | Dipolo de media onda, 915 MHz, L = 150,7 mm | PML, malla λ/80 | 1,5 min |
| `monopolo_450` | Monopolo λ/4 sobre tierra infinita, 450 MHz | PML + PEC en zmin, λ/80 | 3 min |
| `parche_fr4_2450_libro` | Parche FR-4 con dimensiones del modelo de línea de transmisión | MUR, λ/20 | 2 min |
| `parche_fr4_2450_ajustado` | Parche FR-4 ajustado (L = 28,0 mm, sonda a 6,8 mm) | PML, λ/20 | 2 a 5 min |
| `parche_ro4003c_5600`, `_5800`, `_6000` | Parche en RO4003C a 5,6, 5,8 y 6,0 GHz | PML, λ/20 | 2 a 5 min c/u |

Los tiempos son de una computadora portátil de uso general. Para reproducirlo todo:

```bat
python reproducir_tabla2.py
```

Para reproducir solo algunos casos, añade sus nombres. Para comparar resultados ya calculados, usa `--solo-comparar`.

## Tolerancias

El criterio de parada de openEMS se evalúa a intervalos de tiempo, así que dos corridas idénticas pueden detenerse en pasos distintos según la carga del equipo. En el parche observamos diferencias de 0,08 % en frecuencia y de varios dB en un mínimo de S11 cercano a −30 dB. Por eso el script acepta como coincidencia:

- ±0,2 % en la frecuencia de resonancia;
- ±3 dB en el S11 mínimo;
- ±0,1 dBi en la directividad.

En el monopolo no se compara la directividad. openEMS calcula el campo lejano del dipolo equivalente (antena más imagen), unos 2,2 dBi, mientras que el monopolo real sobre tierra infinita tiene unos 5,2 dBi.

## Tabla 3 (sensibilidad a la malla y a los contornos)

Se reproduce con el script del dipolo, cambiando:

- la línea `mesh_res = C0 / f_max / unit / 80.0`, con divisores 20, 40 u 80;
- la lista `BC`, con `['MUR'] * 6` o `['PML_8'] * 6`;
- la longitud, con `--set L=155` o `--set L=149.4`.

Por ejemplo: `python simulate.py --set L=155 --tag L155`.
