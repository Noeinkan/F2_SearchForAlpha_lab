"""Drive one registered Dash callback through the real HTTP endpoint.

Going through ``/_dash-update-component`` rather than calling the function
exercises what a unit call cannot: ``on_error``, ``set_props`` side updates,
``no_update`` handling and the output-key format Dash 4 uses for
``allow_duplicate`` outputs.
"""

from __future__ import annotations

import json


def callback_key(app, output_fragment: str, input_name: str | None = None) -> str:
    """The callback_map key whose outputs mention ``output_fragment``."""
    for key, entry in app.callback_map.items():
        if output_fragment not in key:
            continue
        if input_name is None:
            return key
        names = [f"{d['id']}.{d['property']}" for d in entry['inputs'] if isinstance(d['id'], str)]
        if input_name in names:
            return key
    raise KeyError(output_fragment)


def _outputs_of(key: str):
    if not key.startswith('..'):
        dep_id, prop = key.rsplit('.', 1)
        return {'id': dep_id, 'property': prop}
    parts = key[2:-2].split('...')
    return [dict(zip(('id', 'property'), part.rsplit('.', 1))) for part in parts]


def _deps(deps, values):
    out = []
    for dep in deps:
        if isinstance(dep['id'], str):
            name = f"{dep['id']}.{dep['property']}"
            out.append({'id': dep['id'], 'property': dep['property'], 'value': values.get(name)})
        else:
            out.append([])  # a wildcard dependency that currently matches nothing
    return out


def post_callback(app, key: str, changed: str, values: dict):
    """POST one callback. Returns ``(status_code, parsed_json_or_None)``."""
    entry = app.callback_map[key]
    body = {
        'output': key,
        'outputs': _outputs_of(key),
        'inputs': _deps(entry['inputs'], values),
        'state': _deps(entry.get('state', []), values),
        'changedPropIds': [changed],
    }
    response = app.server.test_client().post('/_dash-update-component', json=body)
    text = response.get_data(as_text=True)
    return response.status_code, (json.loads(text) if text else None)
