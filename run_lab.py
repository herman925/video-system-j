from nicegui import Client, ui

import tracker.effects_lab  # noqa: F401


@ui.page('/')
async def lab_root(client: Client) -> None:
    ui.navigate.to('/tracker-effects-lab')


ui.run(
    title='Tracker Effects Lab',
    port=8766,
    favicon='💎',
    dark=True,
    reload=False,
    storage_secret='jav-dl-effects-lab-2026',
)