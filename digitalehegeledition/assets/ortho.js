// Shared orthographic normalisation for 19th-c. spelling in Schelling's SW.
// Both the global search (search.html) and the in-reader search (text.html)
// fold query and text through this so modern spellings match historical ones
// (e.g. "Sein"→"Seyn", "Teil"→"Theil", "realisieren"→"realisiren", "Geist").
//
// Folds are applied to BOTH sides, so direction only has to be consistent.
// Keep rules conservative — over-folding creates false matches.
(function (global) {
  var ORTHO_MAP = [
    [/ey/g, 'ei'],            // Seyn → Sein, Geyst → Geist
    [/ay/g, 'ai'],            // Mayer → Maier
    [/ß/g, 'ss'],             // daß → dass, Verhältniß → Verhältniss
    [/th(?=[aeiouäöü])/g, 't'], // Theil → Teil, Thätigkeit → Tätigkeit
    [/ct/g, 'kt'],            // Object → Objekt, Subject → Subjekt
    [/ph/g, 'f'],            // Philosophie → Filosofie (folds both sides)
    [/iren\b/g, 'ieren'],     // realisiren → realisieren, construiren
  ];

  function normalizeOrtho(s) {
    var r = String(s == null ? '' : s).toLowerCase();
    for (var i = 0; i < ORTHO_MAP.length; i++) r = r.replace(ORTHO_MAP[i][0], ORTHO_MAP[i][1]);
    return r;
  }

  global.ORTHO_MAP = ORTHO_MAP;
  global.normalizeOrtho = normalizeOrtho;
})(typeof window !== 'undefined' ? window : this);
