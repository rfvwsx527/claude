import { chromium } from 'playwright'; import fs from 'fs';
const URL='http://127.0.0.1:8731/index.html';
const b=await chromium.launch({executablePath:'/opt/pw-browsers/chromium-1194/chrome-linux/chrome'});
let fails=0; const ok=(l,g,w)=>{const p=String(g)===String(w);if(!p)fails++;
  console.log(`${p?'PASS':'FAIL'}  ${l.padEnd(50)} ${g}${p?'':'   期望 '+w}`);};
// stub：把 publish 的檔案寫回伺服器目錄，模擬真實的檔案式發佈
const STUB=`window.__pub={};window.__dl=[];
window.claude={use:async n=>{
  if(n==='artifact')return{publish:async f=>{Object.assign(window.__pub,f);return{version:'v'}}};
  if(n==='downloads')return{save:async r=>{window.__dl.push(r.filename);return{status:'saved'}}};
  return null;}};`;
// 每次從乾淨狀態開始，並依當前內建快照重建 fixture，避免上一輪殘留汙染基準
fs.rmSync('srv/data', {recursive:true, force:true}); fs.mkdirSync('srv/data', {recursive:true});
{
  const page = fs.readFileSync('srv/index.html','utf8');
  const seed = JSON.parse(page.match(/<script id="skill-data" type="application\/json">([\s\S]*?)<\/script>/)[1]);
  seed.scannedAt = '2026-08-28 09:00';
  seed.skills.push({name:'invoice-sorter', zh:'invoice-sorter', cat:'ops', src:'mine', enabled:true,
    desc:'Sort e-invoices.', raw:'Sort e-invoices.', size:'1.2 KB', updated:'2026-08-28',
    nfiles:1, files:['SKILL.md'], path:'/root/.claude/skills/synced/invoice-sorter/', needsCuration:true});
  fs.writeFileSync('srv/installed.json', JSON.stringify(seed));
}
const ctx=await b.newContext({viewport:{width:1400,height:960}});
await ctx.addInitScript(STUB);
const p=await ctx.newPage(); p.on('pageerror',e=>{fails++;console.log('PAGEERROR',e.message)});
const total=()=>p.evaluate(()=>document.getElementById('st-total').textContent);
const has=n=>p.evaluate(x=>[...document.querySelectorAll('.card .name')].some(e=>e.textContent===x),n);
const msg=()=>p.textContent('#newMsg');

await p.goto(URL); await p.waitForTimeout(1300);
const BASE = Number(await total());          // 目錄筆數會隨掃描變動，不寫死
const PLUS = String(BASE + 1);
ok('起始技能數（動態基準）', BASE > 0, 'true');

console.log('\n── 表單驗證 ──');
await p.click('#newBtn'); await p.waitForTimeout(300);
ok('表單開啟', await p.isVisible('#f-name'), 'true');
await p.fill('#f-name','Invoice Sorter!'); await p.fill('#f-raw','x');
await p.click('#newSave'); await p.waitForTimeout(200);
ok('非法名稱被擋', (await msg()).includes('小寫英文'), 'true');
ok('   欄位標紅', await p.evaluate(()=>document.getElementById('f-name').classList.contains('bad')), 'true');
await p.fill('#f-name','docx'); await p.click('#newSave'); await p.waitForTimeout(200);
ok('重名被擋', (await msg()).includes('已經有一個叫'), 'true');
await p.fill('#f-name','invoice-sorter'); await p.fill('#f-raw','');
await p.click('#newSave'); await p.waitForTimeout(200);
ok('缺觸發說明被擋', (await msg()).includes('觸發說明'), 'true');
ok('   清單未被動過', await total(), String(BASE));

console.log('\n── 產生的 SKILL.md ──');
await p.fill('#f-zh','電子發票整理');
await p.fill('#f-desc','自動整理電子發票並依月份歸檔。');
await p.fill('#f-raw','當使用者要求整理電子發票、歸檔發票，或提到「發票對帳」時使用此 skill。');
await p.fill('#f-body','## 步驟\n1. 讀取發票\n2. 依月份歸檔');
await p.waitForTimeout(300);
const md = await p.textContent('#f-preview');
ok('有 frontmatter 起始', md.startsWith('---\nname: invoice-sorter'), 'true');
ok('description 有引號包住', md.includes('description: "當使用者要求整理電子發票'), 'true');
ok('正文有帶到', md.includes('## 步驟'), 'true');

console.log('\n── 下載與複製 ──');
await p.click('#newDownload'); await p.waitForTimeout(300);
ok('下載檔名', await p.evaluate(()=>window.__dl.join()), 'SKILL.md');
ok('   提示上傳位置', (await msg()).includes('Settings'), 'true');

console.log('\n── 存成草稿 ──');
await p.click('#newSave'); await p.waitForTimeout(600);
ok('技能數 +1', await total(), PLUS);
ok('   卡片出現', await has('invoice-sorter'), 'true');
ok('   標示草稿', await p.evaluate(()=>document.querySelectorAll('.chip.draft').length), '1');
ok('   寫入的檔名', await p.evaluate(()=>Object.keys(window.__pub).join()), 'data/drafts.json');
const saved = await p.evaluate(()=>JSON.parse(window.__pub['data/drafts.json']));
ok('   草稿內容正確', saved.drafts[0].name + '/' + saved.drafts[0].zh, 'invoice-sorter/電子發票整理');
fs.writeFileSync('srv/data/drafts.json', JSON.stringify(saved));

console.log('\n── 重新開啟：草稿要還在 ──');
await p.reload(); await p.waitForTimeout(1300);
ok('重整後仍 41', await total(), PLUS);
ok('   仍標示草稿', await p.evaluate(()=>document.querySelectorAll('.chip.draft').length), '1');

console.log('\n── 關鍵：隔天排程發佈了較新的快照（且已裝好該 skill）──');
fs.copyFileSync('srv/installed.json','srv/data/skills.json');
await p.reload(); await p.waitForTimeout(1300);
ok('總數（沒有重複列出）', await total(), PLUS);
ok('   草稿標記消失（已安裝）', await p.evaluate(()=>document.querySelectorAll('.chip.draft').length), '0');
const merged = await p.evaluate(()=>{
  const c=[...document.querySelectorAll('.card')].find(x=>x.querySelector('.name').textContent==='invoice-sorter');
  return {zh:c.querySelector('.zh').textContent, todo:!!c.querySelector('.chip.todo')};
});
ok('   中文名被沿用', merged.zh, '電子發票整理');
ok('   不再標「待補」', merged.todo, 'false');

console.log('\n── 刪除草稿 ──');
fs.rmSync('srv/data/skills.json');           // 回到尚未安裝的狀態
await p.reload(); await p.waitForTimeout(1300);
await p.evaluate(()=>[...document.querySelectorAll('.card')]
  .find(x=>x.querySelector('.name').textContent==='invoice-sorter').click());
await p.waitForTimeout(400);
await p.click('#dDropDraft'); await p.waitForTimeout(600);
ok('刪除後回到基準', await total(), String(BASE));
ok('   卡片消失', await has('invoice-sorter'), 'false');

console.log(fails?`\n${fails} 項未通過`:'\n全部通過');
await b.close(); process.exit(fails?1:0);
