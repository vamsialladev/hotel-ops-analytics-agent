"""Owner only: the shared ops view (hotel-ai-platform) with its own sign-in (ADMIN_PASSWORD, 5 tries then a 15-minute
lock). Registered by app.py only when ADMIN_PASSWORD is set, and hidden from the menu until signed in."""

from hotelplatform import admin_ui

from src import ops

admin_ui.render(
    ops.store(),
    app_title="Hotel Ops Analytics",
    version=ops.running_version(),
    dependencies=ops.dependencies,
    **ops.caps(),
)
