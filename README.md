# JamQ — cola musical compartida y replicada

Proyecto final de CMP5001 Aplicaciones Distribuidas · Julián León

JamQ es la cola de música de una fiesta: varias personas, cada una desde su
navegador, agregan canciones a una misma cola, dan like y saltan la canción
actual. Un navegador hace de parlante. La app corre en 3 réplicas que solo se
comunican por mensajes.

Necesitas Python 3.11 o más nuevo. No hay paquetes que instalar. Con Docker
(Docker Desktop, Colima u OrbStack) quita `--local` de los comandos.

## Tabla de operaciones

| Operación | Garantía | Mecanismo | Si cae el líder o una réplica | Si hay partición | Costo |
|---|---|---|---|---|---|
| `agregar(cancion)` | linearizable | log de Raft + dedup por `request_id` | espera un nuevo líder (~2–3 s) | solo el lado con mayoría acepta | una ronda a la mayoría + fsync |
| `saltar(pos)` | linearizable con condición (CAS) | log de Raft: solo avanza si la posición actual sigue siendo `pos` | igual que agregar | igual que agregar | igual que agregar |
| `ver_cola` | linearizable | la lectura pasa por el log del líder | espera un nuevo líder | el lado con menos réplicas no responde | igual que agregar |
| `ver_cola_rapida` | eventual | estado aplicado de la réplica local | sigue funcionando | los dos lados responden; el de menos réplicas, atrasado | local, sin mensajes |
| `like(cancion, usuario)` | eventual (SEC) | G-set + gossip cada 0.5 s | sigue funcionando | los dos lados aceptan; se unen al sanar | local; gossip periódico |
| `likes(cancion)` | eventual | G-set local | sigue funcionando | cada lado ve sus likes | local, sin mensajes |

## Archivos

| Archivo | Qué hace |
|---|---|
| `app.py` | la réplica: Raft (elección, log, commit, reparación) y likes con gossip |
| `cola.py` | la máquina de estados de la cola (agregar, saltar con CAS, dedup) |
| `raft_rules.py` | las reglas de Raft como funciones puras (voto, log al día, commit, append) |
| `spec.py` | qué hace cada operación con una sola copia, y su garantía (lo usa check.py) |
| `scenarios/` | los escenarios de falla (`comun.py` tiene las ayudas compartidas) |
| `correr_escenarios.sh` | corre todos los escenarios y guarda las salidas de check.py en `salidas/` |
| `salidas/` | `<escenario>.txt` = salida de check.py; `<escenario>.escenario.txt` = lo que imprimió el escenario |
| `historiales/` | los historiales y `roles.log` de cada corrida (los guarda `cluster.py down`) |
| `gateway.py`, `web/` | el front de la demo |
| `tests/` | pruebas unitarias de cola, reglas de Raft, spec y gateway |
| `node.py`, `cluster.py`, `client.py`, `chaos.py`, `check.py` | del starter, sin cambios |

## Correr

```sh
python3 -m unittest discover -s tests -v   # pruebas unitarias
bash correr_escenarios.sh                  # los 5 escenarios + check.py (agrega --docker para Docker)
```

Un escenario a mano:

```sh
python3 cluster.py up --local
python3 scenarios/lider.py
python3 check.py run/lider.jsonl
python3 cluster.py down        # guarda el historial en historiales/FECHA-HORA/
```

| Escenario | Qué pasa | Resultado esperado |
|---|---|---|
| `normal` | todas las operaciones; dos clientes saltan a la vez | sin violaciones; solo un salto |
| `replica` | cae un follower, se agregan 5 canciones, vuelve | sin violaciones; la réplica se pone al día |
| `lider` | cae el líder mientras 3 clientes agregan | sin violaciones; nuevo líder con periodo mayor; nada se pierde |
| `particion` | el líder queda solo contra las otras dos | sin violaciones; el lado solo no puede agregar; los likes convergen |
| `falla` | una réplica aislada recibe un like y vuelve sin disco (`--empty`) | **VIOLACIÓN esperada**: fuera del modelo, el like se pierde |

## Demo con el front

```sh
bash demo.sh        # = python3 cluster.py up --local + python3 gateway.py
```

Si la página dice "las réplicas no están corriendo", falta `python3 cluster.py up --local`.

- `http://localhost:8080/?parlante=1&u=dj`: el parlante. Presiona "Empezar a
  sonar"; cuando termina una canción, pide saltar.
- `http://localhost:8080/?u=ana`: un invitado (cualquier nombre en `u`).
- La barra de abajo muestra cada réplica, su rol y su periodo. Prueba con
  `python3 chaos.py kill leader` o `python3 chaos.py partition n1 / n2 n3`.

Todo lo que se hace en la página queda en `run/web.jsonl`:
`python3 check.py run/web.jsonl`.

La música no viene en el zip: pon 7 MP3 en `web/musica/` llamados `c1.mp3` …
`c7.mp3` (ver `web/musica/LEEME.md`). Sin MP3 todo funciona igual, solo que
no suena.

Las portadas tampoco vienen (son de terceros). Para bajarlas (necesita internet):
`python3 web/bajar_portadas.py`. Sin portadas, cada canción se ve con su color
e iniciales.
