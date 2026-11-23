"""Select ready work in plan order without launching a specialist."""


def ready_items(items, states, active_roles, capacity, *, stopped=False):
    if stopped or capacity <= 0:
        return []
    occupied = set(active_roles)
    selected = []
    for item in sorted(items, key=lambda item: item.get("priorita", 10)):
        if item["id"] in states or item["role"] in occupied:
            continue
        if any(states.get(key) != "SPLNĚNO" for key in item.get("zavisi_na", [])):
            continue
        selected.append(item)
        occupied.add(item["role"])
        if len(selected) == capacity:
            break
    return selected


def verified_dependencies(references, reports):
    """Resolve a verdict by (approved list ID, item ID), independent of list state."""
    return {
        dependency: reports.get(tuple(reference), {}).get("overeni", {}).get("verdikt")
        for dependency, reference in references.items()
    }


def ready_across_inputs(inputs, states, active_items, active_roles, capacity):
    """Choose from fresh approved inputs supplied in durable arrival order.

    Each input supplies its stable ID and its items in arrival order. The caller
    claims each selected (input ID, item ID) and reads again on the next handoff.
    """
    items = []
    originals = {}
    for input_id, entries in inputs:
        for entry in entries:
            identity = (input_id, entry["id"])
            originals[identity] = entry
            dependencies = [(input_id, key) for key in entry.get("zavisi_na", [])]
            dependencies.extend(entry.get("zavisi_na_starsich_vstupech", []))
            items.append({**entry, "id": identity, "zavisi_na": dependencies})
    current = {**states, **dict.fromkeys(active_items, "běží")}
    selected = ready_items(items, current, active_roles, capacity)
    return [(entry["id"][0], originals[entry["id"]]) for entry in selected]
