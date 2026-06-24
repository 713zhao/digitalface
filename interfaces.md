# DigitalFace Layer Interfaces

This document defines the contract between the two layers:

1. Driver layer (`driver/`): low-level display primitives and output backends
2. Application layer (`app/`): face logic, animations, text and state

## Architecture

- Entry point: `main.py`
- Driver API: `driver/display_driver.py`
- Application implementation: `app/face_app.py`

`main.py` wires a `DisplayDriver` instance into `FaceApplication`.

---

## Driver Layer Contract

`DisplayDriver` is the rendering interface consumed by app-layer code.

### Constructor

- `DisplayDriver(surface, presenter, width, height)`

### Required properties

- `surface: pygame.Surface`
- `width: int`
- `height: int`
- `default_font: pygame.font.Font`

### Required methods

- `create_surface() -> pygame.Surface`
- `fill(color, surface=None) -> None`
- `blit(source, pos, surface=None) -> None`
- `line(color, start, end, width=1, surface=None) -> None`
- `rect(color, rect, width=0, surface=None) -> None`
- `circle(color, center, radius, width=0, surface=None) -> None`
- `ellipse(color, rect, width=0, surface=None) -> None`
- `arc(color, rect, start_angle, end_angle, width, surface=None) -> None`
- `text(text, color, pos, font=None, surface=None) -> None`
- `present() -> None`
- `set_led_enabled(enabled: bool) -> bool`
- `close() -> None`

### Presenters

- `SDLPresenter`: displays to SDL window/fullscreen (`pygame.display.flip()`)
- `FramebufferPresenter`: writes RGB565 frames to `/dev/fb*`

### Factory functions

- `create_sdl_driver(width, height) -> DisplayDriver`
- `create_framebuffer_driver(fbdev, width, height) -> DisplayDriver`
- `create_touch_driver(touchdevs=None) -> TouchDriver`

### Touch Driver Contract

`TouchDriver` is responsible for low-level touch event polling.

### Constructor

- `TouchDriver(event_paths=None)`

### Required methods

- `poll() -> bool` (returns `True` if one or more touch events were observed since last poll)
- `close() -> None`

---

## Application Layer Contract

`FaceApplication` is the app-layer unit that should be display-backend agnostic.

### Constructor

- `FaceApplication(driver, control_file, default_expression="happy")`

### Public methods

- `set_expression(name: str) -> None`
- `update(now: float) -> None`
- `render(now: float) -> None`

### Responsibilities

- Own expression state (happy/neutral/listening/surprised)
- Own animation state (blink, aura pulse, eye movement)
- Poll external control file for expression updates
- Draw all visuals only through `DisplayDriver` methods

### Non-responsibilities

- No direct framebuffer device I/O
- No direct SDL setup/teardown
- No process/service management

---

## Entrypoint Responsibilities (`main.py`)

- Acquire single-instance lock
- Parse runtime args (`--force-fb`, `--fbdev`)
- Create the correct driver backend
- Run update/render loop with target FPS
- Poll touch input driver in framebuffer mode
- Auto disable display LED after 10 minutes with both:
  - no expression/display state change
  - no touch event
- Handle graceful shutdown

---

## Extension Guidelines

### Add a new backend

1. Implement a new presenter with `present(surface)` and `close()`
2. Add a new `create_*_driver(...)` factory
3. Keep `FaceApplication` unchanged

### Add a new face or animation

1. Extend theme/state in `app/face_app.py`
2. Add new render logic there
3. Do not add backend-specific code in app layer

### Add text/icon widgets

1. Implement in app layer using driver primitives:
   - `text(...)`
   - `circle/line/rect/ellipse/arc(...)`
2. Keep data/state in app layer
3. Keep low-level drawing abstraction in driver layer

---

## Runtime Control Surface

- Control file: `/tmp/digitalface_expression`
- Valid expressions:
  - `happy`
  - `neutral`
  - `listening`
  - `surprised`

Helper scripts:

- `set_face.sh`
- `list_faces.sh`
- `cycle_faces_bg.sh`
- `stop_cycle_faces.sh`
- `start_digitalface.sh`
