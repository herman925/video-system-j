from nicegui import ui

ui.html('<span style="color:red">Hover me<q-tooltip class="text-body2" style="max-width: 200px; white-space: pre-wrap;">Long text Long text Long text Long text Long text Long text Long text Long text</q-tooltip></span>')

def custom_tt():
    with ui.html('<span style="color:blue">Hover me native</span>'):
        ui.tooltip('Long text Long text Long text Long text Long text Long text Long text').classes('text-body2').style('max-width: 200px; white-space: pre-wrap;')

custom_tt()

ui.run(port=8755, show=False)
