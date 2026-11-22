# Bure: älvdalskt dalrunetypsnitt

`Bure-Regular.otf` är typsnittet (version 1.0.0). Upphovsrätt och licens (SIL Open Font License 1.1, se `OFL.txt`) ligger
i själva filen.

## Webbplatsen

`webbplats/` är källan till webbplatsen för typsnittet (provsida, nedladdning, teckentabell):

- `sida/`: mallarna `index.html` och `stil.css`, skriptet `prov.js` och licensen.
- `bygg.py`: bygger sidan, WOFF2-filen och ikonen ur typsnittsfilen och `mappning-runblocket.csv`.
  Bygget stannar om något inte stämmer (typsnittsfilen, licensen, mappningen).
- `licensrader.py`: lägger upphovsrätt, licens och version i typsnittsfilen (och ändrar inget annat).
- `krav.txt`: de låsta verktygen (fonttools, brotli) med kontrollsummor.

Hur webbplatsen körs (container, proxy) beskrivs inte här; det ligger hos den som driftsätter den.
