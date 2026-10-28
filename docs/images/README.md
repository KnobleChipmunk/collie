# Screenshots

The images in this directory are real collie pane output, not mockups. To regenerate one:

1. Inside Herdr, from the repo root, render something: `collie show src/collie/resident.py:28-62@55-62 --note "debounced redraw on resize"`. collie prints the pane id (`shown in w2:pM0: ...`).
2. Capture the pane with its colors: `herdr pane read <pane-id> --source visible --format ansi > show.ansi`
3. Convert to SVG: `uv run --with rich python docs/images/ansi2svg.py show.ansi show.svg "collie show"`. Your home directory is shortened to `~`.
4. Convert to a 2x PNG with headless Chrome. GitHub blocks the SVG's web font, so commit the PNG, not the SVG:

```bash
W=1702 H=1051   # the SVG's viewBox width and height, rounded up
printf '<body style="margin:0"><img src="show.svg" width="%s" height="%s">' $W $H > show.html
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --hide-scrollbars \
  --force-device-scale-factor=2 --window-size=$W,$H --screenshot="$PWD/collie-show.png" "file://$PWD/show.html"
```
