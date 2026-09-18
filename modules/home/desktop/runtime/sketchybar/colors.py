#!@python@
import sys

from palette import load_palette


def main():
    palette = load_palette()
    colors = palette["colors"]
    if "--borders" in sys.argv:
        print(
            "0xff" + colors["color6"][1:],
            "0xff" + colors["color4"][1:],
            "0x40" + colors["color0"][1:],
        )
        return
    values = {
        "BAR_COLOR": palette["special"]["background"],
        "ACCENT_COLOR": colors["color1"],
        "ICON_COLOR": colors["color4"],
        "LABEL_COLOR": colors["color6"],
    }
    for name, value in values.items():
        alpha = "66" if name == "BAR_COLOR" else "ff"
        print("export " + name + "=0x" + alpha + value[1:])


if __name__ == "__main__":
    main()
