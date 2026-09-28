"""Textual terminal wizard; shares the catalog and writer with text mode."""
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static

from scripts.setup import PRIMARY_PAGES, _help_for, fields_for, _post_save_auth, preflight
from scripts.setup_catalog import BY_KEY, effective, normalize_value, validate, validate_value
from scripts.setup_env import EnvFile

PAGES = (*PRIMARY_PAGES, "Advanced", "Review")


class SetupApp(App[bool]):
    TITLE = "Coderbot · Setup"
    SUB_TITLE = "Jira / GitHub / GDoc  ×  Slack / Email"
    CSS = """
    Screen { background: #102b30; color: #edf8f3; }
    Header, Footer { background: #173b3d; }
    #title { height: 3; padding: 1 2; background: #1c4847; color: #c4f5df; text-style: bold; }
    #description { height: auto; min-height: 3; padding: 1 2; color: #a9cccb; }
    #search { margin: 0 2; display: none; }
    #fields { height: 1fr; margin: 0 2; padding: 0 1; scrollbar-color: #1dad97; }
    #fields Label { margin-top: 1; color: #b6e3cf; }
    #fields Input, #fields Select { width: 100%; }
    #message { height: auto; min-height: 2; padding: 0 2; color: #eaba82; }
    #actions { height: 3; align: right middle; padding: 0 2; }
    #actions Button { margin-left: 1; }
    """
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, env: EnvFile):
        super().__init__()
        self.env = env
        self.values = dict(env.values)
        self.changes: dict[str, str] = {}
        self.page = 0
        self.search = ""
        self.backup = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="title")
        yield Static(id="description")
        yield Input(placeholder="Search by name or description (all settings)", id="search")
        yield VerticalScroll(id="fields")
        yield Static(id="message")
        with Horizontal(id="actions"):
            yield Button("Back", id="back")
            yield Button("Next", variant="primary", id="next")
            yield Button("Save", variant="success", id="save")
            yield Button("Cancel", id="cancel")
        yield Footer()

    async def on_mount(self) -> None:
        await self._render_page()

    def _update(self, key: str, value: str) -> None:
        value = normalize_value(BY_KEY[key], value)
        self.values[key] = value
        if self.env.values.get(key) == value:
            self.changes.pop(key, None)
        else:
            self.changes[key] = value

    def _collect(self) -> str | None:
        if PAGES[self.page] == "Review":
            return None
        container = self.query_one("#fields", VerticalScroll)
        for setting in fields_for(PAGES[self.page], self.values, self.search):
            control = container.query(f"#setting-{setting.key}")
            if not control:
                continue
            widget = control.first()
            value = str(widget.value)
            if error := validate_value(setting, value):
                return f"{setting.key}: {error}"
            if value != effective(setting, self.values):
                self._update(setting.key, value)
        return None

    async def _render_page(self) -> None:
        page = PAGES[self.page]
        self.query_one("#title", Static).update(f"{self.page + 1} / {len(PAGES)}    {page}")
        self.query_one("#search", Input).display = page == "Advanced"
        self.query_one("#back", Button).disabled = self.page == 0
        self.query_one("#next", Button).display = page != "Review"
        self.query_one("#save", Button).display = page == "Review"
        self.query_one("#message", Static).update("")
        description = ("All configuration keys are searchable, including settings for inactive integrations."
                       if page == "Advanced" else
                       "Review every change and save once; secrets remain masked."
                       if page == "Review" else
                       "Select values for this step; use Advanced to inspect or edit every setting.")
        self.query_one("#description", Static).update(description)
        form = self.query_one("#fields", VerticalScroll)
        await form.remove_children()
        if page == "Review":
            errors = validate(self.env.with_changes(self.changes))
            help_text = _help_for(self.values)
            preview = self.env.preview(self.changes)
            await form.mount(Static(help_text + "\n\nChanges (secrets masked):\n" + preview +
                                    ("\n\nFix before saving:\n- " + "\n- ".join(errors) if errors else "")))
            return
        widgets = []
        for setting in fields_for(page, self.values, self.search):
            widgets.append(Label(f"{setting.key} · {setting.help}"))
            value = effective(setting, self.values)
            if setting.choices:
                widgets.append(Select([(choice, choice) for choice in setting.choices],
                                      value=value if value in setting.choices else setting.choices[0],
                                      id=f"setting-{setting.key}"))
            else:
                widgets.append(Input(value=value, password=setting.secret,
                                     placeholder=setting.default or setting.help,
                                     id=f"setting-{setting.key}"))
        await form.mount(*widgets)

    async def on_select_changed(self, event: Select.Changed) -> None:
        if not event.select.id or not event.select.id.startswith("setting-"):
            return
        key = event.select.id.removeprefix("setting-")
        value = str(event.value)
        if key in ("CODEBOT_TASK_SOURCE", "CODEBOT_COMM_CHANNEL", "CODEBOT_AGENT") and value != effective(BY_KEY[key], self.values):
            self._collect()
            self._update(key, value)
            await self._render_page()

    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search" and PAGES[self.page] == "Advanced":
            self._collect()
            self.search = event.value
            await self._render_page()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        action = event.button.id
        if action == "cancel":
            self.exit(False)
            return
        error = self._collect()
        if error:
            self.query_one("#message", Static).update(error)
            return
        if action == "back":
            self.page -= 1
        elif action == "next":
            self.page += 1
        elif action == "save":
            errors = validate(self.env.with_changes(self.changes))
            if errors:
                self.query_one("#message", Static).update("Fix settings before saving: " + "; ".join(errors))
                return
            if errors := preflight(self.env.with_changes(self.changes)):
                self.query_one("#message", Static).update("Check integration access: " + "; ".join(errors))
                return
            try:
                self.backup = self.env.save(self.changes)
            except (OSError, ValueError) as exc:
                self.query_one("#message", Static).update(str(exc))
                return
            self.exit(True)
            return
        await self._render_page()

    def action_cancel(self) -> None:
        self.exit(False)

def run(env: EnvFile) -> bool:
    app = SetupApp(env)
    done = app.run()
    if done:
        print(f"Saved {env.path}" + (f" (backup: {app.backup})" if app.backup else ""))
        _post_save_auth(env.with_changes(app.changes))
    return bool(done)
