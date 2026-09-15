#!@python@
"""Generate Zed's Pywal theme and refresh local bars; no editor settings edits."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'sketchybar'))
from palette import load_palette, _luminance, _readable_color

os.environ['PATH'] = ':'.join(['/opt/homebrew/bin', '/usr/local/bin', str(Path.home() / '.nix-profile/bin'),
    '/etc/profiles/per-user/' + os.environ.get('USER', Path.home().name) + '/bin',
    '/run/current-system/sw/bin', '/usr/bin', '/bin', '/usr/sbin', '/sbin', os.environ.get('PATH', '')])

def generate_colors(image, light=False):
    image = Path(image).expanduser().resolve()
    if not image.is_file():
        raise RuntimeError('Wallpaper image does not exist')
    # The Python environment and ColorThief backend are pinned by Nix.
    wal = '@wal@'
    # Pillow/ColorThief does not read HEIC by default. Cache a sampled PNG;
    # leave the source image and the selected macOS wallpaper untouched.
    color_source = image
    if image.suffix.lower() in ('.heic', '.heif'):
        digest = hashlib.sha256(image.read_bytes()).hexdigest()[:20]
        cache = Path.home() / '.cache/yabai-config/wallpapers'
        cache.mkdir(parents=True, exist_ok=True)
        color_source = cache / (digest + '.png')
        if not color_source.is_file():
            temporary = cache / (digest + '.tmp.png')
            subprocess.run(['/usr/bin/sips', '-s', 'format', 'png',
                            '--resampleHeightWidthMax', '1024', str(image),
                            '--out', str(temporary)], check=True, capture_output=True)
            temporary.replace(color_source)
    # Match palette.py's fixed location even under a customized XDG environment.
    env = dict(os.environ, PYWAL_CACHE_DIR=str(Path.home() / '.cache/wal'), NO_FUN='1')
    # Color generation only: no wallpaper, terminal-sequence, or Xresources changes.
    command = [wal, '--backend', 'colorthief', '-n', '-s', '-t', '-e']
    if light:
        command.append('-l')
    subprocess.run(command + ['-i', str(color_source)], check=True, env=env)

def refresh_running_bars():
    for name in ('borders', 'sketchybar'):
        alive = subprocess.run(['/usr/bin/pgrep', '-x', name], capture_output=True).returncode == 0
        executable = shutil.which(name)
        if not alive or not executable:
            continue
        if name == 'sketchybar':
            subprocess.run([executable, '--reload'], check=True)
        else:
            colors = load_palette()['colors']
            active = 'gradient(top_left=0xff' + colors['color6'][1:] + ',bottom_right=0xff' + colors['color4'][1:] + ')'
            subprocess.run([executable, 'active_color=' + active, 'inactive_color=0x40' + colors['color0'][1:]], check=True)

def lighten_color(hex_color, amount):
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    r = min(255, int(r + (255 - r) * amount))
    g = min(255, int(g + (255 - g) * amount))
    b = min(255, int(b + (255 - b) * amount))

    return f"#{r:02x}{g:02x}{b:02x}"

def lighten_color_by_amount(hex_color, amount):
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    r = min(255, r + amount)
    g = min(255, g + amount)
    b = min(255, b + amount)

    return f"#{r:02x}{g:02x}{b:02x}"

def darken_color(hex_color, amount):
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    r = max(0, int(r * (1 - amount)))
    g = max(0, int(g * (1 - amount)))
    b = max(0, int(b * (1 - amount)))

    return f"#{r:02x}{g:02x}{b:02x}"

def adjust_saturation(hex_color, amount):
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    gray = (r + g + b) // 3

    if amount > 0:
        r = min(255, int(r + (r - gray) * amount))
        g = min(255, int(g + (g - gray) * amount))
        b = min(255, int(b + (b - gray) * amount))
    else:
        factor = 1 + amount
        r = int(gray + (r - gray) * factor)
        g = int(gray + (g - gray) * factor)
        b = int(gray + (b - gray) * factor)

    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))

    return f"#{r:02x}{g:02x}{b:02x}"

def blend_colors(hex_color1, hex_color2, ratio=0.5):
    c1 = hex_color1.lstrip("#")
    c2 = hex_color2.lstrip("#")

    r1, g1, b1 = int(c1[0:2], 16), int(c1[2:4], 16), int(c1[4:6], 16)
    r2, g2, b2 = int(c2[0:2], 16), int(c2[2:4], 16), int(c2[4:6], 16)

    r = int(r1 + (r2 - r1) * ratio)
    g = int(g1 + (g2 - g1) * ratio)
    b = int(b1 + (b2 - b1) * ratio)

    return f"#{r:02x}{g:02x}{b:02x}"

def update_zed_theme(destination=None):
    theme_file = Path(destination).expanduser() if destination else Path.home() / '.config/zed/themes/pywal.json'
    theme_file.parent.mkdir(parents=True, exist_ok=True)
    print("Updating Zed theme...")
    try:
        wal_colors = load_palette()

        bg = wal_colors["special"]["background"]
        # A no-argument reload follows the saved palette, including its appearance.
        is_light = _luminance(bg) > 0.5
        color1 = wal_colors["colors"]["color1"]
        color2 = wal_colors["colors"]["color2"]
        color3 = wal_colors["colors"]["color3"]
        color4 = wal_colors["colors"]["color4"]
        color5 = wal_colors["colors"]["color5"]
        color6 = wal_colors["colors"]["color6"]
        color8 = wal_colors["colors"]["color8"]

        accent_color = color1
        icon_color = color4
        label_color = wal_colors["special"]["foreground"] if is_light else color6
        if is_light:
            # Light UI needs subtle darker surfaces and a pale tinted selection;
            # the original dark-theme offsets would wash every surface to white.
            selection_bg = blend_colors(bg, color4, 0.18)
            bg_elevated = lighten_color(bg, 0.35)
            bg_surface = darken_color(bg, 0.025)
            bg_active = blend_colors(bg, color4, 0.08)
            # Keep text readable on the darkest surface where it can appear.
            text_background = min((bg, selection_bg, bg_elevated, bg_surface, bg_active), key=_luminance)
            readable = lambda color: _readable_color(color, text_background)
            color1, color2, color3, color4, color5, color6, color8 = map(
                readable, (color1, color2, color3, color4, color5, color6, color8))
            accent_color, icon_color = color1, color4
            label_color = readable(label_color)
            emphasize = darken_color
        else:
            selection_bg = lighten_color(bg, 0.25)
            bg_elevated = lighten_color(bg, 0.08)
            bg_surface = lighten_color(bg, 0.04)
            bg_active = lighten_color(bg, 0.12)
            readable = lambda color: color
            emphasize = lighten_color

        keyword_color = color1
        keyword_light = readable(emphasize(color1, 0.15))
        keyword_dim = darken_color(color1, 0.2)

        string_color = color2
        string_light = readable(emphasize(color2, 0.2))
        string_dim = darken_color(color2, 0.15)

        function_color = color3
        function_light = readable(emphasize(color3, 0.15))

        type_color = color4
        type_light = readable(emphasize(color4, 0.15))
        type_dim = darken_color(color4, 0.2)

        punctuation_color = readable(blend_colors(color8, label_color, 0.3))
        operator_color = readable(blend_colors(label_color, color3, 0.25))
        bracket_color = readable(blend_colors(color8, label_color, 0.5))

        comment_color = color8
        comment_doc = readable(emphasize(color8, 0.15))

        variable_color = label_color
        variable_special = readable(blend_colors(label_color, color5, 0.3))
        parameter_color = readable(blend_colors(label_color, color4, 0.2))

        property_color = readable(blend_colors(label_color, color6, 0.4))
        attribute_color = readable(blend_colors(color4, color6, 0.4))

        zed_theme = {
            "$schema": "https://zed.dev/schema/themes/v0.1.0.json",
            "name": "Pywal",
            "author": "Auto-generated from pywal",
            "themes": [
                {
                    "name": "Pywal",
                    "appearance": "light" if is_light else "dark",
                    "style": {
                        "border": bg_surface,
                        "border.variant": bg_elevated,
                        "border.focused": accent_color,
                        "border.selected": accent_color,
                        "border.transparent": "#00000000",
                        "border.disabled": bg_surface,
                        "elevated_surface.background": bg_elevated,
                        "surface.background": bg_surface,
                        "background": bg,
                        "element.background": bg_surface,
                        "element.hover": selection_bg,
                        "element.active": selection_bg,
                        "element.selected": selection_bg,
                        "element.disabled": bg,
                        "drop_target.background": f"{selection_bg}cc",
                        "ghost_element.background": "#00000000",
                        "ghost_element.hover": selection_bg,
                        "ghost_element.active": selection_bg,
                        "ghost_element.selected": selection_bg,
                        "ghost_element.disabled": bg,
                        "text": label_color,
                        "text.muted": color8,
                        "text.placeholder": color8,
                        "text.disabled": color8,
                        "text.accent": accent_color,
                        "icon": icon_color,
                        "icon.muted": color8,
                        "icon.disabled": color8,
                        "icon.placeholder": color8,
                        "icon.accent": accent_color,
                        "status_bar.background": bg_surface,
                        "title_bar.background": bg,
                        "toolbar.background": bg_surface,
                        "tab_bar.background": bg_surface,
                        "tab.inactive_background": bg_surface,
                        "tab.active_background": bg,
                        "search.match_background": selection_bg,
                        "panel.background": bg_elevated,
                        "panel.focused_border": accent_color,
                        "pane.focused_border": accent_color,
                        "scrollbar.thumb.background": f"{selection_bg}80",
                        "scrollbar.thumb.hover_background": f"{selection_bg}cc",
                        "scrollbar.thumb.border": "#00000000",
                        "scrollbar.track.background": "#00000000",
                        "scrollbar.track.border": "#00000000",
                        "editor.foreground": label_color,
                        "editor.background": bg,
                        "editor.gutter.background": bg,
                        "editor.subheader.background": bg_surface,
                        "editor.active_line.background": bg_active,
                        "editor.highlighted_line.background": bg_active,
                        "editor.line_number": color8,
                        "editor.active_line_number": label_color,
                        "editor.invisible": color8,
                        "editor.wrap_guide": bg,
                        "editor.active_wrap_guide": bg,
                        "editor.document_highlight.read_background": f"{selection_bg}80",
                        "editor.document_highlight.write_background": f"{selection_bg}80",
                        "terminal.background": bg,
                        "terminal.foreground": label_color,
                        "terminal.ansi.black": label_color if is_light else bg,
                        "terminal.ansi.bright_black": color8,
                        "terminal.ansi.dim_black": color8 if is_light else bg,
                        "terminal.ansi.red": accent_color,
                        "terminal.ansi.bright_red": accent_color,
                        "terminal.ansi.dim_red": accent_color,
                        "terminal.ansi.green": color2,
                        "terminal.ansi.bright_green": color2,
                        "terminal.ansi.dim_green": color2,
                        "terminal.ansi.yellow": color3,
                        "terminal.ansi.bright_yellow": color3,
                        "terminal.ansi.dim_yellow": color3,
                        "terminal.ansi.blue": icon_color,
                        "terminal.ansi.bright_blue": icon_color,
                        "terminal.ansi.dim_blue": icon_color,
                        "terminal.ansi.magenta": color3,
                        "terminal.ansi.bright_magenta": color3,
                        "terminal.ansi.dim_magenta": color3,
                        "terminal.ansi.cyan": label_color,
                        "terminal.ansi.bright_cyan": label_color,
                        "terminal.ansi.dim_cyan": label_color,
                        "terminal.ansi.white": label_color,
                        "terminal.ansi.bright_white": label_color,
                        "terminal.ansi.dim_white": label_color,
                        "link_text.hover": accent_color,
                        "conflict": accent_color,
                        "conflict.background": bg,
                        "conflict.border": accent_color,
                        "created": color2,
                        "created.background": bg,
                        "created.border": color2,
                        "deleted": accent_color,
                        "deleted.background": bg,
                        "deleted.border": accent_color,
                        "error": accent_color,
                        "error.background": bg,
                        "error.border": accent_color,
                        "hidden": color8,
                        "hidden.background": bg,
                        "hidden.border": color8,
                        "hint": icon_color,
                        "hint.background": bg,
                        "hint.border": icon_color,
                        "ignored": color8,
                        "ignored.background": bg,
                        "ignored.border": color8,
                        "info": icon_color,
                        "info.background": bg,
                        "info.border": icon_color,
                        "modified": color3,
                        "modified.background": bg,
                        "modified.border": color3,
                        "predictive": color8,
                        "predictive.background": bg,
                        "predictive.border": color8,
                        "renamed": color2,
                        "renamed.background": bg,
                        "renamed.border": color2,
                        "success": color2,
                        "success.background": bg,
                        "success.border": color2,
                        "unreachable": color8,
                        "unreachable.background": bg,
                        "unreachable.border": color8,
                        "warning": color3,
                        "warning.background": bg,
                        "warning.border": color3,
                        "players": [],
                        "syntax": {
                            "attribute": {"color": attribute_color},
                            "boolean": {"color": keyword_light, "font_weight": 700},
                            "comment": {"color": comment_color, "font_style": "italic"},
                            "comment.doc": {
                                "color": comment_doc,
                                "font_style": "italic",
                            },
                            "constant": {"color": keyword_color, "font_weight": 700},
                            "constructor": {
                                "color": function_light,
                                "font_weight": 700,
                            },
                            "embedded": {"color": variable_color},
                            "emphasis": {"font_style": "italic"},
                            "emphasis.strong": {"font_weight": 700},
                            "enum": {"color": type_light, "font_weight": 700},
                            "function": {"color": function_color, "font_weight": 700},
                            "hint": {"color": comment_color, "font_weight": 700},
                            "keyword": {"color": keyword_color, "font_weight": 700},
                            "label": {"color": label_color},
                            "link_text": {
                                "color": keyword_light,
                                "font_style": "italic",
                            },
                            "link_uri": {"color": string_light},
                            "number": {"color": keyword_dim},
                            "operator": {"color": operator_color},
                            "predictive": {
                                "color": comment_color,
                                "font_style": "italic",
                            },
                            "preproc": {"color": keyword_dim},
                            "primary": {"color": label_color},
                            "property": {"color": property_color},
                            "punctuation": {"color": punctuation_color},
                            "punctuation.bracket": {"color": bracket_color},
                            "punctuation.delimiter": {"color": punctuation_color},
                            "punctuation.list_marker": {"color": punctuation_color},
                            "punctuation.special": {"color": comment_color},
                            "string": {"color": string_color},
                            "string.escape": {"color": string_dim},
                            "string.regex": {"color": string_light},
                            "string.special": {"color": string_light},
                            "string.special.symbol": {"color": string_dim},
                            "tag": {"color": type_color},
                            "text.literal": {"color": string_color},
                            "title": {"color": keyword_light, "font_weight": 700},
                            "type": {"color": type_color, "font_weight": 700},
                            "variable": {"color": variable_color},
                            "variable.special": {
                                "color": variable_special,
                                "font_style": "italic",
                            },
                            "variant": {"color": type_dim},
                        },
                    },
                }
            ],
        }

        temporary = theme_file.with_name(theme_file.name + '.new')
        temporary.write_text(json.dumps(zed_theme, indent=2) + '\n')
        temporary.replace(theme_file)

        print("Zed theme updated")
        return True
    except Exception as e:
        print(f"Error updating Zed theme: {e}")
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('image', nargs='?', help='Optionally derive colors from a local image')
    parser.add_argument('--reset-palette', action='store_true', help='Restore the Nix-managed Sky Copy palette; backs up the current palette')
    parser.add_argument('--light', action='store_true', help='Generate a light palette (requires an image)')
    parser.add_argument('--zed-theme', help='Output path for the generated theme')
    parser.add_argument('--no-reload', action='store_true', help='Only generate the theme file')
    args = parser.parse_args()
    if args.light and not args.image:
        parser.error('--light requires an image; no-argument reloads retain the saved palette')
    if args.reset_palette and args.image:
        parser.error('--reset-palette and an image cannot be combined')
    if args.reset_palette:
        from datetime import datetime, timezone
        palette = Path.home() / '.cache/wal/colors.json'
        palette.parent.mkdir(parents=True, exist_ok=True)
        if palette.exists() or palette.is_symlink():
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
            palette.rename(palette.with_name(palette.name + '.before-reset-' + stamp))
        shutil.copyfile('@paletteSeed@', palette)
    if args.image:
        generate_colors(args.image, light=args.light)
    if not update_zed_theme(args.zed_theme):
        raise SystemExit(1)
    if not args.no_reload:
        refresh_running_bars()

if __name__ == '__main__':
    main()
