#!/usr/bin/env python3
"""Gör den publicerade versionen av Bure: upphovsrätt, licens och licensadress läggs in i typsnittsfilen och
versionen sätts (F66 c, F93 b). Inget annat ändras, och det prövas.

  python -I licensrader.py <arbetskopia.otf> <ny.otf>

Det enda som ändras: namn-id 0 (upphovsrätt), 13 (licens), 14 (licensadress), 3 och 5 (versionen) för Mac och
Windows, head.fontRevision, OS/2.fsType (0, installerbar, som för fria typsnitt) och CFF-fälten version, Notice och
Copyright. Skriptet stannar om den nya filen skiljer i något annat: övriga tabeller ska vara byte för byte lika, i
head, OS/2 och CFF får bara de fälten skilja (jämförda som TTX-text), och glyfer, teckenkarta, mått och konturer ska
vara desamma. Det stannar också om fonttools varnar när den nya filen öppnas och alla tabeller läses. Tiden i head
ändras inte, så samma indata ger alltid samma fil.

Körs med samma fonttools som bygget (krav.txt), utan nät. 2026-11-13 gjordes version 1.0.0 av
Documents\\Bure font\\Bure-dalecarlian-rune-font\\Bure-Regular.otf ur arbetskopian 1.001 (sparad i
backup/2026-11-13/bure/), och den ersatte arbetskopian (F94 a).
"""
import difflib
import hashlib
import io
import logging
import os
import re
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bygg import LICENS_ADRESS, LICENS_TEXT, UPPHOVSRATT, har_licensen, las_font, samma_glyfer, spara, stopp  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402

VERSION = "1.0.0"          # F93 b: den enda versionen. head.fontRevision får de två första talen (1.0).
TILLATNA_NAMN = {0, 3, 5, 13, 14}
TILLATNA_FALT = {"head": {"checkSumAdjustment", "fontRevision"}, "OS/2": {"fsType"},
                 "CFF ": {"version", "Notice", "Copyright"}}


def med_licens(otf):
    f = las_font(otf)
    if any(n.nameID == 0 for n in f["name"].names):
        stopp("filen har redan en upphovsrättsrad (namn-id 0)")
    for n in f["name"].names:
        if n.nameID == 3:
            n.string = re.sub(r"^[0-9.]+;", VERSION + ";", n.toUnicode())
        elif n.nameID == 5:
            n.string = re.sub(r"^Version [0-9.]+$", "Version " + VERSION, n.toUnicode())
    for nid, text in ((0, UPPHOVSRATT), (13, LICENS_TEXT), (14, LICENS_ADRESS)):
        f["name"].setName(text, nid, 1, 0, 0)
        f["name"].setName(text, nid, 3, 1, 0x409)
    f["head"].fontRevision = float(".".join(VERSION.split(".")[:2]))
    top = f["CFF "].cff.topDictIndex[0]
    top.version, top.Notice, top.Copyright = VERSION, UPPHOVSRATT, UPPHOVSRATT
    f["OS/2"].fsType = 0
    return spara(f)


def namnposter(font):
    return {(n.nameID, n.platformID, n.platEncID, n.langID): n.toUnicode() for n in font["name"].names}


def ttx(font, tabell):
    ut = io.StringIO()
    font.saveXML(ut, tables=[tabell])
    return ut.getvalue().splitlines()


def bara_licensraderna(fore, efter):
    """Stannar om efter skiljer från fore i något annat än det tillåtna. Returnerar ändringarna och de tabeller
    som är byte för byte lika."""
    fa, fb = las_font(fore), las_font(efter)
    if sorted(fa.reader.keys()) != sorted(fb.reader.keys()):
        stopp("tabellerna skiljer")
    andrat, lika = [], []
    for tagg in fa.reader.keys():
        if fa.reader[tagg] == fb.reader[tagg]:
            lika.append(tagg.strip())
        elif tagg == "name":
            na, nb = namnposter(fa), namnposter(fb)
            for k in sorted(set(na) | set(nb)):
                if na.get(k) != nb.get(k):
                    if k[0] not in TILLATNA_NAMN:
                        stopp(f"namn-id {k[0]} ändrades")
                    andrat.append(f"name id {k[0]} ({k[1]}/{k[2]}): {na.get(k)!r} -> {nb.get(k)!r}")
        elif tagg in TILLATNA_FALT:
            for rad in difflib.unified_diff(ttx(fa, tagg), ttx(fb, tagg), lineterm="", n=0):
                if rad.startswith(("---", "+++", "@@")):
                    continue
                m = re.match(r"[-+]\s*<(\w+) value=", rad)
                if not m or m.group(1) not in TILLATNA_FALT[tagg]:
                    stopp(f"{tagg.strip()} ändrades även: {rad.strip()}")
                andrat.append(f"{tagg.strip()} {rad.strip()}")
        else:
            stopp(f"tabellen {tagg.strip()} ändrades")
    samma_glyfer(fa, fb, "den nya filen")
    return andrat, lika


class Fanga(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.poster = []

    def emit(self, post):
        self.poster.append(f"{post.name}: {post.getMessage()}")


def varningar(data):
    """Varningar från fonttools när filen öppnas med kontroll av tabellernas kontrollsummor och alla tabeller läses."""
    fanga, logg = Fanga(), logging.getLogger("fontTools")
    logg.addHandler(fanga)
    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            f = TTFont(io.BytesIO(data), checkChecksums=1)
            f.saveXML(io.StringIO())
    finally:
        logg.removeHandler(fanga)
    return fanga.poster + [str(x.message) for x in w]


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    if os.path.abspath(sys.argv[1]) == os.path.abspath(sys.argv[2]):
        stopp("den nya filen skrivs inte över arbetskopian: spara arbetskopian först och kopiera sedan")
    fore = open(sys.argv[1], "rb").read()
    ny = med_licens(fore)
    if med_licens(fore) != ny:
        stopp("två körningar ger olika filer")
    andrat, lika = bara_licensraderna(fore, ny)
    f = las_font(ny)
    har_licensen(f)
    if {n.toUnicode() for n in f["name"].names if n.nameID == 5} != {"Version " + VERSION} \
            or not all(n.toUnicode().startswith(VERSION + ";") for n in f["name"].names if n.nameID == 3):
        stopp("versionen i namntabellen blev inte " + VERSION)
    varn_fore, varn_efter = varningar(fore), varningar(ny)
    if varn_efter:
        stopp("fonttools varnar för den nya filen: " + "; ".join(varn_efter))
    with open(sys.argv[2], "wb") as ut:
        ut.write(ny)
    sha = lambda d: hashlib.sha256(d).hexdigest()  # noqa: E731
    print(f"före:  {len(fore)} byte, sha256 {sha(fore)}, fonttools varnar: {'; '.join(varn_fore) or 'inte'}")
    print(f"efter: {len(ny)} byte, sha256 {sha(ny)}, fonttools varnar: inte, version {VERSION}")
    for rad in andrat:
        print("  ändrat:", rad)
    print(f"  byte för byte lika: {', '.join(lika)}; glyfordning, teckenkarta, mått och konturer lika")


if __name__ == "__main__":
    main()
