// Bure: knapparna och reglaget vid fältet för egen text. Fältet fungerar utan skriptet (det är satt med Bure
// i stilmallen); skriptet visar bara verktygen, som annars är dolda. Det anropar ingenting och sparar ingenting.
(function () {
  'use strict';
  var falt = document.getElementById('egen');
  var verktyg = document.getElementById('verktyg');
  var storlek = document.getElementById('storlek');
  var varde = document.getElementById('storlek-varde');
  if (!falt || !verktyg || !storlek || !varde) return;

  // Ordskiljaren och meningsskiljaren finns inte på tangentbordet: de sätts in där markören står.
  verktyg.querySelectorAll('button[data-tecken]').forEach(function (knapp) {
    knapp.addEventListener('click', function () {
      falt.setRangeText(knapp.getAttribute('data-tecken'), falt.selectionStart, falt.selectionEnd, 'end');
      falt.focus();
    });
  });

  // Storleken sätts med element.style, som innehållsregeln tillåter (till skillnad från style-attribut i sidan).
  function visaStorlek() {
    falt.style.fontSize = storlek.value + 'px';
    varde.textContent = storlek.value + ' px';
  }
  storlek.addEventListener('input', visaStorlek);
  visaStorlek();
  verktyg.hidden = false;
})();
