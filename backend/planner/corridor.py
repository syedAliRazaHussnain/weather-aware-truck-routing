"""The heatmap: which squares around the routes to colour, and their hourly risk.

Pure functions only: no Django, no network calls. Comments like "#51" point to
the numbered assumptions in the README.

Squares are cut from a lat/lon grid sized for the routes' average latitude, so
they are close to square on the map. Each square gets one forecast at its centre.
"""

from dataclasses import dataclass
from math import ceil, cos, floor, radians

from planner.geo import Point, haversine_mi
from planner.risk import Weather, assess
from planner.routes import resample

MILES_PER_DEGREE_LAT = 69.094

CORRIDOR_MI = 50.0  # #51: squares within this distance of any route
START_SQUARE_MI = 25.0  # #52: smallest square size
GROWTH = 1.25  # #52: how much bigger squares get each time the budget is exceeded
HEATMAP_HOURS = 49  # #48: slider hours 0-48

Cell = tuple[int, int]  # (row, column) in the grid


@dataclass(frozen=True)
class Grid:
    """A grid of squares `square_mi` across, laid over the routes."""

    square_mi: float
    ref_lat: float  # latitude the squares are sized for

    @property
    def cell_lat(self) -> float:
        """Height of one square in degrees of latitude."""
        return self.square_mi / MILES_PER_DEGREE_LAT

    @property
    def cell_lon(self) -> float:
        """Width of one square in degrees of longitude."""
        return self.square_mi / (MILES_PER_DEGREE_LAT * max(cos(radians(self.ref_lat)), 0.01))

    def cell_of(self, p: Point) -> Cell:
        """The square a point falls in."""
        return floor(p[0] / self.cell_lat), floor(p[1] / self.cell_lon)

    def center(self, cell: Cell) -> Point:
        """The middle of a square, where its forecast is taken."""
        return (cell[0] + 0.5) * self.cell_lat, (cell[1] + 0.5) * self.cell_lon

    def corners(self, cell: Cell) -> list[Point]:
        """The square's outline, closed (first corner repeated), for drawing on the map."""
        south, west = cell[0] * self.cell_lat, cell[1] * self.cell_lon
        north, east = south + self.cell_lat, west + self.cell_lon
        return [(south, west), (south, east), (north, east), (north, west), (south, west)]


def corridor_cells(
    paths: list[list[Point]], grid: Grid, corridor_mi: float = CORRIDOR_MI
) -> set[Cell]:
    """Every square whose centre is within `corridor_mi` of any route (#51)."""
    reach = ceil(corridor_mi / grid.square_mi) + 1  # squares to look at around each point
    cells: set[Cell] = set()
    for path in paths:
        for p in resample(path, every_mi=grid.square_mi / 2):
            row, col = grid.cell_of(p)
            cells.add((row, col))  # the route itself is always covered, even by big squares
            for dr in range(-reach, reach + 1):
                for dc in range(-reach, reach + 1):
                    cell = (row + dr, col + dc)
                    if cell not in cells and haversine_mi(grid.center(cell), p) <= corridor_mi:
                        cells.add(cell)
    return cells


def plan_heatmap(paths: list[list[Point]], max_cells: int) -> tuple[Grid, set[Cell]]:
    """The smallest squares (from 25 mi up) that cover the corridor within budget (#52)."""
    if max_cells < 1:
        raise ValueError("the heatmap needs room for at least one square")
    ref_lat = sum(lat for path in paths for lat, _ in path) / sum(len(path) for path in paths)
    square_mi = START_SQUARE_MI
    while True:
        grid = Grid(square_mi=square_mi, ref_lat=ref_lat)
        cells = corridor_cells(paths, grid)
        if len(cells) <= max_cells:
            return grid, cells
        square_mi *= GROWTH  # #37: bigger squares before anything else gives way


def hourly_levels(series: list[Weather], load_lb: float) -> list[int]:
    """Risk level (0-4) for each hour of one square, with the driver's load (#49, #50)."""
    return [int(assess(weather, load_lb).level) for weather in series]
