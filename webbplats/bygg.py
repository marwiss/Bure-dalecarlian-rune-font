#!/usr/bin/env python3
"""Bygger webbplatsen för typsnittet Bure: sidan, typsnittsfilerna, ikonen och licensen.

  python -I bygg.py --summa <början av sha256> <kalla> <sida> <ut>

  kalla  Bure-Regular.otf och mappning-runblocket.csv ur typsnittets mapp (Documents\\Bure font)
  sida   mallarna index.html och stil.css, skriptet prov.js och licensen OFL.txt
  ut     webbplatsens filer; mappen ska saknas eller vara tom
  summa  början av typsnittsfilens sha256 (SUMMA i compose.yaml)

Körs i byggsteget i Dockerfile, med fonttools och brotli. Typsnittsfilen publiceras oförändrad, byte för byte
som i typsnittets mapp (F66 c). Bygget stannar (slutkod 1) om filen inte är den som compose.yaml anger, om den
saknar upphovsrätt och licens, om WOFF2-filen inte har samma tecken, mått och tabeller som OTF-filen, om
mappningen eller licensen inte har väntad form, eller om något som sidans fasta text säger om typsnittet inte
längre stämmer. Allt som sätts in i sidan ur filerna escapas.
"""
import argparse
import csv
import hashlib
import html
import io
import os
import re
import sys
import unicodedata

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

# Licensen (F46, F47). OFL.txt: rad 1 och 2, och därefter SIL:s text från tomraden efter mallens
# upphovsrättsrader till slutet (https://openfontlicense.org/documents/OFL.txt), oförändrad och med LF.
# Typsnittsfilen bär samma upphovsrätt, licensen och licensadressen (F66 c; inlagda med licensrader.py).
NAMN = "Bure"
UPPHOVSRATT = "Copyright (c) 2026, Martin Wiss"
OFL_RAD1 = UPPHOVSRATT + ","
OFL_RAD2 = f"with Reserved Font Name {NAMN}."
OFL_RESTEN_SHA256 = "3e30b6b3044d4856ed99ccefb56c67e194aa1df1a66c7c56d73175999e54861f"
LICENS_TEXT = ("This Font Software is licensed under the SIL Open Font License, Version 1.1. "
               "This license is available with a FAQ at: https://openfontlicense.org")
LICENS_ADRESS = "https://openfontlicense.org"

# Mappningens kolumner i filens ordning. En ändrad rubrikrad stoppar bygget: kolumnernas innebörd kan ha ändrats.
# Kolumnen kommentar visas inte (F67 b).
KOLUMNER = ["latin", "glyfnamn", "form i Bure", "kodpunkt", "runtecken", "unicodenamn", "grund", "säkerhet",
            "kommentar"]
VISAS_INTE = {"kommentar"}
# Rader vars första kolumn inte är tecknen själva, och det som visas med Bure (som i arbetsfiler/skript/mapping.py).
VISAS_SOM = {"ordskiljare": "᛫", "meningsskiljare": "᛬", "0–9": "0123456789"}
RUNBLOCKET = range(0x16A0, 0x1700)
GRUPPER = (("Gemener", "Ll"), ("Versaler", "Lu"), ("Siffror", "Nd"), ("Skiljetecken", "P"))
ORD = "noll en två tre fyra fem sex sju åtta nio tio elva tolv".split()
IKON = "b"                 # tecknet vars glyf blir sidans ikon
IKON_FARG = "#8a3c0c"      # samma som --accent i stil.css (ljust läge)
e = html.escape


def stopp(text):
    sys.exit("FEL: " + text)


def tal(n):
    return f"{n:,}".replace(",", " ")


def tal_ord(n):
    return ORD[n] if 0 <= n < len(ORD) else tal(n)


def lista(delar):
    delar = list(delar)
    return delar[0] if len(delar) == 1 else ", ".join(delar[:-1]) + " och " + delar[-1]


def las_font(data):
    return TTFont(io.BytesIO(data), recalcBBoxes=False, recalcTimestamp=False)


def spara(font):
    ut = io.BytesIO()
    font.save(ut)
    return ut.getvalue()


def former(font):
    """Glyfnamn -> (kontur, bredd) för varje glyf."""
    gs = font.getGlyphSet()
    ut = {}
    for glyf in font.getGlyphOrder():
        pen = RecordingPen()
        gs[glyf].draw(pen)
        ut[glyf] = (tuple((op, tuple(a)) for op, a in pen.value), font["hmtx"][glyf][0])
    return ut


def samma_glyfer(a, b, vad):
    """Stannar om b inte har samma glyfer, teckenkarta, mått och konturer som a."""
    if a.getGlyphOrder() != b.getGlyphOrder():
        stopp(f"{vad}: glyfordningen skiljer")
    if a.getBestCmap() != b.getBestCmap():
        stopp(f"{vad}: teckenkartan skiljer")
    if a["hmtx"].metrics != b["hmtx"].metrics:
        stopp(f"{vad}: måtten (hmtx) skiljer")
    if former(a) != former(b):
        stopp(f"{vad}: konturerna skiljer")


def har_licensen(font):
    """F66 c: filen bär upphovsrätt, licens och licensadress (namn-id 0, 13 och 14, även CFF Notice), och fsType 0."""
    for nid, text in ((0, UPPHOVSRATT), (13, LICENS_TEXT), (14, LICENS_ADRESS)):
        poster = [n.toUnicode() for n in font["name"].names if n.nameID == nid]
        if not poster or any(p != text for p in poster):
            stopp(f"typsnittsfilen har namn-id {nid} {poster}, inte {text!r} (F66 c: lägg in raderna med licensrader.py)")
    if font["OS/2"].fsType != 0 or getattr(font["CFF "].cff.topDictIndex[0], "Notice", None) != UPPHOVSRATT:
        stopp("typsnittsfilen har inte fsType 0 och upphovsrätten i CFF-fältet Notice (F66 c)")


def gor_woff2(otf):
    f = las_font(otf)
    f.flavor = "woff2"
    return spara(f)


def samma_tabeller(a, b, vad):
    """Stannar om en tabell i b skiljer byte för byte från a. head får bara skilja i checkSumAdjustment
    (byte 8-11) och i flaggbit 11, som WOFF2 sätter (förlustfritt omvandlad fil)."""
    if sorted(a.reader.keys()) != sorted(b.reader.keys()):
        stopp(f"{vad}: tabellerna {sorted(b.reader.keys())} i stället för {sorted(a.reader.keys())}")
    for tagg in a.reader.keys():
        ra, rb = a.reader[tagg], b.reader[tagg]
        if ra == rb:
            continue
        if tagg == "head" and len(ra) == len(rb) and ra[:8] == rb[:8] and ra[12:16] == rb[12:16] \
                and ra[18:] == rb[18:] and (int.from_bytes(ra[16:18], "big") ^ int.from_bytes(rb[16:18], "big")) & ~0x0800 == 0:
            continue
        stopp(f"{vad}: tabellen {tagg.strip()} skiljer")
    samma_glyfer(a, b, vad)


def kontrollera_texten(font, cmap, form):
    """Det som sidans fasta text (index.html) säger om typsnittet. Stämmer det inte längre stannar bygget, och
    texten skrivs om innan sidan byggs."""
    if font["name"].getDebugName(1) != NAMN:
        stopp(f"typsnittet heter {font['name'].getDebugName(1)!r}, men sidan och licensen (F47) säger {NAMN}")
    for tabell in ("GSUB", "GPOS", "kern"):
        if tabell in font:
            stopp(f"typsnittet har tabellen {tabell}, men sidan säger att det saknar kerning och OpenType-funktioner")
    if sorted(k for k in cmap if k in RUNBLOCKET) != [0x16EB, 0x16EC]:
        stopp("sidan säger att bara ᛫ U+16EB och ᛬ U+16EC ur runblocket finns i typsnittet")
    if form[cmap[0x20]][0] or form[cmap[0x2E]] != form[cmap[0x16EC]]:
        stopp("sidan säger att mellanslaget är tomt och att punkten har samma form som ᛬")
    andra = [f"U+{k:04X}" for k in cmap if not re.match(r"Ll|Lu|Nd|P|Zs", unicodedata.category(chr(k)))]
    if andra:
        stopp("sidans grupper av tecken saknar " + ", ".join(andra))


def las_licens(vag):
    data = open(vag, "rb").read()
    delar = data.split(b"\n", 2)
    if len(delar) != 3 or delar[0] != OFL_RAD1.encode() or delar[1] != OFL_RAD2.encode() \
            or hashlib.sha256(delar[2]).hexdigest() != OFL_RESTEN_SHA256:
        stopp("OFL.txt har inte rad 1 och 2 enligt F46 och F47 och därefter SIL:s oförändrade text med LF")
    return data


def las_mappning(vag, cmap):
    with open(vag, encoding="utf-8-sig", newline="") as f:
        rader = list(csv.reader(f, delimiter=";"))
    if not rader or rader[0] != KOLUMNER:
        stopp(f"mappningens rubrikrad är {rader[0] if rader else None}, inte {KOLUMNER}")
    data = []
    for nr, rad in enumerate(rader[1:], start=2):
        if len(rad) != len(KOLUMNER):
            stopp(f"rad {nr} i mappningen har {len(rad)} fält, inte {len(KOLUMNER)}")
        r = dict(zip(KOLUMNER, rad))
        if r["kodpunkt"]:
            m = re.fullmatch(r"U\+([0-9A-F]{4,6})", r["kodpunkt"])
            if not m or int(m.group(1), 16) not in RUNBLOCKET or r["runtecken"] != chr(int(m.group(1), 16)):
                stopp(f"rad {nr} i mappningen: kodpunkten {r['kodpunkt']!r} är inte runtecknet {r['runtecken']!r} i runblocket")
            r["kod"] = int(m.group(1), 16)
        elif r["runtecken"]:
            stopp(f"rad {nr} i mappningen har ett runtecken men ingen kodpunkt")
        tecken = r["latin"].split()
        if tecken and all(len(t) == 1 for t in tecken):
            r["visas"] = " ".join(tecken)
        elif r["latin"] in VISAS_SOM:
            r["visas"] = VISAS_SOM[r["latin"]]
        else:
            stopp(f"rad {nr} i mappningen: okänt vad {r['latin']!r} ska visas som med Bure (VISAS_SOM i bygg.py)")
        saknas = [t for t in r["visas"] if t != " " and ord(t) not in cmap]
        if saknas:
            stopp(f"rad {nr} i mappningen: {''.join(saknas)!r} finns inte i typsnittet")
        data.append(r)
    return data


def etikett(t):
    return e(t) if ord(t) < 0x250 else f"U+{ord(t):04X}"


def teckengrupper(cmap):
    ut, antal = [], {}
    for rubrik, kategori in GRUPPER:
        tecken = [chr(k) for k in sorted(cmap) if unicodedata.category(chr(k)).startswith(kategori)]
        antal[rubrik] = len(tecken)
        rutor = "\n".join(f'<li><span class="bure" aria-hidden="true">{e(t)}</span>'
                          f'<span class="latin">{etikett(t)}</span></li>' for t in tecken)
        ut.append(f'<h3>{rubrik} <span class="antal">({len(tecken)})</span></h3>\n<ul class="tecken">\n{rutor}\n</ul>')
    return "\n".join(ut), antal


def lika_former(cmap, form):
    """Tecken med samma kontur och bredd: en lista över grupperna, och versalerna som har gemenens form."""
    per_form = {}
    for k in sorted(cmap):
        if unicodedata.category(chr(k)) != "Zs":
            per_form.setdefault(form[cmap[k]], []).append(chr(k))
    grupper, versal_gemen = [], []
    for tecken in per_form.values():
        if len(tecken) == 2 and tecken[0].lower() == tecken[1]:
            versal_gemen.append(tecken[0])
        elif len(tecken) > 1:
            grupper.append(f'<li><span class="bure" aria-hidden="true">{e(tecken[0])}</span>'
                           f'{" = ".join(e(t) for t in tecken)}</li>')
    versaler = [chr(k) for k in cmap if unicodedata.category(chr(k)) == "Lu"]
    return "\n".join(grupper), lista(versal_gemen), len(versaler) - len(versal_gemen)


def tabell(data, cmap):
    kolumner = [k for k in KOLUMNER[1:] if k not in VISAS_INTE]
    rubriker = "".join(f'<th scope="col">{e(k[0].upper() + k[1:])}</th>' for k in kolumner)
    rader = []
    for r in data:
        celler = [f'<th scope="row">{e(r["latin"])}</th>', f'<td class="bure">{e(r["visas"])}</td>']
        for k in kolumner:
            text = e(r[k])
            if k == "kodpunkt" and r.get("kod") in cmap:
                text += ' <span class="finns">finns i Bure</span>'
            celler.append(f'<td class="runa">{text}</td>' if k == "runtecken" else f"<td>{text}</td>")
        rader.append("<tr>" + "".join(celler) + "</tr>")
    return (f'<thead><tr><th scope="col">{e(KOLUMNER[0][0].upper() + KOLUMNER[0][1:])}</th><th scope="col">Bure</th>'
            f'{rubriker}</tr></thead>\n<tbody>\n' + "\n".join(rader) + "\n</tbody>")


def ikon(font, cmap):
    """Sidans ikon: glyfen för IKON, vit på en rundad ruta."""
    gs = font.getGlyphSet()
    glyf = cmap[ord(IKON)]
    pen, ram = SVGPathPen(gs), BoundsPen(gs)
    gs[glyf].draw(pen)
    gs[glyf].draw(ram)
    x0, y0, x1, y1 = ram.bounds
    sida = round(max(x1 - x0, y1 - y0) * 1.3)
    vx, vy = round((x0 + x1 - sida) / 2), round(-(y0 + y1 + sida) / 2)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vx} {vy} {sida} {sida}">'
            f'<rect x="{vx}" y="{vy}" width="{sida}" height="{sida}" rx="{sida // 6}" fill="{IKON_FARG}"/>'
            f'<path transform="scale(1 -1)" fill="#fff" d="{pen.getCommands()}"/></svg>\n').encode()


def fyll(mall, varden, namn):
    def ersatt(m):
        if m.group(1) not in varden:
            stopp(f"{namn}: okänd platshållare {m.group(0)}")
        return str(varden[m.group(1)])
    text = re.sub(r"\{\{([a-z0-9_]+)\}\}", ersatt, mall)
    if "{{" in text:
        stopp(f"{namn}: en platshållare blev kvar")
    return text


def main():
    p = argparse.ArgumentParser(description="Bygger webbplatsen för typsnittet Bure.")
    p.add_argument("--summa", required=True, help="början av typsnittsfilens sha256 (SUMMA i compose.yaml)")
    p.add_argument("kalla")
    p.add_argument("sida")
    p.add_argument("ut")
    a = p.parse_args()

    otf_vag = os.path.join(a.kalla, "Bure-Regular.otf")
    csv_vag = os.path.join(a.kalla, "mappning-runblocket.csv")
    mallar = {n: os.path.join(a.sida, n) for n in ("index.html", "stil.css", "prov.js", "OFL.txt")}
    if os.path.exists(a.ut) and os.listdir(a.ut):
        stopp(f"{a.ut} är inte tom")

    # 1. Typsnittsfilen publiceras oförändrad, och den ska vara den som compose.yaml anger.
    otf = open(otf_vag, "rb").read()
    summa = hashlib.sha256(otf).hexdigest()
    if not re.fullmatch(r"[0-9a-f]{8,64}", a.summa) or not summa.startswith(a.summa):
        stopp(f"Bure-Regular.otf har sha256 {summa}, men compose.yaml anger SUMMA {a.summa!r}. Ska den här filen "
              f"publiceras: sätt SUMMA: \"{summa[:8]}\" och image: hemsidor-bure:<ååååmmdd>-{summa[:8]} i compose.yaml.")
    font = las_font(otf)
    har_licensen(font)
    cmap = font.getBestCmap()
    form = former(font)
    kontrollera_texten(font, cmap, form)
    ofl = las_licens(mallar["OFL.txt"])

    # 2. WOFF2: samma tecken, mått och tabeller som OTF-filen, och samma fil vid varje bygge.
    woff2 = gor_woff2(otf)
    if gor_woff2(otf) != woff2:
        stopp("WOFF2-filen blir olika vid två byggen")
    samma_tabeller(las_font(otf), las_font(woff2), "WOFF2-filen")
    woff2_summa = hashlib.sha256(woff2).hexdigest()
    woff2_adress = f"typsnitt/Bure-Regular.{woff2_summa[:16]}.woff2"

    # 3. Mappningen och sidans delar.
    data = las_mappning(csv_vag, cmap)
    grupper, antal = teckengrupper(cmap)
    lika, versal_gemen, egna_versaler = lika_former(cmap, form)
    kodpunkter = [r["kod"] for r in data if "kod" in r]
    i_bure = sorted({k for k in kodpunkter if k in cmap})
    version = re.fullmatch(r"Version (\d+(?:\.\d+)+)", font["name"].getDebugName(5) or "")
    if not version:
        stopp(f"namntabellens version är {font['name'].getDebugName(5)!r}")

    varden = {
        "version": version.group(1),
        "woff2_adress": woff2_adress,
        "n_tecken": tal(sum(antal.values())),
        "n_gemener": tal(antal["Gemener"]),
        "n_versaler": tal(antal["Versaler"]),
        "n_siffror": tal_ord(antal["Siffror"]),
        "n_skiljetecken": tal_ord(antal["Skiljetecken"]),
        "teckengrupper": grupper,
        "lika_former": lika,
        "versal_gemen": e(versal_gemen),
        "n_egna_versaler": tal(egna_versaler),
        "n_rader": tal(len(data)),
        "n_kodpunkter": tal(len(kodpunkter)),
        "n_i_bure": tal_ord(len(i_bure)),
        "i_bure": lista(f'<span class="bure">{e(chr(k))}</span> U+{k:04X}' for k in i_bure),
        "tabell": tabell(data, cmap),
        "otf_storlek": tal(len(otf)),
        "otf_summa": summa,
        "woff2_storlek": tal(len(woff2)),
        "woff2_summa": woff2_summa,
        "upphovsratt": e(f"{OFL_RAD1} {OFL_RAD2}"),
    }
    sidan = fyll(open(mallar["index.html"], encoding="utf-8").read(), varden, "index.html")
    if re.search(r"(?i)<style|\sstyle=|<script(?![^>]*\ssrc=)|\son[a-z]+=", sidan):
        stopp("index.html har en inbäddad stil, ett inbäddat skript eller en händelse i ett attribut, "
              "som innehållsregeln i nginx.conf stoppar")
    utifran = re.findall(r'(?:src|href)="((?:https?:)?//[^"]*)"', sidan)
    if utifran:
        stopp("index.html hänvisar till andra värdar: " + ", ".join(utifran))
    stil = fyll(open(mallar["stil.css"], encoding="utf-8").read(), varden, "stil.css")

    # 4. Filerna. Tiden sätts till den nyaste indatafilens, så att ETag bara byts när något har ändrats.
    filer = {
        "index.html": sidan.encode(),
        "stil.css": stil.encode(),
        "prov.js": open(mallar["prov.js"], "rb").read(),
        "ikon.svg": ikon(font, cmap),
        "OFL.txt": ofl,
        "Bure-Regular.otf": otf,
        "Bure-Regular.woff2": woff2,
        woff2_adress: woff2,
    }
    tid = int(max(os.stat(v).st_mtime for v in [otf_vag, csv_vag, os.path.abspath(__file__), *mallar.values()]))
    for namn, innehall in filer.items():
        vag = os.path.join(a.ut, namn)
        os.makedirs(os.path.dirname(vag), exist_ok=True)
        with open(vag, "wb") as f:
            f.write(innehall)
    for rot, _mappar, namn in os.walk(a.ut):
        for v in [rot] + [os.path.join(rot, n) for n in namn]:
            os.chmod(v, 0o755 if v == rot else 0o644)
            os.utime(v, (tid, tid))

    print(f"Bure-Regular.otf, version {version.group(1)}, oförändrad ur typsnittets mapp: {len(otf)} byte, sha256 {summa}")
    print(f"WOFF2 {len(woff2)} byte, sha256 {woff2_summa}: samma tecken, mått och tabeller som OTF-filen")
    print(f"{sum(antal.values())} tecken i {len(GRUPPER)} grupper, mappningen {len(data)} rader, "
          f"{len(i_bure)} av {len(kodpunkter)} kodpunkter finns i typsnittet; {len(filer)} filer i {a.ut}")


if __name__ == "__main__":
    main()
