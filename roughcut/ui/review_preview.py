from nicegui.element import Element


class ReviewPreview(Element, component='review_preview.js'):
    """Play the source while skipping reviewed cuts locally in the browser."""

    def __init__(self, source: str, cuts: list[list[float]]) -> None:
        super().__init__()
        self._props.update(source=source, cuts=cuts)

    def set_cuts(self, cuts: list[list[float]]) -> None:
        self._props['cuts'] = cuts
        self.update()
