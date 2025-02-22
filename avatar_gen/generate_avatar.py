import json
import random
import sys
from pathlib import Path
from typing import NamedTuple, Optional

from PIL import Image

from .mac_lookup import get_vendor_name

_SCRIPT_PATH = Path(__file__).parents[0].resolve()


class _ImageEntry(NamedTuple):
    item_id: int
    layer_id: int
    layer_val: int
    color_id: int
    img_path: Path


class _Part(NamedTuple):
    part_id: int
    name: str
    item_ids: list[int]
    color_ids: list[int]
    # Only support single layer parts.
    layer_id: int
    layer_val: int
    images: list[_ImageEntry]


class Selection(NamedTuple):
    name: str
    item_idx: int | None = None
    color_idx: int | None = None
    disable: bool = False


class AvatarGen:
    def __init__(self, source_dir: Path) -> None:
        image_data = json.load(open(source_dir / 'img.json', 'r'))
        config_data = json.load(
            open(source_dir / 'cf.json', 'r', errors='ignore'))

        image_entries: list[_ImageEntry] = []
        for item_id, v1 in image_data.items():
            for layer_id, v2 in v1.items():
                layer_val = config_data['lyrList'][layer_id]
                for color_id, v3 in v2.items():
                    img_path = source_dir / 'imgs' / v3['url'].split('/')[-1]
                    image_entries.append(_ImageEntry(int(item_id), int(
                        layer_id), layer_val, int(color_id), img_path))

        parts: list[_Part] = []
        for part in config_data['pList']:
            part_id = part['pId']
            name = part['pNm']
            layer_id = part['lyrs'][0]
            layer_val = config_data['lyrList'][str(layer_id)]
            color_list_id = part['cpId']
            color_ids = [c['cId']
                         for c in config_data['cpList'][str(color_list_id)]]
            item_ids = [i['itmId'] for i in part['items']]
            items = [
                i for i in image_entries if i.item_id in item_ids and i.layer_id == layer_id]
            parts.append(_Part(
                part_id,
                name,
                item_ids,
                color_ids,
                layer_id,
                layer_val,
                items
            ))
        self.ordered_parts = sorted(parts, key=lambda x: x.layer_val)

    def describe_choices(self):
        print(f'{len(self.ordered_parts)} types of parts.')
        for p in self.ordered_parts:
            print(f'{p.name} has {len(p.item_ids)} items of {
                  len(p.color_ids)} colors.')

    def get_choices(self) -> list[Selection]:
        selections = []
        for p in self.ordered_parts:
            selections.append(Selection(
                p.name,
                item_idx=len(p.item_ids),
                color_idx=len(p.color_ids)
            ))
        return selections

    def generate_image(self, out_file: Path, selections: list[Selection] = [],
                       seed: int | float | str | bytes | bytearray | None = None):
        r = random.Random(seed)
        part_selections: list[_ImageEntry] = []
        for part in self.ordered_parts:
            images = part.images
            selection = None
            for s in selections:
                if s.name == part.name:
                    selection = s
                    break
            if selection is not None:
                if selection.disable:
                    continue

                if selection.item_idx is not None:
                    item_id = part.item_ids[selection.item_idx]
                    images = [
                        i for i in images if i.item_id == item_id]

                if selection.color_idx is not None:
                    color_id = part.color_ids[selection.color_idx]
                    images = [i for i in images if i.color_id == color_id]
            part_selections.append(r.choice(images))
        combined_image = Image.open(
            part_selections[0].img_path).convert("RGBA")
        for part in part_selections[1:]:
            foreground = Image.open(part.img_path).convert("RGBA")
            combined_image = Image.alpha_composite(combined_image, foreground)

        combined_image.save(out_file)


def get_pet_avatar(out_dir: Path, device_type: str, name: str, mac_address: Optional[str]) -> Path:
    avatar_file = device_type + '-' + name + '.png'
    avatar_path = out_dir / avatar_file
    if avatar_path.exists():
        return avatar_path

    if device_type in ['PC', 'LAPTOP', 'PHONE']:
        avatar_dir = 'bunny'
    elif device_type in ['IOT']:
        avatar_dir = 'nyan'
    elif device_type in ['SERVER', 'ROUTER']:
        avatar_dir = 'asaha'
    else:
        avatar_dir = 'pix_animal'

    generator = AvatarGen(_SCRIPT_PATH / avatar_dir)

    choices = generator.get_choices()
    if mac_address:
        vendor_name = get_vendor_name(mac_address)
    else:
        vendor_name = name
    r = random.Random(vendor_name)
    selections = []
    # No color support for asaha
    if avatar_dir != 'asaha':
        for choice in choices:
            selections.append(Selection(
                choice.name,
                item_idx=r.randint(0, choice.item_idx - 1),  # type: ignore
                disable=choice.name == 'background'
            ))

    generator.generate_image(avatar_path, selections, mac_address)
    return avatar_path


if __name__ == '__main__':
    gen = AvatarGen(Path(sys.argv[1]))
    gen.describe_choices()
    gen.generate_image(Path(sys.argv[2]), [
                       Selection('background', item_idx=0, disable=False)])

    # get_pet_avatar(_DATA_PATH, 'PC', 'C8-D3-FF-40-FF-13')
    # get_pet_avatar(_DATA_PATH, 'PC', '00-E0-4C-20-0A-F2')
    # get_pet_avatar(_DATA_PATH, 'IOT', '64-16-66-A1-D7-82')
    # get_pet_avatar(_DATA_PATH, 'IOT', '64-16-66-A0-BC-8D')
    # get_pet_avatar(_DATA_PATH, 'PC', '64-16-66-A1-D7-82')
    # get_pet_avatar(_DATA_PATH, 'PC', '64-16-66-A0-BC-8D')
    # get_pet_avatar(_DATA_PATH, 'SERVER', '64-16-66-A1-D7-82')
    # get_pet_avatar(_DATA_PATH, 'SERVER', '64-16-66-A0-BC-8D')
