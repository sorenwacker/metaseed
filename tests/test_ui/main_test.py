"""Main entry point for NiceGUI testing.

This file is used by NiceGUI's testing framework to set up the UI.
"""

from nicegui import ui

from miappe_api.ui.app import MIAPPEApp

# Create and set up the app
app = MIAPPEApp()
app._setup_ui()

if __name__ == "__main__":
    ui.run()
