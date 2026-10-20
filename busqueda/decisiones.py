# -*- coding: utf-8 -*-
"""Decisiones del cribado por resumen (178 candidatos) y tabla completa del cribado.

    python decisiones.py cribado.csv unicos.json
"""
import csv
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

# Categorías de inclusión
#  A  IA (agente o tutor) que usa o actúa sobre software de diseño o simulación de ingeniería en la enseñanza
#  B  IA generativa o tutor inteligente en cursos universitarios de diseño, simulación o laboratorio de ingeniería
#  C  descarga cognitiva, agencia, autorregulación o andamiaje con IA generativa en educación superior STEM/ingeniería
#  D  arquitecturas que restringen o regulan el comportamiento de la IA con fines pedagógicos (cualquier disciplina)
#  E  síntesis sobre agentes de IA en educación
# Motivos de exclusión
#  R1 fuera de educación superior en ingeniería/STEM (escolar, salud, humanidades, idiomas, negocios)
#  R2 sin propósito educativo (herramienta profesional o industrial)
#  R3 la IA es contenido del curso o herramienta administrativa o docente, no apoyo al aprendizaje
#  R4 sin marco ni datos evaluables, o sin resumen disponible para evaluarlo
#  R5 tutoría o preguntas y respuestas genéricas, sin relación con diseño, simulación ni reparto de funciones
#  R6 versión previa o duplicada de un trabajo incluido
INC = {
    95: ("A", "Agente con herramientas deterministas para tutoría en análisis de circuitos; evaluación ciega con 135 estudiantes"),
    978: ("A", "AITEE: tutor socrático que delega el cálculo en SPICE y separa conversación y cómputo"),
    808: ("A", "Agentes de IA con herramientas de cálculo y simulación para dinámica estructural"),
    795: ("A", "Tutoría con verificación automática respaldada por simulación en electrónica de potencia"),
    1006: ("A", "SaxoFlow: plataforma agéntica con herramientas EDA para enseñanza e investigación en diseño digital"),
    1214: ("A", "Xmobot: IA agéntica para construir y entrenar robots en cursos de robótica"),
    980: ("B", "ChatGPT como copiloto en un curso de posgrado de diseño de antenas; decálogo de buenas prácticas"),
    1204: ("B", "IA generativa en un curso de modelado y simulación de sistemas"),
    1008: ("B", "Tutor conversacional integrado con simulaciones en ingeniería civil"),
    405: ("B", "Tutor inteligente para conceptos de electromagnetismo"),
    462: ("B", "Tutores de IA para cursos de diseño de circuitos de microondas"),
    268: ("B", "Modelos de lenguaje en cursos de modelado y simulación con MATLAB"),
    780: ("B", "IA generativa en educación en modelado y simulación"),
    1184: ("B", "Laboratorios virtuales con IA y retroalimentación; evaluación cuasiexperimental"),
    943: ("B", "Simulación en tiempo real dSPACE con asistencia de IA en ingeniería eléctrica"),
    240: ("B", "Laboratorio virtual asistido por IA para optoelectrónica"),
    885: ("B", "Tutor inteligente abierto para ejercicios en MATLAB/Simulink"),
    955: ("B", "Tutor de IA generativa integrado con Mathematica para ecuaciones diferenciales"),
    966: ("B", "Tutoría socrática con recuperación de información en juegos de simulación de ingeniería"),
    41: ("B", "Plataforma de simulación virtual dirigida por un modelo de lenguaje en construcción"),
    737: ("B", "IA generativa como andamiaje en robótica de primer año con simulación"),
    174: ("B", "NanoSatPlay: plataforma con IA para diseño y simulación de CubeSat"),
    557: ("B", "Agente docente de IA en un curso de robótica"),
    1208: ("B", "Apoyo de agentes de IA en un curso de ingeniería electrónica de primer año"),
    1200: ("B", "IA generativa en aprendizaje basado en proyectos de sistemas de potencia"),
    682: ("B", "Modelos de lenguaje multiagente en proyectos de diseño de último año"),
    1203: ("B", "Andamiaje en un curso de análisis por elementos finitos con cuadernos computacionales e IA generativa"),
    38: ("C", "Marco de IA generativa para autorregulación en electrónica digital"),
    39: ("C", "Marco centrado en las personas para desarrollar autorregulación con IA generativa"),
    315: ("C", "Marco de aumento y erosión: operaciones periféricas y constitutivas"),
    615: ("C", "Ensayo aleatorizado: entrenamiento estructurado en IA generativa y resolución de problemas STEM"),
    930: ("C", "Tutor de diseño con compuertas de progreso que evita la descarga y evalúa transferencia (ensayo aleatorizado)"),
    695: ("C", "Quién lidera la resolución de problemas entre estudiante e IA generativa"),
    331: ("C", "Marco de sinergia humano-IA según autonomía y colaboración (revisión de 169 estudios)"),
    1019: ("C", "Autorregulación y andamiaje en una herramienta de ayuda de programación con modelo de lenguaje"),
    1177: ("C", "IA generativa con andamiaje cognitivo en ingeniería (cuasiexperimento)"),
    1182: ("C", "Agencia del estudiante en el uso de IA generativa en un curso universitario"),
    517: ("C", "Modelo de diseño de cursos para un uso responsable de IA generativa en ingeniería de software"),
    640: ("C", "Descarga cognitiva bajo andamiaje estructurado de IA generativa en proyectos"),
    509: ("C", "Autorregulación y búsqueda de ayuda mediada por modelos de lenguaje en estudiantes STEM"),
    304: ("C", "Apoyo metacognitivo adaptativo para formular solicitudes a modelos de lenguaje"),
    1011: ("C", "Andamiaje conversacional de la autorregulación en la interacción con modelos de lenguaje"),
    860: ("C", "Estrategias para reducir la dependencia de la IA generativa en ingeniería de computadoras"),
    612: ("C", "Módulo para el pensamiento crítico al idear con IA generativa en ingeniería biomédica"),
    446: ("C", "IA generativa como andamiaje del pensamiento crítico en ingeniería mecánica"),
    565: ("C", "Compromiso evaluativo en la colaboración humano-IA en resolución de problemas de ingeniería"),
    617: ("C", "De la generación de código a la internalización de la lógica (cuasiexperimento)"),
    633: ("C", "Tutor de IA que apoya la autorregulación en programación"),
    255: ("C", "Agentes pedagógicos y carga intrínseca, extrínseca y germana (experimento)"),
    1079: ("C", "La enseñanza de la computación en la era de los agentes de programación"),
    796: ("C", "Modelos de lenguaje en educación en ingeniería eléctrica y de computadoras"),
    657: ("C", "Revisión temática de IA generativa en educación en ingeniería"),
    366: ("C", "Revisión estructurada de chatbots e IA generativa en educación en ingeniería (2020-2024)"),
    115: ("C", "Revisión de alcance de IA generativa en educación química y en ingeniería química"),
    1132: ("D", "Middleware que transforma solicitudes de respuesta directa en indicaciones de exploración guiada"),
    205: ("D", "Funciones de IA con costo y respuesta restringida o libre en un tutor durante un examen"),
    399: ("D", "Sistema regulado de generación de pistas con IA en el aula"),
    936: ("D", "Agente que sondea en lugar de tutorizar, con reglas de diseño explícitas"),
    716: ("D", "Servidor MCP que impone una teoría instruccional mediante esquemas y validadores"),
    17: ("E", "Revisión de agentes basados en modelos de lenguaje para la educación"),
    79: ("E", "Revisión de plataformas adaptativas con IA agéntica"),
    154: ("E", "Flujo de trabajo agéntico para la educación con invocación de herramientas"),
}
# Exclusiones del cribado por resumen
EXC = {
    "R1": [7, 692, 728],
    "R2": [47, 63, 387, 440, 701, 1064, 965],
    "R3": [80, 156, 164, 172, 182, 306, 311, 395, 453, 641, 813, 817, 819, 1083],
    "R4": [140, 207, 234, 244, 284, 286, 287, 310, 338, 361, 386, 393, 437, 460, 473, 600, 601, 602, 618, 632, 644,
           660, 688, 696, 733, 803, 810, 878, 929, 941, 942, 1105, 1121, 1125],
    "R5": [50, 51, 92, 104, 165, 166, 185, 187, 229, 231, 232, 233, 237, 239, 243, 259, 260, 265, 266, 281, 298, 313,
           319, 369, 394, 416, 450, 461, 464, 466, 467, 478, 511, 520, 521, 522, 543, 579, 583, 677, 709, 731, 738,
           739, 801, 816, 827, 882, 916, 990, 1004, 1027, 1028, 1171, 1193],
    "R6": [224, 193, 269],
}
MOT = {"R1": "Fuera de educación superior en ingeniería/STEM", "R2": "Sin propósito educativo",
       "R3": "IA como contenido o herramienta docente o administrativa", "R4": "Sin marco ni datos evaluables o sin resumen",
       "R5": "Tutoría genérica sin relación con diseño, simulación ni reparto de funciones",
       "R6": "Versión previa o duplicada de un trabajo incluido"}

cand = [int(x) for x in open("candidatos.txt").read().split(",")]
exc = {n: r for r, ns in EXC.items() for n in ns if n}
for n in cand:
    if n not in INC and n not in exc:
        print("SIN DECISIÓN", n)
for n in list(INC) + list(exc):
    if n not in cand:
        print("NO ES CANDIDATO", n)
dup = set(INC) & set(exc)
print("en ambos:", dup)

U = json.load(open(sys.argv[2] if len(sys.argv) > 2 else "unicos.json", encoding="utf-8"))
rows = []
for u in U:
    n = u["n"]
    if n in INC:
        etapa, dec, cod, txt = "resumen", "incluido", INC[n][0], INC[n][1]
    elif n in exc:
        etapa, dec, cod, txt = "resumen", "excluido", exc[n], MOT[exc[n]]
    else:
        etapa, dec, cod, txt = "título", "excluido", "T", "No cumple los criterios de elegibilidad por el título"
    rows.append(dict(n=n, anio=u["anio"], titulo=u["titulo"], fuente=u["fuente"], doi=u["doi"], bases="; ".join(u["bases"]),
                     consultas="; ".join(u["consultas"]), etapa_decision=etapa, decision=dec, codigo=cod, motivo_o_aporte=txt))
with open(sys.argv[1], "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
from collections import Counter
print("candidatos", len(cand), "incluidos", len(INC), Counter(v[0] for v in INC.values()))
print("excluidos por resumen", Counter(exc.values()))
print("excluidos por título", sum(1 for r in rows if r["codigo"] == "T"))
