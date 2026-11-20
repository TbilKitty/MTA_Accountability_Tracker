// Shows the first 8 rows of every data table on the page, with a
// "Show all N rows" button underneath to reveal the rest. Works with tables
// that other scripts fill in or redraw later (filters, sorting, reloads),
// because it re-checks each table whenever its rows change.
(function(){
  const PREVIEW = 8;

  function setup(table){
    const body = table.tBodies[0];
    const wrap = table.closest('.dash-table-wrap') || table;
    if (!body || wrap.dataset.preview) return;
    wrap.dataset.preview = '1';
    let expanded = false;

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'dash-more';
    btn.hidden = true;
    wrap.after(btn);

    function apply(){
      const rows = [...body.rows];
      rows.forEach((r, i) => { r.hidden = !expanded && i >= PREVIEW; });
      btn.hidden = rows.length <= PREVIEW;
      btn.textContent = expanded ? 'Show fewer' : `Show all ${rows.length} rows ▾`;
      btn.setAttribute('aria-expanded', String(expanded));
    }
    btn.addEventListener('click', () => {
      expanded = !expanded;
      apply();
      if (!expanded) wrap.scrollIntoView({block: 'nearest'});
    });
    new MutationObserver(apply).observe(body, {childList: true});
    apply();
  }

  function init(){ document.querySelectorAll('table.dash-table').forEach(setup); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
