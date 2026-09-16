---
description: Etapa 4 SDD — implementa una tarea con el ciclo implementador → revisor → validador (tope 3 vueltas)
argument-hint: <carpeta-feature> <numero-o-texto-de-la-tarea>
---

Tarea a implementar: $ARGUMENTS

Orquesta este ciclo, de a una tarea y **de a un subagente por vez** (cada paso espera al anterior;
nunca en paralelo ni en segundo plano). Si el pedido trae varias tareas, hace solo la primera y
pregunta antes de seguir. Entre pasos pasa solo el informe breve del subagente anterior, no
transcripciones ni archivos enteros.

1. Invoca el subagente `implementador` con la carpeta y la tarea.
2. Con lo que devuelva, invoca el subagente `revisor` sobre el cambio.
3. Si el revisor dice **CAMBIOS REQUERIDOS**, vuelve al paso 1 pasandole al implementador el
   informe completo del revisor.
4. Con el revisor en **APROBADO**, invoca el subagente `validador-spec` sobre la feature.
5. Si el validador reporta NO CUMPLE o SIN TEST de criterios que esta tarea debia cubrir, vuelve
   al paso 1 con ese informe.

**Tope: 3 vueltas** por tarea (cada regreso al paso 1 cuenta una). Al llegar al tope, para y
mostra a la persona el ultimo informe de revisor y validador, sin intentar una cuarta.

Nunca se cierra una vuelta bajando un criterio, borrando o salteando un test o relajando una
validacion: si el revisor lo detecta, es bloqueante.

Al final mostra: vueltas usadas, archivos tocados, gates con conteos reales y estado de la tarea
en `tasks.md`. No hagas `git push`.
