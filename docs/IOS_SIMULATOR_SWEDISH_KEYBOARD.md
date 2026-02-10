## iOS Simulator: Swedish keyboard (å/ä/ö)

This is a developer ergonomics note for typing Swedish characters while using the iOS Simulator.

### Option A (recommended): Use your Mac keyboard layout

This makes the Simulator behave like your real keyboard.

1. On your Mac: **System Settings → Keyboard → Input Sources**
2. Add **Swedish** (or **Swedish – Pro**) as an input source.
3. Focus the Simulator (click inside it).
4. Switch input source on your Mac:
   - Use the input menu in the macOS menu bar, or
   - Use your configured keyboard shortcut for switching input sources.

**Verify**: open any text field in the Simulator and type `å ä ö`.

### Option B: Add Swedish as an on-device (software) keyboard in the Simulator

This is useful if you want the iOS keyboard UI to be Swedish.

1. In the Simulator, open **Settings**
2. Go to **General → Keyboard → Keyboards**
3. Tap **Add New Keyboard…**
4. Choose **Swedish**
5. Open an app with a text field (e.g., Notes) and bring up the keyboard
6. Use the **globe** icon to switch to Swedish

**Tip**: If you don’t see the software keyboard, toggle:
- Simulator menu: **I/O → Keyboard → Toggle Software Keyboard**

### Troubleshooting

- **Typing still uses English layout**:
  - Ensure you switched the **Mac input source** (Option A), not just iOS language.
- **No globe icon / can’t switch keyboards**:
  - Make sure Swedish was added under **Settings → General → Keyboard → Keyboards** (Option B).
- **Hardware keyboard feels “stuck”**:
  - Simulator menu: **I/O → Keyboard → Connect Hardware Keyboard** (toggle off/on).


