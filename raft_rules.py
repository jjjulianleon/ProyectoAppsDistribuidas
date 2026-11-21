"""Reglas de Raft (M20, Laboratorio 5) como funciones puras.

Son puras (no envían mensajes ni tocan disco) para poder probarlas solas.
app.py las llama.

Convención: los índices son LONGITUDES. commit = k significa "las primeras k
entradas del log tienen commit"; match[n] = k significa "la réplica n tiene
las primeras k entradas iguales a las del líder".
"""


def log_al_dia(mi_ultimo_term, mi_len, su_ultimo_term, su_len):
    """¿El log del candidato está al menos tan actualizado como el mío?

    Primero se compara el periodo de la última entrada y después la longitud.
    Esta regla garantiza que un líder nuevo ya tiene todas las entradas con
    commit: el commit exige una mayoría, la elección también, y dos mayorías
    siempre comparten una réplica.
    """
    if su_ultimo_term != mi_ultimo_term:
        return su_ultimo_term > mi_ultimo_term
    return su_len >= mi_len


def concede_voto(current_term, voted_for, cand, term, cand_al_dia):
    """Un voto por periodo. Quien llama ya subió current_term si term era mayor.

    El voto se guarda en disco antes de responder: si la réplica se cae y
    vuelve, no puede votar por otro en el mismo periodo. Así nunca hay dos
    líderes en un periodo.
    """
    return term == current_term and voted_for in (None, cand) and cand_al_dia


def nuevo_commit(current_term, terms, match, commit, n):
    """Mayor k > commit que tiene una mayoría y cuya entrada k es del periodo actual.

    terms: periodo de cada entrada del log del líder. match: lo que confirmó
    cada follower. El líder cuenta con len(terms).

    Por qué solo entradas del periodo actual (Raft §5.4.2): una entrada vieja
    puede estar en una mayoría y aun así ser borrada por un líder posterior.
    Al hacer commit de una entrada propia, las anteriores quedan con commit
    también.
    """
    mayoria = n // 2 + 1
    copias = sorted([len(terms)] + list(match.values()), reverse=True)
    k = copias[mayoria - 1]  # la mayoría tiene al menos k entradas
    while k > commit:
        if terms[k - 1] == current_term:
            return k
        k -= 1
    return commit


def aceptar_append(log, prev_len, prev_term, entradas):
    """AppendEntries en el follower. Devuelve (ok, log_nuevo).

    Falla si el follower no tiene la entrada anterior (prev_len, prev_term):
    entonces el líder retrocede y reenvía desde antes (reparación). Si
    coincide, borra lo que contradice al líder y agrega lo nuevo. No recorta
    si no hay conflicto: un mensaje viejo que llega tarde no puede borrar
    entradas que ya llegaron.
    """
    if len(log) < prev_len:
        return False, log
    if prev_len > 0 and log[prev_len - 1]["term"] != prev_term:
        return False, log
    nuevo = list(log)
    for i, e in enumerate(entradas):
        j = prev_len + i
        if j < len(nuevo):
            if nuevo[j]["term"] == e["term"]:
                continue
            del nuevo[j:]
        nuevo.append(e)
    return True, nuevo
