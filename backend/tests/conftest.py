import os

# vyom.api.app builds its module-level app on import, and with no mode set that is production,
# which refuses the development identity. Tests run in development mode.
os.environ.setdefault("VYOM_MODE", "development")
