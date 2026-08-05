"""
v01 TextDelta — her partial buyumesinde delta.
Kisa/yarim kelime de gecer: "c" -> "ca" -> "cabuk" hepsi live.
"""
from __future__ import annotations


def filter_garbage(text: str) -> str:
    return (text or "").strip()


def compute_delta(typed_session: str, new_text: str) -> str:
    """typed = klavyeye basilan (veya onceki full hyp), new = model full hyp."""
    old = typed_session or ""
    neu = (new_text or "").strip()
    if not neu:
        return ""
    if not old.strip():
        return neu

    # case-insensitive prefix growth (en canli yol)
    o = old
    n = neu
    # eger typed tam hipotez degil de "basilan" ise: old often equals previous full
    if n.lower().startswith(o.lower()):
        return n[len(o) :]

    # model kisaltti — bekle, silme
    if o.lower().startswith(n.lower()):
        return ""

    # kelime hizala (v01)
    ow, nw = o.split(), n.split()
    match = 0
    for i in range(min(len(ow), len(nw))):
        a = ow[i].strip(".,?!;:-_\"'()[]{}").lower()
        b = nw[i].strip(".,?!;:-_\"'()[]{}").lower()
        if a == b:
            match = i + 1
        else:
            break

    if match == 0 and ow:
        # basindan rewrite — yarisini bozma, bekle
        return ""

    if match < len(nw):
        delta = " ".join(nw[match:])
        if o and not o.endswith(" ") and delta and not delta.startswith(" "):
            delta = " " + delta
        return delta
    return ""
