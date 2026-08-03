"""The impure layer: filesystem, cache, lineage and JSON output.

The split from `ssc.core` is by purity, not by user interface — `workspace` and `cache`
live here despite having nothing to do with argument parsing, because they touch disk.
"""
