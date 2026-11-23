"""Select ready work in plan order without launching a specialist."""


def ready_items(items, states, active_roles, capacity, *, stopped=False):
    if stopped or capacity <= 0:
        return []
    occupied = set(active_roles)
    selected = []
    for item in items:
        if item["id"] in states or item["role"] in occupied:
            continue
        if any(states.get(key) != "SPLNĚNO" for key in item.get("zavisi_na", [])):
            continue
        selected.append(item)
        occupied.add(item["role"])
        if len(selected) == capacity:
            break
    return selected
