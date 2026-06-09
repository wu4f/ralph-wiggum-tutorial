# Presentation

HTML slideshow built with [reveal.js](https://revealjs.com/).

## Quick Start

```bash
cd presentation
npx serve .
# Open http://localhost:3000 in your browser
```

Or simply open `index.html` directly in a browser.

## Controls

- **→ / ←** — next / previous slide
- **S** — speaker notes
- **F** — fullscreen
- **ESC** — overview mode

## Available Themes

Change the theme by editing the CSS link in `index.html`:

| Theme | File |
|-------|------|
| Beige | `beige.css` |
| Black | `black.css` |
| Black Contrast | `black-contrast.css` |
| Blood | `blood.css` |
| **Dracula** (current) | `dracula.css` |
| League | `league.css` |
| Moon | `moon.css` |
| Night | `night.css` |
| Serif | `serif.css` |
| Simple | `simple.css` |
| Sky | `sky.css` |
| Solarized | `solarized.css` |
| White | `white.css` |
| White Contrast | `white-contrast.css` |

To preview themes, change this line in `index.html`:

```html
<link rel="stylesheet" href="node_modules/reveal.js/dist/theme/dracula.css" />
```

## Adding Slides

Add `<section>` elements inside `<div class="slides">`. You can also use Markdown:

```html
<section data-markdown>
  <textarea data-template>
    ## Slide Title
    - Bullet one
    - Bullet two
  </textarea>
</section>
```
