"""Variable facet (subgroup) handling.

A dataset can store many variables flat in one split (e.g.
``lai_deviation_year``, ``swvl1_deviation_month``, ``rho_bias_lai_year``).
When a ``facet_vocab`` is configured on ``DataConfig``, this module splits
column names on ``"_"`` and attaches a facet value to each name for every
vocabulary facet (e.g. ``group``: ``"lai"``, ``scale``: ``"year"``); tokens
that are not in any vocabulary become the auto-derived ``metric`` facet.

The facets are interchangeable: any combination can be used to filter a
list of names (map picker), or to nest the names into a browse tree
(timeseries browser). Without a configured vocabulary the schema detects
nothing and every name is passed through unchanged (flat mode).
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable


def tokenize(name: str) -> list[str]:
    """Split a column name into lowercase tokens (empty tokens ignored)."""
    return [
        token.strip()
        for token in str(name).lower().split("_")
        if token.strip()
    ]


class FacetSchema:
    """Facet bindings for one namespace of variable names.

    Args:
        names: Column names (map variables or timeseries columns).
        vocab: Facet vocabulary, e.g. ``{"group": ["lai", "swvl1"],
            "scale": ["year", "month"]}``. Facets listed here are the
            configured ones; ``"metric"`` is always available and holds
            the tokens that were not consumed by the vocabulary.
    """

    def __init__(self, names: Iterable[str], vocab: dict[str, list[str]] | None):
        self.vocab = {k: list(v) for k, v in (vocab or {}).items()}
        self.names = list(names)

        # facet -> sorted values found across all names
        self.values: OrderedDict[str, list[str]] = OrderedDict()
        # name -> {facet: value} for vocabulary facets
        self.binding: dict[str, dict[str, str]] = {}
        # name -> sorted metric tokens not consumed by the vocabulary
        self.metric_tokens: dict[str, list[str]] = {}
        self._build()

    def _build(self) -> None:
        for name in self.names:
            tokens = tokenize(name)
            if not tokens:
                continue
            binding: dict[str, str] = {}
            for facet, vocab_tokens in self.vocab.items():
                for token in tokens:
                    if token in vocab_tokens:
                        binding[facet] = token
                        break
            self.binding[name] = binding
            for facet, value in binding.items():
                self._add_value(facet, value)
            if not binding:
                # No vocabulary token: the name is not part of the scheme.
                continue
            vocab_tokens = {t for tokens_ in self.vocab.values() for t in tokens_}
            metric = sorted({t for t in tokens if t not in vocab_tokens})
            self.metric_tokens[name] = metric
            if self._has_metric(name, metric):
                for token in metric:
                    self._add_value("metric", token)

    @staticmethod
    def _has_metric(name: str, metric_tokens: list[str]) -> bool:
        """A name participates in the metric facet when it has leftover
        tokens and is not a bare single-token column (``lat``, ``time``…).
        """
        if len(tokenize(name)) == 1:
            return False
        return bool(metric_tokens)

    def _add_value(self, facet: str, value: str) -> None:
        values = self.values.setdefault(facet, [])
        if value not in values:
            values.append(value)
            values.sort()

    # ------------------------------------------------------------------ #
    # introspection                                                     #
    # ------------------------------------------------------------------ #

    def facet_values(self, facet: str) -> list[str]:
        """Sorted values available for a facet."""
        return list(self.values.get(facet, []))

    def value_of(self, name: str, facet: str) -> str | None:
        """The vocabulary-facet value of a name, or None when it has none.

        Args:
            name: Column name.
            facet: A vocabulary facet (not ``"metric"``).
        """
        return self.binding.get(name, {}).get(facet)

    def has_metric_value(self, name: str, token: str) -> bool:
        """True when the name's metric tokens include ``token``."""
        return token in self.metric_tokens.get(name, [])

    def active_facets(self, include_metric: bool = True) -> list[str]:
        """Vocab facets (then metric) with at least two values each."""
        order = [f for f in self.vocab if len(self.values.get(f, [])) >= 2]
        if include_metric and len(self.values.get("metric", [])) >= 2:
            order.append("metric")
        return order

    def active(self) -> bool:
        """True when the schema detected at least two values of some facet."""
        return bool(self.active_facets())

    # ------------------------------------------------------------------ #
    # filtering (map picker)                                            #
    # ------------------------------------------------------------------ #

    def filter_names(
        self, selection: dict[str, str | None] | None = None
    ) -> list[str]:
        """Names matching every selected facet value (None = no constraint).

        For the ``metric`` facet a name matches when it *contains* the
        selected token.
        """
        selection = {k.lower(): v for k, v in (selection or {}).items() if v}
        out = []
        for name in self.names:
            if all(
                self._matches(name, facet, value)
                for facet, value in selection.items()
            ):
                out.append(name)
        return out

    def _matches(self, name: str, facet: str, value: str) -> bool:
        if facet == "metric":
            return self.has_metric_value(name, value)
        return self.value_of(name, facet) == value

    # ------------------------------------------------------------------ #
    # nesting (timeseries browser)                                      #
    # ------------------------------------------------------------------ #

    def unbound_names(self) -> list[str]:
        """Names not bound to any vocabulary facet (e.g. ``backscatter40``).

        Such columns cannot be reached through the facet dropdowns; they are
        offered to the picker through a dedicated ``other`` facet.
        """
        return sorted(
            name for name in self.names if not self.binding.get(name)
        )

    def group_tree(
        self, facet_order: list[str] | None = None, fallback_value: str = "(unspecified)"
    ) -> dict:
        """Nested facet values -> leaf lists of names.

        The first facet nests outermost; names missing a facet value land
        in ``fallback_value``. A one-facet scheme returns
        ``{value: [names], ...}``; with no facets it returns
        ``{"__all__": names}``.

        Args:
            facet_order: Facets to nest (default: vocab facets with ≥2
                values; metric is never nested because a name can carry
                several metric tokens).
            fallback_value: Label for names without the facet value.

        Returns:
            Nested dict; leaves are sorted lists of names.
        """
        order = facet_order if facet_order is not None else self.active_facets(
            include_metric=False
        )
        if not order:
            return {"__all__": list(self.names)}

        def nest(names: list[str], idx: int) -> dict:
            facet = order[idx]
            buckets: dict[str, list[str]] = {}
            for name in names:
                value = self.value_of(name, facet) or fallback_value
                buckets.setdefault(value, []).append(name)
            for value in buckets:
                buckets[value].sort()
            if idx + 1 == len(order):
                return buckets
            return {
                value: nest(bucket, idx + 1) for value, bucket in buckets.items()
            }

        return nest(list(self.names), 0)
