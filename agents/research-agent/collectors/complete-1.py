from textual.app import App, ComposeResult
from textual.widgets import Button, Static, Header, Footer

import os 
import subprocess

class VNCApp(App):

	CSS = """
	Screen { 
		align: center middle;
	}

	Button {
		margin: 1;
		width: 40;
	}

	#status {
		margin-top: 1;
	}"""

	def compose(self) -> ComposeResult:
		yield Header()
		yield Static("VNC Control Panel (:1)", id="title")
		yield Button("▶ Start VNC", id="start")
		yield Button("⛔ Stop VNC", id="stop")
		yield Button("ℹ Status", id="status_btn")
		yield Static("", id="status")
		yield Footer()

	def on_button_pressed(self, event: Button.Pressed):
		status = self.query_one(#status", Static)

		if event


os.environ["DISPLAY"] = ":1"

subprocess.run(["vncserver", ":1"])

