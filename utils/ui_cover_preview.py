from nicegui import ui


def open_image_preview(src: str) -> None:
    """Open a full-screen image preview dialog that closes on any click or escape."""
    with ui.dialog() as dialog:
        dialog.props("maximized").classes("cover-preview-dialog")
        with ui.element("div").classes("cover-preview-stage").on("click", dialog.close):
            ui.image(src).classes("cover-preview-img").props("loading=eager").on(
                "click", dialog.close
            )
    dialog.open()