"""Validated colors.json with the upstream Nothing palette as an offline fallback."""
import copy
import json
from pathlib import Path
import re

FALLBACK = {'special': {'background': '#000000', 'foreground': '#ffffff', 'cursor': '#d71921'}, 'colors': {'color0': '#000000', 'color1': '#d71921', 'color2': '#4a4a4a', 'color3': '#808080', 'color4': '#b0b0b0', 'color5': '#d71921', 'color6': '#e0e0e0', 'color7': '#ffffff', 'color8': '#666666', 'color9': '#d71921', 'color10': '#5a5a5a', 'color11': '#909090', 'color12': '#c0c0c0', 'color13': '#d71921', 'color14': '#f0f0f0', 'color15': '#ffffff'}}


def _luminance(color):
    components = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in components]
    return sum(a * b for a, b in zip(linear, (0.2126, 0.7152, 0.0722)))

def _contrast(foreground, background):
    dark, light = sorted((_luminance(foreground), _luminance(background)))
    return (light + 0.05) / (dark + 0.05)

def _readable_color(color, background, minimum=4.5):
    if _contrast(color, background) >= minimum:
        return color
    target = 255 if _contrast('#ffffff', background) >= _contrast('#000000', background) else 0
    channels = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    def mix(amount):
        return '#' + ''.join(format(round(c + (target - c) * amount), '02x') for c in channels)
    low, high = 0.0, 1.0
    for _ in range(24):
        middle = (low + high) / 2
        if _contrast(mix(middle), background) >= minimum:
            high = middle
        else:
            low = middle
    return mix(high)

def _readable_palette(data):
    # Derive UI colors without rewriting pywal's original extracted palette.
    # The wallpaper's background stays intact; only low-contrast text is lifted.
    background = data['special']['background']
    for i in range(1, 16):
        key = 'color' + str(i)
        data['colors'][key] = _readable_color(data['colors'][key], background)
    for key in ('foreground', 'cursor'):
        data['special'][key] = _readable_color(data['special'][key], background)
    return data

def load_palette(path=None):
    # A fresh machine starts with Sky Copy even before the first activation.
    paths = [Path(path)] if path else [
        Path.home() / '.cache/wal/colors.json', Path('@paletteSeed@'),
    ]
    for candidate in paths:
        try:
            data = json.loads(candidate.read_text())
            expected = {'special': ('background', 'foreground', 'cursor'),
                        'colors': tuple('color' + str(i) for i in range(16))}
            for section, names in expected.items():
                for name in names:
                    if not isinstance(data[section][name], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', data[section][name]):
                        raise ValueError('Invalid palette')
            return _readable_palette(data)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return _readable_palette(copy.deepcopy(FALLBACK))
