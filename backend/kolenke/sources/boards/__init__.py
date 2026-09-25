from kolenke.sources.boards.base import Board
from kolenke.sources.boards.enbek import Enbek
from kolenke.sources.boards.habr import Habr

REGISTRY: dict[str, Board] = {b.key: b for b in (Habr(), Enbek())}

__all__ = ["REGISTRY", "Board"]
