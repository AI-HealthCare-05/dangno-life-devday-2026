"""Build a curated Universal LPC avatar pack for Carrot Forest.

The upstream repository contains tens of thousands of layer files.  This tool
keeps the application small by composing only reviewed layers into the
standard 13-column LPC sheet while preserving source and licence metadata.

Usage:
    python scripts/build_lpc_avatar_pack.py \
        --source C:/path/to/Universal-LPC-Spritesheet-Character-Generator \
        --output src/frontend/assets/lpc-pack
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

FRAME = 64
SHEET_COLUMNS = 13
SHEET_ROWS = 54
ANIMATION_ROWS = {
    "spellcast": 0,
    "thrust": 4,
    "walk": 8,
    "slash": 12,
    "shoot": 16,
    "hurt": 20,
    "climb": 21,
    "idle": 22,
    "jump": 26,
    "sit": 30,
    "emote": 34,
    "run": 38,
    "combat_idle": 42,
    "backslash": 46,
    "halfslash": 50,
}


@dataclass(frozen=True)
class PackItem:
    item_id: str
    category: str
    label: str
    definition: str
    body_aware: bool = True


BODY_TYPES = ("male", "female", "muscular", "teen")

ITEMS = (
    PackItem("body", "body", "기본 몸", "body/body.json"),
    # LPC bodies intentionally do not contain a head.  Keep the official head
    # layers in the pack so face, hair and headwear share the same 64px anchor.
    PackItem("human_male", "head", "성인 남성 얼굴형", "head/heads/human/heads_human_male.json"),
    PackItem("human_female", "head", "성인 여성 얼굴형", "head/heads/human/heads_human_female.json"),
    PackItem("human_male_small", "head", "작은 남성 얼굴형", "head/heads/human/heads_human_male_small.json"),
    PackItem("human_female_small", "head", "작은 여성 얼굴형", "head/heads/human/heads_human_female_small.json"),
    PackItem("human_male_plump", "head", "둥근 남성 얼굴형", "head/heads/human/heads_human_male_plump.json"),
    PackItem("human_male_gaunt", "head", "갸름한 남성 얼굴형", "head/heads/human/heads_human_male_gaunt.json"),
    PackItem("human_male_elderly", "head", "노년 남성 얼굴형", "head/heads/human/heads_human_male_elderly.json"),
    PackItem("human_female_elderly", "head", "노년 여성 얼굴형", "head/heads/human/heads_human_female_elderly.json"),
    PackItem("bob", "hair", "단정한 단발", "hair/bob/hair_bob.json", False),
    PackItem("afro", "hair", "몽글 아프로", "hair/afro/hair_afro.json", False),
    PackItem("long", "hair", "긴 생머리", "hair/long/hair_long.json", False),
    PackItem("messy", "hair", "헝클어진 숏컷", "hair/short/hair_messy1.json", False),
    PackItem("page", "hair", "페이지 컷", "hair/short/hair_page.json", False),
    PackItem("pixie", "hair", "픽시", "hair/short/hair_pixie.json", False),
    PackItem("bedhead", "hair", "베드헤드", "hair/short/hair_bedhead.json", False),
    PackItem("curtains", "hair", "커튼", "hair/short/hair_curtains.json", False),
    PackItem("idol", "hair", "아이돌", "hair/short/hair_idol.json", False),
    PackItem("buzzcut", "hair", "버즈컷", "hair/bald/hair_buzzcut.json", False),
    PackItem("shorthawk", "hair", "숏호크", "hair/bald/hair_shorthawk.json", False),
    PackItem("lob", "hair", "롱보브", "hair/bob/hair_lob.json", False),
    PackItem("side_bob", "hair", "사이드 보브", "hair/bob/hair_bob_side_part.json", False),
    PackItem("braid", "hair", "브레이드", "hair/braids/hair_braid.json", False),
    PackItem("ponytail", "hair", "포니테일", "hair/braids/hair_ponytail.json", False),
    PackItem("high_ponytail", "hair", "하이 포니테일", "hair/braids/hair_high_ponytail.json", False),
    PackItem("topknot", "hair", "탑노트", "hair/braids/hair_topknot_short.json", False),
    PackItem("curly", "hair", "컬리", "hair/curly/hair_curly_short.json", False),
    PackItem("curly_long", "hair", "롱 컬리", "hair/curly/hair_curly_long.json", False),
    PackItem("natural", "hair", "내추럴", "hair/afro/hair_natural.json", False),
    PackItem("cornrows", "hair", "콘로우", "hair/afro/hair_cornrows.json", False),
    PackItem("dreadlocks", "hair", "드레드록", "hair/afro/hair_dreadlocks_long.json", False),
    PackItem("pigtails", "hair", "피그테일", "hair/pigtails/hair_pigtails.json", False),
    PackItem("wavy", "hair", "웨이브", "hair/long/hair_wavy.json", False),
    PackItem("overalls", "outfit", "정원사 멜빵", "torso/aprons/torso_aprons_overalls.json"),
    PackItem("tshirt", "outfit", "편안한 티셔츠", "torso/shirts/shortsleeve/torso_clothes_tshirt.json"),
    PackItem("cardigan", "outfit", "포근한 카디건", "torso/shirts/longsleeve/torso_clothes_longsleeve2_cardigan.json"),
    PackItem("sleeveless", "outfit", "산뜻한 민소매", "torso/shirts/sleeveless/torso_clothes_sleeveless2.json"),
    PackItem(
        "short_cardigan", "outfit", "반소매 카디건", "torso/shirts/shortsleeve/torso_clothes_shortsleeve_cardigan.json"
    ),
    PackItem("apron_full", "outfit", "긴 앞치마", "torso/aprons/torso_aprons_apron_full.json"),
    PackItem("suspenders", "outfit", "서스펜더", "torso/aprons/torso_aprons_suspenders.json"),
    PackItem("trench", "outfit", "트렌치 코트", "torso/jacket/torso_jacket_trench.json"),
    PackItem("collared_coat", "outfit", "칼라 코트", "torso/jacket/torso_jacket_collared.json"),
    PackItem("bodice_dress", "outfit", "보디스 드레스", "torso/dresses/dress_bodice.json"),
    PackItem("sash_dress", "outfit", "새시 드레스", "torso/dresses/dress_sash.json"),
    PackItem("open_vest", "outfit", "오픈 조끼", "torso/vest/torso_clothes_vest_open.json"),
    PackItem("blouse", "outfit", "블라우스", "torso/shirts/torso_clothes_blouse.json"),
    PackItem("long_blouse", "outfit", "긴 블라우스", "torso/shirts/torso_clothes_blouse_longsleeve.json"),
    PackItem("tunic", "outfit", "튜닉", "torso/shirts/torso_clothes_tunic.json"),
    PackItem("robe", "outfit", "로브", "torso/shirts/torso_clothes_robe.json"),
    PackItem("corset", "outfit", "코르셋", "torso/shirts/torso_clothes_corset.json"),
    PackItem("formal", "outfit", "포멀", "torso/shirts/longsleeve/torso_clothes_longsleeve_formal.json"),
    PackItem("laced", "outfit", "레이스", "torso/shirts/longsleeve/torso_clothes_longsleeve_laced.json"),
    PackItem("polo", "outfit", "폴로", "torso/shirts/longsleeve/torso_clothes_longsleeve2_polo.json"),
    PackItem("buttoned", "outfit", "버튼 셔츠", "torso/shirts/longsleeve/torso_clothes_longsleeve2_buttoned.json"),
    PackItem("vneck", "outfit", "브이넥", "torso/shirts/longsleeve/torso_clothes_longsleeve2_vneck.json"),
    PackItem("short_polo", "outfit", "반소매 폴로", "torso/shirts/shortsleeve/torso_clothes_shortsleeve_polo.json"),
    PackItem("tshirt_vneck", "outfit", "브이넥 티", "torso/shirts/shortsleeve/torso_clothes_tshirt_vneck.json"),
    PackItem("tanktop", "outfit", "탱크톱", "torso/shirts/sleeveless/torso_clothes_sleeveless_tanktop.json"),
    PackItem("vest", "outfit", "조끼", "torso/vest/torso_clothes_vest.json"),
    PackItem("gloves", "arms", "장갑", "arms/arms_gloves.json"),
    PackItem("bracers", "arms", "손목 보호대", "arms/wrists/arms_bracers.json"),
    PackItem("cuffs", "arms", "소매 장식", "arms/wrists/wrists_cuffs.json"),
    PackItem("pauldrons", "arms", "어깨 보호대", "arms/shoulders/shoulders_pauldrons.json"),
    PackItem("axe", "tool", "도끼", "tools/tool_axe.json"),
    PackItem("hammer", "tool", "망치", "tools/tool_hammer.json"),
    PackItem("hoe", "tool", "괭이", "tools/tool_hoe.json"),
    PackItem("pickaxe", "tool", "곡괭이", "tools/tool_pickaxe.json"),
    PackItem("shovel", "tool", "삽", "tools/tool_shovel.json"),
    PackItem("watering_can", "tool", "물뿌리개", "tools/tool_watering_can.json"),
    PackItem("arming_sword", "weapon", "아밍 소드", "weapons/sword/weapon_sword_arming.json"),
    PackItem("dagger", "weapon", "단검", "weapons/sword/weapon_sword_dagger.json"),
    PackItem("cane", "weapon", "지팡이", "weapons/polearm/weapon_polearm_cane.json"),
    PackItem("bow", "weapon", "활", "weapons/ranged/bow/weapon_ranged_bow_normal.json"),
    PackItem("wand", "weapon", "마법봉", "weapons/magic/weapon_magic_wand.json"),
    PackItem("wheelchair", "mobility", "휠체어", "body/wheelchair.json"),
    PackItem("feathered_wings", "mobility", "깃털 날개", "body/wings/wings_feathered.json"),
    PackItem("lizard_wings", "mobility", "리자드 날개", "body/wings/wings_lizard_alt.json"),
    PackItem("bat_wings", "mobility", "박쥐 날개", "body/wings/wings_bat.json"),
    PackItem("lunar_wings", "mobility", "달빛 날개", "body/wings/wings_lunar.json"),
    PackItem("pants", "bottom", "기본 바지", "legs/pants/legs_pants.json"),
    PackItem("long_pants", "bottom", "긴 바지", "legs/pants/legs_pants2.json"),
    PackItem("shorts", "bottom", "산책 반바지", "legs/shorts/legs_shorts.json"),
    PackItem("leggings", "bottom", "활동 레깅스", "legs/leggings/legs_leggings.json"),
    PackItem("leggings2", "bottom", "슬림 레깅스", "legs/leggings/legs_leggings2.json"),
    PackItem("hose", "bottom", "호즈", "legs/leggings/legs_hose.json"),
    PackItem("short_short", "bottom", "짧은 반바지", "legs/shorts/legs_shorts_short.json"),
    PackItem("formal_pants", "bottom", "정장 바지", "legs/pants/legs_formal.json"),
    PackItem("cuffed", "bottom", "커프 바지", "legs/pants/legs_cuffed.json"),
    PackItem("pantaloons", "bottom", "판탈롱", "legs/pants/legs_pantaloons.json"),
    PackItem("widepants", "bottom", "와이드 팬츠", "legs/pants/legs_widepants.json"),
    PackItem("plain_skirt", "bottom", "기본 스커트", "legs/skirts/legs_skirts_plain.json"),
    PackItem("slit_skirt", "bottom", "슬릿 스커트", "legs/skirts/legs_skirts_slit.json"),
    PackItem("shoes", "shoes", "기본 운동화", "feet/shoes/feet_shoes_basic.json"),
    PackItem("boots", "shoes", "정원 워커", "feet/boots/feet_boots_basic.json"),
    PackItem("slippers", "shoes", "폭신 슬리퍼", "feet/feet_slippers.json"),
    PackItem("sandals", "shoes", "샌들", "feet/feet_sandals.json"),
    PackItem("shoe_revised", "shoes", "가죽 구두", "feet/shoes/feet_shoes_revised.json"),
    PackItem("ghillies", "shoes", "길리 슈즈", "feet/shoes/feet_shoes_ghillies.json"),
    PackItem("sara_shoes", "shoes", "사라 슈즈", "feet/shoes/feet_shoes_sara.json"),
    PackItem("boots_fold", "shoes", "폴드 부츠", "feet/boots/feet_boots_fold.json"),
    PackItem("boots_rim", "shoes", "림 부츠", "feet/boots/feet_boots_rim.json"),
    PackItem("boots_revised", "shoes", "롱 부츠", "feet/boots/feet_boots_revised.json"),
    PackItem("ankle_socks", "shoes", "앵클 삭스", "feet/socks/feet_socks_ankle.json"),
    PackItem("high_socks", "shoes", "하이 삭스", "feet/socks/feet_socks_high.json"),
    PackItem("leather_cap", "hat", "가죽 산책 모자", "headwear/hats/caps/hat_cap_leather.json", False),
    PackItem("bowler", "hat", "포멀 보울러", "headwear/hats/formal/hat_formal_bowler.json", False),
    PackItem("bandana", "hat", "숲 반다나", "headwear/coverings/bandana/hat_bandana.json", False),
    PackItem("bonnie", "hat", "보니", "headwear/hats/caps/hat_cap_bonnie.json", False),
    PackItem("bonnie_feather", "hat", "깃털 보니", "headwear/hats/caps/hat_cap_bonnie_feather.json", False),
    PackItem("cavalier", "hat", "카발리에", "headwear/hats/caps/hat_cap_cavalier.json", False),
    PackItem("leather_feather", "hat", "깃털 가죽캡", "headwear/hats/caps/hat_cap_leather_feather.json", False),
    PackItem("crown", "hat", "왕관", "headwear/hats/formal/hat_formal_crown.json", False),
    PackItem("tiara", "hat", "티아라", "headwear/hats/formal/hat_formal_tiara.json", False),
    PackItem("tophat", "hat", "톱햇", "headwear/hats/formal/hat_formal_tophat.json", False),
    PackItem("wizard", "hat", "마법사", "headwear/hats/magic/hat_magic_wizard.json", False),
    PackItem("wizard_buckle", "hat", "버클 마법사", "headwear/hats/magic/hat_magic_wizard_buckle.json", False),
    PackItem("celestial", "hat", "천체 모자", "headwear/hats/magic/hat_magic_celestial.json", False),
    PackItem("celestial_moon", "hat", "달 모자", "headwear/hats/magic/hat_magic_celestial_moon.json", False),
    PackItem("santa", "hat", "산타", "headwear/hats/holiday/hat_holiday_santa.json", False),
    PackItem("elf", "hat", "엘프", "headwear/hats/holiday/hat_holiday_elf.json", False),
    PackItem("tricorne", "hat", "트라이콘", "headwear/hats/tricorne/hat_tricorne.json", False),
    PackItem("pirate_bandana", "hat", "해적 반다나", "headwear/coverings/bandana/hat_bandana_pirate.json", False),
    PackItem("hijab", "hat", "히잡", "headwear/coverings/hoods/hat_hood_hijab.json", False),
    PackItem("round", "eyewear", "동그란 안경", "headwear/accessories/glasses/facial_glasses_round.json", False),
    PackItem("halfmoon", "eyewear", "반달 안경", "headwear/accessories/glasses/facial_glasses_halfmoon.json", False),
    PackItem("sunglasses", "eyewear", "선글라스", "headwear/accessories/glasses/facial_glasses_sunglasses.json", False),
    PackItem("basic_glasses", "eyewear", "기본 안경", "headwear/accessories/glasses/facial_glasses.json", False),
    PackItem("nerd", "eyewear", "너드 안경", "headwear/accessories/glasses/facial_glasses_nerd.json", False),
    PackItem("secretary", "eyewear", "세크리터리", "headwear/accessories/glasses/facial_glasses_secretary.json", False),
    PackItem("shades", "eyewear", "셰이드", "headwear/accessories/glasses/facial_glasses_shades.json", False),
    PackItem("patch_left", "eyewear", "왼쪽 안대", "headwear/accessories/eyepatch/facial_eyepatch_left.json", False),
    PackItem(
        "patch_right", "eyewear", "오른쪽 안대", "headwear/accessories/eyepatch/facial_eyepatch_right.json", False
    ),
    PackItem(
        "patch_small_left",
        "eyewear",
        "작은 왼쪽 안대",
        "headwear/accessories/eyepatch/facial_eyepatch_small_left.json",
        False,
    ),
    PackItem(
        "patch_small_right",
        "eyewear",
        "작은 오른쪽 안대",
        "headwear/accessories/eyepatch/facial_eyepatch_small_right.json",
        False,
    ),
    PackItem("patch_ambi", "eyewear", "양안대", "headwear/accessories/eyepatch/facial_eyepatch_ambi.json", False),
    PackItem("monocle_left", "eyewear", "왼쪽 모노클", "headwear/accessories/monocle/facial_monocle_left.json", False),
    PackItem(
        "monocle_right", "eyewear", "오른쪽 모노클", "headwear/accessories/monocle/facial_monocle_right.json", False
    ),
    PackItem(
        "monocle_frame_left",
        "eyewear",
        "왼쪽 프레임",
        "headwear/accessories/monocle/facial_monocle_left_frame.json",
        False,
    ),
    PackItem(
        "monocle_frame_right",
        "eyewear",
        "오른쪽 프레임",
        "headwear/accessories/monocle/facial_monocle_right_frame.json",
        False,
    ),
    *(
        PackItem(name.removeprefix("face_"), "expression", name, f"head/faces/{name}.json")
        for name in (
            "face_angry",
            "face_angry2",
            "face_blush",
            "face_closed",
            "face_closing",
            "face_eyeroll",
            "face_happy",
            "face_happy2",
            "face_look_l",
            "face_look_r",
            "face_neutral",
            "face_sad",
            "face_sad2",
            "face_shame",
            "face_shock",
            "face_tears",
        )
    ),
    PackItem("thick", "eyebrow", "굵은 눈썹", "head/eyebrows/eyebrows_thick.json"),
    PackItem("thin", "eyebrow", "얇은 눈썹", "head/eyebrows/eyebrows_thin.json"),
    PackItem("big", "nose", "큰 코", "head/nose/head_nose_big.json"),
    PackItem("button", "nose", "버튼 코", "head/nose/head_nose_button.json"),
    PackItem("elderly", "nose", "노년 코", "head/nose/head_nose_elderly.json"),
    PackItem("large", "nose", "넓은 코", "head/nose/head_nose_large.json"),
    PackItem("straight", "nose", "곧은 코", "head/nose/head_nose_straight.json"),
    PackItem("cyclops", "eyes", "특수 눈 1", "head/eyes/eyes_cyclops.json"),
    PackItem("cyclops2", "eyes", "특수 눈 2", "head/eyes/eyes_cyclops2.json"),
    PackItem("wrinkles", "wrinkles", "주름", "head/head_wrinkles.json"),
)

CLOTHING_ROOTS = {"torso": "outfit", "legs": "bottom", "feet": "shoes"}


def is_complete_garment(relative: str, category: str) -> bool:
    """Keep wearable garments, not the component layers used to assemble them.

    The upstream ``torso`` tree also contains pockets, straps, sleeves, trims,
    backpacks and other overlays.  Showing those as a standalone shirt leaves
    the avatar bare and makes animation layers look detached.
    """

    path = relative.lower()
    if category == "outfit":
        excluded = (
            "/accessory/",
            "/backpack/",
            "/cape/",
            "/shirts/sleeves/",
            "longsleeves",
            "_trim.json",
            "_buttons.json",
            "_collar.json",
            "_lace.json",
            "_lapel.json",
            "_pockets.json",
            "_straps.json",
            "_contents_",
            "vneck",
            "scoop",
            "cardigan",
            "polo",
            "laced",
            "/vest/",
            "jacket_frock",
            "jacket_collared",
            "dress_bodice",
            "dress_sash",
            "dress_slit",
            "kimono_oversize",
            "kimono_longsleeve",
            "clothes_robe",
        )
        if any(token in path for token in excluded):
            return False
        # Aprons are official overlay garments.  Runtime places a plain base
        # shirt below them so the torso is never exposed while they animate.
        if "/aprons/" in path:
            return any(token in path for token in ("apron.json", "apron_full.json", "apron_half.json"))
        if any(token in path for token in ("sleeveless", "tanktop", "corset")):
            return False
        return any(token in path for token in ("/shirts/", "/jacket/", "/dresses/", "/armour/", "/vest/"))
    if category == "bottom":
        return not any(token in path for token in ("/accessory/", "_trim.json"))
    if category == "shoes":
        # Feet accessories, socks, sandals and slippers expose most of the
        # underlying foot and read as "barefoot" in the compact editor card.
        # Keep only complete shoes/boots plus the one full-foot armour sheet.
        return "/shoes/" in path or "/boots/" in path or path.endswith("feet_armour.json")
    return True


def garment_sort_key(item: PackItem) -> tuple[int, str]:
    """Put familiar everyday clothing before costumes and armour."""

    everyday = {
        "tshirt": 0,
        "official_torso_shirts_shortsleeve_torso_clothes_shortsleeve": 1,
        "official_torso_shirts_longsleeve_torso_clothes_longsleeve": 2,
        "official_torso_shirts_longsleeve_torso_clothes_longsleeve2": 3,
        "cardigan": 4,
        "short_cardigan": 5,
        "polo": 6,
        "short_polo": 7,
        "buttoned": 8,
        "tshirt_vneck": 9,
        "vneck": 10,
        "formal": 11,
        "blouse": 12,
        "long_blouse": 13,
    }
    if item.item_id in everyday:
        return -1, f"{everyday[item.item_id]:03d}"
    path = item.definition.lower()
    priority = 9
    for index, token in enumerate(
        ("/shirts/", "/jacket/", "/vest/", "/dresses/", "/aprons/", "/pants/", "/skirts/", "/shoes/", "/armour/")
    ):
        if token in path:
            priority = index
            break
    return priority, item.label.casefold()


def discover_official_clothing(source: Path) -> tuple[PackItem, ...]:
    """Return every renderable adult LPC torso, legs and feet definition.

    Existing curated identifiers are preserved so saved outfits continue to
    load, while every other official definition receives a deterministic ID
    derived from its repository path. Child- and pregnancy-only definitions
    are intentionally excluded from this service.
    """

    curated = {item.definition: item for item in ITEMS if item.category in set(CLOTHING_ROOTS.values())}
    discovered: list[PackItem] = []
    for root, category in CLOTHING_ROOTS.items():
        definition_root = source / "sheet_definitions" / root
        for path in sorted(definition_root.rglob("*.json")):
            relative = path.relative_to(source / "sheet_definitions").as_posix()
            lowered = relative.lower()
            if path.stem.startswith("meta_") or "child" in lowered or "pregnant" in lowered:
                continue
            if not is_complete_garment(relative, category):
                continue
            definition = json.loads(path.read_text(encoding="utf-8"))
            layers = [
                value for key, value in definition.items() if key.startswith("layer_") and isinstance(value, dict)
            ]
            if not layers or not any(any(body_type in layer for body_type in BODY_TYPES) for layer in layers):
                continue
            if relative in curated:
                discovered.append(curated[relative])
                continue
            suffix = path.relative_to(definition_root).with_suffix("").as_posix()
            item_id = re.sub(r"[^a-z0-9]+", "_", f"official_{root}_{suffix}".lower()).strip("_")
            label = str(definition.get("name") or path.stem).replace("_", " ").strip()
            discovered.append(PackItem(item_id, category, label, relative))
    return tuple(sorted(discovered, key=garment_sort_key))


def discover_official_mobility(source: Path) -> tuple[PackItem, ...]:
    """Collect the official wheelchair and every adult LPC wing definition."""

    curated = {item.definition: item for item in ITEMS if item.category == "mobility"}
    definitions = [source / "sheet_definitions" / "body" / "wheelchair.json"]
    definitions.extend(sorted((source / "sheet_definitions" / "body" / "wings").rglob("*.json")))
    discovered: list[PackItem] = []
    for path in definitions:
        if path.stem.startswith("meta_"):
            continue
        relative = path.relative_to(source / "sheet_definitions").as_posix()
        if relative in curated:
            discovered.append(curated[relative])
            continue
        definition = json.loads(path.read_text(encoding="utf-8"))
        layers = [value for key, value in definition.items() if key.startswith("layer_") and isinstance(value, dict)]
        if not layers or not any(any(body_type in layer for body_type in BODY_TYPES) for layer in layers):
            continue
        suffix = path.relative_to(source / "sheet_definitions" / "body" / "wings").with_suffix("").as_posix()
        item_id = re.sub(r"[^a-z0-9]+", "_", f"wings_{suffix}".lower()).strip("_")
        label = str(definition.get("name") or path.stem).replace("_", " ").strip()
        discovered.append(PackItem(item_id, "mobility", label, relative))
    return tuple(discovered)


def load_definition(source: Path, relative: str) -> dict[str, Any]:
    path = source / "sheet_definitions" / relative
    if not path.is_file():
        raise FileNotFoundError(f"Missing LPC definition: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def layer_paths(definition: dict[str, Any], body_type: str) -> list[tuple[int, str, str | None]]:
    layers: list[tuple[int, str, str | None]] = []
    for index in range(1, 10):
        layer = definition.get(f"layer_{index}")
        if not isinstance(layer, dict):
            continue
        relative = layer.get(body_type)
        if relative:
            head_type = "female" if body_type == "female" else "male"
            layers.append(
                (
                    int(layer.get("zPos", 100)),
                    str(relative).replace("${head}", head_type),
                    str(layer.get("custom_animation")) if layer.get("custom_animation") else None,
                )
            )
    return sorted(layers, key=lambda value: value[0])


def animation_source(folder: Path, animation: str, preferred_variant: str | None) -> Path | None:
    if preferred_variant:
        candidate = folder / animation / f"{preferred_variant}.png"
        if candidate.is_file():
            return candidate
    candidate = folder / f"{animation}.png"
    if candidate.is_file():
        return candidate
    variants = sorted((folder / animation).glob("*.png"))
    return variants[0] if variants else None


CUSTOM_ANIMATION_TARGETS = {
    "tool_axe": "slash",
    "tool_hammer": "slash",
    "slash_128": "slash",
    "backslash_128": "backslash",
    "halfslash_128": "halfslash",
}


def custom_animation_source(source: Path, relative: str, preferred_variant: str | None) -> Path | None:
    """Find a single-animation LPC sheet stored outside the standard row folders."""
    base = source / "spritesheets" / relative
    if base.is_file():
        return base
    direct = base.with_suffix(".png")
    if direct.is_file():
        return direct
    if preferred_variant:
        variant = base / f"{preferred_variant}.png"
        if variant.is_file():
            return variant
    variants = sorted(base.glob("*.png"))
    return variants[0] if variants else None


def compose_custom_animation_sheet(
    source: Path,
    relative: str,
    custom_animation: str,
    preferred_variant: str | None,
) -> tuple[Image.Image, list[str]]:
    """Normalize official 128px/custom LPC actions into the app's 64px rows."""
    target_animation = CUSTOM_ANIMATION_TARGETS.get(custom_animation)
    path = custom_animation_source(source, relative, preferred_variant)
    custom_frame = 128
    sheet = Image.new(
        "RGBA",
        (SHEET_COLUMNS * custom_frame, SHEET_ROWS * custom_frame),
        (0, 0, 0, 0),
    )
    if target_animation is None or path is None:
        return sheet, []

    raw = Image.open(path).convert("RGBA")
    source_frame = 128 if raw.height >= 128 * 4 and raw.width % 128 == 0 else FRAME
    source_columns = min(SHEET_COLUMNS, raw.width // source_frame)
    source_rows = min(4, raw.height // source_frame)
    target_row = ANIMATION_ROWS[target_animation]
    for direction_row in range(source_rows):
        for frame in range(source_columns):
            tile = raw.crop(
                (
                    frame * source_frame,
                    direction_row * source_frame,
                    (frame + 1) * source_frame,
                    (direction_row + 1) * source_frame,
                )
            )
            if source_frame != custom_frame:
                tile = tile.resize((custom_frame, custom_frame), Image.Resampling.NEAREST)
            sheet.alpha_composite(
                tile,
                (frame * custom_frame, (target_row + direction_row) * custom_frame),
            )
    return sheet, [target_animation]


def compose_layer_sheet(
    source: Path,
    relative: str,
    declared: set[str],
    preferred_variant: str | None,
) -> tuple[Image.Image, list[str]]:
    sheet = Image.new("RGBA", (SHEET_COLUMNS * FRAME, SHEET_ROWS * FRAME), (0, 0, 0, 0))
    supported: list[str] = []
    declared_normalized = set(declared)
    if "watering" in declared:
        declared_normalized.add("thrust")
    for animation, row in ANIMATION_ROWS.items():
        source_animation = "combat" if animation == "combat_idle" else animation
        if source_animation not in declared_normalized and animation not in declared_normalized:
            continue
        path = animation_source(source / "spritesheets" / relative, animation, preferred_variant)
        if path is None and animation == "combat_idle":
            path = animation_source(source / "spritesheets" / relative, "combat", preferred_variant)
        if path is not None:
            layer = Image.open(path).convert("RGBA")
            sheet.alpha_composite(layer, (0, row * FRAME))
            supported.append(animation)
    return sheet, supported


def compose_wheelchair_sheet(
    source: Path, relative: str, preferred_variant: str = "black"
) -> tuple[Image.Image, list[str]]:
    """Normalize the official 2-frame x 4-direction wheelchair into LPC rows."""
    folder = source / "spritesheets" / relative
    source_file = folder / f"{preferred_variant}.png"
    if not source_file.is_file():
        variants = sorted(folder.glob("*.png"))
        if not variants:
            return Image.new("RGBA", (SHEET_COLUMNS * FRAME, SHEET_ROWS * FRAME), (0, 0, 0, 0)), []
        source_file = variants[0]
    raw = Image.open(source_file).convert("RGBA")
    sheet = Image.new("RGBA", (SHEET_COLUMNS * FRAME, SHEET_ROWS * FRAME), (0, 0, 0, 0))
    frame_counts = {"idle": 2, "walk": 9, "run": 8, "sit": 3}
    for animation, frame_count in frame_counts.items():
        row_base = ANIMATION_ROWS[animation]
        for direction_row in range(4):
            for frame in range(frame_count):
                source_frame = frame % 2
                tile = raw.crop(
                    (
                        source_frame * FRAME,
                        direction_row * FRAME,
                        (source_frame + 1) * FRAME,
                        (direction_row + 1) * FRAME,
                    )
                )
                sheet.alpha_composite(tile, (frame * FRAME, (row_base + direction_row) * FRAME))
    return sheet, ["idle", "walk", "run", "sit"]


def credit_records(definition: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for credit in definition.get("credits", []):
        records.append(
            {
                "file": credit.get("file", ""),
                "authors": credit.get("authors", []),
                "licenses": credit.get("licenses", []),
                "urls": credit.get("urls", []),
                "notes": credit.get("notes", ""),
            }
        )
    return records


def build(source: Path, output: Path) -> None:  # noqa: C901
    if not (source / "sheet_definitions").is_dir() or not (source / "spritesheets").is_dir():
        raise FileNotFoundError("--source must be a Universal LPC generator checkout")

    output.mkdir(parents=True, exist_ok=True)
    for old_sheet in output.glob("*.png"):
        old_sheet.unlink()

    manifest: dict[str, Any] = {
        "format": "gandang-lpc-pack-v1",
        "frame": FRAME,
        "columns": SHEET_COLUMNS,
        "rows": SHEET_ROWS,
        "animationRows": ANIMATION_ROWS,
        "directionRows": {"up": 0, "left": 1, "down": 2, "right": 3},
        "source": "Universal-LPC-Spritesheet-Character-Generator",
        "sourceUrl": "https://github.com/liberatedpixelcup/Universal-LPC-Spritesheet-Character-Generator",
        "items": [],
    }
    credits: list[dict[str, Any]] = []

    generated_categories = {*CLOTHING_ROOTS.values(), "mobility"}
    core_items = tuple(item for item in ITEMS if item.category not in generated_categories)
    pack_items = (*core_items, *discover_official_clothing(source), *discover_official_mobility(source))

    for item in pack_items:
        definition = load_definition(source, item.definition)
        preferred_variant = "brown" if "variants" in definition else None
        body_types = BODY_TYPES if item.body_aware else ("male",)
        sources: dict[str, list[dict[str, Any]]] = {}
        animation_union: set[str] = set()
        declared = set(definition.get("animations") or ANIMATION_ROWS)
        for body_type in body_types:
            suffix = body_type if item.body_aware else "adult"
            rendered_layers: list[dict[str, Any]] = []
            paths = layer_paths(definition, body_type)
            if not paths and not item.body_aware:
                paths = layer_paths(definition, "female")
            for layer_index, (z_pos, relative, custom_animation) in enumerate(paths, start=1):
                if item.item_id == "wheelchair":
                    sheet, supported = compose_wheelchair_sheet(source, relative)
                elif custom_animation:
                    sheet, supported = compose_custom_animation_sheet(
                        source, relative, custom_animation, preferred_variant
                    )
                else:
                    sheet, supported = compose_layer_sheet(source, relative, declared, preferred_variant)
                if not supported:
                    continue
                filename = f"{item.category}-{item.item_id}-{suffix}-layer{layer_index}.png"
                sheet.save(output / filename, optimize=True)
                rendered_layers.append(
                    {
                        "file": filename,
                        "z": z_pos,
                        "frameSize": FRAME if item.item_id == "wheelchair" else 128 if custom_animation else FRAME,
                    }
                )
                animation_union.update(supported)
            if rendered_layers:
                sources[body_type] = rendered_layers
        if not sources:
            raise RuntimeError(f"No renderable LPC layers found for {item.item_id}")
        if not item.body_aware:
            for body_type in BODY_TYPES:
                sources[body_type] = sources["male"]
        manifest["items"].append(
            {
                "id": item.item_id,
                "category": item.category,
                "label": item.label,
                "sources": sources,
                "animations": sorted(animation_union, key=lambda value: list(ANIMATION_ROWS).index(value)),
                "definition": item.definition,
            }
        )
        for record in credit_records(definition):
            record["usedBy"] = item.item_id
            credits.append(record)

    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "credits.json").write_text(json.dumps(credits, ensure_ascii=False, indent=2), encoding="utf-8")
    upstream_readme = source / "README.md"
    if upstream_readme.is_file():
        shutil.copy2(upstream_readme, output / "UPSTREAM_README.md")

    print(f"Built {len(manifest['items'])} LPC catalog items in {output}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    build(arguments.source.resolve(), arguments.output.resolve())


if __name__ == "__main__":
    main()
