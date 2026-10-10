// 用法：node run.js <html 絕對路徑> <chrome 路徑> [--shots 目錄]
const p = require('puppeteer-core'), fs = require('fs'), path = require('path');
const [file, chrome] = process.argv.slice(2); const si = process.argv.indexOf('--shots'); const shots = si > 0 ? process.argv[si + 1] : null;
const html = fs.readFileSync(file, 'utf8').replace(/&/g, '&amp;').replace(/"/g, '&quot;');
const sl = ms => new Promise(r => setTimeout(r, ms)); let fail = 0;
async function run(b, W, H) {
  const wrap = path.join(require('os').tmpdir(), `t2h_${W}.html`);
  fs.writeFileSync(wrap, `<body style="margin:0"><iframe sandbox="allow-scripts" style="width:${W}px;height:${H}px;border:0" srcdoc="${html}"></iframe>`);
  const pg = await b.newPage(); await pg.setViewport({ width: W, height: H }); await pg.goto('file://' + wrap); await sl(800);
  const f = pg.frames().find(x => x !== pg.mainFrame()); const mobile = W < 800;
  const on = () => f.evaluate(() => { const a = document.querySelector('#toc a.on'); return a ? a.getAttribute('href') : null });
  const ids = await f.evaluate(() => [...document.querySelectorAll('#toc a.sub')].map(a => a.getAttribute('href')));
  let ok = 0, bad = [];
  for (const id of ids) {
    if (mobile) { await (await f.$('#tg')).click(); await sl(150); }
    await (await f.$(`#toc a[href="${id}"]`)).click(); await sl(1300);
    const r = await f.evaluate(id => { const e = document.querySelector(id).getBoundingClientRect(); return { vis: e.top >= 0 && e.top < innerHeight, closed: !document.body.classList.contains('open') } }, id);
    if ((await on()) === id && r.vis && r.closed) ok++; else bad.push(id);
  }
  console.log(`${W}x${H} 目錄點擊：${ok}/${ids.length}`, bad.join(' ')); if (ok !== ids.length) fail++;
  await f.evaluate(() => scrollTo(0, 0)); await sl(300); await pg.mouse.move(Math.min(W - 50, 600), 400);
  const expect = () => f.evaluate(() => { const line = (document.getElementById('tg').offsetHeight || 0) + 80; let best = null; document.querySelectorAll('#toc a').forEach(a => { const e = document.querySelector(a.getAttribute('href')); if (e && e.getBoundingClientRect().top <= line) best = a.getAttribute('href') }); const se = document.scrollingElement; const all = [...document.querySelectorAll('#toc a')]; if (se.scrollTop + innerHeight >= se.scrollHeight - 2) best = all[all.length - 1].getAttribute('href'); return best || all[0].getAttribute('href') });
  let wok = 0, n = 0;
  for (let i = 0; i < 80; i++) { await pg.mouse.wheel({ deltaY: (i % 7 == 3) ? -500 : 900 }); await sl(350); n++; if ((await on()) === (await expect())) wok++; if (await f.evaluate(() => scrollY + innerHeight >= document.scrollingElement.scrollHeight - 2)) break; }
  console.log(`${W}x${H} 滾輪高亮：${wok}/${n}`); if (wok !== n) fail++;
  if (shots) await pg.screenshot({ path: path.join(shots, `test_${W}x${H}.png`) });
  if (!mobile) {
    const L = await f.evaluate(() => { const as = [...document.querySelectorAll('main a[href^="http"]')]; const w = document.createTreeWalker(document.querySelector('main'), NodeFilter.SHOW_TEXT); let t, plain = 0; while (t = w.nextNode()) if (/https?:\/\//.test(t.data) && !t.parentElement.closest('a')) plain++; const lazy = document.querySelectorAll('img[loading=lazy]').length, nodim = [...document.querySelectorAll('img')].filter(i => !i.getAttribute('width')).length; return { n: as.length, ext: as.every(a => a.target === '_blank' && a.rel.includes('noopener')), plain, lazy, nodim } });
    const good = L.ext && L.plain === 0 && L.lazy === 0 && L.nodim === 0;
    console.log(`外部連結 ${L.n} 個、皆開新分頁：${L.ext}；未連結網址：${L.plain}；lazy 圖：${L.lazy}；缺寬高圖：${L.nodim}`); if (!good) fail++;
  }
  await pg.close();
}
(async () => { const b = await p.launch({ executablePath: chrome, args: ['--no-sandbox'] }); await run(b, 1280, 800); await run(b, 390, 844); await b.close(); console.log(fail ? '結果：失敗' : '結果：全部通過'); process.exit(fail ? 1 : 0) })().catch(e => { console.error(e); process.exit(1) });
