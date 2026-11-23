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
