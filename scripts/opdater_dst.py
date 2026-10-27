#!/usr/bin/env python3
"""
Henter de nyeste tal fra Danmarks Statistiks åbne API (api.statbank.dk)
og opdaterer datafilerne:

  data/loenindeks.csv         Standardberegnet lønindeks, årlig stigning
  data/byggeomkostninger.csv  Byggeomkostningsindeks for boliger
  data/forbrugerpriser.csv    Forbrugerprisindeks, årlig stigning

Scriptet finder selv variabler og værdier ud fra tabellernes tekster og
sammenligner de perioder, der allerede ligger i filerne, med de nye tal.
Afviger et overlappende tal, stopper det uden at skrive noget, så en
ændret tabel hos Danmarks Statistik aldrig giver forkerte tal på siden.

Kun Pythons standardbibliotek bruges. Kør:  python3 scripts/opdater_dst.py
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

API = "https://api.statbank.dk/v1"
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TOLERANCE = 0.15  # største tilladte afvigelse på overlappende perioder


class Stop(Exception):
    """En fejl, der skal stoppe opdateringen af én kilde."""


# ---------------------------------------------------------------- API
def post(path: str, body: dict) -> str:
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "markedsovervaagning/1.0"},
    )
    with urllib.request.urlopen(req, timeout=60) as res:
        return res.read().decode("utf-8-sig")


def tableinfo(table: str) -> dict:
    return json.loads(post("/tableinfo", {"table": table, "format": "JSON", "lang": "da"}))


def fetch(table: str, selection: dict[str, list[str]]) -> list[dict]:
    body = {
        "table": table,
        "format": "BULK",
        "lang": "da",
        "valuePresentation": "Code",
        "variables": [{"code": k, "values": v} for k, v in selection.items()],
    }
    text = post("/data", body)
    rows = [{k.strip().upper(): (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(io.StringIO(text), delimiter=";")]
    if not rows:
        raise Stop(f"{table}: tomt svar")
    return rows


def number(s: str) -> float | None:
    s = (s or "").strip().replace(",", ".")
    if s in ("", "..", "-", ".."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# --------------------------------------------------------- matching
def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


def time_var(info: dict) -> dict:
    for v in info["variables"]:
        if v.get("time") or v["id"].upper() == "TID":
            return v
    raise Stop(f"{info['id']}: ingen tidsvariabel")


def pick(var: dict, *patterns: str) -> str | None:
    """Første værdi i variablen, hvis tekst matcher et af mønstrene (i rækkefølge)."""
    for pat in patterns:
        rx = re.compile(pat, re.I)
        for val in var["values"]:
            if rx.search(norm(val["text"])):
                return val["id"]
    return None


def describe(info: dict) -> str:
    out = [f"Tabel {info['id']}: {info.get('text', '')}"]
    for v in info["variables"]:
        vals = ", ".join(f"{x['id']}={x['text']}" for x in v["values"][:12])
        out.append(f"  {v['id']} ({v['text']}): {vals}{' …' if len(v['values']) > 12 else ''}")
    return "\n".join(out)


def first_working(candidates: list[str], build) -> tuple[str, dict, object]:
    errors = []
    for table in candidates:
        try:
            info = tableinfo(table)
        except Exception as err:  # tabellen findes ikke
            errors.append(f"{table}: {err}")
            continue
        try:
            return table, info, build(info)
        except Stop as err:
            errors.append(f"{err}\n{describe(info)}")
    raise Stop("Ingen af tabellerne passede:\n" + "\n\n".join(errors))


# --------------------------------------------------------- perioder
def quarter_label(code: str) -> str:
    m = re.fullmatch(r"(\d{4})K(\d)", code)
    if not m:
        raise Stop(f"uventet kvartalskode {code}")
    return f"Q{m.group(2)} {m.group(1)}"


def month_label(code: str) -> str:
    m = re.fullmatch(r"(\d{4})M(\d{2})", code)
    if not m:
        raise Stop(f"uventet månedskode {code}")
    return f"{m.group(1)}-{m.group(2)}"


def yoy(series: dict[str, float], lag: int) -> dict[str, float]:
    keys = sorted(series)
    out = {}
    for i, k in enumerate(keys):
        if i >= lag and series[keys[i - lag]]:
            out[k] = round((series[k] / series[keys[i - lag]] - 1) * 100, 1)
    return out


# ------------------------------------------------------------ kilder
def build_loen(info: dict):
    tid = time_var(info)
    sel, sector_var, is_change = {}, None, False
    for v in info["variables"]:
        if v is tid:
            continue
        priv = pick(v, r"virksomheder og organisationer")
        alle = pick(v, r"sektorer i alt", r"^i alt$", r"alle sektorer")
        if priv and alle:
            sector_var = v
            sel[v["id"]] = [priv, alle]
            continue
        change = pick(v, r"samme kvartal (året|aaret) før", r"(årlig|aarlig).*(ændring|stigning)")
        if change:
            is_change = True
            sel[v["id"]] = [change]
            continue
        index = pick(v, r"^indeks", r"indeks$")
        if index and re.search(r"enhed|type|indeks", norm(v["text"])):
            sel[v["id"]] = [index]
            continue
        total = pick(v, r"i alt", r"alle")
        if not total:
            raise Stop(f"{info['id']}: kan ikke vælge værdi for {v['id']} ({v['text']})")
        sel[v["id"]] = [total]
    if not sector_var:
        raise Stop(f"{info['id']}: fandt ikke sektorerne")
    sel[tid["id"]] = ["*"]
    rows = fetch(info["id"], sel)
    priv_id, alle_id = sel[sector_var["id"]]
    series = {priv_id: {}, alle_id: {}}
    for r in rows:
        val = number(r.get("INDHOLD", ""))
        if val is None:
            continue
        series[r[sector_var["id"].upper()]][r[tid["id"].upper()]] = val
    if not is_change:
        series = {k: yoy(s, 4) for k, s in series.items()}
    periods = sorted(set(series[priv_id]) & set(series[alle_id]))
    if not periods:
        raise Stop(f"{info['id']}: ingen tal")
    return [
        {"kvartal": quarter_label(p), "privat_aarlig_stigning": f"{series[priv_id][p]:.1f}",
         "alle_sektorer_aarlig_stigning": f"{series[alle_id][p]:.1f}"}
        for p in periods
    ][-8:]


def build_byg(info: dict):
    tid = time_var(info)
    sel, art_var = {}, None
    for v in info["variables"]:
        if v is tid:
            continue
        mat = pick(v, r"^materialer$", r"materialer")
        arb = pick(v, r"^arbejdsløn$", r"arbejdsløn", r"arbejdsomkostning", r"^arbejde")
        tot = pick(v, r"^i alt$", r"byggeomkostningsindeks i alt", r"i alt")
        if mat and arb and tot:
            art_var = v
            sel[v["id"]] = [tot, mat, arb]
            continue
        index = pick(v, r"^indeks$", r"^indeks", r"indeks \(")
        if index and re.search(r"enhed|type", norm(v["text"])):
            sel[v["id"]] = [index]
            continue
        total = pick(v, r"boliger i alt", r"^i alt$", r"i alt", r"boliger")
        if not total:
            raise Stop(f"{info['id']}: kan ikke vælge værdi for {v['id']} ({v['text']})")
        sel[v["id"]] = [total]
    if not art_var:
        raise Stop(f"{info['id']}: fandt ikke i alt/materialer/arbejdsløn")
    sel[tid["id"]] = ["*"]
    rows = fetch(info["id"], sel)
    tot_id, mat_id, arb_id = sel[art_var["id"]]
    s: dict[str, dict[str, float]] = {}
    for r in rows:
        val = number(r.get("INDHOLD", ""))
        if val is not None:
            s.setdefault(r[tid["id"].upper()], {})[r[art_var["id"].upper()]] = val
    periods = sorted(p for p, d in s.items() if {tot_id, mat_id, arb_id} <= set(d))
    if not periods:
        raise Stop(f"{info['id']}: ingen tal")
    return [
        {"kvartal": quarter_label(p), "i_alt": f"{s[p][tot_id]:.1f}",
         "materialer": f"{s[p][mat_id]:.1f}", "arbejdsloen": f"{s[p][arb_id]:.1f}"}
        for p in periods
    ][-8:]


def build_fpi(info: dict):
    tid = time_var(info)
    sel, change_found = {}, False
    for v in info["variables"]:
        if v is tid:
            continue
        change = pick(v, r"samme måned (året|aaret) før", r"(årlig|aarlig).*(ændring|stigning)")
        if change:
            sel[v["id"]] = [change]
            change_found = True
            continue
        total = pick(v, r"forbrugerprisindekset i alt", r"^00\b", r"i alt", r"^indeks$")
        if not total:
            raise Stop(f"{info['id']}: kan ikke vælge værdi for {v['id']} ({v['text']})")
        sel[v["id"]] = [total]
    sel[tid["id"]] = ["*"]
    rows = fetch(info["id"], sel)
    series = {}
    for r in rows:
        val = number(r.get("INDHOLD", ""))
        if val is not None:
            series[r[tid["id"].upper()]] = val
    if not change_found:
        series = yoy(series, 12)
    periods = sorted(series)
    if not periods:
        raise Stop(f"{info['id']}: ingen tal")
    return [{"maaned": month_label(p), "aarlig_stigning": f"{series[p]:.1f}"} for p in periods][-12:]


SOURCES = [
    # (fil, nøglekolonne, kandidattabeller, bygger, dataset-id)
    ("loenindeks.csv", "kvartal", ["SBLON1", "ILON22", "ILON12"], build_loen, "loenindeks"),
    ("byggeomkostninger.csv", "kvartal", ["BYG42", "BYG41"], build_byg, "byggeomkostninger"),
    ("forbrugerpriser.csv", "maaned", ["PRIS111", "PRIS113", "PRIS112"], build_fpi, "forbrugerpriser"),
]


# ------------------------------------------------------------ filer
def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(newline="", encoding="utf-8") as fh:
        r = csv.DictReader(fh)
        return list(r.fieldnames or []), list(r)


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def check_overlap(name: str, key: str, old: list[dict], new: list[dict]) -> None:
    new_by = {r[key]: r for r in new}
    overlap = 0
    for o in old:
        n = new_by.get(o[key])
        if not n:
            continue
        overlap += 1
        for col, val in o.items():
            if col == key:
                continue
            a, b = number(val), number(n.get(col, ""))
            if a is None or b is None or abs(a - b) > TOLERANCE:
                raise Stop(f"{name}: {o[key]} {col} er {val} i filen men {n.get(col)} fra API'et")
    if old and overlap == 0:
        raise Stop(f"{name}: ingen overlappende perioder at kontrollere mod")


def main() -> int:
    manifest_path = DATA / "datasets.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    changed, failed = [], []
    for fname, key, candidates, build, ds_id in SOURCES:
        path = DATA / fname
        fields, old = read_csv(path)
        try:
            table, _, new = first_working(candidates, build)
            check_overlap(fname, key, old, new)
        except Exception as err:  # noqa: BLE001 – rapportér og fortsæt med de andre kilder
            failed.append(f"{fname}: {err}")
            print(f"FEJL {fname}:\n{err}\n", file=sys.stderr)
            continue
        # Behold ældre rækker, som API-udtrækket ikke længere dækker, og tilføj nye
        merged = {r[key]: r for r in old}
        merged.update({r[key]: r for r in new})
        rows = sorted(merged.values(), key=lambda r: r[key] if key == "maaned" else (r[key][3:], r[key][:2]))
        if rows != old:
            write_csv(path, fields, rows)
            manifest["datasets"][ds_id]["opdateret"] = date.today().isoformat()
            manifest["datasets"][ds_id]["af"] = f"GitHub Action, fra Danmarks Statistik ({table})"
            changed.append(f"{fname} ({table}): seneste periode {rows[-1][key]}")
            print(f"Opdateret {fname} fra {table}: {rows[-1]}")
        else:
            print(f"Ingen nye tal i {fname} ({table}).")
    if changed:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n".join(["", "Ændret:"] + (changed or ["intet"])))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
