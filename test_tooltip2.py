from nicegui import ui

with ui.html('<span style="color:blue">Hover me native</span>'):
    ui.tooltip('Long text Long text Long text Long text Long text Long text Long text').classes('text-body2 bg-grey-9 text-white').style('max-width: 300px; white-space: pre-wrap; word-break: break-word; font-size: 13px; padding: 10px;')

ui.run(port=8755, show=False)
