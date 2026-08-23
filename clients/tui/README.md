# SecOps TUI — Proof of Concept

A two-pane [Textual](https://textual.textualize.io) terminal interface for SecOps case triage that delegates all API work to background threads, demonstrating clean separation between domain logic (the SDK facade) and presentation layer.

---

## Design

The TUI consists of three files:

1. **`render.py`**: Pure Rich-based rendering functions. Each function consumes a domain dataclass from `engine.domain` and returns a Rich `Table`, `Panel`, or `Text`. This layer is **stateless** and reusable in CLI scripts or reports.

2. **`app.py`**: The Textual `App` subclass. All SDK calls (`search_cases`, `investigate_case`) occur in `@work(thread=True)` decorated methods. Results are posted back to the UI thread as custom `Message` subclasses, where message handlers update widgets. This ensures the UI remains responsive even on slow networks.

3. **`run_tui.py`**: The launcher (lives at project root for import-path reasons). It constructs a `SecOpsEngine` from the root facade and launches the app. Also provides a `--demo` offline mode with fake data so the layout and threading can be validated without live credentials.

**Layout** (two-pane, composed via TCSS):

```
+----------------------+---------------------------------+
|  search input        |                                 |
+----------------------+   detail pane                   |
|  cases DataTable     |   (CaseInvestigation render)    |
|  (CaseSearchResult)  |                                 |
+----------------------+---------------------------------+
|  status / key hints                                    |
+--------------------------------------------------------+
```

The **left pane** displays search results in a `DataTable` (ID, priority, title, stage, alerts, assignee, created). The **right pane** shows the full investigation detail for the selected row (alerts table, entities table, comments), rendered via `render.case_detail()`.

---

## Installation

Textual is not a core dependency of the SDK; it's only required for this TUI POC:

```bash
pip install -r clients/tui/requirements-tui.txt
```

(This installs `textual>=0.60.0` and `rich>=13.0.0`.)

---

## Running

From the **project root** (ensures the facade's root-relative imports resolve):

```bash
# Live mode (requires configured Google SecOps creds):
python run_tui.py

# Offline demo (fake data, no API calls):
python run_tui.py --demo

# Seed the search box with a query:
python run_tui.py --query "Priority:HIGH"
```

In **live mode**, the app constructs a `SecOpsEngine()` using the normal tenant config from `SECOPS_CONFIG_PATH` or embedded fallback. In **demo mode**, it runs entirely offline with synthetic case data so the UI layout and threading mechanics can be validated without live credentials.

---

## Key Bindings

- `/` → focus the search input
- `r` → refresh (re-runs the current query)
- `Enter` on the search input → execute query
- Arrow keys / `j`/`k` → navigate case list
- `Enter` on a row → load full case detail in right pane
- `q` → quit

---

## Threading Invariant

**No facade call happens on the UI thread.** Both `search_cases` and `investigate_case` are dispatched via `@work(thread=True)` and post their results (or errors) as custom `Message` subclasses. The UI thread handles these messages by updating widgets. This keeps the interface responsive even on slow networks and demonstrates the SDK's thread-safety (the facade is designed for concurrent access by multiple workers).

The worker setup:

```python
@work(thread=True, exclusive=True, group="search")
def _load_cases(self, query: str) -> None:
    try:
        batch = self._engine.search_cases(query=query, page_size=self._page_size)
        items = list(getattr(batch, "results", []) or [])
        total = int(getattr(batch, "total_count", len(items)))
        self.post_message(self.CasesLoaded(items=items, total=total, query=query))
    except Exception as exc:
        self.post_message(self.CasesFailed(error=str(exc), query=query))

def on_cases_loaded(self, msg: CasesLoaded) -> None:
    # Back on the UI thread; safe to manipulate widgets.
    table = self.query_one("#cases", DataTable)
    table.clear()
    # ... populate from msg.items
```

**Rationale**: Blocking the UI thread with network I/O produces a frozen interface. Textual's `@work` decorator runs the method on a background thread (from Python's `concurrent.futures.ThreadPoolExecutor`) and posts the message when done, which is then dispatched to the handler on the UI thread.

---

## Why Textual?

1. **Proper layout engine**: Unlike raw curses/blessed, Textual provides a CSS-like box model for responsive layout (the left/right pane split adapts to terminal size).
2. **Message-driven**: The message/worker pattern cleanly separates I/O from rendering, which is *essential* for a responsive UI when driving slow remote APIs.
3. **Accessibility**: Built-in keyboard navigation, screen reader hints, and a focus system.
4. **Zero dependency on X11/Wayland**: Runs over SSH, in tmux, inside tiling WMs, etc. (my primary use case).

---

## Why This Is a POC (Not Production UI)

This demonstrates clean separation and responsive threading, but is deliberately minimal:

- **No pagination controls**: The SDK supports page tokens; the TUI doesn't expose them (always fetches page 0).
- **No alert/entity drill-down**: Clicking an alert row doesn't open an alert detail view (would need more workers + panes).
- **No update/comment actions**: The facade exposes `update_case`, `add_comment`, etc., but this POC is read-only.
- **No error recovery**: Failed API calls surface in the detail pane; there's no retry logic or offline cache.

The goal was to prove the facade's domain models map cleanly to a presentation layer (they do) and that the threading model is sound (it is). A production TUI would add navigation depth, bulk actions, persistent state, and keybindings for update workflows.

---

## Extending

To add a new workflow (e.g., "update case assignee on keypress"):

1. Add a `@dataclass class AssignmentUpdated(Message)` to the `App`.
2. Write a `@work(thread=True)` method that calls `self._engine.update_case(...)` and posts `AssignmentUpdated` (or an error message).
3. Add an action binding (`("a", "assign", "Assign")`) that triggers the worker.
4. Add an `on_assignment_updated(self, msg)` handler that refreshes the detail pane or shows a notification.

The pattern scales: every SDK method maps to a worker, every worker posts a message, every message has a handler that updates widgets. The UI stays responsive, and the facade stays stateless.

---

## Testing Without Live Credentials

The `--demo` mode is explicitly for this. It builds a minimal engine stand-in (defined in `run_tui.py::_build_demo_engine()`) that returns synthetic `CaseSearchResultItem` and `CaseInvestigation` objects using the real domain dataclasses. This ensures:

- The render layer's field access patterns are correct (no `AttributeError` on misnamed fields).
- The layout behaves correctly on realistic data (long titles, missing assignees, zero-alert cases, etc.).
- The threading and message dispatch logic works even without a network.

Run:

```bash
python run_tui.py --demo
```

You'll see six fake cases; clicking one loads a detail view with synthetic alerts/entities. All the same UI/threading mechanics are exercised, but no API calls are made.

---

## Architecture Notes

**Why `render.py` lives in `tui/` instead of a top-level `cli/` folder**:

It's specific to the TUI POC right now. If we build a stateless CLI (`secops-cli case show <id>`), we'd promote `render.py` to a shared `cli/` or `presentation/` module and have both the TUI and CLI import it. For now, it's colocated with the app to keep the POC self-contained.

**Why `run_tui.py` lives at the project root**:

The facade uses root-relative imports (`from adapters.google_secops import ...`). Running from within `tui/` would require `sys.path` manipulation or a package install. Anchoring the launcher at the root ensures imports work whether run from anywhere (`python run_tui.py`) or via a shebang (`./run_tui.py`).

**Why the demo engine is inline in `run_tui.py` instead of a separate module**:

It's ~60 lines and only used by one script. If we add more launchers (e.g., a web dashboard POC), we'd extract it to `tests/fixtures/demo_engine.py` and share it. For now, keeping it colocated with its single consumer minimizes file scatter.
