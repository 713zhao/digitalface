# Games Collection for Digital Face

Touch-screen controlled games for Raspberry Pi LCD display.

## Available Games

### 1. Flappy Bird Clone
- **Description**: Tap to make the bird jump, avoid obstacles
- **Controls**: Tap anywhere or press SPACE to jump
- **Launch**: `./flappy_bird/launch.sh` or `./launch_game.sh 1`
- **Features**:
  - Score tracking
  - Procedural pipe generation
  - Smooth physics
  - Touch screen support
  - Game over screen with restart

## How to Launch

### Option 1: Launch Game Selector Menu (Recommended)
```bash
cd /home/eric/projects/digitalface/games
./launch_game.sh
```

### Option 2: Launch Specific Game in SDL Mode (Testing - No Setup Needed)
```bash
cd /home/eric/projects/digitalface/games
./flappy_bird/launch.sh --sdl
```
✅ Works immediately - runs in SDL window without stopping digitalface

### Option 3: Launch on Framebuffer (Full Screen - Requires Setup)
```bash
# 1. Stop digitalface to free the framebuffer
sudo systemctl stop digitalface

# 2. Run game
cd /home/eric/projects/digitalface/games
./flappy_bird/launch.sh

# 3. Restart digitalface when done
sudo systemctl start digitalface
```

### Option 4: Direct Python
```bash
cd /home/eric/projects/digitalface/games/flappy_bird
python3 main.py --sdl                    # SDL window
python3 main.py                          # Framebuffer (requires stopping digitalface)
python3 main.py --fbdev /dev/fb0         # Use different framebuffer
```

## Controls

### Flappy Bird
- **Jump**: Tap screen or press SPACE
- **Restart** (after game over): Tap screen or press SPACE
- **Exit**: Press ESC or close window

## Game Features

### Current (Flappy Bird)
- ✅ Touch screen input
- ✅ Framebuffer support
- ✅ Score tracking
- ✅ Collision detection
- ✅ Game over screen
- ✅ Restart functionality

### Planned
- 🔄 2048 Puzzle (in progress)
- 🔄 Whack-a-Mole (in progress)
- 🔄 High score persistence
- 🔄 Sound effects
- 🔄 Game settings/difficulty levels

## Development

### Game Structure

Each game should follow this structure:
```
games/
├── launch_game.sh          # Main launcher
├── README.md              # This file
└── flappy_bird/
    ├── launch.sh          # Game launcher script
    ├── main.py            # Entry point with framebuffer/SDL modes
    ├── game.py            # Game logic and classes
    └── README.md          # Game-specific documentation (optional)
```

### Creating a New Game

1. Create game directory: `mkdir games/new_game`
2. Create `game.py` with main game class (inherit pattern from flappy_bird)
3. Create `main.py` with framebuffer/SDL launcher
4. Create `launch.sh` shell script
5. Update this README

### Game Base Class Template

```python
class GameBase:
    def __init__(self, screen_width=480, screen_height=320):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.surface = pygame.display.set_mode((screen_width, screen_height))
        self.clock = pygame.time.Clock()
        self.fps = 60
        self.running = True
    
    def handle_events(self):
        """Process input events."""
        pass
    
    def update(self):
        """Update game state."""
        pass
    
    def draw(self):
        """Render game."""
        pass
    
    def run(self):
        """Main game loop."""
        while self.running:
            self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(self.fps)
        pygame.quit()
```

## Performance Notes

- Games run at 60 FPS
- Framebuffer mode reduces CPU overhead vs SDL
- Tested on Raspberry Pi 4 with 3.5" SPI LCD
- Touch latency: ~50-100ms (depending on event loop)

## Troubleshooting

### Game doesn't start
1. Check `.venv` is properly configured: `source .venv/bin/activate`
2. Verify pygame installed: `pip list | grep pygame`
3. Check framebuffer: `ls -l /dev/fb1`

### Touch input not working
1. Verify touch device: `ls -la /dev/input/event1`
2. Test touch: `sudo cat /dev/input/event1` (touch screen, watch output)
3. Check SDL env vars in launcher

### Game runs slow
1. Close other processes: `sudo systemctl stop digitalface`
2. Check CPU: `top` or `htop`
3. Reduce graphics complexity or FPS if needed

### Screen goes black
1. Framebuffer might be inactive
2. Try: `sudo systemctl restart digitalface` after game exits
3. Try SDL mode: `python3 main.py --sdl`

## Future Ideas

- [ ] Leaderboard/high scores (persistent storage)
- [ ] Game difficulty levels
- [ ] Sound effects (using espeak or audio device)
- [ ] Integrate with digitalface animations
- [ ] Menu system to switch games without restarting
- [ ] Network multiplayer (future: WiFi features)
- [ ] Game customization settings

## License

Same as digitalface project.
