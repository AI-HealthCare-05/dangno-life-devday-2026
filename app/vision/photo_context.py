"""User-reported photo conditions are review hints, never completion evidence."""

from dataclasses import asdict, dataclass
from typing import Literal

PhotoAnswer = Literal["yes", "no", "unsure"]


@dataclass(frozen=True)
class FoodPhotoContext:
    contains_kimchi: PhotoAnswer = "unsure"
    strong_seasoning: PhotoAnswer = "unsure"
    white_food_on_white: PhotoAnswer = "unsure"

    def as_dict(self) -> dict[str, str]:
        return asdict(self)

    @property
    def needs_supplement(self) -> bool:
        return any(answer != "no" for answer in self.as_dict().values())
